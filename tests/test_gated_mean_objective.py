"""Independent exact controls for selection and correlation/loss compatibility."""
from fractions import Fraction as F
import unittest

from adc_research.theory.gated_mean_objective import (
    affine_loss_change, gated_affine_moments, phase_selection_moments,
)
from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.window_mean_map import analyze_window_mean


class GatedMeanObjectiveTests(unittest.TestCase):
    def test_uniform_phase_mean_and_full_vector_covariance(self):
        result = phase_selection_moments(((1, 2), (3, 4), (5, -2), (7, 0)), phase_size=2)
        self.assertEqual(result.full_mean, (4, 1))
        self.assertEqual(result.selected_mean, result.full_mean)
        self.assertEqual(result.covariance, ((4, -4), (-4, 4)))
        self.assertEqual(result.bias, (0, 0))

    def test_biased_selector_is_not_fixed_by_mean_normalization(self):
        result = phase_selection_moments(((0,), (2,)), (F(3, 4), F(1, 4)), phase_size=1)
        self.assertEqual(result.full_mean, (1,))
        self.assertEqual(result.selected_mean, (F(1, 2),))
        self.assertEqual(result.bias, (F(-1, 2),))
        self.assertEqual(result.covariance, ((F(3, 4),),))

    def test_zero_target_instrument_does_not_make_root_minimize_mse(self):
        # Dimensionless static quadratic transfer at input +/-1; T=0.
        args = (((F(3, 2),), (F(-1, 2),)), (1, -1), ((True,), (True,)))
        root = gated_affine_moments(*args, (1,), (0, 0))
        optimum = gated_affine_moments(*args, (F(4, 5),), (0, 0))
        self.assertEqual(root.correlations, (0,))
        self.assertEqual(root.instrument_target, (0,))
        self.assertEqual(root.half_gradient, (F(1, 4),))
        self.assertEqual(optimum.half_gradient, (0,))
        self.assertEqual((root.mse, optimum.mse), (F(1, 4), F(1, 5)))
        self.assertEqual(affine_loss_change(root, (F(-1, 5),)), F(-1, 20))

    def test_null_learning_direction_can_have_output_energy(self):
        moments = gated_affine_moments(((1, 1), (-1, 1)), (1, -1),
            ((True, False), (True, False)), (1, 2), (1, 1))
        self.assertEqual(moments.instrument_matrix, ((1, 0), (0, 0)))
        self.assertEqual(moments.correlations, (0, 0))
        self.assertEqual(moments.gram, ((1, 0), (0, 1)))
        self.assertEqual(moments.half_gradient, (0, 1))
        self.assertEqual(affine_loss_change(moments, (0, -1)), -1)

    def test_learning_and_evaluation_laws_remain_distinct(self):
        moments = gated_affine_moments(((1,), (3,)), (1, -1), ((True,), (True,)),
            (1,), (0, 0), learning_weights=(1, 0), evaluation_weights=(0, 1))
        self.assertEqual(moments.correlations, (0,))
        self.assertEqual(moments.half_gradient, (12,))
        self.assertEqual(moments.mse, 16)

    def test_exact_digital_front_means_against_frozen_readout(self):
        samples = tuple(Sample(0, 0, be, d1, d2) for be, d1, d2 in ((79, 1, 1), (-49, -1, -1), (99, 1, -1)))
        mean = analyze_window_mean(samples, (F(1),)*8)
        targets = (F(2), F(-1), F(3))
        moments = gated_affine_moments([r.basis1 for r in mean.rows], [r.dither1 for r in mean.rows],
            [r.gates1 for r in mean.rows], mean.coefficients[4:], targets)
        self.assertEqual(moments.correlations, mean.mean_products[4:])
        self.assertEqual(moments.instrument_matrix, tuple(row[4:] for row in mean.fixed_mask_jacobian[4:]))
        self.assertEqual(moments.mse, sum((r.local1-t)**2 for r, t in zip(mean.rows, targets))/3)

    def test_random_phase_adds_nonnegative_fixed_back_continuous_cost(self):
        moments = gated_affine_moments(((1, 2), (3, -1)), (1, -1),
            ((True, True), (True, True)), (1, 1), (0, 1))
        phases = phase_selection_moments(((1, -1), (-1, 1)), phase_size=1)
        direct = sum(affine_loss_change(moments, row) for row in phases.phase_means)/2
        trace = sum(moments.gram[i][j]*phases.covariance[j][i] for i in range(2) for j in range(2))
        self.assertEqual(direct, affine_loss_change(moments, phases.selected_mean)+trace)
        self.assertEqual(trace, F(17, 2))

    def test_unrounded_mean_descent_requires_finite_step_bound(self):
        moments = gated_affine_moments(((1,),), (1,), ((True,),), (2,), (0,))
        self.assertEqual(affine_loss_change(moments, (-1,)), -1)
        self.assertEqual(affine_loss_change(moments, (-3,)), 3)

    def test_invalid_laws_and_shapes_are_rejected(self):
        with self.assertRaises(ValueError):
            phase_selection_moments(((1,), (2,)), (F(1, 2), F(1, 3)), phase_size=1)
        with self.assertRaises(TypeError):
            phase_selection_moments(((0.1,),), phase_size=1)
        with self.assertRaises(ValueError):
            gated_affine_moments(((1,),), (1,), ((True,),), (1,), (0,), learning_weights=(0,))
        with self.assertRaises(ValueError):
            gated_affine_moments(((1,),), (1,), ((1,),), (1,), (0,))


if __name__ == '__main__':
    unittest.main()
