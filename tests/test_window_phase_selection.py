import unittest

from adc_research.calibration.window_phase_selection import WindowPhaseSchedule, xorshift32
from adc_research.calibration.fixed_four_lane_window import (
    FourLaneConversion, FixedFourLaneWindowConfig, correct_fixed_four_lane_window,
)
from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial


class WindowPhaseSelectionTests(unittest.TestCase):
    def test_rotation_covers_each_lane_phase_once_before_wrapping(self):
        schedule = WindowPhaseSchedule("rotate")
        phases = []
        for _ in range(60):
            phases.append(schedule.phase)
            schedule = schedule.advance()
        self.assertEqual(phases, list(range(30))*2)

    def test_fixed_phase_never_moves(self):
        schedule = WindowPhaseSchedule("fixed", 17)
        for _ in range(160):
            self.assertEqual(schedule.phase, 17)
            schedule = schedule.advance()

    def test_nonzero_prng_state_and_phase_range(self):
        schedule = WindowPhaseSchedule("xorshift32", 0x13579bdf)
        original = schedule.state
        for _ in range(1000):
            self.assertTrue(0 <= schedule.phase < 30)
            self.assertTrue(0 < schedule.state < 2**32)
            schedule = schedule.advance()
        self.assertNotEqual(schedule.state, original)

    def test_xorshift_known_unsigned_vector(self):
        # Hand evaluation for input 1: 1^8192=8193; >>17=0;
        # 8193 ^ (8193<<5) = 270369.
        self.assertEqual(xorshift32(1),270369)

    def test_rejects_invalid_control_states(self):
        for mode,state in (("fixed",30),("rotate",-1),("xorshift32",0),
                           ("xorshift32",2**32),("other",0),("fixed",True)):
            with self.assertRaises(ValueError):
                WindowPhaseSchedule(mode,state)

    def test_each_phase_selects_four_aligned_samples_without_changing_current_codes(self):
        cfg = _config()
        samples = tuple(Sample(0,0,64,1,-1) for _ in range(120))
        rows = tuple(FourLaneConversion(n,n % 4,s) for n,s in enumerate(samples))
        outputs = None
        selected = []
        for phase in range(30):
            result = correct_fixed_four_lane_window(rows,_initial(cfg),
                FixedFourLaneWindowConfig(cfg,selection="point_products",point_phase=phase))
            self.assertEqual(result.selected_conversion_ids,tuple(range(4*phase,4*phase+4)))
            self.assertEqual(result.stage1_update.product_multiplier,30)
            if outputs is None:
                outputs = result.calibrations
            self.assertEqual(result.calibrations,outputs)
            selected.extend(result.selected_conversion_ids)
        self.assertEqual(selected,list(range(120)))

    def test_phase_partition_identity_at_common_old_state(self):
        cfg = _config()
        rows = tuple(FourLaneConversion(n,n % 4,Sample(0,0,64*(1 if n % 3 else -1),
            -1 if n % 2 else 1,1)) for n in range(120))
        initial = _initial(cfg)
        all_result = correct_fixed_four_lane_window(rows,initial,FixedFourLaneWindowConfig(cfg))
        totals = [[0]*4 for _ in range(2)]
        for phase in range(30):
            result = correct_fixed_four_lane_window(rows,initial,
                FixedFourLaneWindowConfig(cfg,selection="point_products",point_phase=phase))
            for bank,update in enumerate((result.stage1_update,result.stage2_update)):
                for i,value in enumerate(update.selected_product_sums):
                    totals[bank][i] += value
        self.assertEqual(tuple(totals[0]),all_result.stage1_update.selected_product_sums)
        self.assertEqual(tuple(totals[1]),all_result.stage2_update.selected_product_sums)


if __name__ == "__main__":
    unittest.main()
