from __future__ import annotations

import unittest
from pathlib import Path

import yaml

from adc_research.platform.pipeline import process
from adc_research.platform.presets import build_gu_static_hypothesis_a


class GuBehavioralV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[1]
        path = root / "configs" / "architectures" / "gu_behavioral_v1.yaml"
        cls.config = yaml.safe_load(path.read_text(encoding="utf-8"))

    def test_freeze_scope_is_explicitly_not_silicon_bit_true(self) -> None:
        self.assertEqual(self.config["status"], "frozen_behavioral_baseline")
        self.assertEqual(
            self.config["claim_scope"],
            "executable_static_behavior_not_silicon_bit_true",
        )
        self.assertIsNone(
            self.config["dither_hypothesis"]["physical_prng_switch_mapping"]
        )

    def test_frozen_config_builds_and_preserves_ideal_identity(self) -> None:
        platform_config = build_gu_static_hypothesis_a(self.config)
        for expected in range(4096):
            value = -1 + (expected + 0.5) / 2048
            result = process(value, platform_config, sample_index=expected)
            self.assertEqual(result.reconstruction.output_code, expected)

    def test_reported_interstage_mismatch_maps_only_to_stage2_flash(self) -> None:
        platform_config = build_gu_static_hypothesis_a(
            self.config,
            stage2_flash_auxiliary_gain_ratio=1.03,
        )
        self.assertEqual(platform_config.auxiliary_gain_ratios, (1.0, 1.03))


if __name__ == "__main__":
    unittest.main()
