"""Independent finite outcome enumeration and stability boundary controls."""

from fractions import Fraction as F
from itertools import product
import unittest

from adc_research.theory.gu_step_stability import (
    continuous_net_mse_u_upper, request_dead_zone_step, scalar_step_law,
)
from adc_research.theory.scalar_quantized_dither import scalar_population, scalar_window_law


class GuStepStabilityTests(unittest.TestCase):
    def toy(self, step):
        # X,D independently +/-1; R=X+D => DR is 0 or 2 equally often.
        return scalar_step_law(correlation=F(1), product_second_moment=F(2),
                               dither=F(1), step=F(step), selected=1, multiplier=F(1))

    def test_mean_stable_can_have_growing_second_moment(self):
        law = self.toy(F(3, 2))
        self.assertEqual(law.mean_factor, F(-1, 2))
        self.assertEqual(law.second_factor, F(5, 2))
        self.assertTrue(law.mean_stable)
        self.assertFalse(law.mean_square_stable)
        self.assertEqual(law.exact_moments(3)[0], 1)
        self.assertGreater(law.exact_moments(3)[1], law.exact_moments(2)[1])
        with self.assertRaises(ValueError):
            _ = law.stationary_variance

    def test_critical_second_moment_grows_linearly(self):
        law = self.toy(F(1))
        self.assertEqual(law.second_factor, 1)
        self.assertEqual(law.exact_moments(7), (F(1), F(7)))
        self.assertFalse(law.mean_square_stable)

    def test_enumerated_window_outcomes_and_all_finite_paths(self):
        m, alpha, d = 2, F(1, 8), F(1)
        # Four equally likely per-sample outcomes; do not call a recurrence.
        sample_products = [dd*(xx+dd) for xx, dd in product((-1, 1), repeat=2)]
        window_sums = [sum(values) for values in product(sample_products, repeat=m)]
        law = scalar_step_law(correlation=F(1), product_second_moment=F(2),
                               dither=d, step=alpha, selected=m, multiplier=F(1))
        states = [F(3, 4)]
        for windows in range(1, 4):
            states = [(1-alpha*ss)*kk+alpha*m*d*d for kk in states for ss in window_sums]
            mean = sum(states)/len(states)
            variance = sum((kk-mean)**2 for kk in states)/len(states)
            self.assertEqual(law.exact_moments(windows, F(3, 4)), (mean, variance))

    def test_window_size_and_multiplier_change_noise_not_equal_mean(self):
        pop = scalar_population(gain=F(39, 40), dither=F(64), low=F(-256),
                                high=F(256), quantized=False)
        laws = [scalar_step_law(correlation=pop.correlation,
                product_second_moment=pop.product_second_moment, dither=F(64),
                step=F(1, 262144000), selected=m, multiplier=F(p))
                for m, p in ((4, 30), (120, 1))]
        self.assertEqual(laws[0].mean_factor, laws[1].mean_factor)
        self.assertEqual(laws[0].multiplier_variance, 30*laws[1].multiplier_variance)
        self.assertEqual(laws[0].gamma, F(4, 3))
        self.assertEqual(laws[1].gamma, F(2, 45))
        self.assertGreater(laws[0].stationary_variance, 30*laws[1].stationary_variance)

    def test_closed_moments_match_independent_existing_recurrence(self):
        pop = scalar_population(gain=F(39, 40), dither=F(64), low=F(-256),
                                high=F(256), quantized=False)
        for ratio in (F(1, 4), F(1, 2), F(1), F(2)):
            step = ratio/F(262144000)
            law = scalar_step_law(correlation=pop.correlation,
                product_second_moment=pop.product_second_moment, dither=F(64),
                step=step, selected=4, multiplier=F(30))
            old = scalar_window_law(pop, dither=64, step=float(step), selected=4, multiplier=30)
            for n in (0, 1, 128, 2500, 4096):
                mean, var = law.float_moments(n)
                old_mean, old_var = old.mean_variance(n)
                self.assertAlmostEqual(mean, old_mean, places=12)
                self.assertAlmostEqual(var, old_var, places=12)

    def test_net_mse_upper_by_direct_output_moments(self):
        gain, gamma, d, ex2 = F(39, 40), F(4, 3), F(64), F(256**2, 3)
        upper = continuous_net_mse_u_upper(gain=gain, gamma=gamma)
        self.assertEqual(upper, F(6, 6407))
        unit_mse = (gain-1)**2*(ex2+d*d)
        for u, sign in ((upper/2, -1), (upper, 0), (upper*2, 1)):
            law = scalar_step_law(correlation=gain*d*d,
                product_second_moment=gain*gain*d*d*(ex2+d*d), dither=d,
                step=u/(30*4*gain*d*d), selected=4, multiplier=F(30))
            mse = gain*gain*(ex2+d*d)*law.stationary_variance
            self.assertEqual((mse > unit_mse)-(mse < unit_mse), sign)

    def test_quantized_root_is_step_independent(self):
        pop = scalar_population(gain=F(39, 40), dither=F(64), low=F(-1, 4),
                                high=F(1, 4), quantized=True)
        for step in (F(1, 1048576000), F(1, 262144000)):
            law = scalar_step_law(correlation=pop.correlation,
                product_second_moment=pop.product_second_moment, dither=F(64),
                step=step, selected=4, multiplier=F(30))
            self.assertEqual(law.equilibrium, F(128, 125))
            self.assertNotEqual(law.equilibrium, F(40, 39))

    def test_zero_excitation_variance_and_mean_oscillation(self):
        law = scalar_step_law(correlation=F(1), product_second_moment=F(1),
                dither=F(1), step=F(3, 2), selected=1, multiplier=F(1))
        self.assertTrue(law.mean_square_stable)
        self.assertEqual(law.stationary_variance, 0)
        self.assertEqual(law.exact_moments(2, F(0)), (F(3, 4), F(0)))

    def test_nearest_even_dead_zone_includes_half_lsb(self):
        upper = request_dead_zone_step(product_sum=F(8), multiplier=F(30))
        self.assertEqual(round(-2**22*upper*30*8), 0)
        self.assertEqual(round(-2**22*upper*F(1001, 1000)*30*8), -1)
        self.assertIsNone(request_dead_zone_step(product_sum=F(0), multiplier=F(30)))

    def test_population_moving_gate_derivative_differs_from_fixed_mask(self):
        # X~U[-1,1], D=+/-1, R=X+D. B=1/2 fixed. DR=U~U[0,2].
        def integral(k):
            lo, hi = F(1, 2)/k, F(3, 2)/k
            def primitive(u):
                return (k*u*u/2-u)/2
            return primitive(lo)-primitive(0)+primitive(2)-primitive(hi)
        h = F(1, 10)
        self.assertEqual((integral(1+h)-integral(1-h))/(2*h), 1)
        # At k=1 the open tails are [0,1/2] and [3/2,2].
        frozen_mask_derivative = (F(1, 2)**2 + 2**2-F(3, 2)**2)/4
        self.assertEqual(frozen_mask_derivative, F(1, 2))

    def test_mean_error_count_and_invalid_moments(self):
        law = self.toy(F(1, 2))
        self.assertEqual(law.mean_error_windows(.125), 3)
        with self.assertRaises(ValueError):
            scalar_step_law(correlation=F(2), product_second_moment=F(3),
                           dither=F(1), step=F(1), selected=1, multiplier=F(1))


if __name__ == "__main__":
    unittest.main()
