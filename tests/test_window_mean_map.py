"""Analytic derivatives, exact finite changes and valid-margin boundaries."""

from dataclasses import replace
from fractions import Fraction as F
import itertools
import unittest

from adc_research.calibration.fixed_adaptive_two_stage import cascade_from_fixed_state
from adc_research.calibration.fixed_gated_lms import adaptive_lower_thresholds_scaled
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.window_mean_map import (
    MeanGeometry, analyze_window_mean, certify_mean_cell, certify_q3_mean_error, exact_matrix_rank,
    mean_update_infinity_bound, phase_product_means,
)
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial


class WindowMeanMapTests(unittest.TestCase):
    def setUp(self):
        self.slopes = (F(1),)*8
        self.samples = (Sample(0, 0, 79, 1, 1), Sample(0, 1, -49, 1, 1))

    def test_known_redundant_branches_have_different_local_learning(self):
        result = analyze_window_mean(self.samples, self.slopes)
        self.assertEqual([r.local2 for r in result.rows], [F(63), F(-65)])
        self.assertEqual([r.local1 for r in result.rows], [F(-1), F(-1)])
        self.assertEqual([r.gates2[2] for r in result.rows], [False, True])
        self.assertEqual(result.mean_products[2], F(-520))

    def test_analytic_block_structure_and_exact_derivative_entries(self):
        result = analyze_window_mean((self.samples[1],), self.slopes)
        matrix = result.fixed_mask_jacobian
        self.assertTrue(all(matrix[i][j] == 0 for i in range(4) for j in range(4, 8)))
        self.assertEqual(matrix[0][:4], (F(-512), F(-272), F(0), F(0)))
        self.assertEqual(matrix[4][:4], (F(-2048), F(-1088), F(0), F(0)))
        self.assertEqual(matrix[4][4:], (F(4032), F(0), F(0), F(0)))

    def test_exact_bilinear_taylor_bound_at_all_eight_dimensional_corners(self):
        result = analyze_window_mean(self.samples, self.slopes)
        radius = F(1, 10000)
        certificate = certify_mean_cell(result, radius)
        self.assertTrue(result.open_cell_regular)
        self.assertTrue(certificate.all_masks_and_domains_stable)
        for signs in itertools.product((-1, 1), repeat=8):
            delta = tuple(sign*radius for sign in signs)
            changed = analyze_window_mean(self.samples, tuple(a+b for a, b in zip(self.slopes, delta)))
            for i, mean in enumerate(changed.mean_products):
                predicted = result.mean_products[i]+sum(
                    (a*b for a, b in zip(result.fixed_mask_jacobian[i], delta)), F(0))
                self.assertLessEqual(abs(mean-predicted), certificate.taylor_remainder_bounds[i])

    def test_gate_equality_is_not_claimed_as_an_open_linearization_cell(self):
        sample = Sample(0, 0, 80, 1, 1)  # y2=64 equals third gate threshold.
        result = analyze_window_mean((sample,), self.slopes)
        self.assertFalse(result.open_cell_regular)
        self.assertFalse(certify_mean_cell(result, F(1, 10000)).all_masks_and_domains_stable)
        down = analyze_window_mean((sample,), (F(9999, 10000),)*4+self.slopes[4:])
        up = analyze_window_mean((sample,), (F(10001, 10000),)*4+self.slopes[4:])
        self.assertFalse(down.rows[0].gates2[2])
        self.assertTrue(up.rows[0].gates2[2])

    def test_phase_averages_reproduce_full_mean_without_independence(self):
        samples = tuple(Sample(0, 0, 64*d1+16*d2+8, d1, d2)
                        for n in range(120) for d1, d2 in [(-1 if n % 2 == 0 else 1, 1 if n < 60 else -1)])
        result = analyze_window_mean(samples, self.slopes)
        phases = phase_product_means(result)
        self.assertEqual(tuple(sum((phase[i] for phase in phases), F(0))/30 for i in range(8)),
                         result.mean_products)
        self.assertEqual(result.mean_products[0], 0)
        self.assertEqual(phases[0][0], 128)
        self.assertEqual(phases[-1][0], -128)

    def test_rank_and_contraction_distinguish_inactive_directions(self):
        self.assertEqual(exact_matrix_rank(((F(1), F(2)), (F(2), F(4)))), 1)
        result = analyze_window_mean(self.samples, self.slopes)
        self.assertLess(exact_matrix_rank(result.fixed_mask_jacobian), 8)
        self.assertGreaterEqual(mean_update_infinity_bound(result, (F(1, 1000000),)*8), 1)

    def test_inactive_gu_gate_does_not_imply_no_digital_parameter_information(self):
        # Raw backend=100 uses the fourth PWL slope, while local y2=84
        # lies below its LMS threshold 96 after subtracting dither 16.
        result = analyze_window_mean((Sample(0, 0, 100, 1, 1),), self.slopes)
        self.assertEqual(result.rows[0].basis2[3], 4)
        self.assertFalse(result.rows[0].gates2[3])
        self.assertEqual(result.mean_products[3], 0)
        self.assertEqual(result.fixed_mask_jacobian[0][3], 64)
        changed = analyze_window_mean((Sample(0, 0, 100, 1, 1),),
                                      (F(1), F(1), F(1), F(1001, 1000), *self.slopes[4:]))
        self.assertNotEqual(result.mean_products[0], changed.mean_products[0])
        self.assertEqual(changed.mean_products[3], 0)

    def test_q3_error_budget_and_margin_gate_protection(self):
        cfg = _config()
        codes2 = (1025, 1073, 1101, 1008)
        codes1 = (1042, 1066, 1010, 1024)
        initial = _initial(cfg)
        state = replace(initial, stage2=replace(initial.stage2, accumulator_codes=tuple(x << 12 for x in codes2)),
                        stage1=replace(initial.stage1, accumulator_codes=tuple(x << 12 for x in codes1)))
        dynamic = cascade_from_fixed_state(cfg.cascade, state, cfg.stage1_lms, cfg.stage2_lms)
        samples = tuple(Sample(0, q2, backend, d1, d2) for q2 in (-1, 0, 1)
                        for backend in range(-128, 128, 17) for d1, d2 in itertools.product((-1, 1), repeat=2))
        slopes = tuple(F(x, 1024) for x in (*codes2, *codes1))
        result = analyze_window_mean(samples, slopes)
        mean_certificate = certify_q3_mean_error(result)
        actual_sums = [F(0)]*8
        errors = (F(1, 8), (1+max(slopes[4:]))/8)
        thresholds = (adaptive_lower_thresholds_scaled(codes2, cfg.stage2_lms),
                      adaptive_lower_thresholds_scaled(codes1, cfg.stage1_lms))
        for sample, row in zip(samples, result.rows):
            fixed = correct_two_stage_fixed_observed(sample, dynamic)
            actual = (F(fixed.stage2_pwl.corrected_code_scaled-fixed.stage2_dither_scaled, 8),
                      F(fixed.stage1_pwl.corrected_code_scaled-fixed.stage1_dither_scaled, 8))
            for bank, (value, exact, error, margins, gates) in enumerate(zip(
                actual, (row.local2, row.local1), errors,
                (row.gate_margins2, row.gate_margins1), (row.gates2, row.gates1))):
                self.assertLessEqual(abs(value-exact), error)
                for i, margin in enumerate(margins, 1):
                    if margin > error+F(1, 16):
                        self.assertEqual(abs(value) >= F(thresholds[bank][i], 8), gates[i])
                for i in range(4):
                    gate = i == 0 or abs(value) >= F(thresholds[bank][i], 8)
                    dither = (row.dither2, row.dither1)[bank]
                    actual_sums[bank*4+i] += dither*value*int(gate)/len(samples)
        for actual, mean, bound, preserved in zip(actual_sums, result.mean_products,
                mean_certificate.mean_product_error_bounds, mean_certificate.correlation_sign_preserved):
            self.assertLessEqual(abs(actual-mean), bound)
            if preserved:
                self.assertGreater(actual*mean, 0)

    def test_invalid_values_and_domains_are_rejected(self):
        with self.assertRaises(TypeError):
            analyze_window_mean(self.samples, (1.0,)*8)
        with self.assertRaises(ValueError):
            analyze_window_mean(self.samples, (F(0),)*8)
        with self.assertRaises(ValueError):
            analyze_window_mean((Sample(0, 0, 128, 1, 1),), self.slopes)
        with self.assertRaises(ValueError):
            MeanGeometry(stage1_width=128.0)
        result = analyze_window_mean(self.samples, self.slopes)
        with self.assertRaises(ValueError):
            certify_mean_cell(result, F(-1))
        with self.assertRaises(ValueError):
            phase_product_means(result)


if __name__ == "__main__":
    unittest.main()
