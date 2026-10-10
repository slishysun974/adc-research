from dataclasses import replace
import unittest
from adc_research.calibration.fixed_four_lane_window import FixedFourLaneWindowConfig,FourLaneConversion,correct_fixed_four_lane_window
from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial


class HighGateSensitivityTests(unittest.TestCase):
    def run_at(self,raw,third_export_code,second_export_code=1024):
        cfg=FixedFourLaneWindowConfig(_config(),lane_period=1)
        state=_initial(cfg.adaptive)
        state=replace(state,stage2=replace(state.stage2,accumulator_codes=(2**22,second_export_code*4096,third_export_code*4096,2**22)))
        samples=tuple(FourLaneConversion(i,i,Sample(0,0,raw if i%2 else -raw,
                       1 if i%2 else -1,-1 if i%2 else 1)) for i in range(4))
        return correct_fixed_four_lane_window(samples,state,cfg)

    def test_open_third_gate_and_nonzero_request_with_zero_own_basis(self):
        unit=self.run_at(63,1024)
        changed=self.run_at(63,1536)
        self.assertEqual(unit.stage2_update.selected_gate_counts[2],4)
        self.assertNotEqual(unit.stage2_update.requested_deltas[2],0)
        self.assertEqual(unit.stage2_learning_outputs_scaled,changed.stage2_learning_outputs_scaled)
        self.assertEqual(unit.stage2_update.requested_deltas[2],changed.stage2_update.requested_deltas[2])

    def test_nonzero_third_basis_changes_output_by_declared_amount(self):
        unit=self.run_at(79,1024)
        changed=self.run_at(79,1536)
        differences=tuple(a-b for a,b in zip(changed.stage2_learning_outputs_scaled,unit.stage2_learning_outputs_scaled))
        self.assertEqual(differences,(-60,60,-60,60))

    def test_q3_equality_gate_opens_without_third_basis(self):
        result=self.run_at(48,1024,1025)
        self.assertEqual(result.stage2_learning_outputs_scaled,(-512,512,-512,512))
        self.assertEqual(result.stage2_update.thresholds_scaled[2],512)
        self.assertEqual(result.stage2_update.selected_gate_counts[2],4)
        self.assertFalse(any(abs(y)>512 for y in result.stage2_learning_outputs_scaled))


if __name__=='__main__':
    unittest.main()
