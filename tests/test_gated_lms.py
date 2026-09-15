import unittest

from adc_research.calibration.gated_lms import (
    GatedLmsConfig,
    GatedLmsState,
    adaptive_lower_thresholds,
    update,
    update_block_mean,
)


class GatedLmsTests(unittest.TestCase):
    def test_adaptive_thresholds_follow_preceding_coefficients(self) -> None:
        thresholds = adaptive_lower_thresholds(
            (1.08, 0.94, 1.03, 0.95),
            128,
        )
        self.assertEqual(thresholds[0], 0.0)
        self.assertAlmostEqual(thresholds[1], 138.24)
        self.assertAlmostEqual(thresholds[2], 258.56)
        self.assertAlmostEqual(thresholds[3], 390.4)

    def test_first_coefficient_uses_all_samples_and_higher_gates_are_lower_only(self) -> None:
        config = GatedLmsConfig(0.25, (0.1, 0.1, 0.1, 0.1))
        state = GatedLmsState.unity(4)

        small = update(
            state,
            dither_code=0.25,
            corrected_output=0.1,
            config=config,
        )
        self.assertEqual(small.gate_mask, (True, False, False, False))

        large = update(
            state,
            dither_code=0.25,
            corrected_output=1.2,
            config=config,
        )
        self.assertEqual(large.gate_mask, (True, True, True, True))

    def test_threshold_equality_belongs_to_active_range(self) -> None:
        config = GatedLmsConfig(0.25, (0.1, 0.1))
        result = update(
            GatedLmsState.unity(2),
            dither_code=1.0,
            corrected_output=-0.25,
            config=config,
        )
        self.assertEqual(result.gate_mask, (True, True))

    def test_update_is_simultaneous_and_uses_preupdate_thresholds(self) -> None:
        config = GatedLmsConfig(0.25, (0.1, 0.2))
        state = GatedLmsState.unity(2)
        result = update(
            state,
            dither_code=0.5,
            corrected_output=0.3,
            config=config,
        )
        self.assertEqual(result.adaptive_lower_thresholds, (0.0, 0.25))
        self.assertEqual(result.gate_mask, (True, True))
        self.assertAlmostEqual(result.coefficients_after[0], 0.985)
        self.assertAlmostEqual(result.coefficients_after[1], 0.97)
        self.assertEqual(result.state.gate_counts, (1, 1))
        self.assertEqual(result.state.sample_count, 1)

    def test_unexcited_outer_coefficient_is_frozen(self) -> None:
        config = GatedLmsConfig(0.25, (0.1, 0.1, 0.1, 0.1))
        state = GatedLmsState.unity(4)
        for _ in range(20):
            state = update(
                state,
                dither_code=0.25,
                corrected_output=0.2,
                config=config,
            ).state
        self.assertEqual(state.coefficients[1:], (1.0, 1.0, 1.0))
        self.assertEqual(state.gate_counts[1:], (0, 0, 0))

    def test_coefficient_bounds_are_enforced(self) -> None:
        config = GatedLmsConfig(0.25, (1.0,), coefficient_bounds=(0.0, 2.0))
        low = update(
            GatedLmsState((0.1,), (0,)),
            dither_code=1.0,
            corrected_output=1.0,
            config=config,
        )
        high = update(
            GatedLmsState((1.9,), (0,)),
            dither_code=-1.0,
            corrected_output=1.0,
            config=config,
        )
        self.assertEqual(low.coefficients_after, (0.0,))
        self.assertEqual(high.coefficients_after, (2.0,))

    def test_single_observation_block_matches_instantaneous_update(self) -> None:
        config = GatedLmsConfig(0.25, (0.1, 0.2))
        state = GatedLmsState.unity(2)
        instantaneous = update(
            state,
            dither_code=0.5,
            corrected_output=0.3,
            config=config,
        )
        block = update_block_mean(
            state,
            observations=((0.5, 0.3),),
            config=config,
        )
        self.assertEqual(block.coefficients_after, instantaneous.coefficients_after)
        self.assertEqual(block.state, instantaneous.state)

    def test_block_mean_uses_fixed_thresholds_and_full_block_denominator(self) -> None:
        config = GatedLmsConfig(0.25, (0.1, 0.2))
        state = GatedLmsState.unity(2)
        result = update_block_mean(
            state,
            observations=((1.0, 0.3), (-1.0, 0.1)),
            config=config,
        )
        self.assertEqual(result.adaptive_lower_thresholds, (0.0, 0.25))
        self.assertEqual(result.gate_counts, (2, 1))
        self.assertAlmostEqual(result.mean_gated_products[0], 0.1)
        self.assertAlmostEqual(result.mean_gated_products[1], 0.15)
        self.assertAlmostEqual(result.coefficients_after[0], 0.99)
        self.assertAlmostEqual(result.coefficients_after[1], 0.97)
        self.assertEqual(result.state.gate_counts, (2, 1))
        self.assertEqual(result.state.sample_count, 2)


if __name__ == "__main__":
    unittest.main()
