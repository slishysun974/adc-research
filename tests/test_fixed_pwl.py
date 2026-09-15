from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from adc_research.calibration.fixed_point import (
    UnsignedFixedFormat,
    round_shift,
    signed_bits_required,
)
from adc_research.calibration.fixed_pwl import (
    FixedPwlArithmetic,
    correct_fixed,
    correct_two_stage_fixed,
    quantize_pwl_config,
    quantize_two_stage_config,
)
from adc_research.calibration.known_truth import build_two_stage_oracle
from adc_research.calibration.pwl import PwlConfig
from adc_research.platform.pipeline import process
from adc_research.platform.presets import (
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
)


ROOT = Path(__file__).resolve().parents[1]


class FixedPointPrimitiveTests(unittest.TestCase):
    def test_round_shift_rules_are_explicit_for_positive_and_negative_values(self) -> None:
        self.assertEqual(round_shift(7, 1, "floor"), 3)
        self.assertEqual(round_shift(-7, 1, "floor"), -4)
        self.assertEqual(round_shift(-7, 1, "toward_zero"), -3)
        self.assertEqual(round_shift(5, 1, "nearest_even"), 2)
        self.assertEqual(round_shift(7, 1, "nearest_even"), 4)
        self.assertEqual(round_shift(-7, 1, "nearest_even"), -4)

    def test_unsigned_11_bit_q10_format_has_explicit_upper_endpoint(self) -> None:
        coefficient_format = UnsignedFixedFormat(11, 10)
        self.assertEqual(coefficient_format.maximum_code, 2047)
        self.assertEqual(coefficient_format.maximum_value, 2047 / 1024)
        code, saturated = coefficient_format.quantize(
            2.0,
            rounding="nearest_even",
            overflow="saturate",
        )
        self.assertEqual(code, 2047)
        self.assertTrue(saturated)
        with self.assertRaises(OverflowError):
            coefficient_format.quantize(
                2.0,
                rounding="nearest_even",
                overflow="raise",
            )

    def test_signed_bit_count_matches_twos_complement_endpoints(self) -> None:
        self.assertEqual(signed_bits_required(0), 1)
        self.assertEqual(signed_bits_required(7), 4)
        self.assertEqual(signed_bits_required(-8), 4)
        self.assertEqual(signed_bits_required(8), 5)


class FixedPwlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        architecture = yaml.safe_load(
            (ROOT / "configs" / "architectures" / "gu_behavioral_v1.yaml").read_text(
                encoding="utf-8"
            )
        )
        effects = yaml.safe_load(
            (
                ROOT
                / "configs"
                / "nonidealities"
                / "gu_gate_d_static_v0_1.yaml"
            ).read_text(encoding="utf-8")
        )
        cls.pipeline = build_gu_static_hypothesis_a(architecture)
        cls.nonidealities = build_gu_gate_d_nonidealities(
            effects,
            enabled_effects=("static_pwl_truth",),
        )
        cls.oracle = build_two_stage_oracle(cls.pipeline, cls.nonidealities)

    def test_unity_coefficients_are_exact_identity_on_q3_grid(self) -> None:
        arithmetic = FixedPwlArithmetic()
        config = quantize_pwl_config(
            PwlConfig(32, (1.0, 1.0, 1.0, 1.0)),
            arithmetic,
        )
        for raw_scaled in range(-128 * 8, 128 * 8):
            self.assertEqual(
                correct_fixed(raw_scaled, config).corrected_code_scaled,
                raw_scaled,
            )

    def test_offset_rounding_rule_is_visible_at_a_slice_boundary(self) -> None:
        arithmetic = FixedPwlArithmetic(
            coefficient_rounding="nearest_even",
            multiplication_rounding="nearest_even",
            offset_rounding="after_coefficient_sum",
        )
        config = quantize_pwl_config(
            PwlConfig(32, (1.08, 0.94, 1.03, 0.95)),
            arithmetic,
        )
        boundary = 2 * config.slice_width_scaled
        result = correct_fixed(boundary, config)
        expected = round_shift(
            config.slice_width_scaled * sum(config.coefficient_codes[:2]),
            arithmetic.coefficient_format.fractional_bits,
            arithmetic.multiplication_rounding,
        )
        self.assertEqual(result.slice_index, 2)
        self.assertEqual(result.local_code_scaled, 0)
        self.assertEqual(result.offset_scaled, expected)
        self.assertEqual(result.corrected_code_scaled, expected)

    def test_two_stage_fixed_cascade_preserves_local_dither_order(self) -> None:
        arithmetic = FixedPwlArithmetic()
        config = quantize_two_stage_config(self.oracle, arithmetic)
        raw = process(
            0.314159,
            self.pipeline,
            sample_index=6,
            dither_symbols=(1, -1),
            nonidealities=self.nonidealities,
        )
        result = correct_two_stage_fixed(raw, config)
        self.assertEqual(result.stage2_dither_scaled, -16 * 8)
        self.assertEqual(result.stage1_dither_scaled, 64 * 8)
        self.assertEqual(
            result.stage1_raw_scaled,
            result.stage1_raw_before_dither_scaled + 16 * 8,
        )
        self.assertEqual(result.unclipped_output_scaled % 1, 0)
        self.assertLessEqual(result.maximum_signed_data_bits_required, 16)


if __name__ == "__main__":
    unittest.main()

