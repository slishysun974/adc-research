from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from adc_research.calibration.known_truth import (
    build_two_stage_oracle,
    correct_two_stage,
    oracle_pwl_config,
)
from adc_research.calibration.pwl import correct
from adc_research.platform.amplifier import (
    StaticPwlTruthConfig,
    amplify_static_pwl_truth,
)
from adc_research.platform.pipeline import StaticPipelineNonidealities, process
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stage import StaticStageNonidealities


def truth_from_oracle_slopes(slopes: tuple[float, ...]) -> StaticPwlTruthConfig:
    distorted_edges = tuple(index / len(slopes) for index in range(len(slopes) + 1))
    ideal_edges = [0.0]
    for slope in slopes:
        ideal_edges.append(ideal_edges[-1] + slope / len(slopes))
    return StaticPwlTruthConfig(tuple(ideal_edges), distorted_edges)


class GuTwoStagePwlTruthTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[1]
        architecture = yaml.safe_load(
            (root / "configs" / "architectures" / "gu_behavioral_v1.yaml").read_text(
                encoding="utf-8"
            )
        )
        base = build_gu_static_hypothesis_a(architecture)
        cls.stage1_slopes = (1.08, 0.94, 1.03, 0.95)
        cls.stage2_slopes = (0.92, 1.06, 0.98, 1.04)
        cls.stage1_truth = truth_from_oracle_slopes(cls.stage1_slopes)
        cls.stage2_truth = truth_from_oracle_slopes(cls.stage2_slopes)
        cls.pipeline = base
        cls.nonidealities = StaticPipelineNonidealities(
            stage1=StaticStageNonidealities(pwl_truth=cls.stage1_truth),
            stage2=StaticStageNonidealities(pwl_truth=cls.stage2_truth),
        )
        cls.oracle = build_two_stage_oracle(cls.pipeline, cls.nonidealities)

    def test_truth_is_independent_paired_edge_model_with_expected_forward_slopes(self) -> None:
        expected = tuple(1 / slope for slope in self.stage1_slopes)
        for actual, target in zip(
            self.stage1_truth.forward_slopes, expected, strict=True
        ):
            self.assertAlmostEqual(actual, target)

        with self.assertRaises(ValueError):
            StaticPwlTruthConfig((0.0, 0.5, 0.4), (0.0, 0.5, 1.0))
        with self.assertRaises(ValueError):
            StaticPwlTruthConfig((0.0, 1.0), (0.0, 0.4, 1.0))

    def test_oracle_recovers_reported_and_derived_slice_widths(self) -> None:
        self.assertEqual(self.oracle.stage1_pwl.slice_width, 128)
        self.assertEqual(self.oracle.stage2_pwl.slice_width, 32)
        for actual, expected in zip(
            self.oracle.stage1_pwl.slopes, self.stage1_slopes, strict=True
        ):
            self.assertAlmostEqual(actual, expected)
        for actual, expected in zip(
            self.oracle.stage2_pwl.slopes, self.stage2_slopes, strict=True
        ):
            self.assertAlmostEqual(actual, expected)

    def test_oracle_exactly_inverts_the_continuous_truth(self) -> None:
        for truth, full_scale in (
            (self.stage1_truth, 512),
            (self.stage2_truth, 128),
        ):
            oracle = oracle_pwl_config(truth, raw_code_full_scale=full_scale)
            for index in range(-4096, 4096):
                ideal_output = index / 4096
                amplified = amplify_static_pwl_truth(
                    ideal_output / 4,
                    nominal_gain=4,
                    truth=truth,
                )
                raw_code_coordinate = amplified.output_value * full_scale
                recovered = correct(raw_code_coordinate, oracle).corrected_code
                self.assertAlmostEqual(recovered, ideal_output * full_scale)

    def test_second_stage_is_corrected_before_first_stage_with_local_dither(self) -> None:
        raw = process(
            0.314159,
            self.pipeline,
            sample_index=6,
            dither_symbols=(1, -1),
            nonidealities=self.nonidealities,
        )
        calibrated = correct_two_stage(raw, self.oracle)

        self.assertEqual(calibrated.stage2_dither_copy, -16)
        self.assertEqual(calibrated.stage1_dither_copy, 64)
        self.assertAlmostEqual(
            calibrated.stage1_raw_code,
            calibrated.stage1_raw_code_before_dither_subtraction + 16,
        )
        self.assertAlmostEqual(
            calibrated.corrected_centered_code,
            512 * raw.stage1.quantizer.symbol
            + calibrated.stage1_pwl.corrected_code
            - 64,
        )

    def test_quantized_two_stage_oracle_reduces_error_and_wrong_order_does_not(self) -> None:
        corrected_absolute_error = 0.0
        uncorrected_absolute_error = 0.0
        wrong_order_absolute_error = 0.0
        maximum_corrected_error = 0.0
        checks = 0

        for pair in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
            for expected in range(4096):
                value = -1 + (expected + 0.5) / 2048
                raw = process(
                    value,
                    self.pipeline,
                    sample_index=expected,
                    dither_symbols=pair,
                    nonidealities=self.nonidealities,
                )
                calibrated = correct_two_stage(raw, self.oracle)
                error = calibrated.unclipped_output_code - expected
                corrected_absolute_error += abs(error)
                maximum_corrected_error = max(maximum_corrected_error, abs(error))
                uncorrected_absolute_error += abs(
                    raw.reconstruction.unclipped_output_code - expected
                )

                wrong_stage1_input = (
                    self.oracle.stage2_symbol_weight * raw.stage2.quantizer.symbol
                    + calibrated.stage2_pwl.corrected_code
                )
                wrong_stage1 = correct(wrong_stage1_input, self.oracle.stage1_pwl)
                wrong_output = (
                    self.oracle.output_offset
                    + self.oracle.stage1_symbol_weight * raw.stage1.quantizer.symbol
                    + wrong_stage1.corrected_code
                    - calibrated.stage2_dither_copy
                    - calibrated.stage1_dither_copy
                )
                wrong_order_absolute_error += abs(wrong_output - expected)
                checks += 1

        corrected_mae = corrected_absolute_error / checks
        uncorrected_mae = uncorrected_absolute_error / checks
        wrong_order_mae = wrong_order_absolute_error / checks
        self.assertLess(maximum_corrected_error, 0.65)
        self.assertLess(corrected_mae, 0.25)
        self.assertGreater(uncorrected_mae, 5.0)
        self.assertGreater(wrong_order_mae, 0.9)
        self.assertLess(corrected_mae, uncorrected_mae / 20)
        self.assertLess(corrected_mae, wrong_order_mae / 4)


if __name__ == "__main__":
    unittest.main()
