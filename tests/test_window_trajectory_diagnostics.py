from dataclasses import replace
from fractions import Fraction as F
import unittest

from adc_research.calibration.fixed_four_lane_window import (
    FourLaneConversion, FixedFourLaneWindowConfig, correct_fixed_four_lane_window,
)
from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.evaluation.window_trajectory_diagnostics import (
    digital_front_window, offline_front_attribution, code_error_stats,
)
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial


class WindowTrajectoryDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        self.cfg = _config()
        self.samples = tuple(Sample(0, 0, 8+64*(-1 if n % 2 else 1)+16*(1 if n < 60 else -1),
                                    -1 if n % 2 else 1, 1 if n < 60 else -1) for n in range(120))
        self.targets = (2056,)*120

    def result(self, method="all_products"):
        return correct_fixed_four_lane_window(tuple(FourLaneConversion(n,n % 4,s)
            for n,s in enumerate(self.samples)),_initial(self.cfg),FixedFourLaneWindowConfig(self.cfg,selection=method))

    def test_independent_gate_sums_and_exact_update_accounting(self):
        for method in ("all_products","point_products"):
            result = self.result(method)
            frame = digital_front_window(self.samples,result,self.cfg)
            gates = offline_front_attribution(frame,self.targets,result,self.cfg)
            for i,gate in enumerate(gates):
                self.assertEqual(gate["learning_product_sum"],gate["target_product_sum"]+gate["error_product_sum"])
                self.assertEqual(sum((gate[k] for k in ("target_delta_q22","error_delta_q22",
                    "rounding_delta_q22","clipping_delta_q22")),F(0)),result.stage1_update.applied_deltas[i])

    def test_offline_target_changes_do_not_change_digital_evidence(self):
        result = self.result()
        frame = digital_front_window(self.samples,result,self.cfg)
        a = offline_front_attribution(frame,self.targets,result,self.cfg)
        b = offline_front_attribution(frame,(2048,)*120,result,self.cfg)
        self.assertEqual([r["learning_product_sum"] for r in a],[r["learning_product_sum"] for r in b])
        self.assertEqual(frame,digital_front_window(self.samples,result,self.cfg))

    def test_point_scaling_retains_full_record_comparison(self):
        result = self.result("point_products")
        frame = digital_front_window(self.samples,result,self.cfg)
        gates = offline_front_attribution(frame,self.targets,result,self.cfg)
        self.assertEqual(sum(r["selected"] for r in frame),4)
        self.assertEqual(gates[0]["scaled_selection_difference"],
            30*gates[0]["learning_product_sum"]-gates[0]["all_product_sum_at_same_state"])

    def test_zero_raw_has_zero_basis_even_when_first_gate_is_open(self):
        samples = (Sample(0,0,16,1,1),)*120
        result = correct_fixed_four_lane_window(tuple(FourLaneConversion(n,n % 4,s)
            for n,s in enumerate(samples)),_initial(self.cfg),FixedFourLaneWindowConfig(self.cfg))
        frame = digital_front_window(samples,result,self.cfg)
        self.assertTrue(all(r["gates"][0] and not r["support"][0] for r in frame))
        gates = offline_front_attribution(frame,(2048,)*120,result,self.cfg)
        self.assertEqual(gates[0]["zero_basis_selected_count"],120)

    def test_clipping_is_accounted_separately(self):
        result = self.result()
        frame = digital_front_window(self.samples,result,self.cfg)
        update = replace(result.stage1_update,applied_deltas=tuple(d-7 for d in result.stage1_update.requested_deltas))
        modified = replace(result,stage1_update=update)
        gates = offline_front_attribution(frame,self.targets,modified,self.cfg)
        self.assertTrue(all(g["clipping_delta_q22"] == -7 for g in gates))

    def test_rejects_misalignment_and_invalid_targets(self):
        result = self.result()
        with self.assertRaises(ValueError):
            digital_front_window(self.samples[:-1],result,self.cfg)
        frame = digital_front_window(self.samples,result,self.cfg)
        for targets in ((),(True,)*120,(4096,)*120):
            with self.assertRaises(ValueError):
                offline_front_attribution(frame,targets,result,self.cfg)

    def test_exact_integer_error_stats(self):
        stats = code_error_stats((1,4,6),(2,2,6))
        self.assertEqual(stats["mse_codes_squared"],F(5,3))
        self.assertEqual(stats["mae_codes"],1)
        self.assertEqual(stats["bias_codes"],F(1,3))
        with self.assertRaises(ValueError):
            code_error_stats((1,2),(1,))


if __name__ == "__main__":
    unittest.main()
