"""Checks for the offline PWL objective direction diagnostic."""

import unittest
from dataclasses import replace
from types import SimpleNamespace

from adc_research.calibration.fixed_pwl import correct_fixed, correct_two_stage_fixed_observed
from adc_research.calibration.observation import DigitalCalibrationSample
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_052_objective_alignment.run import analyze_window, basis, code_from_scaled


class ObjectiveAlignmentTests(unittest.TestCase):
    def test_signed_basis_matches_continuous_pwl_and_q3_rounding_bound(self):
        config = _config().cascade.stage1_pwl
        codes = (997, 1053, 969, 1101)
        changed = (1011, 1047, 989, 1089)
        for raw in (-4096, -3081, -2048, -1023, 0, 1024, 2123, 3199, 4095):
            before = correct_fixed(raw, replace(config, coefficient_codes=codes))
            after = correct_fixed(raw, replace(config, coefficient_codes=changed))
            b = basis(SimpleNamespace(stage1_pwl=before), config.slice_width_scaled)
            old_numerator = sum(x*q for x, q in zip(b, codes, strict=True))
            new_numerator = sum(x*q for x, q in zip(b, changed, strict=True))
            self.assertLessEqual(abs(1024*before.corrected_code_scaled-old_numerator), 1024)
            self.assertLessEqual(abs(1024*after.corrected_code_scaled-new_numerator), 1024)
            self.assertEqual(new_numerator-old_numerator,
                             sum(x*(bq-aq) for x, aq, bq in zip(b, codes, changed, strict=True)))

    def test_no_coefficient_change_is_neutral(self):
        cfg = _config()
        state = {"stage1": [1024]*4, "stage2": [1024]*4,
                 "stage1_q22": [4194304]*4, "stage2_q22": [4194304]*4}
        sample = DigitalCalibrationSample(0, 0, 0, 1, 1)
        result = analyze_window((sample,), (2048,), state, state,
                                {"applied_deltas": [[0]*4, [0]*4]}, cfg)
        self.assertEqual(result["direction_q22"], "neutral")
        self.assertEqual(result["integer_sse_change_codes_squared"], 0)
        self.assertEqual(result["continuous_sse_change_codes_squared"], 0)

    def test_changed_front_score_matches_full_cascade(self):
        cfg = _config()
        old = {"stage1": [1024]*4, "stage2": [1024]*4,
               "stage1_q22": [4194304]*4, "stage2_q22": [4194304]*4}
        new = {"stage1": [1040, 1016, 1024, 1024], "stage2": [1024]*4,
               "stage1_q22": [4194304+16*4096, 4194304-8*4096, 4194304, 4194304],
               "stage2_q22": [4194304]*4}
        samples = (DigitalCalibrationSample(0, 0, 0, 1, 1),
                   DigitalCalibrationSample(1, -1, 40, -1, 1),
                   DigitalCalibrationSample(-1, 1, 20, 1, -1))
        targets = (2048, 2110, 1990)
        result = analyze_window(samples, targets, old, new,
                                {"applied_deltas": [[16*4096, -8*4096, 0, 0], [0]*4]}, cfg)
        revised = replace(cfg.cascade, stage1_pwl=replace(cfg.cascade.stage1_pwl,
                                                          coefficient_codes=tuple(new["stage1"])))
        direct_sse = sum((code_from_scaled(correct_two_stage_fixed_observed(s, revised).unclipped_output_scaled)-t)**2
                         for s, t in zip(samples, targets, strict=True))
        self.assertEqual(result["new_integer_sse_codes_squared"], direct_sse)


if __name__ == "__main__":
    unittest.main()
