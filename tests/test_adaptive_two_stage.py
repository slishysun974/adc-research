import unittest
from pathlib import Path

import yaml

from adc_research.calibration.adaptive_two_stage import (
    TwoStageAdaptiveConfig,
    TwoStageAdaptiveState,
    correct_and_update,
    observe,
    update_block_mean_observations,
)
from adc_research.calibration.gated_lms import GatedLmsConfig, GatedLmsState
from adc_research.calibration.known_truth import build_two_stage_oracle
from adc_research.platform.pipeline import process
from adc_research.platform.presets import (
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
)


ROOT = Path(__file__).resolve().parents[1]


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class AdaptiveTwoStageTests(unittest.TestCase):
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
        cls.config = TwoStageAdaptiveConfig(
            cascade=oracle,
            stage1_lms=GatedLmsConfig(
                oracle.stage1_pwl.slice_width,
                (1e-9, 1e-9, 1e-9, 1e-9),
            ),
            stage2_lms=GatedLmsConfig(
                oracle.stage2_pwl.slice_width,
                (1e-9, 1e-9, 1e-9, 1e-9),
            ),
        )
        cls.state = TwoStageAdaptiveState(
            stage1=GatedLmsState.unity(4),
            stage2=GatedLmsState.unity(4),
        )

    def test_local_learning_outputs_exclude_each_coarse_symbol(self) -> None:
        raw = process(
            0.731,
            self.pipeline,
            dither_symbols=(1, -1),
            nonidealities=self.nonidealities,
        )
        result = correct_and_update(raw, self.state, self.config)
        calibration = result.calibration
        self.assertEqual(
            result.stage2_local_learning_output,
            calibration.stage2_pwl.corrected_code
            - calibration.stage2_dither_copy,
        )
        self.assertEqual(
            result.stage1_local_learning_output,
            calibration.stage1_pwl.corrected_code
            - calibration.stage1_dither_copy,
        )
        self.assertNotEqual(
            result.stage1_local_learning_output,
            calibration.corrected_centered_code,
        )

    def test_current_sample_uses_preupdate_coefficients(self) -> None:
        raw = process(
            -0.217,
            self.pipeline,
            dither_symbols=(-1, 1),
            nonidealities=self.nonidealities,
        )
        result = correct_and_update(raw, self.state, self.config)
        self.assertEqual(
            result.calibration.stage1_pwl.selected_slope,
            self.state.stage1.coefficients[
                result.calibration.stage1_pwl.slice_index
            ],
        )
        self.assertEqual(
            result.calibration.stage2_pwl.selected_slope,
            self.state.stage2.coefficients[
                result.calibration.stage2_pwl.slice_index
            ],
        )
        self.assertEqual(result.state.stage1.sample_count, 1)
        self.assertEqual(result.state.stage2.sample_count, 1)

    def test_adaptive_update_requires_both_dither_symbols(self) -> None:
        raw = process(
            0.1,
            self.pipeline,
            dither_symbols=(None, 1),
            nonidealities=self.nonidealities,
        )
        with self.assertRaises(ValueError):
            correct_and_update(raw, self.state, self.config)

    def test_mismatched_lms_and_cascade_dimensions_fail(self) -> None:
        with self.assertRaises(ValueError):
            TwoStageAdaptiveConfig(
                cascade=self.config.cascade,
                stage1_lms=GatedLmsConfig(64, (1e-9,) * 4),
                stage2_lms=self.config.stage2_lms,
            )

    def test_observation_does_not_change_state_and_block_update_counts_support(self) -> None:
        raw1 = process(
            -0.217,
            self.pipeline,
            dither_symbols=(-1, 1),
            nonidealities=self.nonidealities,
        )
        raw2 = process(
            0.731,
            self.pipeline,
            dither_symbols=(1, -1),
            nonidealities=self.nonidealities,
        )
        observations = (
            observe(raw1, self.state, self.config),
            observe(raw2, self.state, self.config),
        )
        self.assertEqual(self.state.stage1.sample_count, 0)
        self.assertEqual(self.state.stage2.sample_count, 0)
        result = update_block_mean_observations(
            self.state,
            observations,
            self.config,
        )
        self.assertEqual(result.state.stage1.sample_count, 2)
        self.assertEqual(result.state.stage2.sample_count, 2)
        self.assertEqual(result.stage1_update.gate_counts[0], 2)
        self.assertEqual(result.stage2_update.gate_counts[0], 2)


if __name__ == "__main__":
    unittest.main()
