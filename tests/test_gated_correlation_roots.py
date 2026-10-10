"""Hand roots, gate equality, and sign jumps without an intermediate zero."""

from fractions import Fraction as F
import unittest

from adc_research.theory.gated_correlation_roots import (
    WeightedStageRow as Row, scan_two_slope_roots, stage_basis, stage_correlations,
)


class GatedCorrelationRootTests(unittest.TestCase):
    def test_regular_root_has_hand_computed_coefficients(self):
        rows = (Row(F(-5, 2), F(-1)), Row(F(-1), F(-1)), Row(F(-1), F(1)))
        scan = scan_two_slope_roots(rows, 1)
        self.assertTrue(scan.complete_on_declared_domain)
        self.assertEqual(len(scan.roots), 1)
        root = scan.roots[0]
        self.assertEqual(root.coefficients, (F(1), F(3, 2), F(1), F(1)))
        self.assertFalse(root.at_gate_boundary)
        self.assertEqual(stage_correlations(rows, root.coefficients, 1)[:2], (F(0), F(0)))

    def test_boundary_root_uses_greater_or_equal_gate(self):
        rows = (Row(F(-3), F(-1)), Row(F(-5, 2), F(-1)), Row(F(-5, 2), F(1)))
        scan = scan_two_slope_roots(rows, 1)
        root = scan.roots[0]
        self.assertTrue(root.at_gate_boundary)
        self.assertEqual(root.coefficients, (F(3, 2), F(1, 2), F(1), F(1)))
        self.assertEqual(stage_correlations(rows, root.coefficients, 1)[:2], (F(0), F(0)))
        # The middle row's y=-3/2 must be included at the threshold 3/2.
        self.assertEqual(next(b.value for b in scan.boundaries if b.parameter == F(1, 2)), 0)

    def test_two_sign_jumps_do_not_create_spurious_roots(self):
        rows = (Row(F(-2), F(-1), 4), Row(F(3, 2), F(-1), 2), Row(F(0), F(1), 3),
                Row(F(-5, 2), F(-1), 2), Row(F(-3, 2), F(-1)))
        scan = scan_two_slope_roots(rows, 1)
        self.assertEqual(scan.status, "no_roots")
        self.assertEqual(scan.roots, ())
        jumps = [b for b in scan.boundaries if b.left_limit*b.right_limit < 0]
        self.assertEqual([b.parameter for b in jumps], [F(1), F(12, 11)])
        self.assertEqual((jumps[0].left_limit, jumps[0].value, jumps[0].right_limit),
                         (F(-1, 6), F(1, 5), F(1, 5)))
        for boundary in scan.boundaries:
            k = tuple(p*boundary.parameter+q for p, q in zip(
                scan.coefficient_line_slopes, scan.coefficient_line_intercepts))+(F(1),)*2
            self.assertEqual(stage_correlations(rows, k, 1)[:2], (F(0), boundary.value))
        for cell in scan.cells:
            for t in ((2*cell.low+cell.high)/3, (cell.low+2*cell.high)/3):
                k = tuple(p*t+q for p, q in zip(scan.coefficient_line_slopes,
                                               scan.coefficient_line_intercepts))+(F(1),)*2
                self.assertEqual(stage_correlations(rows, k, 1)[:2],
                                 (F(0), cell.correlation_slope*t+cell.correlation_intercept))

    def test_zero_intervals_are_not_reported_as_unique_roots(self):
        rows = (Row(F(1), F(1)), Row(F(-1), F(-1)))
        scan = scan_two_slope_roots(rows, 1)
        self.assertEqual(scan.status, "zero_intervals_present")
        self.assertEqual(scan.zero_intervals, ((F(0), F(2)),))
        self.assertEqual(scan.coefficient_line_intercepts, (F(1), F(0)))

    def test_alternate_elimination_pivot_and_zero_interval(self):
        scan = scan_two_slope_roots((Row(F(2), F(1, 2)), Row(F(1), F(-1, 2))), 1)
        self.assertEqual(scan.coefficient_line_slopes, (F(1), F(0)))
        self.assertEqual(scan.coefficient_line_intercepts, (F(0), F(1)))
        self.assertEqual(scan.zero_intervals, ((F(0), F(2)),))

    def test_primary_no_zero_and_underdetermined_problem_are_distinct(self):
        missing = scan_two_slope_roots((Row(F(0), F(1)),), 1)
        self.assertEqual(missing.status, "primary_has_no_zero")
        self.assertTrue(missing.complete_on_declared_domain)
        unspecified = scan_two_slope_roots((Row(F(-4), F(-1)), Row(F(-2), F(1))), 1)
        self.assertEqual(unspecified.status, "primary_identically_zero")
        self.assertFalse(unspecified.complete_on_declared_domain)

    def test_weighting_matches_explicit_repetition(self):
        rows = (Row(F(-5, 2), F(-1), 3), Row(F(-1), F(-1), 2), Row(F(-1), F(1), 2))
        expanded = tuple(Row(row.raw, row.dither) for row in rows for _ in range(row.count))
        weighted, repeated = scan_two_slope_roots(rows, 1), scan_two_slope_roots(expanded, 1)
        self.assertEqual(weighted.roots, repeated.roots)
        self.assertEqual(weighted.cells, repeated.cells)
        self.assertEqual([b.value for b in weighted.boundaries], [b.value for b in repeated.boundaries])

    def test_domain_and_exact_arithmetic_requirements(self):
        self.assertEqual(stage_basis(F(-4), F(1)), (F(-1),)*4)
        with self.assertRaises(ValueError):
            stage_basis(F(4), F(1))
        with self.assertRaises(TypeError):
            stage_basis(0.1, F(1))
        with self.assertRaises(ValueError):
            Row(F(0), F(0))
        with self.assertRaises(ValueError):
            Row(F(0), F(1), True)
        with self.assertRaises(TypeError):
            scan_two_slope_roots((), 1)
        with self.assertRaises(ValueError):
            scan_two_slope_roots((Row(F(0), F(1)),), 1, (F(2), F(1)))


if __name__ == "__main__":
    unittest.main()
