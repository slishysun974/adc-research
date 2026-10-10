"""Regression checks for the online/offline information boundary."""

import unittest
from dataclasses import replace
from pathlib import Path

import yaml

from adc_research.calibration.adaptive_two_stage import (
    TwoStageAdaptiveConfig,
    TwoStageAdaptiveState,
    correct_and_update,
)
from adc_research.calibration.gated_lms import GatedLmsConfig, GatedLmsState
from adc_research.calibration.gu_baseline import build_gu_two_stage_baseline
from adc_research.calibration.fixed_pwl import (
    FixedPwlArithmetic,
    correct_two_stage_fixed_observed,
    quantize_two_stage_config,
)
from adc_research.calibration.two_stage import (
    correct_two_stage_observed,
)
from adc_research.evaluation.oracle import build_two_stage_oracle
from adc_research.evaluation.observations import digital_sample
from adc_research.evaluation.scoring import (
    correct_two_stage,
    correct_two_stage_fixed,
)
from adc_research.platform.pipeline import process
from adc_research.platform.presets import (
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
)


ROOT = Path(__file__).resolve().parents[1]


class InformationBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        architecture = yaml.safe_load(
            (ROOT / "configs/architectures/gu_behavioral_v1.yaml").read_text(
                encoding="utf-8"
            )
        )
        cls.pipeline = build_gu_static_hypothesis_a(architecture)
        cls.baseline = build_gu_two_stage_baseline(
            cls.pipeline, architecture["pwl_implications"]
        )
        cls.config = TwoStageAdaptiveConfig(
            cascade=cls.baseline,
            stage1_lms=GatedLmsConfig(128, (1e-9,) * 4),
            stage2_lms=GatedLmsConfig(32, (1e-9,) * 4),
        )
        cls.state = TwoStageAdaptiveState(
            stage1=GatedLmsState.unity(4),
            stage2=GatedLmsState.unity(4),
        )

    def test_geometry_comes_from_declared_digital_bits(self) -> None:
        self.assertEqual(self.baseline.stage1_pwl.slice_width, 128)
        self.assertEqual(self.baseline.stage2_pwl.slice_width, 32)
        self.assertEqual(self.baseline.stage1_pwl.slopes, (1.0,) * 4)
        with self.assertRaises(ValueError):
            build_gu_two_stage_baseline(
                self.pipeline,
                {
                    "stage1_positive_magnitude_bits": 9,
                    "stage2_positive_magnitude_bits": 7,
                    "stage1_four_slice_b0": 64,
                    "stage2_four_slice_b0": 32,
                },
            )

    def test_old_synthetic_oracle_only_shares_geometry_not_slopes(self) -> None:
        effects = yaml.safe_load(
            (ROOT / "configs/nonidealities/gu_gate_d_static_v0_1.yaml").read_text(
                encoding="utf-8"
            )
        )
        analog_truth = build_gu_gate_d_nonidealities(
            effects, enabled_effects=("static_pwl_truth",)
        )
        oracle = build_two_stage_oracle(self.pipeline, analog_truth)
        self.assertEqual(
            self.baseline.stage1_pwl.slice_width, oracle.stage1_pwl.slice_width
        )
        self.assertEqual(
            self.baseline.stage2_pwl.slice_width, oracle.stage2_pwl.slice_width
        )
        self.assertNotEqual(self.baseline.stage1_pwl.slopes, oracle.stage1_pwl.slopes)

    def test_digital_correction_matches_offline_correction_when_no_overload(self) -> None:
        raw = process(-0.217, self.pipeline, dither_symbols=(-1, 1))
        offline = correct_two_stage(raw, self.baseline)
        online = correct_two_stage_observed(digital_sample(raw), self.baseline)
        self.assertEqual(offline, online)

    def test_hidden_analog_fields_cannot_change_online_update(self) -> None:
        raw = process(-0.217, self.pipeline, dither_symbols=(-1, 1))
        changed = replace(
            raw,
            input_value=0.95,
            stage1=replace(raw.stage1, residue=99.0, correctable=False),
        )
        self.assertEqual(digital_sample(raw), digital_sample(changed))
        first = correct_and_update(digital_sample(raw), self.state, self.config)
        second = correct_and_update(digital_sample(changed), self.state, self.config)
        self.assertEqual(first.state, second.state)
        self.assertEqual(first.calibration.output_code, second.calibration.output_code)

    def test_full_platform_trace_is_rejected_by_online_api(self) -> None:
        raw = process(-0.217, self.pipeline, dither_symbols=(-1, 1))
        with self.assertRaises(TypeError):
            correct_two_stage_observed(raw, self.baseline)

    def test_fixed_point_has_same_digital_boundary(self) -> None:
        raw = process(-0.217, self.pipeline, dither_symbols=(-1, 1))
        fixed = quantize_two_stage_config(self.baseline, FixedPwlArithmetic())
        offline = correct_two_stage_fixed(raw, fixed)
        online = correct_two_stage_fixed_observed(digital_sample(raw), fixed)
        self.assertEqual(offline, online)
        with self.assertRaises(TypeError):
            correct_two_stage_fixed_observed(raw, fixed)

    def test_online_update_sources_do_not_import_oracle(self) -> None:
        for relative in (
            "calibration/adaptive_two_stage.py",
            "calibration/fixed_adaptive_two_stage.py",
            "calibration/gated_lms.py",
            "calibration/fixed_gated_lms.py",
            "calibration/gu_baseline.py",
        ):
            source = (ROOT / "src/adc_research" / relative).read_text(
                encoding="utf-8"
            )
            self.assertNotIn("calibration.known_truth", source, relative)
            self.assertNotIn("evaluation.oracle", source, relative)
            self.assertNotIn("pwl_truth", source, relative)


if __name__ == "__main__":
    unittest.main()
