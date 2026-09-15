from __future__ import annotations

import math
import unittest
from pathlib import Path

import yaml


class GuStaticHypothesisATests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = Path(__file__).resolve().parents[1]
        path = root / "configs" / "architectures" / "gu_static_hypothesis_a_v0_1.yaml"
        cls.config = yaml.safe_load(path.read_text(encoding="utf-8"))
        cls.stage = cls.config["front_stage_template"]

    @classmethod
    def stage_convert(cls, value: float) -> tuple[int, float]:
        thresholds = cls.stage["thresholds"]
        symbols = cls.stage["output_symbols"]
        region = sum(value >= threshold for threshold in thresholds)
        symbol = symbols[region]
        residue = cls.stage["nominal_interstage_gain"] * (
            value - cls.stage["dac_levels"][region]
        )
        return symbol, residue

    @classmethod
    def stage_convert_with_threshold_shift(
        cls, value: float, threshold_index: int, shift: float
    ) -> tuple[int, float]:
        thresholds = list(cls.stage["thresholds"])
        thresholds[threshold_index] += shift
        symbols = cls.stage["output_symbols"]
        region = sum(value >= threshold for threshold in thresholds)
        symbol = symbols[region]
        residue = cls.stage["nominal_interstage_gain"] * (
            value - cls.stage["dac_levels"][region]
        )
        return symbol, residue

    @staticmethod
    def backend_convert(value: float) -> tuple[int, int]:
        raw = math.floor(128 * (value + 1))
        raw = min(max(raw, 0), 255)
        return raw, raw - 128

    def test_eight_thresholds_create_nine_thermometer_states(self) -> None:
        self.assertEqual(len(self.stage["thresholds"]), 8)
        self.assertEqual(len(self.stage["output_symbols"]), 9)
        self.assertEqual(
            self.stage["thermometer_ones_by_symbol"],
            list(range(9)),
        )

    def test_dac_levels_and_residue_follow_radix_four_equation(self) -> None:
        for symbol, dac_level in zip(
            self.stage["output_symbols"], self.stage["dac_levels"], strict=True
        ):
            self.assertEqual(dac_level, symbol / 4)

        # Sample every final 12-bit code center. Both front-stage residues
        # must remain inside their nominal half-range.
        for raw_12 in range(4096):
            value = -1 + (raw_12 + 0.5) / 2048
            _, residue_1 = self.stage_convert(value)
            _, residue_2 = self.stage_convert(residue_1)
            self.assertGreaterEqual(residue_1, -0.5)
            self.assertLess(residue_1, 0.5)
            self.assertGreaterEqual(residue_2, -0.5)
            self.assertLess(residue_2, 0.5)

    def test_pipeline_reconstruction_equals_ideal_twelve_bit_quantizer(self) -> None:
        for expected_raw in range(4096):
            value = -1 + (expected_raw + 0.5) / 2048
            q1, residue_1 = self.stage_convert(value)
            q2, residue_2 = self.stage_convert(residue_1)
            _, backend_centered = self.backend_convert(residue_2)
            centered = 512 * q1 + 128 * q2 + backend_centered
            actual_raw = centered + 2048
            self.assertEqual(actual_raw, expected_raw)

    def test_first_stage_backend_code_matches_reported_b0_partition(self) -> None:
        for raw_12 in range(4096):
            value = -1 + (raw_12 + 0.5) / 2048
            _, residue_1 = self.stage_convert(value)
            q2, residue_2 = self.stage_convert(residue_1)
            _, backend_centered = self.backend_convert(residue_2)
            combined_10_bit = 128 * q2 + backend_centered
            self.assertEqual(combined_10_bit, math.floor(512 * residue_1))

        implications = self.config["pwl_implications"]
        self.assertEqual(implications["stage1_four_slice_b0"], 128)
        self.assertEqual(implications["stage2_four_slice_b0"], 32)

    def test_normalized_redundancy_maps_to_reported_62_5_millivolts(self) -> None:
        volts_per_normalized_unit = 1.0 / 2
        input_referred_redundancy = (1 / 8) * volts_per_normalized_unit
        self.assertAlmostEqual(input_referred_redundancy, 0.0625)

    def test_adjacent_decision_errors_inside_redundancy_range_reconstruct(self) -> None:
        shift_magnitudes = (0.01, 0.0625, 0.124)
        for threshold_index, threshold in enumerate(self.stage["thresholds"]):
            for sign in (-1, 1):
                for magnitude in shift_magnitudes:
                    shift = sign * magnitude
                    # This point lies strictly between the nominal and shifted
                    # threshold, so the shifted flash takes the adjacent path.
                    value = threshold + shift * 0.999
                    q1, residue_1 = self.stage_convert_with_threshold_shift(
                        value, threshold_index, shift
                    )
                    self.assertGreaterEqual(residue_1, -1)
                    self.assertLess(residue_1, 1)

                    q2, residue_2 = self.stage_convert(residue_1)
                    _, backend_centered = self.backend_convert(residue_2)
                    reconstructed = 512 * q1 + 128 * q2 + backend_centered + 2048
                    ideal = math.floor(2048 * (value + 1))
                    self.assertEqual(reconstructed, ideal)

    def test_threshold_shift_beyond_redundancy_creates_overload_region(self) -> None:
        # Use an interior threshold so the displaced interval remains inside
        # the converter input range. A delayed decision just below the shifted
        # threshold produces residue greater than the next-stage full scale.
        threshold_index = 3
        threshold = self.stage["thresholds"][threshold_index]
        shift = 0.126
        value = threshold + shift - 1e-9
        _, residue = self.stage_convert_with_threshold_shift(
            value, threshold_index, shift
        )
        self.assertGreater(residue, 1)


if __name__ == "__main__":
    unittest.main()
