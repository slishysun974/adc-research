from __future__ import annotations

import unittest

from adc_research.calibration.pwl import (
    PwlConfig,
    correct,
    slice_width_from_unsigned_bits,
)


class GuQ008PwlTests(unittest.TestCase):
    def test_reported_nine_bit_magnitude_and_derived_seven_bit_magnitude(self) -> None:
        self.assertEqual(slice_width_from_unsigned_bits(9), 128)
        self.assertEqual(slice_width_from_unsigned_bits(7), 32)

    def test_unity_coefficients_are_identity_over_both_signed_code_ranges(self) -> None:
        for width in (32, 128):
            config = PwlConfig(width, (1.0, 1.0, 1.0, 1.0))
            full_scale = 4 * width
            for raw_code in range(-full_scale, full_scale):
                self.assertEqual(correct(raw_code, config).corrected_code, raw_code)

    def test_cumulative_offsets_make_every_slice_boundary_continuous(self) -> None:
        config = PwlConfig(32, (1.1, 0.8, 1.25, 0.95))
        epsilon = 1e-9
        for index in range(1, 4):
            boundary = index * config.slice_width
            at_boundary = correct(boundary, config)
            below = correct(boundary - epsilon, config)
            self.assertEqual(at_boundary.slice_index, index)
            self.assertAlmostEqual(
                at_boundary.corrected_code,
                config.slice_offsets[index],
            )
            self.assertAlmostEqual(
                below.corrected_code,
                at_boundary.corrected_code,
                places=7,
            )

    def test_symmetric_mode_is_odd_away_from_unpaired_endpoint(self) -> None:
        config = PwlConfig(32, (1.1, 0.8, 1.25, 0.95))
        for raw_code in range(1, 128):
            self.assertAlmostEqual(
                correct(-raw_code, config).corrected_code,
                -correct(raw_code, config).corrected_code,
            )

    def test_negative_full_scale_has_explicit_continuous_extension(self) -> None:
        config = PwlConfig(32, (1.1, 0.8, 1.25, 0.95))
        result = correct(-128, config)
        self.assertTrue(result.negative_full_scale_extension)
        self.assertEqual(result.slice_index, 3)
        self.assertEqual(result.local_code, 32)
        self.assertAlmostEqual(result.corrected_code, -sum(config.slopes) * 32)

    def test_negative_full_scale_can_be_rejected_for_bit_true_audit(self) -> None:
        config = PwlConfig(
            32,
            (1.0, 1.0, 1.0, 1.0),
            negative_full_scale_policy="reject",
        )
        with self.assertRaises(ValueError):
            correct(-128, config)
        self.assertEqual(correct(-127, config).corrected_code, -127)

    def test_out_of_range_and_invalid_configurations_fail_early(self) -> None:
        config = PwlConfig(32, (1.0, 1.0, 1.0, 1.0))
        for raw_code in (-129, 128):
            with self.assertRaises(ValueError):
                correct(raw_code, config)
        with self.assertRaises(ValueError):
            PwlConfig(0, (1.0,))
        with self.assertRaises(ValueError):
            PwlConfig(32, (1.0, -0.1))
        with self.assertRaises(ValueError):
            slice_width_from_unsigned_bits(2, slice_count=4)

    def test_known_inverse_pwl_truth_is_recovered(self) -> None:
        config = PwlConfig(32, (1.1, 0.8, 1.25, 0.95))
        offsets = config.slice_offsets
        corrected_upper_edges = tuple(
            offset + slope * config.slice_width
            for offset, slope in zip(offsets, config.slopes, strict=True)
        )

        for target_index in range(1, 1000):
            target = corrected_upper_edges[-1] * target_index / 1000
            segment = next(
                index
                for index, upper in enumerate(corrected_upper_edges)
                if target <= upper
            )
            raw_magnitude = (
                segment * config.slice_width
                + (target - offsets[segment]) / config.slopes[segment]
            )
            self.assertAlmostEqual(
                correct(raw_magnitude, config).corrected_code,
                target,
            )
            self.assertAlmostEqual(
                correct(-raw_magnitude, config).corrected_code,
                -target,
            )

    def test_uniform_internal_code_scaling_does_not_change_slice_selection(self) -> None:
        base = PwlConfig(32, (0.92, 1.06, 0.98, 1.04))
        for scale in (2, 4, 8):
            scaled = PwlConfig(
                base.slice_width * scale,
                base.slopes,
            )
            for raw_code in range(-128, 128):
                reference = correct(raw_code, base)
                actual = correct(raw_code * scale, scaled)
                self.assertEqual(actual.slice_index, reference.slice_index)
                self.assertAlmostEqual(
                    actual.corrected_code,
                    reference.corrected_code * scale,
                )


if __name__ == "__main__":
    unittest.main()
