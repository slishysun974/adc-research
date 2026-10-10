from fractions import Fraction as F
import unittest

from adc_research.theory.filtered_mean_dynamics import scalar_filtered_moments


class FilteredMeanDynamicsTests(unittest.TestCase):
    def test_covariance_satisfies_exact_discrete_lyapunov_identity(self):
        for alpha,beta,step in ((F(1,4),F(1),F(1)),(F(1),F(1,3),F(1,8)),(F(1,4),F(13),F(2))):
            result = scalar_filtered_moments(alpha,beta,step,F(3,2))
            a,p,b = result["matrix"],result["covariance"],result["noise_vector"]
            for i in range(2):
                for j in range(2):
                    propagated = sum((a[i][k]*p[k][l]*a[j][l] for k in range(2) for l in range(2)),F(0))
                    self.assertEqual(p[i][j],propagated+F(3,2)*b[i]*b[j])

    def test_statistic_and_state_variances_are_different(self):
        result = scalar_filtered_moments(F(1,4),F(1))
        self.assertEqual(result["fixed_state_statistic_variance_ratio"],F(1,7))
        self.assertEqual(result["scalar_state_variance"],F(7,13))
        self.assertEqual(result["baseline_variance"],1)
        self.assertEqual(result["quarter_step_variance"],F(1,7))

    def test_unstable_boundary_and_float_parameters_are_rejected(self):
        for beta in (F(0),F(14),F(15)):
            with self.assertRaises(ValueError):
                scalar_filtered_moments(F(1,4),beta)
        with self.assertRaises(TypeError):
            scalar_filtered_moments(0.25,F(1))


if __name__ == "__main__":
    unittest.main()
