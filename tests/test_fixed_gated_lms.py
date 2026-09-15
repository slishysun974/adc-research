import unittest
from fractions import Fraction
from pathlib import Path

import yaml

from adc_research.calibration.fixed_adaptive_two_stage import (
    FixedTwoStageAdaptiveConfig,
    FixedTwoStageAdaptiveState,
    correct_and_update_fixed,
)
from adc_research.calibration.fixed_gated_lms import (
    FixedGatedLmsConfig,
    FixedGatedLmsState,
    adaptive_lower_thresholds_scaled,
    exported_coefficient_codes,
    update_fixed,
)
from adc_research.calibration.fixed_point import (
    UnsignedFixedFormat,
    round_fraction,
)
from adc_research.calibration.fixed_pwl import (
    FixedPwlArithmetic,
    quantize_two_stage_config,
)
from adc_research.calibration.known_truth import build_two_stage_oracle
from adc_research.platform.pipeline import process
from adc_research.platform.presets import (
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
)


ROOT = Path(__file__).resolve().parents[1]


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class FixedGatedLmsTests(unittest.TestCase):
    def test_exact_rational_rounding_handles_signed_ties(self) -> None:
        self.assertEqual(round_fraction(5, 2, "nearest_even"), 2)
        self.assertEqual(round_fraction(7, 2, "nearest_even"), 4)
        self.assertEqual(round_fraction(-5, 2, "nearest_even"), -2)
        self.assertEqual(round_fraction(-7, 2, "nearest_even"), -4)
        self.assertEqual(round_fraction(-5, 2, "floor"), -3)
        self.assertEqual(round_fraction(-5, 2, "toward_zero"), -2)

    def test_accumulator_must_not_have_fewer_fractional_bits(self) -> None:
        with self.assertRaises(ValueError):
            FixedGatedLmsConfig(
                slice_width_scaled=8,
                step_sizes=(Fraction(1, 1000),),
                coefficient_format=UnsignedFixedFormat(11, 10),
                accumulator_fractional_bits=9,
            )

    def test_direct_q10_accumulator_discards_a_small_update(self) -> None:
        config = FixedGatedLmsConfig(
            slice_width_scaled=8,
            step_sizes=(Fraction(1, 100000),),
            accumulator_fractional_bits=10,
        )
        state = FixedGatedLmsState.unity(config)
        result = update_fixed(
            state,
            dither_code_scaled=8,
            corrected_output_scaled=8,
            config=config,
        )
        self.assertEqual(result.gate_mask, (True,))
        self.assertEqual(result.requested_accumulator_deltas, (0,))
        self.assertEqual(result.state.nonzero_update_counts, (0,))
        self.assertEqual(result.coefficient_codes_after, (1024,))

    def test_guard_fractional_bits_accumulate_sub_lsb_updates(self) -> None:
        config = FixedGatedLmsConfig(
            slice_width_scaled=8,
            step_sizes=(Fraction(1, 100000),),
            accumulator_fractional_bits=20,
        )
        state = FixedGatedLmsState.unity(config)
        first = update_fixed(
            state,
            dither_code_scaled=8,
            corrected_output_scaled=8,
            config=config,
        )
        self.assertEqual(first.requested_accumulator_deltas, (-10,))
        self.assertEqual(first.coefficient_codes_after, (1024,))
        state = first.state
        for _ in range(51):
            state = update_fixed(
                state,
                dither_code_scaled=8,
                corrected_output_scaled=8,
                config=config,
            ).state
        self.assertEqual(exported_coefficient_codes(state, config), (1023,))
        self.assertEqual(state.nonzero_update_counts, (52,))
        self.assertEqual(state.coefficient_change_counts, (1,))

    def test_thresholds_use_exported_q1_10_coefficients(self) -> None:
        config = FixedGatedLmsConfig(
            slice_width_scaled=8,
            step_sizes=(Fraction(1, 1000),) * 3,
            accumulator_fractional_bits=20,
        )
        thresholds = adaptive_lower_thresholds_scaled(
            (1024, 512, 2047),
            config,
        )
        self.assertEqual(thresholds, (0, 8, 12))


class FixedAdaptiveTwoStageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        architecture = read_yaml(
            ROOT / "configs" / "architectures" / "gu_behavioral_v1.yaml"
        )
        effects = read_yaml(
            ROOT / "configs" / "nonidealities" / "gu_gate_d_static_v0_1.yaml"
        )
        cls.pipeline = build_gu_static_hypothesis_a(architecture)
        cls.nonidealities = build_gu_gate_d_nonidealities(
            effects,
            enabled_effects=("static_pwl_truth",),
        )
        oracle = build_two_stage_oracle(cls.pipeline, cls.nonidealities)
        arithmetic = FixedPwlArithmetic()
        cascade = quantize_two_stage_config(oracle, arithmetic)
        stage1_lms = FixedGatedLmsConfig(
            slice_width_scaled=cascade.stage1_pwl.slice_width_scaled,
            step_sizes=(Fraction(1, 1000000),) * 4,
            accumulator_fractional_bits=22,
        )
        stage2_lms = FixedGatedLmsConfig(
            slice_width_scaled=cascade.stage2_pwl.slice_width_scaled,
            step_sizes=(Fraction(1, 1000000),) * 4,
            accumulator_fractional_bits=22,
        )
        cls.config = FixedTwoStageAdaptiveConfig(
            cascade=cascade,
            stage1_lms=stage1_lms,
            stage2_lms=stage2_lms,
        )
        cls.state = FixedTwoStageAdaptiveState(
            stage1=FixedGatedLmsState.unity(stage1_lms),
            stage2=FixedGatedLmsState.unity(stage2_lms),
        )

    def test_current_sample_uses_preupdate_coefficients(self) -> None:
        raw = process(
            -0.217,
            self.pipeline,
            dither_symbols=(-1, 1),
            nonidealities=self.nonidealities,
        )
        result = correct_and_update_fixed(raw, self.state, self.config)
        self.assertEqual(result.calibration.stage1_pwl.coefficient_code, 1024)
        self.assertEqual(result.calibration.stage2_pwl.coefficient_code, 1024)
        self.assertEqual(result.state.stage1.sample_count, 1)
        self.assertEqual(result.state.stage2.sample_count, 1)
        self.assertEqual(
            result.stage1_local_learning_output_scaled,
            result.calibration.stage1_pwl.corrected_code_scaled
            - result.calibration.stage1_dither_scaled,
        )
        self.assertEqual(
            result.stage2_local_learning_output_scaled,
            result.calibration.stage2_pwl.corrected_code_scaled
            - result.calibration.stage2_dither_scaled,
        )


if __name__ == "__main__":
    unittest.main()
