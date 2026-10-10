"""Exact sign, quantization bias and stochastic-noise controls."""

from fractions import Fraction
import unittest

from adc_research.theory.dither_information import binary_conditional_correlation, scalar_window_moments


class DitherInformationTests(unittest.TestCase):
    def test_linear_mean_direction_is_correct_without_known_input(self):
        x, d, gain = 0.43, 0.125, 0.97
        for k in (0.9, 1/gain, 1.2):
            positive, negative = k*gain*(x+d)-d, k*gain*(x-d)+d
            corr = binary_conditional_correlation(positive, negative)
            self.assertAlmostEqual(corr, d*(k*gain-1), places=14)

    def test_lower_gate_preserves_order_but_upper_gate_can_reverse_it(self):
        for low, high in ((-0.6,-0.4),(-0.4,0.2),(0.4,0.6),(-0.6,0.6)):
            self.assertGreaterEqual(binary_conditional_correlation(high, low, 0.5), 0)
        self.assertLess((0-0.4)/2, 0)  # upper gate discards high=0.6 only

    def test_quantization_can_bias_binary_correlation_at_perfect_gain(self):
        # Midrise 0.1 steps, corrected gain exactly one, input x=0, d=0.16.
        # Quantized levels +/-0.15 leave +/-(-0.01) after subtraction.
        self.assertAlmostEqual(binary_conditional_correlation(0.15-0.16, -0.15+0.16), -0.01)

    def test_one_window_exact_moments_and_thirtyfold_selection_noise(self):
        params = dict(gain=0.975, dither=64, residue_variance=256**2/3,
                      step=float(Fraction(1,262144000)), windows=1)
        point = scalar_window_moments(**params, selected=4, multiplier=30)
        full = scalar_window_moments(**params, selected=120, multiplier=1)
        self.assertAlmostEqual(point.mean_coefficient, full.mean_coefficient)
        self.assertAlmostEqual(point.coefficient_variance/full.coefficient_variance, 30)

    def test_perfect_model_has_zero_mean_error_but_positive_learning_noise(self):
        result = scalar_window_moments(gain=1, dither=64, residue_variance=256**2/3,
             step=1/262144000, selected=4, multiplier=30, windows=128)
        self.assertAlmostEqual(result.mean_coefficient, 1)
        self.assertGreater(result.coefficient_variance, 0)
        self.assertGreater(result.stationary_variance, 0)


if __name__ == "__main__":
    unittest.main()
