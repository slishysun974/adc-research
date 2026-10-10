from __future__ import annotations

import unittest

from adc_research.calibration.flash_interface import (
    decode_candidate_flash_thermometer,
)
from adc_research.platform.quantizer import QuantizerConfig, convert


class FlashInterfaceTests(unittest.TestCase):
    def test_all_nine_candidate_regions_and_threshold_ties(self) -> None:
        thresholds = tuple((-7 + 2 * index) / 8 for index in range(8))
        quantizer = QuantizerConfig(thresholds, tuple(range(-4, 5)))
        for count in range(9):
            raw = (1 << count) - 1
            expected_q = count - 4
            self.assertEqual(decode_candidate_flash_thermometer(raw), expected_q)
            if count < 8:
                # A sample exactly at threshold[count] enters the next state.
                value = thresholds[count]
                self.assertEqual(convert(value, quantizer).symbol, expected_q + 1)
                self.assertEqual(
                    decode_candidate_flash_thermometer((1 << (count + 1)) - 1),
                    expected_q + 1,
                )

    def test_all_other_eight_bit_words_are_rejected(self) -> None:
        legal = {(1 << count) - 1 for count in range(9)}
        for raw in set(range(256)) - legal:
            with self.assertRaises(ValueError):
                decode_candidate_flash_thermometer(raw)

    def test_non_words_are_rejected(self) -> None:
        for raw in (-1, 256, True, 1.0):
            with self.assertRaises(ValueError):
                decode_candidate_flash_thermometer(raw)


if __name__ == "__main__":
    unittest.main()
