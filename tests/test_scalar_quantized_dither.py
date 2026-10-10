"""Independent exact moments and temporal covariance checks."""

from fractions import Fraction as F
import unittest

from adc_research.theory.scalar_quantized_dither import scalar_population, scalar_window_law
from adc_research.theory.dither_information import scalar_window_moments


class ScalarQuantizedTests(unittest.TestCase):
    def test_floor_dc_bias_exact_and_not_white_noise(self):
        pop = scalar_population(gain=F(39,40), dither=F(64), low=F(37,100),
                                high=F(37,100), quantized=True)
        self.assertEqual(pop.correlation, 4000)  # R+=62, R-=-63
        self.assertEqual(pop.quantization_error_correlation, F(32,5))
        self.assertEqual(pop.raw_mean, F(-1,2))
        self.assertEqual(F(64)**2/pop.correlation, F(128,125))
        k = F(128,125)
        direct = sum((k*q-s*64-F(37,100))**2 for s,q in ((1,62),(-1,-63)))/2
        self.assertAlmostEqual(pop.mse(float(k)), float(direct), places=10)

    def test_uniform_floor_integrals_hand_computed(self):
        pop = scalar_population(gain=F(1),dither=F(1,2),low=F(0),high=F(1),quantized=True)
        # Four equal probability intervals: R+=0,1; R-=-1,0.
        self.assertEqual(pop.correlation, F(1,4))
        self.assertEqual(pop.product_second_moment, F(1,8))
        self.assertEqual(pop.raw_mean, 0)
        self.assertEqual(pop.raw_second_moment, F(1,2))
        self.assertEqual(pop.raw_target_cross_moment, F(3,8))

    def test_continuous_general_law_matches_previous_theory(self):
        pop = scalar_population(gain=F(39,40),dither=F(64),low=F(-256),high=F(256),quantized=False)
        law = scalar_window_law(pop,dither=64,step=1/262144000,selected=4,multiplier=30)
        mean, variance = law.mean_variance(128)
        old = scalar_window_moments(gain=.975,dither=64,residue_variance=256**2/3,
                                    step=1/262144000,selected=4,multiplier=30,windows=128)
        self.assertAlmostEqual(mean,old.mean_coefficient,places=13)
        self.assertAlmostEqual(variance,old.coefficient_variance,places=13)
        self.assertAlmostEqual(law.stationary_variance,old.stationary_variance,places=13)

    def test_block_and_drift_variance_by_explicit_covariance(self):
        pop = scalar_population(gain=F(1),dither=F(64),low=F(-256),high=F(256),quantized=False)
        law = scalar_window_law(pop,dither=64,step=1/262144000,selected=4,multiplier=30)
        n=17
        direct = sum(law.stationary_variance*law.contraction**abs(i-j)
                     for i in range(n) for j in range(n))/n**2
        self.assertAlmostEqual(law.stationary_mean_variance(n),direct,places=12)
        weights = [-1/n]*n+[1/n]*n
        drift = sum(weights[i]*weights[j]*law.stationary_variance*law.contraction**abs(i-j)
                    for i in range(2*n) for j in range(2*n))
        self.assertAlmostEqual(law.adjacent_half_drift_variance(n),drift,places=12)


if __name__ == "__main__":
    unittest.main()
