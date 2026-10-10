"""Information, update closure, switching, and observation-law boundaries."""

from fractions import Fraction as F
import unittest

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.window_mean_map import MeanGeometry, analyze_window_mean, exact_matrix_rank
from adc_research.theory.window_excitation import (
    chronological_product, empirical_total_variation, exact_nullspace, gram_lower_bound,
    infinity_norm, matmul, positive_definite, product_magnitude_bounds,
    readout_gram, restricted_transition,
)


class WindowExcitationTests(unittest.TestCase):
    def test_inactive_update_has_nonzero_readout_energy(self):
        result = analyze_window_mean((Sample(0, 0, 100, 1, 1),), (F(1),)*8)
        gram = readout_gram(result)
        self.assertEqual(gram[3][3], 32)  # psi2[3]=4, k1=1: 4^2+4^2.
        self.assertTrue(all(x == 0 for x in result.fixed_mask_jacobian[3]))
        self.assertEqual(result.fixed_mask_jacobian[0][3], 64)
        self.assertEqual(exact_matrix_rank(gram), 2)
        for vector in exact_nullspace(gram):
            self.assertTrue(all(sum(a*b for a, b in zip(row, vector)) == 0 for row in gram))

    def test_full_rank_readout_does_not_imply_stable_update(self):
        gram = ((F(1),),)
        update = restricted_transition(((F(-1),),), (F(1, 2),), (0,))
        self.assertGreater(gram_lower_bound(gram), 0)
        self.assertEqual(update.transition, ((F(3, 2),),))
        self.assertGreater(update.norm_bound, 1)

    def test_subspace_leakage_prevents_principal_minor_claim(self):
        result = restricted_transition(((F(1), F(0)), (F(2), F(1))), (F(1, 2),)*2, (0,))
        self.assertEqual(result.norm_bound, F(1, 2))
        self.assertFalse(result.invariant)
        self.assertEqual(result.leakage, ((F(-1),),))

    def test_inactive_rows_close_a_frozen_coordinate_subspace(self):
        result = restricted_transition(((F(1), F(7)), (F(0), F(0))), (F(1, 2),)*2, (0,))
        self.assertTrue(result.invariant)
        self.assertEqual(result.norm_bound, F(1, 2))

    def test_chronological_product_keeps_order_and_switching_growth(self):
        a = ((F(1, 2), F(2)), (F(0), F(1, 2)))
        b = ((F(1, 2), F(0)), (F(2), F(1, 2)))
        product = chronological_product((a, b))
        self.assertEqual(product, ((F(1, 4), F(1)), (F(1), F(17, 4))))
        self.assertNotEqual(product, chronological_product((b, a)))
        self.assertEqual(infinity_norm(product), F(21, 4))
        self.assertEqual(matmul(product, ((F(0),), (F(1),))), ((F(1),), (F(17, 4),)))

    def test_exact_ldlt_and_positive_gram_lower_bound(self):
        gram = ((F(1), F(1)), (F(1), F(2)))
        self.assertTrue(positive_definite(gram))
        alpha = gram_lower_bound(gram)
        self.assertEqual(alpha, F(1, 4))
        self.assertTrue(positive_definite(((1-alpha, F(1)), (F(1), 2-alpha))))
        self.assertEqual(gram_lower_bound(((1, 1), (1, 1))), 0)
        self.assertFalse(positive_definite(((1, 2), (2, 1))))

    def test_nullspace_detects_combinations_not_just_missing_columns(self):
        self.assertEqual(exact_nullspace(((F(1), F(2)), (F(2), F(4)))), ((F(-2), F(1)),))
        self.assertEqual(exact_nullspace(((1, 0), (0, 1))), ())

    def test_tv_handles_permutation_and_protects_common_reference_means(self):
        a, b, c = Sample(0, 0, 79, 1, 1), Sample(0, 1, -49, 1, 1), Sample(0, 0, 0, -1, -1)
        self.assertEqual(empirical_total_variation((a, b), (b, a)), 0)
        left, right = (a, a, b, c), (a, b, b, b)
        tv = empirical_total_variation(left, right)
        self.assertEqual(tv, F(1, 2))
        x, y = (analyze_window_mean(record, (F(1),)*8) for record in (left, right))
        bounds = product_magnitude_bounds((F(1),)*8, MeanGeometry())
        self.assertEqual(bounds, (F(2304),)*4+(F(36864),)*4)
        self.assertTrue(all(abs(a-b) <= 2*bound*tv for a, b, bound in zip(
            x.mean_products, y.mean_products, bounds)))

    def test_invalid_inputs_and_unclosed_or_unproved_cases_are_not_certified(self):
        with self.assertRaises(TypeError):
            infinity_norm(((1.0,),))
        with self.assertRaises(ValueError):
            restricted_transition(((1,),), (F(1),), (0, 0))
        with self.assertRaises(ValueError):
            restricted_transition(((1,),), (0.5,), (0,))
        with self.assertRaises(ValueError):
            positive_definite(((1, 2), (0, 1)))
        with self.assertRaises(ValueError):
            gram_lower_bound(((1, 2), (2, 1)))
        with self.assertRaises(ValueError):
            gram_lower_bound(((-1, 0), (0, 0)))
        with self.assertRaises(ValueError):
            gram_lower_bound(((0, 1), (1, 0)))
        with self.assertRaises(ValueError):
            empirical_total_variation((), ())
        with self.assertRaises(ValueError):
            chronological_product(())


if __name__ == "__main__":
    unittest.main()
