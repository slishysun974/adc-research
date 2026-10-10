from fractions import Fraction as F
import unittest

from adc_research.theory.paired_dither_conditions import (
    PairedDitherObservation as Pair, analyze_pair_equations, pair_constraint_components,
)
from adc_research.evaluation.paired_target_diagnostics import decompose_pair_targets


class PairedDitherConditionsTests(unittest.TestCase):
    def test_equal_target_shared_gate_cancels_signal_but_not_error(self):
        result = decompose_pair_targets(F(100), F(100), F(104), F(102), F(64))
        self.assertEqual(result['target_signal_contribution'], 0)
        self.assertEqual(result['error_contribution'], 64)
        self.assertEqual(result['learning_contribution'], 64)

    def test_unequal_gates_restore_signal_despite_balanced_dither(self):
        result = decompose_pair_targets(F(100), F(100), F(100), F(100), F(64), True, False)
        self.assertEqual(result['target_signal_contribution'], 3200)
        self.assertEqual(result['gate_mismatch_contribution'], 3200)

    def test_target_mismatch_is_not_fixed_by_a_shared_gate(self):
        result = decompose_pair_targets(F(101), F(99), F(101), F(99), F(64))
        self.assertEqual(result['target_signal_contribution'], 64)
        self.assertEqual(result['target_mismatch_contribution'], 64)
        self.assertEqual(result['signal_leakage_bound'], 64)

    def test_two_opposite_contrasts_cancel_moment_but_not_squared_loss(self):
        pairs = (Pair(F(130), F(0), F(64)), Pair(F(126), F(0), F(64)))
        result = analyze_pair_equations(pairs)
        self.assertEqual(result['shared_gate_correlation'], 0)
        self.assertEqual(result['contrast_mse'], 4)

    def test_full_excitation_has_known_four_slope_solution(self):
        # Four pairs stay inside the four positive PWL segments.
        pairs = tuple(Pair(F(center+8), F(center-8), F(8)) for center in (64, 192, 320, 448))
        result = analyze_pair_equations(pairs, (F(9, 10), F(11, 10), F(6, 5), F(4, 5)))
        self.assertEqual(result['basis_difference_rank'], 4)
        self.assertEqual(result['basis_difference_gram'], tuple(tuple(F(64)*int(i == j) for j in range(4)) for i in range(4)))
        self.assertEqual(result['contrast_least_squares_coefficients'], (F(1),)*4)
        self.assertEqual(result['minimum_contrast_mse'], 0)

    def test_inner_excitation_does_not_identify_outer_slopes(self):
        pairs = tuple(Pair(F(center+64), F(center-64), F(64)) for center in (-48, -16, 16, 48))
        a = analyze_pair_equations(pairs, (F(1), F(1), F(1), F(1)))
        b = analyze_pair_equations(pairs, (F(1), F(1, 2), F(3, 2), F(1, 4)))
        self.assertEqual(a['basis_difference_rank'], 1)
        self.assertEqual(a['contrast_mse'], b['contrast_mse'])
        self.assertIsNone(a['contrast_least_squares_coefficients'])

    def test_empty_common_selection_is_reported_as_rank_zero(self):
        result = analyze_pair_equations((Pair(F(64), F(-64), F(64)),), common_gates=(False,))
        self.assertEqual(result['basis_difference_rank'], 0)
        self.assertEqual(result['accepted_pairs'], 0)

    def test_finite_support_connectivity_is_not_just_the_gcd(self):
        result = pair_constraint_components(range(-2, 3), (4, 6))
        self.assertEqual(result['component_count'], 4)
        self.assertEqual(result['edge_count'], 1)
        self.assertEqual(result['edge_constraint_rank'], 1)

    def test_connected_error_graph_still_has_an_offset(self):
        result = pair_constraint_components(range(5), (1,))
        self.assertEqual(result['component_count'], 1)
        self.assertEqual(result['unanchored_error_dimensions'], 1)

    def test_mixed_target_gate_leakage_exact_triangle_bound(self):
        for gp, gm in ((True, False), (False, True), (True, True), (False, False)):
            result = decompose_pair_targets(F(103), F(-47), F(9), F(-11), F(64), gp, gm)
            self.assertLessEqual(abs(result['target_signal_contribution']), result['signal_leakage_bound'])

    def test_invalid_exact_pair_contract_is_rejected(self):
        with self.assertRaises(ValueError):
            Pair(F(0), F(0), F(0))
        with self.assertRaises(ValueError):
            Pair(0.0, F(0), F(64))
        with self.assertRaises(ValueError):
            Pair(F(0), F(0), F(64), True)


if __name__ == '__main__':
    unittest.main()
