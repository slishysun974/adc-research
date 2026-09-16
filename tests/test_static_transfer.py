from __future__ import annotations

import math
import unittest
from pathlib import Path

import yaml

from adc_research.platform.pipeline import process
from adc_research.platform.presets import (
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
)
from adc_research.theory.static_transfer import (
    build_gu_theory_config,
    predict_static_transfer,
)


class StaticTransferTheoryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[1]
        cls.architecture = yaml.safe_load(
            (root / "configs" / "architectures" / "gu_behavioral_v1.yaml").read_text(
                encoding="utf-8"
            )
        )
        cls.nonideality_profile = yaml.safe_load(
            (
                root
                / "configs"
                / "nonidealities"
                / "gu_gate_d_static_v0_1.yaml"
            ).read_text(encoding="utf-8")
        )

    def test_ideal_partition_is_exact_twelve_bit_transfer(self) -> None:
        prediction = predict_static_transfer(
            build_gu_theory_config(self.architecture)
        )

        self.assertEqual(len(prediction.segments), 4096)
        self.assertEqual(prediction.missing_codes, ())
        self.assertEqual(prediction.negative_step_count, 0)
        self.assertEqual(prediction.uncorrectable_input_width, 0.0)
        self.assertEqual(max(map(abs, prediction.dnl_lsb)), 0.0)
        self.assertEqual(max(map(abs, prediction.transition_inl_lsb)), 0.0)
        for code in range(4096):
            value = -1 + (code + 0.5) / 2048
            self.assertEqual(prediction.code_at(value), code)

    def test_all_static_effects_match_independent_platform_on_holdout_grid(self) -> None:
        enabled = (
            "flash_threshold_offsets",
            "cdac_code_level_mismatch",
            "linear_interstage_gain",
            "static_pwl_truth",
        )
        theory = predict_static_transfer(
            build_gu_theory_config(
                self.architecture,
                nonidealities=self.nonideality_profile,
                enabled_effects=enabled,
            )
        )
        platform = build_gu_static_hypothesis_a(self.architecture)
        applied = build_gu_gate_d_nonidealities(
            self.nonideality_profile,
            enabled_effects=enabled,
        )

        sample_count = 16384
        phase = (math.sqrt(5) - 1) / 2
        for sample_index in range(sample_count):
            value = -1 + 2 * (sample_index + phase) / sample_count
            predicted = theory.segment_at(value)
            observed = process(
                value,
                platform,
                sample_index=sample_index,
                nonidealities=applied,
            )
            self.assertEqual(
                predicted.output_code,
                observed.reconstruction.output_code,
            )
            self.assertEqual(
                predicted.correctable,
                observed.reconstruction.correctable,
            )

    def test_boundary_failure_width_and_codes_match_platform(self) -> None:
        ratio = 0.964
        offset = -0.08
        dither_symbols = (1, 1)
        theory = predict_static_transfer(
            build_gu_theory_config(
                self.architecture,
                dither_symbols=dither_symbols,
                stage2_flash_auxiliary_gain_ratio=ratio,
                stage2_flash_auxiliary_offset=offset,
            )
        )
        self.assertGreater(theory.uncorrectable_input_width, 0.0)

        platform = build_gu_static_hypothesis_a(
            self.architecture,
            stage2_flash_auxiliary_gain_ratio=ratio,
            stage2_flash_auxiliary_offset=offset,
        )
        for sample_index, segment in enumerate(theory.segments):
            value = (segment.input_lower + segment.input_upper) / 2
            observed = process(
                value,
                platform,
                sample_index=sample_index,
                dither_symbols=dither_symbols,
            )
            self.assertEqual(
                segment.output_code,
                observed.reconstruction.output_code,
            )
            self.assertEqual(
                segment.correctable,
                observed.reconstruction.correctable,
            )

    def test_theory_adapter_rejects_hidden_or_unknown_effects(self) -> None:
        with self.assertRaises(ValueError):
            build_gu_theory_config(
                self.architecture,
                enabled_effects=("static_pwl_truth",),
            )
        with self.assertRaises(ValueError):
            build_gu_theory_config(
                self.architecture,
                nonidealities=self.nonideality_profile,
                enabled_effects=("mystery_effect",),
            )


if __name__ == "__main__":
    unittest.main()
