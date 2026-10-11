"""Exact controls distinguish tangents, straight lines, curves and integer codes."""
from fractions import Fraction as F
from itertools import product
import unittest

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.correlation_preserving_directions import (
    correlation_geometry, direction_polynomial, exact_linear_solution, exact_nullspace,
    mixed_direction_terms,
)
from adc_research.theory.static_fixed_contract import export, nearest_even, readout
from adc_research.theory.target_moment_bounds import loss_change_interval
from adc_research.theory.window_mean_map import analyze_window_mean, certify_mean_cell


def controls(offset=4):
    return tuple(Sample(0, 0, 64*d1+16*d2+offset, d1, d2)
                 for d1, d2 in product((-1, 1), repeat=2))


def outputs(samples, k, q3=False):
    return tuple(readout(s.stage1_symbol, s.stage2_symbol, F(s.backend_centered_code),
                        s.stage1_dither_symbol, s.stage2_dither_symbol,
                        k[4:]+k[:4], data_q3=q3).output for s in samples)


class CorrelationPreservingTests(unittest.TestCase):
    def test_exact_nullspace_and_linear_jet_solver(self):
        matrix = ((1, 2, 3), (2, 4, 6), (0, 0, 0))
        self.assertEqual(exact_nullspace(matrix), ((-2, 1, 0), (-3, 0, 1)))
        self.assertEqual(exact_linear_solution(matrix, (5, 10, 0)), (5, 0, 0))
        self.assertIsNone(exact_linear_solution(matrix, (5, 11, 0)))
        self.assertEqual(exact_nullspace(((0, 0),)), ((1, 0), (0, 1)))
        self.assertEqual(exact_nullspace(((1, 0), (0, 1))), ())

    def test_neutral_tangent_is_not_correlation_preserving_straight_line(self):
        samples, k = controls(), (F(1),)*8
        result = analyze_window_mean(samples, k)
        geo = correlation_geometry(result)
        v = (F(1), F(0), F(0), F(0), F(-1, 2), F(0), F(0), F(0))
        direction = direction_polynomial(result, geo, v)
        self.assertEqual(geo.correlations, (0,)*8)
        self.assertTrue(geo.correlation_derivative_regular)
        self.assertTrue(direction.first_order_neutral)
        self.assertFalse(direction.straight_line_preserves_correlations)
        self.assertEqual(direction.quadratic_correlations, (0,)*4+(-1024, 0, 0, 0))
        self.assertEqual(direction.linear_outputs, (-2,)*4)
        self.assertIsNotNone(direction.second_jet_acceleration)
        for u in (F(-1, 512), F(1, 512)):
            h = tuple(u*x for x in v)
            self.assertTrue(certify_mean_cell(result, max(map(abs, h))).all_masks_and_domains_stable)
            end = analyze_window_mean(samples, tuple(a+b for a, b in zip(k, h)))
            self.assertEqual(end.mean_products, (0,)*4+(-1024*u*u, 0, 0, 0))
            self.assertEqual(outputs(samples, end.coefficients), tuple(
                2052+u*l+u*u*b for l, b in zip(direction.linear_outputs, direction.quadratic_outputs)))

    def test_actual_rational_root_curve_changes_output(self):
        samples = controls()
        for u in (F(-1, 64), F(0), F(1, 64), F(1, 512)):
            k = (1+u, F(1), F(1), F(1), 1/(1+u/2), F(1), F(1), F(1))
            result = analyze_window_mean(samples, k)
            self.assertEqual(result.mean_products, (0,)*8)
            self.assertTrue(result.open_cell_regular)
            self.assertEqual(outputs(samples, k), (2048+4/(1+u/2),)*4)

    def test_root_curve_loss_needs_target_and_ignores_no_spectrum_claim(self):
        samples, u = controls(), F(1, 64)
        old = (F(1),)*8
        new = (1+u, F(1), F(1), F(1), 1/(1+u/2), F(1), F(1), F(1))
        a, b = outputs(samples, old), outputs(samples, new)
        self.assertLess(loss_change_interval(a, b, (2048,)*4, (2048,)*4).center, 0)
        self.assertGreater(loss_change_interval(a, b, (2060,)*4, (2060,)*4).center, 0)
        uncertain = loss_change_interval(a, b, (2048,)*4, (2060,)*4, groups=(0,)*4)
        self.assertLess(uncertain.lower, 0)
        self.assertGreater(uncertain.upper, 0)

    def test_genuine_correlation_preserving_line_changes_unselected_output(self):
        samples = controls()+(Sample(0, 1, 17, 1, -1),)
        result = analyze_window_mean(samples, (F(1),)*8)
        geo = correlation_geometry(result, (1, 1, 1, 1, 0))
        v = (0, 0, 0, 0, 0, 1, 0, 0)
        direction = direction_polynomial(result, geo, v)
        self.assertTrue(direction.straight_line_preserves_correlations)
        self.assertEqual(direction.linear_outputs, (0, 0, 0, 0, 33))
        self.assertFalse(direction.straight_line_preserves_output)
        u = F(1, 32)
        end = tuple(F(1)+u*x for x in v)
        self.assertEqual(correlation_geometry(analyze_window_mean(samples, end), (1, 1, 1, 1, 0)).correlations, (0,)*8)
        self.assertEqual(tuple(nearest_even(x) for x in outputs(samples, end, True)), (2052,)*4+(2146,))
        self.assertEqual(tuple(nearest_even(x) for x in outputs(samples, (F(1),)*8, True)), (2052,)*4+(2145,))

    def test_curve_export_q3_correlation_changes_but_integer_plateau_stays(self):
        samples, u = controls(), F(1, 512)
        curve = (1+u, F(1), F(1), F(1), 1/(1+u/2), F(1), F(1), F(1))
        acc = tuple(nearest_even(x*(1 << 22)) for x in curve[4:]+curve[:4])
        bank = tuple(F(x, 1024) for x in export(acc))
        readings = [readout(0, 0, F(s.backend_centered_code), s.stage1_dither_symbol,
                           s.stage2_dither_symbol, bank, data_q3=True) for s in samples]
        front_c = sum(64*s.stage1_dither_symbol*r.y1 for s, r in zip(samples, readings))/4
        self.assertEqual(front_c, -4)
        self.assertEqual(tuple(nearest_even(r.output) for r in readings), (2052,)*4)
        self.assertNotEqual(bank, (F(1),)*8)

    def test_singular_block_polynomial_has_nonliftable_kernel_direction(self):
        # Abstract block-triangular bilinear control C=(x, y+z, yz).
        # At zero ker M contains (0,1,-1), but yz=-u^2 cannot be corrected by M*a.
        m = ((1, 0, 0), (0, 1, 1), (0, 0, 0))
        self.assertEqual(exact_nullspace(m), ((0, -1, 1),))
        self.assertIsNone(exact_linear_solution(m, (0, 0, 2)))
        for u in (F(-1, 8), F(1, 8)):
            x, y, z = F(0), u, -u
            self.assertEqual((x, y+z, y*z), (0, 0, -u*u))

    def test_invisible_direction_is_actual_output_preserving_line(self):
        result = analyze_window_mean(controls(), (F(1),)*8)
        direction = direction_polynomial(result, correlation_geometry(result), (0, 0, 0, 1, 0, 0, 0, 0))
        self.assertTrue(direction.straight_line_preserves_correlations)
        self.assertTrue(direction.straight_line_preserves_output)

    def test_basis_diagonal_checks_do_not_replace_mixed_terms(self):
        result = analyze_window_mean(controls(), (F(1),)*8)
        geo = correlation_geometry(result)
        v, w = (1, 0, 0, 0, 0, 0, 0, 0), (0, 0, 0, 0, 1, 0, 0, 0)
        dv, dw = direction_polynomial(result, geo, v), direction_polynomial(result, geo, w)
        self.assertEqual(dv.quadratic_correlations, (0,)*8)
        self.assertEqual(dw.quadratic_correlations, (0,)*8)
        c, z = mixed_direction_terms(result, geo, v, w)
        self.assertEqual(c, (0,)*4+(2048, 0, 0, 0))
        self.assertEqual(z, (-32, -32, 32, 32))
        ds = direction_polynomial(result, geo, tuple(a+b for a, b in zip(v, w)))
        self.assertEqual(ds.quadratic_correlations, c)
        self.assertEqual(ds.quadratic_outputs, z)

    def test_boundary_flags_and_invalid_inputs(self):
        result = analyze_window_mean((Sample(0, 1, 16, -1, 1),), (F(1),)*8)
        geo = correlation_geometry(result)
        self.assertFalse(geo.output_derivative_regular)
        self.assertFalse(geo.correlation_derivative_regular)
        with self.assertRaises(ValueError):
            exact_nullspace(((1, 0), (0,)))
        with self.assertRaises(TypeError):
            exact_nullspace(((1.0,),))
        with self.assertRaises(ValueError):
            direction_polynomial(result, geo, (1, 0))


if __name__ == '__main__':
    unittest.main()
