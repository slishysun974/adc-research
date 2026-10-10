from dataclasses import replace
from fractions import Fraction as F
import unittest

from adc_research.calibration.fixed_filtered_window import (
    FilteredWindowState,FILTER_LIMITS,smooth_product,correct_filtered_window,
)
from adc_research.calibration.fixed_four_lane_window import (
    FourLaneConversion,FixedFourLaneWindowConfig,correct_fixed_four_lane_window,
)
from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.calibration.fixed_gated_lms import exported_coefficient_codes
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial


class FixedFilteredWindowTests(unittest.TestCase):
    def setUp(self):
        self.cfg = _config()
        self.config = FixedFourLaneWindowConfig(self.cfg,selection="point_products")
        self.rows = tuple(FourLaneConversion(n,n % 4,Sample(0,0,64,1,1)) for n in range(120))

    def test_first_filter_update_matches_quarter_step(self):
        filtered = correct_filtered_window(self.rows,FilteredWindowState(_initial(self.cfg)),self.config)
        slower = replace(self.cfg,stage1_lms=replace(self.cfg.stage1_lms,step_sizes=tuple(s/4 for s in self.cfg.stage1_lms.step_sizes)),
                         stage2_lms=replace(self.cfg.stage2_lms,step_sizes=tuple(s/4 for s in self.cfg.stage2_lms.step_sizes)))
        control = correct_fixed_four_lane_window(self.rows,_initial(slower),
            FixedFourLaneWindowConfig(slower,selection="point_products"))
        self.assertEqual(filtered.raw.calibrations,control.calibrations)
        self.assertEqual(filtered.state.calibration,control.state)

    def test_zero_products_decay_past_filter_and_can_keep_updating(self):
        rows = tuple(FourLaneConversion(n,n % 4,Sample(0,0,80,1,1)) for n in range(120))
        initial = FilteredWindowState(_initial(self.cfg),(4000,0,0,0),(0,0,0,0))
        result = correct_filtered_window(rows,initial,self.config)
        self.assertEqual(result.raw.stage1_update.selected_product_sums[0],0)
        self.assertEqual(result.state.stage1_filter_codes[0],3000)
        self.assertNotEqual(result.requested_deltas[0][0],0)

    def test_gate_counts_and_actual_update_counters_are_consistent(self):
        result = correct_filtered_window(self.rows,FilteredWindowState(_initial(self.cfg)),self.config)
        for bank,update,deltas in zip((result.state.calibration.stage1,result.state.calibration.stage2),
            (result.raw.stage1_update,result.raw.stage2_update),result.applied_deltas):
            self.assertEqual(bank.sample_count,120)
            self.assertEqual(bank.gate_counts,update.selected_gate_counts)
            self.assertEqual(bank.nonzero_update_counts,tuple(int(d != 0) for d in deltas))

    def test_same_current_codes_and_next_window_uses_filtered_bank(self):
        initial = _initial(self.cfg)
        baseline = correct_fixed_four_lane_window(self.rows,initial,self.config)
        filtered = correct_filtered_window(self.rows,FilteredWindowState(initial),self.config)
        self.assertEqual(baseline.calibrations,filtered.raw.calibrations)
        rows = tuple(FourLaneConversion(n,n % 4,Sample(0,0,64,1,1)) for n in range(120,240))
        following = correct_filtered_window(rows,filtered.state,self.config)
        self.assertEqual(following.raw.stage1_update.coefficient_codes_before,
                         exported_coefficient_codes(filtered.state.calibration.stage1,self.cfg.stage1_lms))
        self.assertEqual(following.state.calibration.stage1.sample_count,240)

    def test_constant_filter_rounding_error_bound_and_range(self):
        value = 0
        exact = F(0)
        for _ in range(100):
            value = smooth_product(value,7,100)
            exact = 3*exact/4+7
            self.assertLessEqual(abs(F(value)-exact),2)
        for bound in FILTER_LIMITS:
            self.assertEqual(smooth_product(bound,bound//4,bound),bound)
            self.assertEqual(smooth_product(-bound,-bound//4,bound),-bound)

    def test_rejects_noncontract_selection_and_invalid_states(self):
        with self.assertRaises(ValueError):
            correct_filtered_window(self.rows,FilteredWindowState(_initial(self.cfg)),FixedFourLaneWindowConfig(self.cfg))
        for previous,product in ((True,0),(FILTER_LIMITS[0]+1,0),(0,FILTER_LIMITS[0])):
            with self.assertRaises(ValueError):
                smooth_product(previous,product,FILTER_LIMITS[0])
        with self.assertRaises(ValueError):
            FilteredWindowState(_initial(self.cfg),[0]*4)


if __name__ == "__main__":
    unittest.main()
