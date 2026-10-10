"""Window timing, exact products, aliasing and once-per-window arithmetic."""

from dataclasses import replace
import unittest

from adc_research.calibration.fixed_adaptive_two_stage import cascade_from_fixed_state, correct_and_update_fixed
from adc_research.calibration.fixed_four_lane_window import (
    FixedFourLaneWindowConfig, FourLaneConversion, correct_fixed_four_lane_window,
)
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState, update_fixed
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.observation import DigitalCalibrationSample
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial


class FixedFourLaneWindowTests(unittest.TestCase):
    def setUp(self):
        self.config = _config()
        self.initial = _initial(self.config)

    def rows(self, period=30, start=0, order=(0, 1, 2, 3)):
        return tuple(FourLaneConversion(start+n, order[(start+n) % 4],
                     DigitalCalibrationSample(0, 0, 64*d1+16*d2+8, d1, d2))
                     for n in range(4*period)
                     for d1, d2 in [((-1 if n % 2 == 0 else 1), (1 if n < 2*period else -1))])

    def test_frozen_scores_and_next_window_activation(self):
        rows = self.rows()
        full = correct_fixed_four_lane_window(rows, self.initial, FixedFourLaneWindowConfig(self.config))
        point = correct_fixed_four_lane_window(rows, self.initial,
                                              FixedFourLaneWindowConfig(self.config, selection="point_products"))
        self.assertEqual(full.calibrations, point.calibrations)
        frozen = cascade_from_fixed_state(self.config.cascade, self.initial,
                                           self.config.stage1_lms, self.config.stage2_lms)
        self.assertEqual(full.calibrations, tuple(correct_two_stage_fixed_observed(r.sample, frozen) for r in rows))
        next_point = correct_fixed_four_lane_window(self.rows(start=120), point.state,
                                                    FixedFourLaneWindowConfig(self.config, selection="point_products"))
        self.assertNotEqual(point.calibrations, next_point.calibrations)

    def test_full_zero_gradient_but_point_alias_changes_state(self):
        full = correct_fixed_four_lane_window(self.rows(), self.initial, FixedFourLaneWindowConfig(self.config))
        point = correct_fixed_four_lane_window(self.rows(), self.initial,
                                              FixedFourLaneWindowConfig(self.config, selection="point_products"))
        self.assertEqual(full.stage2_update.selected_product_sums[0], 0)
        self.assertEqual(full.stage2_update.requested_deltas[0], 0)
        self.assertEqual(point.stage2_update.selected_product_sums[0], 32768)
        self.assertEqual(point.stage2_update.product_multiplier, 30)
        self.assertEqual(point.stage2_update.requested_deltas[0], -3932)
        self.assertEqual(point.selected_conversion_ids, (0, 1, 2, 3))
        self.assertEqual(full.state.stage2.sample_count, 120)
        self.assertEqual(point.state.stage2.sample_count, 120)
        self.assertEqual(point.stage2_update.selected_gate_counts[0], 4)

    def test_lane_sum_and_permutation_preserve_shared_update(self):
        order = (2, 0, 3, 1)
        base = correct_fixed_four_lane_window(self.rows(3), self.initial,
                                             FixedFourLaneWindowConfig(self.config, lane_period=3))
        permuted = correct_fixed_four_lane_window(self.rows(3, order=order), self.initial,
                    FixedFourLaneWindowConfig(self.config, lane_period=3, lane_order=order))
        self.assertEqual(base.state, permuted.state)
        for update in (base.stage1_update, base.stage2_update):
            self.assertEqual(update.selected_product_sums,
                             tuple(sum(bank[i] for bank in update.lane_product_sums) for i in range(4)))

    def test_rounding_once_is_distinct_from_summing_rounded_updates(self):
        rows = tuple(FourLaneConversion(n, n % 4, DigitalCalibrationSample(0, 0, 17, 1, 1)) for n in range(8))
        result = correct_fixed_four_lane_window(rows, self.initial,
                                               FixedFourLaneWindowConfig(self.config, lane_period=2))
        one = update_fixed(self.initial.stage2, dither_code_scaled=128, corrected_output_scaled=8,
                            config=self.config.stage2_lms)
        self.assertEqual(8*one.requested_accumulator_deltas[0], -32)
        self.assertEqual(result.stage2_update.requested_deltas[0], -33)

    def test_equality_gate_and_full_length_normalization(self):
        rows = tuple(FourLaneConversion(n, n % 4,
                     DigitalCalibrationSample(0, 0, 48 if n == 0 else 16, 1, 1)) for n in range(8))
        result = correct_fixed_four_lane_window(rows, self.initial,
                                               FixedFourLaneWindowConfig(self.config, lane_period=2))
        self.assertEqual(result.stage2_learning_outputs_scaled[0], 256)
        self.assertEqual(result.stage2_update.selected_gate_counts[1], 1)
        self.assertEqual(result.stage2_update.selected_product_sums[1], 128*256)
        self.assertEqual(result.stage2_update.requested_deltas[1], -393)

    def test_single_commit_saturates_at_declared_accumulator_bounds(self):
        maximum = self.config.stage2_lms.maximum_accumulator_code
        bank = replace(self.initial.stage2, accumulator_codes=(maximum-1,)*4)
        state = replace(self.initial, stage2=bank)
        rows = tuple(FourLaneConversion(n, n % 4, DigitalCalibrationSample(0, 0, 0, 1, 1)) for n in range(8))
        result = correct_fixed_four_lane_window(rows, state,
                                               FixedFourLaneWindowConfig(self.config, lane_period=2))
        self.assertGreater(result.stage2_update.requested_deltas[0], 1)
        self.assertEqual(result.stage2_update.applied_deltas[0], 1)
        self.assertEqual(result.state.stage2.accumulator_codes[0], maximum)
        self.assertEqual(result.state.stage2.nonzero_update_counts[0], 1)

    def test_missing_reordered_or_misaligned_rows_are_rejected(self):
        cfg = FixedFourLaneWindowConfig(self.config, lane_period=2)
        rows = self.rows(2)
        with self.assertRaises(ValueError):
            correct_fixed_four_lane_window(rows[:-1], self.initial, cfg)
        for changed in ((rows[1], rows[0], *rows[2:]),
                        (replace(rows[0], lane=3), *rows[1:]), self.rows(2, start=4)):
            with self.assertRaises(ValueError):
                correct_fixed_four_lane_window(changed, self.initial, cfg)
        with self.assertRaises(TypeError):
            FourLaneConversion(0, 0, object())
        with self.assertRaises(ValueError):
            FixedFourLaneWindowConfig(self.config, point_phase=30)
        with self.assertRaises(ValueError):
            FixedFourLaneWindowConfig(self.config, lane_order=(0, 1, 1, 3))

    def test_overrange_state_and_unequal_bank_epochs_rejected(self):
        cfg = FixedFourLaneWindowConfig(self.config, lane_period=2)
        bad = replace(self.initial.stage2, accumulator_codes=(self.config.stage2_lms.maximum_accumulator_code+1,)*4)
        with self.assertRaises(ValueError):
            correct_fixed_four_lane_window(self.rows(2), replace(self.initial, stage2=bad), cfg)
        with self.assertRaises(ValueError):
            correct_fixed_four_lane_window(self.rows(2),
                replace(self.initial, stage2=replace(self.initial.stage2, sample_count=8)), cfg)

    def test_redundant_flash_branch_preserves_final_code_but_changes_learning_gate(self):
        # Nominal stage-2 main input 63/512, d2=+1. Choosing q2=0 or 1
        # changes the backend by -128, preserving the reconstructed code.
        lower = correct_and_update_fixed(DigitalCalibrationSample(0, 0, 79, 1, 1), self.initial, self.config)
        upper = correct_and_update_fixed(DigitalCalibrationSample(0, 1, -49, 1, 1), self.initial, self.config)
        self.assertEqual(lower.calibration.unclipped_output_scaled, 2047*8)
        self.assertEqual(upper.calibration.unclipped_output_scaled, 2047*8)
        self.assertEqual(lower.stage2_local_learning_output_scaled, 504)
        self.assertEqual(upper.stage2_local_learning_output_scaled, -520)
        self.assertFalse(lower.stage2_update.gate_mask[2])
        self.assertTrue(upper.stage2_update.gate_mask[2])


if __name__ == "__main__":
    unittest.main()
