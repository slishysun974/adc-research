from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from adc_research.platform.amplifier import (
    CubicAmplifierResult,
    StaticCubicTruthConfig,
    StaticPwlTruthConfig,
    amplify_static_cubic_truth,
)
from adc_research.platform.pipeline import StaticPipelineNonidealities, process
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stage import StaticStageNonidealities


class StaticCubicTruthTests(unittest.TestCase):
    def test_odd_monotone_transfer_and_local_derivative(self) -> None:
        truth = StaticCubicTruthConfig(1.0, -0.08)
        outputs = [
            amplify_static_cubic_truth(value / 4, nominal_gain=4, truth=truth)
            for value in (-1.0, -0.8, -0.3, 0.0, 0.3, 0.8, 1.0)
        ]
        self.assertTrue(all(right.output_value > left.output_value
                            for left, right in zip(outputs, outputs[1:])))
        self.assertAlmostEqual(outputs[1].output_value, -outputs[-2].output_value)
        self.assertAlmostEqual(outputs[-1].output_value, 0.92)
        self.assertAlmostEqual(outputs[-1].local_derivative, 0.76)

    def test_invalid_or_conflicting_truth_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            StaticCubicTruthConfig(1.0, -0.4)
        with self.assertRaises(ValueError):
            StaticStageNonidealities(
                pwl_truth=StaticPwlTruthConfig((0.0, 1.0), (0.0, 1.0)),
                cubic_truth=StaticCubicTruthConfig(1.0, -0.08),
            )
        with self.assertRaises(ValueError):
            amplify_static_cubic_truth(
                0.3, nominal_gain=4, truth=StaticCubicTruthConfig(1.0, -0.08)
            )

    def test_identity_cubic_truth_preserves_full_pipeline(self) -> None:
        root = Path(__file__).resolve().parents[1]
        architecture = yaml.safe_load(
            (root / "configs" / "architectures" / "gu_behavioral_v1.yaml")
            .read_text(encoding="utf-8")
        )
        pipeline = build_gu_static_hypothesis_a(architecture)
        identity = StaticCubicTruthConfig(1.0, 0.0)
        nonidealities = StaticPipelineNonidealities(
            stage1=StaticStageNonidealities(cubic_truth=identity),
            stage2=StaticStageNonidealities(cubic_truth=identity),
        )
        for index in range(256):
            value = -0.95 + 1.9 * (index + 0.37) / 256
            pair = (-1 if index & 1 else 1, -1 if index & 2 else 1)
            nominal = process(value, pipeline, sample_index=index, dither_symbols=pair)
            cubic = process(
                value, pipeline, sample_index=index, dither_symbols=pair,
                nonidealities=nonidealities,
            )
            self.assertIsInstance(cubic.stage1.amplifier, CubicAmplifierResult)
            self.assertEqual(cubic.reconstruction.output_code,
                             nominal.reconstruction.output_code)
            self.assertAlmostEqual(cubic.stage1.residue, nominal.stage1.residue)
            self.assertAlmostEqual(cubic.stage2.residue, nominal.stage2.residue)


if __name__ == "__main__":
    unittest.main()
