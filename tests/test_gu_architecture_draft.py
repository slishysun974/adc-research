from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class GuArchitectureDraftTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        path = cls.root / "configs" / "architectures" / "gu_nominal_v0_1_draft.yaml"
        cls.config = yaml.safe_load(path.read_text(encoding="utf-8"))

    def test_effective_bits_sum_to_nominal_resolution(self) -> None:
        architecture = self.config["architecture"]
        self.assertEqual(
            sum(architecture["effective_bit_contributions"]["value"]),
            architecture["nominal_output_bits"]["value"],
        )

    def test_two_front_stages_have_reported_nominal_structure(self) -> None:
        stages = self.config["stages"]
        self.assertEqual(len(stages), 2)
        for stage in stages:
            self.assertEqual(stage["subadc_label_bits"]["value"], 3)
            self.assertEqual(stage["effective_bits"]["value"], 2)
            self.assertEqual(stage["nominal_interstage_gain"]["value"], 4.0)
            self.assertEqual(stage["redundancy_bits"]["value"], 1)

    def test_unpublished_code_details_remain_explicitly_unresolved(self) -> None:
        for stage in self.config["stages"]:
            for field in (
                "flash_thresholds_normalized",
                "flash_output_symbols",
                "cdac_levels_normalized",
            ):
                item = stage[field]
                self.assertIsNone(item["value"])
                self.assertEqual(item["provenance"], "unresolved")
                self.assertIn("open_question", item)

        reconstruction = self.config["digital_reconstruction"]
        for item in reconstruction.values():
            self.assertIsNone(item["value"])
            self.assertEqual(item["provenance"], "unresolved")

    def test_draft_cannot_accidentally_enable_unvalidated_features(self) -> None:
        defaults = self.config["model_defaults"]
        self.assertEqual(defaults["fidelity"], "ideal_static")
        self.assertFalse(defaults["dither_enabled"])
        self.assertFalse(defaults["nonidealities_enabled"])
        self.assertEqual(defaults["calibration_mode"], "none")


if __name__ == "__main__":
    unittest.main()
