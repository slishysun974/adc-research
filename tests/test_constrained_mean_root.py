"""Weighted empirical derivatives and a uniform constrained-cell norm bound."""

from fractions import Fraction as F
from itertools import product
import unittest

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.constrained_mean_root import weighted_cascade_mean, certify_low4_root, low4_cell_stable
from adc_research.theory.window_mean_map import analyze_window_mean
from adc_research.theory.window_excitation import restricted_transition


class ConstrainedMeanRootTests(unittest.TestCase):
    def test_weighted_mean_and_jacobian_match_expanded_record(self):
        record = ((Sample(0, 0, 79, 1, 1), 2), (Sample(0, 1, -49, 1, 1), 3))
        weighted = weighted_cascade_mean(record, (F(1),)*8)
        repeated = analyze_window_mean(tuple(sample for sample, count in record for _ in range(count)), (F(1),)*8)
        self.assertEqual(weighted.mean_products, repeated.mean_products)
        self.assertEqual(weighted.jacobian, repeated.fixed_mask_jacobian)

    def test_uniform_row_variation_bound_at_all_low4_box_corners(self):
        samples = []
        # Unit correction produces y1=80 or 150, with balanced d1. y2 is
        # independent of d2, and d2 is balanced at every other condition.
        for local1, d1, d2 in product((80, 150), (-1, 1), (-1, 1)):
            q2 = 1 if local1 == 150 or d1 == 1 else 0
            local2 = local1+64*d1-128*q2
            samples.append(Sample(0, q2, local2+16*d2, d1, d2))
        record = tuple((sample, 1) for sample in samples)
        mean = weighted_cascade_mean(record, (F(1),)*8)
        self.assertEqual(mean.mean_products, (F(0),)*8)
        steps = (F(1, 1000000),)*8
        certificate = certify_low4_root(mean, steps)
        self.assertTrue(certificate['all_masks_and_domains_stable'])
        self.assertFalse(certificate['frozen_gates_all_closed'])
        self.assertFalse(certificate['full_gu_empirical_map_has_same_invariant_box'])
        radius = certificate['box_radius']
        for signs in product((-1, 1), repeat=4):
            slopes = [F(1)]*8
            for i, sign in zip((0, 1, 4, 5), signs):
                slopes[i] += sign*radius
            changed = weighted_cascade_mean(record, tuple(slopes))
            norm = restricted_transition(changed.jacobian, steps, (0, 1, 4, 5)).norm_bound
            self.assertLessEqual(norm, certificate['uniform_norm_bound'])

    def test_nonroot_and_invalid_weights_are_rejected(self):
        with self.assertRaises(ValueError):
            weighted_cascade_mean(((Sample(0, 0, 1, 1, 1), 0),), (F(1),)*8)
        mean = weighted_cascade_mean(((Sample(0, 0, 1, 1, 1), 1),), (F(1),)*8)
        with self.assertRaises(ValueError):
            certify_low4_root(mean, (F(1, 1000000),)*8)

    def test_constant_boundary_on_clamped_subspace_differs_from_variable_tie(self):
        constant = weighted_cascade_mean(((Sample(0, 0, 80, 1, 1), 1),), (F(1),)*8)
        self.assertFalse(constant.base.open_cell_regular)
        self.assertTrue(low4_cell_stable(constant, F(1, 100000)))
        # raw=80, d2=16 has y2=32*k0+32*k1 at all free k0,k1,
        # since the clamped third slope is exactly one.
        variable = weighted_cascade_mean(((Sample(0, 0, 48, 1, -1), 1),), (F(1),)*8)
        self.assertFalse(low4_cell_stable(variable, F(0)))
        self.assertFalse(low4_cell_stable(variable, F(1, 100000)))


if __name__ == '__main__':
    unittest.main()
