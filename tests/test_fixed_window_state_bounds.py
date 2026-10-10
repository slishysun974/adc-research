from dataclasses import replace
from fractions import Fraction as F
from itertools import product
import unittest

from adc_research.calibration.fixed_four_lane_window import FixedFourLaneWindowConfig,FourLaneConversion,correct_fixed_four_lane_window
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState
from adc_research.calibration.fixed_point import UnsignedFixedFormat,round_fraction
from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.evaluation.fixed_online_state_bounds import FixedStateBox,IntegerInterval
from adc_research.evaluation.fixed_window_state_bounds import bound_frozen_window
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial


def actual(samples,state,cfg):
    start=state.stage1.sample_count
    return correct_fixed_four_lane_window(tuple(FourLaneConversion(start+i,i%4,s) for i,s in enumerate(samples)),state,cfg)


def code(result):
    return min(max(round_fraction(result.unclipped_output_scaled,8,'nearest_even'),0),4095)


class FixedWindowStateBoundsTests(unittest.TestCase):
    def setUp(self):
        self.cfg=FixedFourLaneWindowConfig(_config(),lane_period=1)
        self.samples=(Sample(0,0,47,1,1),Sample(0,0,-47,-1,-1),Sample(0,1,-52,1,-1),Sample(0,0,32,-1,1))

    def test_point_box_matches_unchanged_four_lane_updater_all_fields(self):
        state=_initial(self.cfg.adaptive)
        bounds=bound_frozen_window(self.samples,FixedStateBox.from_state(state),self.cfg)
        result=actual(self.samples,state,self.cfg)
        self.assertEqual(tuple(i.lower for i in bounds.codes),tuple(code(r) for r in result.calibrations))
        self.assertEqual(bounds.next_state_box,FixedStateBox.from_state(result.state))
        self.assertEqual(tuple(i.lower for i in bounds.products_stage1),result.stage1_update.selected_product_sums)
        self.assertEqual(tuple(i.lower for i in bounds.products_stage2),result.stage2_update.selected_product_sums)
        self.assertEqual(tuple(i.lower for i in bounds.requested_stage1),result.stage1_update.requested_deltas)
        self.assertEqual(tuple(i.lower for i in bounds.requested_stage2),result.stage2_update.requested_deltas)
        self.assertTrue(bounds.all_exported_coefficients_singleton)

    def test_exhaustive_eighty_one_states_straddle_export_boundaries(self):
        state=_initial(self.cfg.adaptive)
        centers=(2**22+2048,)*2+(2**22,)*2
        state=replace(state,stage1=replace(state.stage1,accumulator_codes=centers),
                      stage2=replace(state.stage2,accumulator_codes=centers))
        intervals=tuple(IntegerInterval(z-1,z+1) if i<2 else IntegerInterval(z,z) for i,z in enumerate(centers))
        bounds=bound_frozen_window(self.samples,FixedStateBox(intervals,intervals),self.cfg)
        self.assertFalse(bounds.all_exported_coefficients_singleton)
        for signs in product((-1,0,1),repeat=4):
            s1=tuple(z+signs[i] if i<2 else z for i,z in enumerate(centers))
            s2=tuple(z+signs[i+2] if i<2 else z for i,z in enumerate(centers))
            candidate=replace(state,stage1=replace(state.stage1,accumulator_codes=s1),stage2=replace(state.stage2,accumulator_codes=s2))
            result=actual(self.samples,candidate,self.cfg)
            for actual_bank,predicted in ((result.state.stage1,bounds.next_state_box.stage1_accumulators),
                                          (result.state.stage2,bounds.next_state_box.stage2_accumulators)):
                self.assertTrue(all(p.lower<=z<=p.upper for z,p in zip(actual_bank.accumulator_codes,predicted)))
            self.assertTrue(all(p.lower<=code(r)<=p.upper for r,p in zip(result.calibrations,bounds.codes)))

    def test_same_export_cell_preserves_q22_width_under_translation(self):
        state=_initial(self.cfg.adaptive)
        intervals=(IntegerInterval(2**22-1,2**22+1),)*4
        result=bound_frozen_window(self.samples,FixedStateBox(intervals,intervals),self.cfg)
        self.assertTrue(result.all_exported_coefficients_singleton)
        self.assertEqual(tuple(p.upper-p.lower for p in result.next_state_box.stage1_accumulators),(2,)*4)
        self.assertEqual(tuple(p.upper-p.lower for p in result.next_state_box.stage2_accumulators),(2,)*4)

    def test_complete_window_aggregation_is_not_sequential_commits(self):
        cfg=self.cfg.adaptive
        from adc_research.calibration.fixed_adaptive_two_stage import correct_and_update_fixed
        amplified=replace(cfg,stage1_lms=replace(cfg.stage1_lms,step_sizes=tuple(s*100 for s in cfg.stage1_lms.step_sizes)),
                          stage2_lms=replace(cfg.stage2_lms,step_sizes=tuple(s*100 for s in cfg.stage2_lms.step_sizes)))
        window_cfg=replace(self.cfg,adaptive=amplified)
        state=_initial(amplified)
        predicted=bound_frozen_window(self.samples,FixedStateBox.from_state(state),window_cfg)
        window=actual(self.samples,state,window_cfg)
        self.assertEqual(predicted.next_state_box,FixedStateBox.from_state(window.state))
        sequential=state
        for sample in self.samples:
            sequential=correct_and_update_fixed(sample,sequential,amplified).state
        self.assertNotEqual(predicted.next_state_box,FixedStateBox.from_state(sequential))

    def test_output_and_update_saturation_are_enclosed(self):
        cfg=self.cfg.adaptive
        top=cfg.stage2_lms.maximum_accumulator_code
        state=_initial(cfg)
        state=replace(state,stage2=replace(state.stage2,accumulator_codes=(top,)*4))
        samples=(Sample(4,0,20,-1,1),)*4
        predicted=bound_frozen_window(samples,FixedStateBox.from_state(state),self.cfg)
        result=actual(samples,state,self.cfg)
        self.assertEqual(predicted.next_state_box,FixedStateBox.from_state(result.state))
        self.assertEqual(tuple(i.lower for i in predicted.codes),tuple(code(r) for r in result.calibrations))

    def test_undefined_possible_branch_fails(self):
        state=_initial(self.cfg.adaptive)
        with self.assertRaises(ValueError):
            bound_frozen_window((Sample(0,4,127,1,-1),)*4,FixedStateBox.from_state(state),self.cfg)

    def test_partial_window_and_point_selection_are_rejected(self):
        state=FixedStateBox.from_state(_initial(self.cfg.adaptive))
        with self.assertRaises(ValueError):bound_frozen_window(self.samples[:3],state,self.cfg)
        with self.assertRaises(ValueError):bound_frozen_window(self.samples,state,replace(self.cfg,selection='point_products'))

    def test_hidden_analog_rows_and_bad_dither_are_rejected(self):
        state=FixedStateBox.from_state(_initial(self.cfg.adaptive))
        with self.assertRaises(TypeError):bound_frozen_window(({},)*4,state,self.cfg)
        with self.assertRaises(ValueError):bound_frozen_window((Sample(0,0,0,1,None),)*4,state,self.cfg)


if __name__=='__main__':
    unittest.main()
