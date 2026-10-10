"""Short end-to-end check from analog intervals to online spectrum bounds."""

from __future__ import annotations

import unittest
from math import floor

from adc_research.calibration.adaptive_two_stage import (
    TwoStageAdaptiveConfig,
    TwoStageAdaptiveState,
    correct_and_update,
)
from adc_research.calibration.gated_lms import GatedLmsConfig, GatedLmsState
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.calibration.pwl import PwlConfig
from adc_research.calibration.two_stage import TwoStagePwlCalibrationConfig
from adc_research.evaluation.static_online_reachability import (
    StaticAnalogFrame,
    propagate_static_online_codes,
)
from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.theory.finite_record_bounds import bound_finite_coherent_tone
from adc_research.theory.static_observation_reachability import (
    ClosedInterval,
    StaticCandidateArchitecture,
)


def identity(interval: ClosedInterval) -> ClosedInterval:
    return interval


class StaticOnlineReachabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        # This deliberately small, memoryless physical candidate has no front
        # flash thresholds. Its 5-bit backend has 1.25-V cells centered at
        # code b when v is in [1.25*b, 1.25*(b+1)).
        self.architecture = StaticCandidateArchitecture(
            stage1_thresholds=(),
            stage2_thresholds=(),
            stage1_symbols=(0,),
            stage2_symbols=(0,),
            stage1_dac_levels=(0.0,),
            stage2_dac_levels=(0.0,),
            front_nominal_range=(-20.0, 20.0),
            backend_range=(-20.0, 20.0),
            backend_bits=5,
        )
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
        self.calibration = TwoStageAdaptiveConfig(
            cascade=cascade,
            stage1_lms=GatedLmsConfig(10, (0.2,)),
            stage2_lms=GatedLmsConfig(10, (0.001,)),
        )
        self.initial_state = TwoStageAdaptiveState(
            GatedLmsState.unity(1), GatedLmsState.unity(1)
        )
        self.backend_codes = (2, 5, 8, 5, 2, -1, -4, -1)
        self.frames = (
            StaticAnalogFrame(
                ClosedInterval(2.49, 2.51),
                ClosedInterval(-0.1, -0.1),
                ClosedInterval(0.1, 0.1),
                -1, 1,
            ),
        ) + tuple(
            StaticAnalogFrame(
                ClosedInterval(1.25 * code + 0.425, 1.25 * code + 0.425),
                ClosedInterval(0.1, 0.1),
                ClosedInterval(0.1, 0.1),
                1, 1,
            )
            for code in self.backend_codes[1:]
        )

    def _reachability(self, max_paths: int = 100_000):
        return propagate_static_online_codes(
            self.frames, self.architecture,
            identity, identity, identity,
            self.initial_state, self.calibration,
            max_paths=max_paths,
        )

    def test_covered_analog_record_reaches_online_codes_and_spectrum(self) -> None:
        result = self._reachability()
        self.assertEqual(
            [len(envelope.outcomes) for envelope in result.observation_envelopes],
            [2] + [1] * 7,
        )
        paths = result.code_reachability.paths
        self.assertEqual(
            {path.integer_codes for path in paths},
            {
                (129, 132, 130, 127, 127, 126, 123, 124),
                (130, 133, 130, 127, 127, 126, 124, 124),
            },
        )
        self.assertEqual(len(paths), 2)
        self.assertNotEqual(
            result.code_reachability.lower_codes[1],
            result.code_reachability.upper_codes[1],
        )

        bounds = bound_finite_coherent_tone(
            paths[0].integer_codes,
            result.code_reachability.lower_codes,
            result.code_reachability.upper_codes,
            fundamental_bin=1,
        )
        for first_voltage, expected_path in zip(
            (2.49, 2.51), sorted(paths, key=lambda path: path.integer_codes[0]),
            strict=True,
        ):
            state = self.initial_state
            actual_codes = []
            for index, frame in enumerate(self.frames):
                voltage = first_voltage if index == 0 else frame.input_voltage.lower
                backend_voltage = (
                    voltage + frame.stage1_dither_preamp.lower
                    + frame.stage2_dither_preamp.lower
                )
                backend = min(max(floor((backend_voltage + 20) / 1.25), 0), 31) - 16
                observed = DigitalCalibrationSample(
                    0, 0, backend,
                    frame.stage1_dither_symbol, frame.stage2_dither_symbol,
                )
                self.assertIn(observed, tuple(
                    path.observations[index] for path in paths
                ))
                updated = correct_and_update(observed, state, self.calibration)
                actual_codes.append(round(updated.calibration.unclipped_output_code))
                state = updated.state
            self.assertEqual(tuple(actual_codes), expected_path.integer_codes)
            metrics = analyze_coherent_tone(
                actual_codes, sample_rate_hz=8, fundamental_bin=1,
                harmonic_orders=(2, 3),
            ).metrics
            self.assertLessEqual(bounds.sndr_db.lower, metrics.sndr_db)
            self.assertLessEqual(metrics.sndr_db, bounds.sndr_db.upper)
            self.assertLessEqual(bounds.sfdr_dbc.lower, metrics.sfdr_dbc)
            self.assertLessEqual(metrics.sfdr_dbc, bounds.sfdr_dbc.upper)

    def test_path_limit_rejects_incomplete_envelope(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_paths"):
            self._reachability(max_paths=1)

    def test_possible_out_of_domain_observation_stops_the_bound(self) -> None:
        frame = StaticAnalogFrame(
            ClosedInterval(15.425, 15.425),
            ClosedInterval(0.1, 0.1),
            ClosedInterval(0.1, 0.1),
            1, 1,
        )
        with self.assertRaisesRegex(ValueError, "conversion 0"):
            propagate_static_online_codes(
                (frame,), self.architecture,
                identity, identity, identity,
                self.initial_state, self.calibration,
            )


if __name__ == "__main__":
    unittest.main()
