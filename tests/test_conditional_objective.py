"""Check the exact conditional objective audit independently of its experiment."""

import unittest

from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.calibration.pwl import PwlConfig
from adc_research.calibration.two_stage import (
    TwoStagePwlCalibrationConfig, correct_two_stage_observed,
)
from adc_research.evaluation.conditional_objective import (
    FirstSliceAffineSample, conditional_first_slice_objectives,
    first_slice_affine_sample, score_affine_samples,
)


class ConditionalObjectiveTests(unittest.TestCase):
    def test_weighted_median_and_correlation_root_are_distinct(self):
        samples = [
            FirstSliceAffineSample(0, 1, 2, 1, 1),
            FirstSliceAffineSample(4, 0, 2, 1, 2),
            FirstSliceAffineSample(9, 0, 2, 1, 3),
        ]
        result = conditional_first_slice_objectives(samples, 0)
        self.assertEqual(result["mae_minimizer_interval"], [2, 3])
        self.assertAlmostEqual(result["correlation_zero_coefficient"], -1)
        self.assertAlmostEqual(
            score_affine_samples(samples, 0, 2)["mae_codes"],
            score_affine_samples(samples, 0, 3)["mae_codes"],
        )
        self.assertGreater(
            score_affine_samples(samples, 0, -1)["mae_codes"],
            score_affine_samples(samples, 0, 2)["mae_codes"],
        )

    def test_first_slice_basis_matches_full_cascade_across_slices(self):
        observed = DigitalCalibrationSample(1, 1, 3, 1, 1)

        def cascade(k1):
            return TwoStagePwlCalibrationConfig(
                stage1_pwl=PwlConfig(4, (k1, 1.1, 0.9, 1.0)),
                stage2_pwl=PwlConfig(2, (1.0, 1.0, 1.0, 1.0)),
                stage1_symbol_weight=16,
                stage2_symbol_weight=4,
                backend_weight=1,
                output_offset=0,
                output_range=(-100, 100),
                dither_code_copies=({-1: -1, 1: 1}, {-1: -1, 1: 1}),
            )

        reference = correct_two_stage_observed(observed, cascade(1.0))
        self.assertEqual(reference.stage1_pwl.slice_index, 1)
        affine = first_slice_affine_sample(reference, 20, 4)
        changed = correct_two_stage_observed(observed, cascade(1.2))
        self.assertAlmostEqual(
            changed.unclipped_output_code,
            affine.output_at_reference + 0.2 * affine.basis,
        )
        self.assertAlmostEqual(
            changed.stage1_pwl.corrected_code - changed.stage1_dither_copy,
            affine.local_at_reference + 0.2 * affine.basis,
        )


if __name__ == "__main__":
    unittest.main()
