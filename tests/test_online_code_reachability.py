import unittest

from adc_research.calibration.adaptive_two_stage import (
    TwoStageAdaptiveConfig,
    TwoStageAdaptiveState,
    correct_and_update,
)
from adc_research.calibration.gated_lms import GatedLmsConfig, GatedLmsState
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.calibration.pwl import PwlConfig
from adc_research.calibration.two_stage import TwoStagePwlCalibrationConfig
from adc_research.evaluation.online_code_reachability import enumerate_online_code_paths
from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.theory.finite_record_bounds import bound_finite_coherent_tone


def sample(backend: int, dither1: int = 1) -> DigitalCalibrationSample:
    return DigitalCalibrationSample(0, 0, backend, dither1, 1)


class OnlineCodeReachabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        cascade = TwoStagePwlCalibrationConfig(
            stage1_pwl=PwlConfig(10, (1.0,)),
            stage2_pwl=PwlConfig(10, (1.0,)),
            stage1_symbol_weight=20,
            stage2_symbol_weight=10,
            backend_weight=1,
            output_offset=128,
            output_range=(0, 255),
            dither_code_copies=({-1: -1, 1: 1}, {-1: -1, 1: 1}),
        )
        self.config = TwoStageAdaptiveConfig(
            cascade=cascade,
            stage1_lms=GatedLmsConfig(10, (0.2,)),
            stage2_lms=GatedLmsConfig(10, (0.001,)),
        )
        self.state = TwoStageAdaptiveState(
            GatedLmsState.unity(1), GatedLmsState.unity(1)
        )

    def test_early_observation_changes_later_code_through_coefficients(self) -> None:
        first = (sample(1, -1), sample(2, -1))
        second = sample(6)
        result = enumerate_online_code_paths((first, (second,)), self.state, self.config)
        manual = []
        for initial in first:
            step1 = correct_and_update(initial, self.state, self.config)
            step2 = correct_and_update(second, step1.state, self.config)
            manual.append((
                round(step1.calibration.unclipped_output_code),
                round(step2.calibration.unclipped_output_code),
            ))
        self.assertEqual({path.integer_codes for path in result.paths}, set(manual))
        self.assertEqual({path.integer_codes for path in result.paths}, {(129, 133), (130, 134)})
        self.assertNotEqual(result.lower_codes[1], result.upper_codes[1])
        frozen_second = round(correct_and_update(second, self.state, self.config).calibration.unclipped_output_code)
        self.assertNotEqual(result.upper_codes[1], frozen_second)
        self.assertEqual({path.final_state.stage1.sample_count for path in result.paths}, {2})

    def test_path_codes_feed_finite_record_bounds(self) -> None:
        sequence = (2, 5, 8, 5, 2, -1, -4, -1)
        alternatives = ((sample(sequence[0] - 1, -1), sample(sequence[0], -1)),)
        frames = alternatives + tuple((sample(value),) for value in sequence[1:])
        result = enumerate_online_code_paths(frames, self.state, self.config)
        self.assertEqual(len(result.paths), 2)
        bounds = bound_finite_coherent_tone(
            result.paths[0].integer_codes, result.lower_codes, result.upper_codes,
            fundamental_bin=1,
        )
        for path in result.paths:
            metrics = analyze_coherent_tone(
                path.integer_codes, sample_rate_hz=8, fundamental_bin=1,
                harmonic_orders=(2, 3),
            ).metrics
            self.assertLessEqual(bounds.sndr_db.lower, metrics.sndr_db)
            self.assertLessEqual(metrics.sndr_db, bounds.sndr_db.upper)
            self.assertLessEqual(bounds.sfdr_dbc.lower, metrics.sfdr_dbc)
            self.assertLessEqual(metrics.sfdr_dbc, bounds.sfdr_dbc.upper)

    def test_incomplete_enumeration_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_paths"):
            enumerate_online_code_paths(
                ((sample(1, -1), sample(2, -1)),),
                self.state, self.config, max_paths=1,
            )
        with self.assertRaisesRegex(ValueError, "at least one observation"):
            enumerate_online_code_paths(((),), self.state, self.config)


if __name__ == "__main__":
    unittest.main()
