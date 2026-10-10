"""Check conditional backend-voltage envelopes against the Gu candidate."""

from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

import numpy as np
import yaml

from adc_research.calibration.gu_baseline import build_gu_two_stage_baseline
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.calibration.pwl import PwlConfig
from adc_research.calibration.two_stage import correct_two_stage_observed
from adc_research.evaluation.backend_code_envelope import (
    bound_backend_voltage_to_gu_code,
)
from adc_research.evaluation.observations import digital_sample
from adc_research.platform.amplifier import StaticPwlTruthConfig
from adc_research.platform.backend_sar import convert as convert_sar
from adc_research.platform.pipeline import StaticPipelineNonidealities, process
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stage import StaticStageNonidealities


ROOT = Path(__file__).resolve().parents[1]


class BackendCodeEnvelopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        architecture = yaml.safe_load(
            (ROOT / "configs/architectures/gu_behavioral_v1.yaml").read_text(
                encoding="utf-8"
            )
        )
        cls.pipeline = build_gu_static_hypothesis_a(architecture)
        cls.backend = cls.pipeline.backend
        cls.baseline = build_gu_two_stage_baseline(
            cls.pipeline,
            architecture["pwl_implications"],
        )
        cls.observed = DigitalCalibrationSample(0, 0, 0, None, None)

    def test_backend_threshold_equality_is_included(self) -> None:
        result = bound_backend_voltage_to_gu_code(
            self.observed, self.backend, self.baseline, -1e-8, 0.0
        )
        self.assertEqual(
            (result.lower_backend_centered_code, result.upper_backend_centered_code),
            (-1, 0),
        )
        self.assertEqual(
            (result.lower_output_code, result.upper_output_code), (2047, 2048)
        )
        self.assertFalse(result.backend_overload_possible)

    def test_nonunit_gu_coefficients_cover_every_voltage(self) -> None:
        calibration = replace(
            self.baseline,
            stage1_pwl=PwlConfig(128, (1.08, 0.95, 1.02, 0.98)),
            stage2_pwl=PwlConfig(32, (1.05, 0.97, 1.01, 0.99)),
        )
        observed = DigitalCalibrationSample(1, -1, 0, 1, -1)
        result = bound_backend_voltage_to_gu_code(
            observed, self.backend, calibration, -0.021, 0.024
        )
        for voltage in np.linspace(-0.021, 0.024, 91):
            sar = convert_sar(float(voltage), self.backend)
            candidate = replace(observed, backend_centered_code=sar.centered_code)
            corrected = correct_two_stage_observed(candidate, calibration)
            code = min(max(round(corrected.unclipped_output_code), 0), 4095)
            self.assertLessEqual(result.lower_output_code, code)
            self.assertLessEqual(code, result.upper_output_code)

    def test_overload_is_flagged_and_bad_intervals_rejected(self) -> None:
        result = bound_backend_voltage_to_gu_code(
            self.observed, self.backend, self.baseline, 0.99, 1.01
        )
        self.assertTrue(result.backend_overload_possible)
        with self.assertRaises(ValueError):
            bound_backend_voltage_to_gu_code(
                self.observed, self.backend, self.baseline, 0.1, -0.1
            )

    def test_exp020_threshold_crossing_is_enclosed(self) -> None:
        # EXP-020's first held-out mismatch changes only the second-stage
        # main transfer; both front-stage decisions and dither tags stay fixed.
        value = 0.6801685889011048
        reference = process(value, self.pipeline, dither_symbols=(1, 1))
        truth = StaticPwlTruthConfig(
            (0.0, 0.50390625, 0.5078125, 0.51171875, 1.0),
            (0.0, 0.50390625, 0.5083125, 0.51171875, 1.0),
        )
        alternative = process(
            value,
            self.pipeline,
            dither_symbols=(1, 1),
            nonidealities=StaticPipelineNonidealities(
                stage2=StaticStageNonidealities(pwl_truth=truth)
            ),
        )
        reference_observed = digital_sample(reference)
        alternative_observed = digital_sample(alternative)
        self.assertEqual(
            (reference_observed.stage1_symbol, reference_observed.stage2_symbol),
            (alternative_observed.stage1_symbol, alternative_observed.stage2_symbol),
        )
        envelope = bound_backend_voltage_to_gu_code(
            reference_observed,
            self.backend,
            self.baseline,
            min(reference.stage2.residue, alternative.stage2.residue),
            max(reference.stage2.residue, alternative.stage2.residue),
        )
        self.assertEqual(
            (envelope.lower_backend_centered_code,
             envelope.upper_backend_centered_code),
            (64, 65),
        )
        self.assertEqual(
            (envelope.lower_output_code, envelope.upper_output_code),
            (3440, 3441),
        )


if __name__ == "__main__":
    unittest.main()
