from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from adc_research.platform.amplifier import (
    PwlAmplifierResult,
    StaticPwlTruthConfig,
    amplify_static_pwl_truth,
)
from adc_research.platform.cdac import CdacMismatch
from adc_research.platform.pipeline import (
    StaticPipelineNonidealities,
    process,
)
from adc_research.platform.presets import (
    GU_GATE_D_EFFECTS,
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
)
from adc_research.platform.stage import (
    STATIC_NONIDEALITY_ORDER,
    StaticStageNonidealities,
)


class PlatformGateDTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[1]
        architecture = yaml.safe_load(
            (root / "configs" / "architectures" / "gu_behavioral_v1.yaml").read_text(
                encoding="utf-8"
            )
        )
        cls.profile = yaml.safe_load(
            (
                root
                / "configs"
                / "nonidealities"
                / "gu_gate_d_static_v0_1.yaml"
            ).read_text(encoding="utf-8")
        )
        cls.pipeline = build_gu_static_hypothesis_a(architecture)

    def test_profile_and_runtime_freeze_the_same_composition_order(self) -> None:
        self.assertEqual(
            tuple(self.profile["composition_order"]), STATIC_NONIDEALITY_ORDER
        )
        with self.assertRaises(ValueError):
            build_gu_gate_d_nonidealities(
                self.profile, enabled_effects=("unknown_effect",)
            )

    def test_explicit_zero_bundle_is_numerically_identical_to_disabled(self) -> None:
        identity = StaticPwlTruthConfig(
            (0.0, 0.25, 0.5, 0.75, 1.0),
            (0.0, 0.25, 0.5, 0.75, 1.0),
        )
        zero_stage = StaticStageNonidealities(
            threshold_offsets=(0.0,) * 8,
            cdac_mismatch=CdacMismatch(
                code_level_errors={symbol: 0.0 for symbol in range(-4, 5)}
            ),
            actual_interstage_gain=4.0,
            pwl_truth=identity,
        )
        zero_bundle = StaticPipelineNonidealities(zero_stage, zero_stage)

        for expected in range(4096):
            value = -1 + (expected + 0.5) / 2048
            pair = (-1 if expected & 1 else 1, -1 if expected & 2 else 1)
            baseline = process(
                value,
                self.pipeline,
                sample_index=expected,
                dither_symbols=pair,
            )
            explicit_zero = process(
                value,
                self.pipeline,
                sample_index=expected,
                dither_symbols=pair,
                nonidealities=zero_bundle,
            )
            self.assertEqual(
                explicit_zero.reconstruction.output_code,
                baseline.reconstruction.output_code,
            )
            self.assertAlmostEqual(explicit_zero.stage1.residue, baseline.stage1.residue)
            self.assertAlmostEqual(explicit_zero.stage2.residue, baseline.stage2.residue)

    def test_each_switch_populates_only_its_own_trace_fields(self) -> None:
        value = 0.314159
        for effect in sorted(GU_GATE_D_EFFECTS):
            applied = build_gu_gate_d_nonidealities(
                self.profile, enabled_effects=(effect,)
            )
            result = process(
                value,
                self.pipeline,
                dither_symbols=(1, -1),
                nonidealities=applied,
            )
            stages = (result.stage1, result.stage2)
            has_threshold = any(
                any(offset != 0 for offset in stage.quantizer.applied_threshold_offsets)
                for stage in stages
            )
            has_cdac = any(stage.cdac.mismatch_contribution != 0 for stage in stages)
            has_gain = any(
                stage.amplifier.actual_gain != stage.amplifier.nominal_gain
                for stage in stages
            )
            has_pwl = any(
                isinstance(stage.amplifier, PwlAmplifierResult) for stage in stages
            )
            self.assertEqual(has_threshold, effect == "flash_threshold_offsets")
            self.assertEqual(has_cdac, effect == "cdac_code_level_mismatch")
            self.assertEqual(has_gain, effect == "linear_interstage_gain")
            self.assertEqual(has_pwl, effect == "static_pwl_truth")

    def test_combined_trace_obeys_gain_then_pwl_order(self) -> None:
        applied = build_gu_gate_d_nonidealities(
            self.profile, enabled_effects=tuple(GU_GATE_D_EFFECTS)
        )
        result = process(
            0.314159,
            self.pipeline,
            dither_symbols=(1, -1),
            nonidealities=applied,
        )

        noncommutative_examples = 0
        for stage, stage_config, stage_effects in (
            (result.stage1, self.pipeline.stage1, applied.stage1),
            (result.stage2, self.pipeline.stage2, applied.stage2),
        ):
            self.assertEqual(stage.applied_nonideality_order, STATIC_NONIDEALITY_ORDER)
            self.assertAlmostEqual(
                stage.residue_preamp,
                stage.main_input
                - stage.cdac.nominal_value
                - stage.cdac.mismatch_contribution
                + stage.cdac.dither_contribution,
            )
            self.assertIsInstance(stage.amplifier, PwlAmplifierResult)
            self.assertAlmostEqual(
                stage.amplifier.ideal_output_value,
                stage_effects.actual_interstage_gain * stage.residue_preamp,
            )

            counterfactual_shape_first = amplify_static_pwl_truth(
                stage.residue_preamp,
                nominal_gain=stage_config.nominal_interstage_gain,
                truth=stage_effects.pwl_truth,
            ).output_value
            counterfactual_shape_first *= (
                stage_effects.actual_interstage_gain
                / stage_config.nominal_interstage_gain
            )
            if abs(counterfactual_shape_first - stage.residue) > 1e-12:
                noncommutative_examples += 1
        self.assertGreater(noncommutative_examples, 0)

    def test_invalid_effect_values_fail_before_conversion(self) -> None:
        with self.assertRaises(ValueError):
            StaticStageNonidealities(actual_interstage_gain=0)
        invalid = StaticPipelineNonidealities(
            stage1=StaticStageNonidealities(threshold_offsets=(0.0,)),
        )
        with self.assertRaises(ValueError):
            process(0.0, self.pipeline, nonidealities=invalid)


if __name__ == "__main__":
    unittest.main()
