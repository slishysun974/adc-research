from fractions import Fraction as F
from itertools import product
import unittest

from adc_research.theory.finite_observation_limits import observation_loss, reference_loss
from adc_research.theory.triangular_cascade_bounds import cascade_bound, weighted_contraction


class FiniteObservationLimitsTests(unittest.TestCase):
    def test_integer_information_optimum_by_complete_enumeration(self):
        observations = (0, 0, 1, 1)
        targets = (F(1,4), F(5,4), F(7,4), F(11,4))
        losses = []
        for a, b in product(range(4), repeat=2):
            result = observation_loss(observations, targets, (a,a,b,b), maximum=3)
            losses.append(result.actual_loss)
            self.assertTrue(result.fixed_mapping)
        self.assertEqual(min(losses), result.information_bound)
        self.assertEqual(result.target_variance, F(1,4))
        self.assertEqual(result.integer_penalty, F(1,16))

    def test_visible_state_can_beat_current_word_only_bound(self):
        result = observation_loss((0,0), (0,1), (0,1), maximum=1)
        self.assertEqual(result.actual_loss, 0)
        self.assertEqual(result.information_bound, F(1,2))
        self.assertEqual(result.target_output_covariance, F(1,4))
        self.assertFalse(result.fixed_mapping)
        refined = observation_loss(((0,0),(0,1)), (0,1), (0,1), maximum=1)
        self.assertEqual(refined.information_bound, 0)

    def test_real_target_and_integer_clipping_are_explicit(self):
        result = observation_loss((0,0), (-2,-1), (0,0), maximum=1)
        self.assertEqual(result.information_bound, F(5,2))
        self.assertEqual(result.integer_penalty, F(9,4))

    def test_reference_displacement_need_not_be_a_cost(self):
        base, power, cross, actual = reference_loss((0,2), (1,1), (0,2))
        self.assertEqual((base,power,cross,actual), (1,1,-2,0))

    def test_refinement_does_not_increase_finite_information_optimum(self):
        for y in product(range(3), repeat=4):
            coarse = observation_loss((0,0,0,0), (0,0,1,2), y, maximum=2)
            fine = observation_loss((0,0,1,1), (0,0,1,2), y, maximum=2)
            self.assertLessEqual(fine.information_bound, coarse.information_bound)

    def test_invalid_inputs(self):
        for args in (((),(),()), ((0,), (0,1), (0,)), ((0,), (0,), (F(1,2),))):
            with self.assertRaises(ValueError): observation_loss(*args)


class TriangularCascadeBoundsTests(unittest.TestCase):
    def test_full_sign_enumeration_is_bounded_and_attains_envelope(self):
        bound = cascade_bound(F(1,2), F(1,3), 2, F(1,8), F(1,9), 1, 2, 4)
        for signs in product((-1,1), repeat=8):
            front, rear = F(1), F(2)
            for m in range(4):
                front, rear = (front/2 + 2*rear + signs[2*m]*F(1,8),
                               rear/3 + signs[2*m+1]*F(1,9))
                self.assertLessEqual(abs(front), bound.front[m+1])
                self.assertLessEqual(abs(rear), bound.rear[m+1])
        self.assertEqual(front, bound.front[-1])
        self.assertEqual(rear, bound.rear[-1])

    def test_strong_coupling_allows_transient_growth_despite_stable_diagonals(self):
        bound = cascade_bound(F(1,2), F(1,2), 2, 0, 0, 0, 1, 8)
        self.assertEqual(bound.front[1], 2)
        self.assertEqual(bound.front[8], F(1,8))
        self.assertEqual(weighted_contraction(F(1,2), F(1,2), 2, 8), F(3,4))
        self.assertGreater(weighted_contraction(F(1,2), F(1,2), 2, 1), 1)

    def test_perturbation_floor_and_zero_coupling(self):
        bound = cascade_bound(F(1,2), F(1,4), 3, F(1,8), F(1,16), 0, 0, 6)
        self.assertEqual((bound.front_limit,bound.rear_limit), (F(3,4),F(1,12)))
        uncoupled = cascade_bound(0, 0, 0, F(1,8), F(1,16), 7, 8, 2)
        self.assertEqual(uncoupled.front[1:], (F(1,8),)*2)

    def test_no_bound_claim_for_unsupported_or_unstable_direction(self):
        for rho in (1, F(3,2), -1):
            with self.assertRaises(ValueError): cascade_bound(rho, F(1,2), 1, 0, 0, 0, 0, 3)
        with self.assertRaises(ValueError): cascade_bound(F(1,2), F(1,2), 1, 0, 0, 0, 0, -1)
