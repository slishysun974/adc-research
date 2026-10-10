from fractions import Fraction as F
import unittest

from adc_research.calibration.fixed_point import round_fraction
from adc_research.theory.paired_dither_conditions import analyze_pair_equations
from experiments.exp_048_paired_dither_conditions.examples import periodic_cubic_error, periodic_counterexample


class PairedPeriodicCounterexampleTests(unittest.TestCase):
    def test_exact_period_oddness_and_zero_anchor(self):
        self.assertEqual(periodic_cubic_error(F(0)), 0)
        for value in (F(-123, 7), F(0), F(39), F(64), F(511, 2)):
            self.assertEqual(periodic_cubic_error(value+128), periodic_cubic_error(value))
            self.assertEqual(periodic_cubic_error(-value), -periodic_cubic_error(value))

    def test_full_rank_unique_contrast_fit_still_has_output_error(self):
        pairs, targets = periodic_counterexample(tuple(F(13*i) for i in range(-33, 34)))
        result = analyze_pair_equations(pairs)
        self.assertEqual(result['basis_difference_rank'], 4)
        self.assertEqual(result['contrast_least_squares_coefficients'], (F(1),)*4)
        self.assertTrue(all(v == 0 for v in result['contrast_residuals']))
        self.assertTrue(any(pair.raw_plus-pair.dither_magnitude != target for pair, target in zip(pairs, targets)))

    def test_quantization_does_not_remove_the_counterexample(self):
        pairs, targets = periodic_counterexample(tuple(F(13*i) for i in range(-33, 34)))
        errors = []
        for pair, target in zip(pairs, targets):
            plus = round_fraction(8*pair.raw_plus.numerator, pair.raw_plus.denominator, 'nearest_even')
            minus = round_fraction(8*pair.raw_minus.numerator, pair.raw_minus.denominator, 'nearest_even')
            self.assertEqual(plus-minus, 1024)
            errors.append(F(plus, 8)-64-target)
        self.assertTrue(any(errors))

    def test_two_commensurate_dither_sizes_keep_a_smaller_periodic_error(self):
        pairs, targets = periodic_counterexample(tuple(F(13*i) for i in range(-30, 31)),
                                                (F(64), F(80)), F(16), F(2))
        result = analyze_pair_equations(pairs)
        self.assertTrue(all(v == 0 for v in result['contrast_residuals']))
        self.assertTrue(any(pair.raw_plus-pair.dither_magnitude != target for pair, target in zip(pairs, targets)))

    def test_derivative_bound_certifies_strict_monotonicity(self):
        half_period, scale = F(64), F(8)
        self.assertEqual(1-2*scale/half_period, F(3, 4))
        self.assertGreater(1-2*scale/half_period, 0)


if __name__ == '__main__':
    unittest.main()
