"""Distinguishing traces for unpublished merge and activation hypotheses."""

from dataclasses import replace
from fractions import Fraction
import unittest

from adc_research.calibration.fixed_commit_broadcast import (
    CommitBroadcastState, correct_commit_broadcast_window,
)
from adc_research.calibration.fixed_four_lane_window import (
    FourLaneConversion, FixedFourLaneWindowConfig, correct_fixed_four_lane_window,
)
from adc_research.calibration.observation import DigitalCalibrationSample
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial


class CommitBroadcastTests(unittest.TestCase):
    def setUp(self):
        self.cfg = _config()
        self.initial = _initial(self.cfg)
        self.state = CommitBroadcastState(self.initial, self.initial)
        self.window = FixedFourLaneWindowConfig(self.cfg, lane_period=2, selection="point_products")

    def rows(self, start=0, backend=17):
        return tuple(FourLaneConversion(start+i, (start+i) % 4,
                     DigitalCalibrationSample(0, 0, backend, 1, 1)) for i in range(8))

    def test_merged_matches_unchanged_reference(self):
        original = correct_fixed_four_lane_window(self.rows(), self.initial, self.window)
        result = correct_commit_broadcast_window(self.rows(), self.state, self.window, "merged_boundary")
        self.assertEqual(result.calibrations, original.calibrations)
        self.assertEqual(result.state.master, original.state)
        self.assertEqual(result.state.visible, original.state)

    def test_lane_rounding_is_distinguishable_and_at_most_two_lsb_at_same_state(self):
        differences = []
        for backend in range(16, 28):
            merged = correct_commit_broadcast_window(self.rows(backend=backend), self.state, self.window, "merged_boundary")
            rounded = correct_commit_broadcast_window(self.rows(backend=backend), self.state, self.window, "lane_rounded_boundary")
            self.assertEqual(merged.calibrations, rounded.calibrations)
            diffs = [a-b for a, b in zip(rounded.commits[0].requested[1], merged.commits[0].requested[1])]
            self.assertTrue(all(abs(d) <= 2 for d in diffs))
            differences.extend(diffs)
        self.assertTrue(any(d != 0 for d in differences))

    def test_delay_has_two_unity_windows_then_old_master(self):
        first = correct_commit_broadcast_window(self.rows(backend=79), self.state, self.window, "delayed_broadcast")
        self.assertEqual(first.state.visible.stage2.accumulator_codes, self.initial.stage2.accumulator_codes)
        second = correct_commit_broadcast_window(self.rows(8, 79), first.state, self.window, "delayed_broadcast")
        self.assertEqual(first.calibrations, second.calibrations)
        self.assertEqual(second.state.visible.stage2.accumulator_codes, first.state.master.stage2.accumulator_codes)
        third = correct_commit_broadcast_window(self.rows(16, 79), second.state, self.window, "delayed_broadcast")
        self.assertNotEqual(third.calibrations, second.calibrations)
        self.assertEqual(third.state.master.stage2.sample_count, 24)

    def test_serial_never_uses_its_own_postupdate_coefficients(self):
        result = correct_commit_broadcast_window(self.rows(backend=79), self.state, self.window, "serial_immediate")
        merged = correct_commit_broadcast_window(self.rows(backend=79), self.state, self.window, "merged_boundary")
        self.assertEqual(result.calibrations[0], merged.calibrations[0])
        self.assertNotEqual(result.calibrations[1:], merged.calibrations[1:])
        self.assertEqual([e.after_conversion_id for e in result.commits], [0, 1, 2, 3])
        self.assertEqual(result.commits[1].learning_state, result.commits[0].master_after)
        self.assertEqual(result.state.master.stage1.sample_count, 8)

    def test_serial_ordered_saturation_differs_from_single_net_commit(self):
        # Strong declared test steps force both signs through the lower bound.
        cfg = replace(self.cfg, stage2_lms=replace(self.cfg.stage2_lms,
                      step_sizes=(Fraction(1, 2000),)*4))
        initial = self.initial
        state = CommitBroadcastState(initial, initial)
        window = replace(self.window, adaptive=cfg)
        rows = list(self.rows())
        for i, backend in enumerate((127, -127, 127, -127)):
            rows[i] = replace(rows[i], sample=DigitalCalibrationSample(0, 0, backend, 1, 1))
        serial = correct_commit_broadcast_window(rows, state, window, "serial_immediate")
        merged = correct_commit_broadcast_window(rows, state, window, "merged_boundary")
        self.assertTrue(any(a != b for e in serial.commits for a, b in zip(e.requested[1], e.applied[1])))
        self.assertNotEqual(serial.state.master.stage2.accumulator_codes, merged.state.master.stage2.accumulator_codes)

    def test_malformed_alignment_and_mixed_latency_are_rejected(self):
        for rows in (self.rows()[:-1], tuple(reversed(self.rows()))):
            with self.assertRaises(ValueError):
                correct_commit_broadcast_window(rows, self.state, self.window, "serial_immediate")
        with self.assertRaises(ValueError):
            correct_commit_broadcast_window(self.rows(), self.state, self.window, "unknown")
        with self.assertRaises(TypeError):
            FourLaneConversion(0, 0, {"ideal_code": 2048})
        lag = correct_commit_broadcast_window(self.rows(backend=79), self.state, self.window, "delayed_broadcast").state
        with self.assertRaises(ValueError):
            correct_commit_broadcast_window(self.rows(8), lag, self.window, "merged_boundary")


if __name__ == "__main__":
    unittest.main()
