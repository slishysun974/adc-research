from __future__ import annotations

import unittest

from adc_research.platform.cdac import CdacConfig, CdacMismatch, reconstruct
from adc_research.platform.quantizer import QuantizerConfig, convert
from adc_research.platform.stage import StaticStageConfig, process
from adc_research.theory.redundancy import correctable_boundary_window


class PlatformGateABTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.thresholds = tuple((symbol + 0.5) / 4 for symbol in range(-4, 4))
        cls.symbols = tuple(range(-4, 5))
        cls.levels = {symbol: symbol / 4 for symbol in cls.symbols}
        cls.quantizer = QuantizerConfig(cls.thresholds, cls.symbols)
        cls.cdac = CdacConfig(
            nominal_levels=cls.levels,
            dither_levels={-1: -1 / 32, 1: 1 / 32},
        )
        cls.stage = StaticStageConfig(cls.quantizer, cls.cdac, 4)

    def test_threshold_equality_enters_higher_region(self) -> None:
        for index, threshold in enumerate(self.thresholds):
            result = convert(threshold, self.quantizer)
            self.assertEqual(result.region_index, index + 1)
            self.assertEqual(result.symbol, index - 3)
            self.assertEqual(result.distance_to_nearest_threshold, 0)

    def test_invalid_quantizer_tables_fail_early(self) -> None:
        with self.assertRaises(ValueError):
            QuantizerConfig((0.0, 0.0), (-1, 0, 1))
        with self.assertRaises(ValueError):
            QuantizerConfig((0.0,), (-1, 0, 1))

    def test_cdac_keeps_nominal_mismatch_and_dither_separate(self) -> None:
        result = reconstruct(
            2,
            -1,
            self.cdac,
            CdacMismatch(code_level_errors={2: 0.007}),
        )
        self.assertAlmostEqual(result.nominal_value, 0.5)
        self.assertAlmostEqual(result.mismatch_contribution, 0.007)
        self.assertAlmostEqual(result.actual_dac_value, 0.507)
        self.assertAlmostEqual(result.dither_contribution, -1 / 32)

    def test_nominal_cdac_table_is_strictly_monotone(self) -> None:
        ordered_levels = [self.levels[symbol] for symbol in self.symbols]
        self.assertTrue(
            all(
                right > left
                for left, right in zip(
                    ordered_levels, ordered_levels[1:], strict=False
                )
            )
        )

    def test_dither_disabled_is_a_zero_contribution(self) -> None:
        result = reconstruct(0, None, self.cdac)
        self.assertEqual(result.dither_contribution, 0)
        self.assertEqual(result.actual_dac_value, 0)

    def test_nominal_region_residues_stay_in_half_range(self) -> None:
        boundaries = (-1.0, *self.thresholds, 1.0)
        for index, symbol in enumerate(self.symbols):
            lower = boundaries[index]
            upper = boundaries[index + 1]
            for value in (lower, (lower + upper) / 2, upper - 1e-12):
                result = process(value, value, None, self.stage)
                self.assertEqual(result.quantizer.symbol, symbol)
                self.assertGreaterEqual(result.residue, -0.5)
                self.assertLess(result.residue, 0.5)
                self.assertTrue(result.correctable)

    def test_samplewise_platform_agrees_with_independent_boundary_theory(
        self,
    ) -> None:
        for index, nominal_boundary in enumerate(self.thresholds):
            left_symbol = self.symbols[index]
            right_symbol = self.symbols[index + 1]
            window = correctable_boundary_window(
                self.levels[left_symbol],
                self.levels[right_symbol],
                interstage_gain=4,
                dither_half_amplitude=1 / 32,
            )

            for boundary in (window.lower + 1e-8, window.upper - 1e-8):
                threshold_offset = boundary - nominal_boundary
                shifted = tuple(
                    threshold + (threshold_offset if i == index else 0)
                    for i, threshold in enumerate(self.thresholds)
                )
                stage = StaticStageConfig(
                    QuantizerConfig(shifted, self.symbols), self.cdac, 4
                )
                probe = boundary - 1e-9 if boundary > nominal_boundary else boundary
                for dither_symbol in (-1, 1):
                    result = process(probe, probe, dither_symbol, stage)
                    self.assertTrue(result.correctable)

            shifted = tuple(
                threshold + (window.upper - nominal_boundary + 1e-6 if i == index else 0)
                for i, threshold in enumerate(self.thresholds)
            )
            if all(right > left for left, right in zip(shifted, shifted[1:])):
                stage = StaticStageConfig(
                    QuantizerConfig(shifted, self.symbols), self.cdac, 4
                )
                result = process(window.upper + 5e-7, window.upper + 5e-7, 1, stage)
                self.assertFalse(result.correctable)
                self.assertTrue(result.overload_high)

    def test_auxiliary_gain_changes_decision_but_not_main_residue_equation(
        self,
    ) -> None:
        threshold = self.thresholds[-1]
        main_input = threshold / 1.03 + 1e-6
        result = process(main_input, 1.03 * main_input, None, self.stage)
        self.assertEqual(result.quantizer.symbol, 4)
        self.assertAlmostEqual(
            result.residue_preamp,
            main_input - self.levels[4],
        )
        self.assertTrue(result.correctable)


if __name__ == "__main__":
    unittest.main()
