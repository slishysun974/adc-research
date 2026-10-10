"""Independent checks of sound fixed-point coefficient-box propagation."""

from __future__ import annotations

import unittest
from fractions import Fraction
from itertools import product

from adc_research.calibration.fixed_adaptive_two_stage import (
    FixedTwoStageAdaptiveConfig,
    FixedTwoStageAdaptiveState,
    correct_and_update_fixed,
)
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsConfig, FixedGatedLmsState
from adc_research.calibration.fixed_point import (
    UnsignedFixedFormat,
    round_fraction,
)
from adc_research.calibration.fixed_pwl import (
    FixedPwlArithmetic,
    FixedPwlConfig,
    FixedTwoStageConfig,
    correct_fixed,
)
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.evaluation.fixed_online_state_bounds import (
    FixedStateBox,
    IntegerInterval,
    _corrected_interval,
    bound_fixed_online_codes,
)
from adc_research.evaluation.static_online_reachability import (
    StaticAnalogFrame,
    propagate_static_fixed_online_codes,
)
from adc_research.theory.static_observation_reachability import (
    ClosedInterval,
    StaticCandidateArchitecture,
)


def candidate_config() -> FixedTwoStageAdaptiveConfig:
    def pwl(width: int) -> FixedPwlConfig:
        return FixedPwlConfig(
            slice_width_scaled=width,
            coefficient_codes=(1024,) * 4,
            source_slopes=(1.0,) * 4,
            arithmetic=FixedPwlArithmetic(),
            coefficient_saturations=(False,) * 4,
        )

    cascade = FixedTwoStageConfig(
        stage1_pwl=pwl(1024), stage2_pwl=pwl(256),
        stage1_symbol_weight_scaled=4096,
        stage2_symbol_weight_scaled=1024,
        backend_weight_scaled=8,
        output_offset_scaled=16384,
        output_range_scaled=(0, 32760),
        dither_code_copies_scaled=({-1: -512, 1: 512}, {-1: -128, 1: 128}),
        data_fractional_bits=3,
    )
    numerators = (1, 3, 6, 12)
    return FixedTwoStageAdaptiveConfig(
        cascade=cascade,
        stage1_lms=FixedGatedLmsConfig(
            slice_width_scaled=1024,
            step_sizes=tuple(Fraction(n, 1000 * 512 * 512) for n in numerators),
            accumulator_fractional_bits=22,
        ),
        stage2_lms=FixedGatedLmsConfig(
            slice_width_scaled=256,
            step_sizes=tuple(Fraction(n, 1000 * 128 * 128) for n in numerators),
            accumulator_fractional_bits=22,
        ),
    )


def initial_state(config: FixedTwoStageAdaptiveConfig) -> FixedTwoStageAdaptiveState:
    return FixedTwoStageAdaptiveState(
        FixedGatedLmsState.unity(config.stage1_lms),
        FixedGatedLmsState.unity(config.stage2_lms),
    )


def final_code(result) -> int:
    return min(max(round_fraction(
        result.calibration.unclipped_output_scaled, 8, "nearest_even"
    ), 0), 4095)


def sample(backend: int, q1: int = 0, d1: int = 1, d2: int = 1) -> DigitalCalibrationSample:
    return DigitalCalibrationSample(q1, 0, backend, d1, d2)


class FixedOnlineStateBoundsTests(unittest.TestCase):
    def test_pwl_extrema_cover_all_small_integer_coefficient_combinations(self) -> None:
        arithmetic = FixedPwlArithmetic(
            coefficient_format=UnsignedFixedFormat(4, 2),
            data_fractional_bits=0,
        )
        pwl = FixedPwlConfig(
            slice_width_scaled=3,
            coefficient_codes=(1, 2, 3),
            source_slopes=(0.25, 0.5, 0.75),
            arithmetic=arithmetic,
            coefficient_saturations=(False,) * 3,
        )
        coefficient_box = ((1, 2, 3), (4, 6, 5))
        for raw_low, raw_high in ((-9, 8), (-6, -1), (-4, 4), (0, 8), (3, 3)):
            predicted = _corrected_interval(
                IntegerInterval(raw_low, raw_high), pwl, coefficient_box
            )
            actual = []
            for codes in product(range(1, 5), range(2, 7), range(3, 6)):
                configured = FixedPwlConfig(
                    slice_width_scaled=3,
                    coefficient_codes=codes,
                    source_slopes=pwl.source_slopes,
                    arithmetic=arithmetic,
                    coefficient_saturations=(False,) * 3,
                )
                actual.extend(
                    correct_fixed(raw, configured).corrected_code_scaled
                    for raw in range(raw_low, raw_high + 1)
                )
            self.assertEqual((predicted.lower, predicted.upper),
                             (min(actual), max(actual)))

    def test_joined_box_contains_every_short_exact_history(self) -> None:
        config = candidate_config()
        state = initial_state(config)
        choices = (
            (sample(10, d1=-1), sample(11, d1=-1)),
            (sample(20),),
            (sample(-13),),
            (sample(-8, d2=-1), sample(-7, d2=-1)),
            (sample(33),),
            (sample(-40),),
            (sample(5, d1=-1),),
            (sample(0),),
        )
        bound = bound_fixed_online_codes(
            choices, FixedStateBox.from_state(state), config
        )
        exact = [(state, ())]
        for alternatives in choices:
            exact = [
                (updated.state, record + (final_code(updated),))
                for old_state, record in exact
                for observed in alternatives
                for updated in (correct_and_update_fixed(observed, old_state, config),)
            ]
        self.assertEqual(len(exact), 4)
        for exact_state, record in exact:
            for index, code in enumerate(record):
                self.assertLessEqual(bound.lower_codes[index], code)
                self.assertLessEqual(code, bound.upper_codes[index])
            for bank, intervals in (
                (exact_state.stage1, bound.final_state_box.stage1_accumulators),
                (exact_state.stage2, bound.final_state_box.stage2_accumulators),
            ):
                for code, interval in zip(bank.accumulator_codes, intervals, strict=True):
                    self.assertLessEqual(interval.lower, code)
                    self.assertLessEqual(code, interval.upper)

    def test_many_binary_code_histories_keep_exact_state_without_path_storage(self) -> None:
        config = candidate_config()
        state = initial_state(config)
        alternatives = (sample(0, q1=0), sample(0, q1=1))
        length = 512
        bound = bound_fixed_online_codes(
            (alternatives for _ in range(length)),
            FixedStateBox.from_state(state), config,
        )
        exact_codes = []
        for _ in range(length):
            updated = correct_and_update_fixed(alternatives[0], state, config)
            exact_codes.append(final_code(updated))
            state = updated.state
        self.assertEqual(bound.lower_codes, tuple(exact_codes))
        self.assertEqual(bound.upper_codes, tuple(code + 512 for code in exact_codes))
        self.assertEqual(bound.final_state_box, FixedStateBox.from_state(state))

    def test_undefined_digital_branch_is_rejected(self) -> None:
        config = candidate_config()
        with self.assertRaisesRegex(ValueError, "conversion 0"):
            bound_fixed_online_codes(
                ((DigitalCalibrationSample(0, 4, 127, 1, 1),),),
                FixedStateBox.from_state(initial_state(config)), config,
            )

    def test_static_analog_intervals_feed_longer_fixed_state_box(self) -> None:
        config = candidate_config()
        architecture = StaticCandidateArchitecture(
            stage1_thresholds=(), stage2_thresholds=(),
            stage1_symbols=(0,), stage2_symbols=(0,),
            stage1_dac_levels=(0.0,), stage2_dac_levels=(0.0,),
            front_nominal_range=(-128.0, 128.0),
            backend_range=(-128.0, 128.0), backend_bits=8,
        )
        frame = StaticAnalogFrame(
            ClosedInterval(0.79, 0.81),
            ClosedInterval(0.1, 0.1),
            ClosedInterval(0.1, 0.1), 1, 1,
        )
        length = 256
        result = propagate_static_fixed_online_codes(
            (frame for _ in range(length)), architecture,
            lambda value: value, lambda value: value, lambda value: value,
            FixedStateBox.from_state(initial_state(config)), config,
        )
        self.assertEqual(len(result.observation_envelopes), length)
        self.assertTrue(all(
            {item.backend_centered_code for item in envelope.outcomes} == {0, 1}
            for envelope in result.observation_envelopes
        ))
        for backend in (0, 1):
            state = initial_state(config)
            for index in range(length):
                updated = correct_and_update_fixed(sample(backend), state, config)
                code = final_code(updated)
                self.assertLessEqual(result.code_bounds.lower_codes[index], code)
                self.assertLessEqual(code, result.code_bounds.upper_codes[index])
                state = updated.state
            for bank, intervals in (
                (state.stage1, result.code_bounds.final_state_box.stage1_accumulators),
                (state.stage2, result.code_bounds.final_state_box.stage2_accumulators),
            ):
                for code, interval in zip(bank.accumulator_codes, intervals, strict=True):
                    self.assertLessEqual(interval.lower, code)
                    self.assertLessEqual(code, interval.upper)


if __name__ == "__main__":
    unittest.main()
