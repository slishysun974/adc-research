"""Independent rational controls of the two-bank stationary-point conditions."""
from fractions import Fraction as F
from itertools import product
import unittest

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.cascade_mean_output import cascade_loss_change
from adc_research.theory.coupled_stationarity import (
    coupled_moments, correlation_polynomial_change, instrument_span_ranks,
)
from adc_research.theory.static_fixed_contract import nearest_even, readout
from adc_research.theory.window_mean_map import analyze_window_mean, certify_mean_cell


def direct(samples, k, targets, rounded=False):
    values = [readout(s.stage1_symbol, s.stage2_symbol, F(s.backend_centered_code),
                     s.stage1_dither_symbol, s.stage2_dither_symbol,
                     k[4:]+k[:4], data_q3=rounded).output for s in samples]
    return sum((z-t)**2 for z, t in zip(values, targets))/len(values)


class CoupledStationarityTests(unittest.TestCase):
    def test_eight_correlation_root_with_zero_leakage_is_not_stationary(self):
        samples = tuple(Sample(0, 0, 64*d1+16*d2+4, d1, d2)
                        for d1, d2 in product((-1, 1), repeat=2))
        mean = analyze_window_mean(samples, (F(1),)*8)
        m = coupled_moments(mean, (2048,)*4, (2048,)*4)
        self.assertTrue(m.output_derivative_regular and m.correlation_derivative_regular)
        self.assertEqual(m.correlations, (0,)*8)
        self.assertEqual(m.target_leakage, (0,)*8)
        self.assertEqual(m.output_cross_moment, (0, 8, 8, 0, 16, 0, 0, 0))
        self.assertEqual(m.mse, 16)
        r, extended = instrument_span_ranks(m)
        self.assertGreater(extended, r)
        h = (F(0),)*4+(F(-1, 1024),)+(F(0),)*3
        end = tuple(a+b for a, b in zip(mean.coefficients, h))
        self.assertEqual(direct(samples, end, (2048,)*4)-m.mse, F(-1791, 65536))
        # A continuous improvement can lie entirely on an integer plateau.
        for s in samples:
            z = readout(0, 0, F(s.backend_centered_code), s.stage1_dither_symbol,
                        s.stage2_dither_symbol, end[4:]+end[:4], data_q3=True).output
            self.assertEqual(nearest_even(z), 2052)

    def test_digital_stationary_point_has_negative_curvature(self):
        samples = tuple(Sample(0, q2, be, -1, -1) for q2, be in ((0,16),(0,-8),(1,16),(1,-8)))
        mean = analyze_window_mean(samples, (F(1),)*8)
        targets = (2060, 1880, 2260, 2296)
        m = coupled_moments(mean, (2048,)*4, targets)
        self.assertEqual(m.output_cross_moment, (0,)*8)
        self.assertTrue(m.output_derivative_regular)
        direction = (1,0,0,0,0,-1,0,0)
        curvature = sum(F(direction[i])*m.half_loss_hessian[i][j]*direction[j]
                        for i in range(8) for j in range(8))
        self.assertEqual(curvature, -80)
        self.assertEqual(m.residual_curvature[0][4:6], (-144, 144))
        h = tuple(F(x,16) for x in direction)
        change = cascade_loss_change(mean, h, m.errors)
        self.assertEqual(change.mse_difference, F(-1211,4096))
        end = tuple(a+b for a,b in zip(mean.coefficients,h))
        self.assertEqual(direct(samples,end,targets)-m.mse, change.mse_difference)

    def test_protected_correlation_polynomial_for_joint_changes(self):
        samples = (Sample(0,0,79,1,1), Sample(0,0,-49,-1,-1), Sample(0,1,13,-1,-1))
        k = (F(1),)*8
        mean = analyze_window_mean(samples,k)
        m = coupled_moments(mean,(2048,)*3,(2047,2050,2180))
        self.assertTrue(certify_mean_cell(mean,F(1,4096)).all_masks_and_domains_stable)
        self.assertEqual(m.correlations,mean.mean_products)
        self.assertEqual(m.correlation_jacobian,mean.fixed_mask_jacobian)
        for signs in product((-1,1),repeat=8):
            h = tuple(F(x,4096) for x in signs)
            end = analyze_window_mean(samples,tuple(a+b for a,b in zip(k,h)))
            self.assertEqual(tuple(b-a for a,b in zip(m.correlations,end.mean_products)),
                             correlation_polynomial_change(m,h))
            change = cascade_loss_change(mean,h,m.errors)
            quadratic = 2*sum(g*x for g,x in zip(m.output_cross_moment,h))+sum(
                h[i]*m.half_loss_hessian[i][j]*h[j] for i in range(8) for j in range(8))
            self.assertEqual(change.mse_difference,quadratic+change.linear_bilinear_cross+change.bilinear_square)

    def test_zero_residual_positive_control_and_instrument_decomposition(self):
        samples = (Sample(0,0,17,1,-1),Sample(0,1,-7,-1,-1))
        mean = analyze_window_mean(samples,(F(1),)*8)
        targets = tuple(2048+r.local1 for r in mean.rows)
        m = coupled_moments(mean,(2048,)*2,targets,learning_weights=(1,0))
        self.assertEqual(m.output_cross_moment,(0,)*8)
        self.assertEqual(m.residual_curvature,((F(0),)*8,)*8)
        self.assertEqual(m.half_loss_hessian,m.gram)
        self.assertEqual(m.correlations,m.target_leakage)
        self.assertEqual(m.instrument_residual,(0,)*8)
        self.assertEqual(m.instruments[1],(0,)*8)

    def test_target_change_is_invisible_to_digital_correlations(self):
        samples = (Sample(0,0,17,1,-1),Sample(0,1,-7,-1,-1))
        mean = analyze_window_mean(samples,(F(1),)*8)
        a = coupled_moments(mean,(2048,)*2,(2048,2048),learning_weights=(1,0))
        b = coupled_moments(mean,(2048,)*2,(2048,2049),learning_weights=(1,0))
        self.assertEqual(a.correlations,b.correlations)
        self.assertEqual(a.correlation_jacobian,b.correlation_jacobian)
        self.assertEqual(a.instruments,b.instruments)
        self.assertEqual(a.target_leakage,b.target_leakage)
        self.assertEqual(tuple(x-y for x,y in zip(a.output_cross_moment,b.output_cross_moment)),
                         tuple(j/2 for j in a.output_jacobians[1]))

    def test_boundaries_are_polynomial_values_without_derivative_claim(self):
        mean = analyze_window_mean((Sample(0,1,16,-1,1),),(F(1),)*8)
        m = coupled_moments(mean,(2048,),(2048,))
        self.assertFalse(m.output_derivative_regular)
        self.assertFalse(m.correlation_derivative_regular)
        self.assertEqual(m.correlations,mean.mean_products)

    def test_invalid_target_types_and_uncovered_law_are_rejected(self):
        mean = analyze_window_mean((Sample(0,0,17,1,-1),Sample(0,1,-7,-1,-1)),(F(1),)*8)
        with self.assertRaises(TypeError):
            coupled_moments(mean,(2048,2048),(2048.0,2048))
        with self.assertRaises(ValueError):
            coupled_moments(mean,(2048,2048),(2048,2048),learning_weights=(1,0),evaluation_weights=(0,1))
        with self.assertRaises(ValueError):
            coupled_moments(mean,(2048,),(2048,))


if __name__ == '__main__':
    unittest.main()
