from __future__ import annotations

import math
import unittest

from adc_research.theory.redundancy import (
    correctable_boundary_window,
    effective_boundary,
    residue_extrema,
)


class GuJointRedundancyRegionTests(unittest.TestCase):
    symbols = tuple(range(-4, 5))
    thresholds = tuple((symbol + 0.5) / 4 for symbol in range(-4, 4))
    dac_levels = {symbol: symbol / 4 for symbol in symbols}

    @staticmethod
    def decide(value: float, thresholds: tuple[float, ...]) -> int:
        return sum(value >= threshold for threshold in thresholds) - 4

    def test_nominal_window_reduces_to_plus_or_minus_one_eighth(self) -> None:
        for symbol, threshold in zip(
            self.symbols[:-1], self.thresholds, strict=True
        ):
            window = correctable_boundary_window(
                self.dac_levels[symbol],
                self.dac_levels[symbol + 1],
                interstage_gain=4,
            )
            self.assertAlmostEqual(window.center, threshold)
            self.assertAlmostEqual(window.half_width, 1 / 8)

    def test_hypothesis_a_dither_reduces_threshold_margin_to_three_32nds(
        self,
    ) -> None:
        # 1/16 of a backend full-scale span of two normalized units is a
        # +/-1/8 backend-input shift. Referred through nominal gain four to
        # the residue summing node, the dither is +/-1/32.
        for symbol, threshold in zip(
            self.symbols[:-1], self.thresholds, strict=True
        ):
            window = correctable_boundary_window(
                self.dac_levels[symbol],
                self.dac_levels[symbol + 1],
                interstage_gain=4,
                dither_half_amplitude=1 / 32,
            )
            self.assertAlmostEqual(window.center, threshold)
            self.assertAlmostEqual(window.half_width, 3 / 32)

    def test_paper_reported_three_percent_auxiliary_gain_mismatch_fits_margin(
        self,
    ) -> None:
        for ratio in (0.97, 1.03):
            for symbol, threshold in zip(
                self.symbols[:-1], self.thresholds, strict=True
            ):
                boundary = effective_boundary(
                    threshold, auxiliary_gain_ratio=ratio
                )
                window = correctable_boundary_window(
                    self.dac_levels[symbol],
                    self.dac_levels[symbol + 1],
                    interstage_gain=4,
                    dither_half_amplitude=1 / 32,
                )
                self.assertTrue(window.contains(boundary))

    def test_window_matches_brute_force_residue_endpoint_check(self) -> None:
        gain = 4.1
        dither = 0.02
        left_dac = -0.25 + 0.006
        right_dac = 0.0 - 0.004
        window = correctable_boundary_window(
            left_dac,
            right_dac,
            interstage_gain=gain,
            dither_half_amplitude=dither,
        )
        self.assertTrue(window.feasible)

        boundary = window.center
        _, left_supremum = residue_extrema(
            -1,
            boundary,
            left_dac,
            interstage_gain=gain,
            dither_half_amplitude=dither,
        )
        right_infimum, _ = residue_extrema(
            boundary,
            1,
            right_dac,
            interstage_gain=gain,
            dither_half_amplitude=dither,
        )
        self.assertLessEqual(left_supremum, 1)
        self.assertGreaterEqual(right_infimum, -1)

        _, overloaded = residue_extrema(
            -1,
            window.upper + 1e-6,
            left_dac,
            interstage_gain=gain,
            dither_half_amplitude=dither,
        )
        self.assertGreater(overloaded, 1)

    def test_two_dithers_cancel_exactly_in_the_ideal_three_stage_chain(
        self,
    ) -> None:
        # The first-stage backend has 1024 codes and the SAR has 256 codes.
        # A 1/16-FS dither therefore has exact digital copies 64 and 16.
        for raw_12 in range(4096):
            value = -1 + (raw_12 + 0.5) / 2048
            q1 = self.decide(value, self.thresholds)
            for sign1 in (-1, 1):
                x2 = 4 * (value - q1 / 4 + sign1 / 32)

                # Exercise the reported 3% auxiliary-path gain mismatch in
                # both directions while the CDAC operates on the main path.
                for auxiliary_ratio in (0.97, 1.03):
                    effective_thresholds = tuple(
                        threshold / auxiliary_ratio
                        for threshold in self.thresholds
                    )
                    q2 = self.decide(x2, effective_thresholds)
                    for sign2 in (-1, 1):
                        x3 = 4 * (x2 - q2 / 4 + sign2 / 32)
                        self.assertGreaterEqual(x3, -1)
                        self.assertLess(x3, 1)

                        backend = math.floor(128 * (x3 + 1)) - 128
                        reconstructed = (
                            512 * q1
                            + 128 * q2
                            + backend
                            - 64 * sign1
                            - 16 * sign2
                            + 2048
                        )
                        self.assertEqual(reconstructed, raw_12)


if __name__ == "__main__":
    unittest.main()
