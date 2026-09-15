from __future__ import annotations

import unittest

from adc_research.theory.dual_path import (
    audit_auxiliary_boundaries,
    joint_auxiliary_offset_interval,
)


class GuQ007DualPathTests(unittest.TestCase):
    thresholds = tuple((symbol + 0.5) / 4 for symbol in range(-4, 4))
    dac_levels = tuple(symbol / 4 for symbol in range(-4, 5))

    @classmethod
    def interval(cls, ratio: float):
        return joint_auxiliary_offset_interval(
            cls.thresholds,
            cls.dac_levels,
            auxiliary_gain_ratio=ratio,
            interstage_gain=4,
            dither_half_amplitude=1 / 32,
        )

    def test_nominal_common_offset_interval_is_plus_minus_three_32nds(self) -> None:
        interval = self.interval(1.0)
        self.assertAlmostEqual(interval.lower, -3 / 32)
        self.assertAlmostEqual(interval.upper, 3 / 32)

    def test_reported_systematic_gain_directions_leave_finite_offset_margin(self) -> None:
        low = self.interval(0.97)
        high = self.interval(1.03)
        self.assertAlmostEqual(low.half_width, 0.0646875)
        self.assertAlmostEqual(high.half_width, 0.0703125)
        self.assertAlmostEqual(low.center, 0.0)
        self.assertAlmostEqual(high.center, 0.0)

    def test_pretrim_one_sigma_rectangular_envelope_is_inside_redundancy(self) -> None:
        # Under the candidate 1-Vpp differential mapping, 20 mV is 0.04
        # normalized.  This is a deterministic corner audit, not a yield claim.
        for systematic in (-0.03, 0.03):
            for random_gain in (-0.003, 0.003):
                interval = self.interval(1 + systematic + random_gain)
                for offset in (-0.04, 0.04):
                    self.assertTrue(interval.contains(offset))

    def test_pretrim_two_sigma_rectangular_envelope_is_not_guaranteed(self) -> None:
        failures = []
        for systematic in (-0.03, 0.03):
            for random_gain in (-0.006, 0.006):
                interval = self.interval(1 + systematic + random_gain)
                for offset in (-0.08, 0.08):
                    failures.append(not interval.contains(offset))
        self.assertTrue(any(failures))

    def test_posttrim_three_sigma_drift_envelope_has_large_margin(self) -> None:
        # Post-trim sigma: gain drift <0.1%, offset drift <0.5 mV.  The latter
        # is <0.001 normalized; use the reported upper bounds conservatively.
        for ratio in (1 - 0.003, 1 + 0.003):
            interval = self.interval(ratio)
            for offset in (-0.003, 0.003):
                self.assertTrue(interval.contains(offset))

    def test_boundary_audit_identifies_the_violating_outer_threshold(self) -> None:
        ratio = 0.964
        offset = 0.08
        audits = audit_auxiliary_boundaries(
            self.thresholds,
            self.dac_levels,
            auxiliary_gain_ratio=ratio,
            auxiliary_offset=offset,
            interstage_gain=4,
            dither_half_amplitude=1 / 32,
        )
        self.assertTrue(any(not audit.correctable for audit in audits))
        worst = min(audits, key=lambda audit: audit.minimum_margin)
        self.assertEqual(worst.nominal_threshold, -0.875)
        self.assertLess(worst.minimum_margin, 0)


if __name__ == "__main__":
    unittest.main()
