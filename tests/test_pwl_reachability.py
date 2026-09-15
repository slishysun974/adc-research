from __future__ import annotations

import unittest

from adc_research.theory.pwl_reachability import pwl_slice_reachability


class PwlReachabilityTests(unittest.TestCase):
    def test_exp006_fourth_slice_thresholds_are_below_redundancy_limit(self) -> None:
        stage1 = pwl_slice_reachability(
            0.7625,
            nominal_residue_output_half_range=0.5,
            interstage_gain=4,
        )
        stage2 = pwl_slice_reachability(
            0.74,
            nominal_residue_output_half_range=0.5,
            interstage_gain=4,
        )
        self.assertAlmostEqual(stage1.minimum_preamp_dither_infimum, 0.065625)
        self.assertAlmostEqual(stage2.minimum_preamp_dither_infimum, 0.06)
        self.assertAlmostEqual(
            stage1.maximum_preamp_dither_without_nominal_overload, 0.125
        )
        self.assertTrue(stage1.feasible_below_nominal_overload)
        self.assertTrue(stage2.feasible_below_nominal_overload)
        self.assertFalse(stage1.reached_by(1 / 32))
        self.assertFalse(stage2.reached_by(1 / 32))
        self.assertTrue(stage1.reached_by(5 / 64))
        self.assertTrue(stage2.reached_by(5 / 64))

    def test_open_boundary_requires_strictly_more_than_the_infimum(self) -> None:
        audit = pwl_slice_reachability(
            0.75,
            nominal_residue_output_half_range=0.5,
            interstage_gain=4,
        )
        self.assertFalse(audit.reached_by(1 / 16))
        self.assertTrue(audit.reached_by(1 / 16 + 1e-12))

    def test_invalid_ranges_fail_early(self) -> None:
        with self.assertRaises(ValueError):
            pwl_slice_reachability(
                0.75,
                nominal_residue_output_half_range=1.1,
                interstage_gain=4,
            )


if __name__ == "__main__":
    unittest.main()
