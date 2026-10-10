"""Sound integer-box propagation for the fixed-point online Gu candidate.

The eight accumulator intervals enclose every allowed history. Correlations
between accumulators, observations, and conversion times are discarded at
each join, so bounds can widen. Arithmetic within this module is integer and
uses the same explicit Q-format and rounding rules as fixed_gated_lms.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Iterable

from adc_research.calibration.fixed_adaptive_two_stage import (
    FixedTwoStageAdaptiveConfig,
    FixedTwoStageAdaptiveState,
)
from adc_research.calibration.fixed_gated_lms import (
    FixedGatedLmsConfig,
    adaptive_lower_thresholds_scaled,
)
from adc_research.calibration.fixed_point import round_fraction, round_shift
from adc_research.calibration.fixed_pwl import FixedPwlConfig, correct_fixed
from adc_research.calibration.observation import DigitalCalibrationSample


@dataclass(frozen=True)
class IntegerInterval:
    lower: int
    upper: int

    def __post_init__(self) -> None:
        if (not isinstance(self.lower, int) or not isinstance(self.upper, int)
                or self.lower > self.upper):
            raise ValueError("integer interval needs increasing integer endpoints")

    def shifted(self, amount: int) -> "IntegerInterval":
        return IntegerInterval(self.lower + amount, self.upper + amount)

    def hull(self, other: "IntegerInterval") -> "IntegerInterval":
        return IntegerInterval(min(self.lower, other.lower), max(self.upper, other.upper))


@dataclass(frozen=True)
class FixedStateBox:
    stage1_accumulators: tuple[IntegerInterval, ...]
    stage2_accumulators: tuple[IntegerInterval, ...]

    @classmethod
    def from_state(cls, state: FixedTwoStageAdaptiveState) -> "FixedStateBox":
        return cls(
            tuple(IntegerInterval(value, value) for value in state.stage1.accumulator_codes),
            tuple(IntegerInterval(value, value) for value in state.stage2.accumulator_codes),
        )

    def hull(self, other: "FixedStateBox") -> "FixedStateBox":
        if (len(self.stage1_accumulators) != len(other.stage1_accumulators)
                or len(self.stage2_accumulators) != len(other.stage2_accumulators)):
            raise ValueError("state boxes have different coefficient counts")
        return FixedStateBox(
            tuple(left.hull(right) for left, right in zip(
                self.stage1_accumulators, other.stage1_accumulators, strict=True
            )),
            tuple(left.hull(right) for left, right in zip(
                self.stage2_accumulators, other.stage2_accumulators, strict=True
            )),
        )


@dataclass(frozen=True)
class FixedOnlineCodeBounds:
    lower_codes: tuple[int, ...]
    upper_codes: tuple[int, ...]
    final_state_box: FixedStateBox


def _validate_bank(
    intervals: tuple[IntegerInterval, ...], config: FixedGatedLmsConfig
) -> None:
    if len(intervals) != config.coefficient_count:
        raise ValueError("state box and LMS coefficient counts differ")
    if any(item.lower < 0 or item.upper > config.maximum_accumulator_code
           for item in intervals):
        raise ValueError("state box accumulator lies outside configured range")


def _coefficient_bounds(
    intervals: tuple[IntegerInterval, ...], config: FixedGatedLmsConfig
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    shift = config.guard_fractional_bits
    maximum = config.coefficient_format.maximum_code

    def exported(value: int) -> int:
        return min(max(round_shift(value, shift, config.coefficient_export_rounding), 0),
                   maximum)

    return (
        tuple(exported(item.lower) for item in intervals),
        tuple(exported(item.upper) for item in intervals),
    )


def _corrected_interval(
    raw: IntegerInterval,
    pwl: FixedPwlConfig,
    coefficients: tuple[tuple[int, ...], tuple[int, ...]],
) -> IntegerInterval:
    """Exact extrema over a raw-code interval and a coefficient rectangle.

    For fixed raw sign and slice, the result is monotone in raw magnitude and
    each unsigned coefficient. Check interval ends and both sides of every
    slice/sign boundary under the lower and upper coefficient corners.
    """
    full_scale = pwl.full_scale_scaled
    if raw.lower < -full_scale or raw.upper >= full_scale:
        raise ValueError("possible raw code lies outside the signed PWL domain")
    if raw.lower == -full_scale and pwl.negative_full_scale_policy == "reject":
        raise ValueError("negative full-scale endpoint is rejected by PWL policy")
    candidates = {raw.lower, raw.upper}
    for boundary_index in range(-pwl.slice_count, pwl.slice_count + 1):
        boundary = boundary_index * pwl.slice_width_scaled
        for code in (boundary - 1, boundary, boundary + 1):
            if raw.lower <= code <= raw.upper:
                candidates.add(code)
    values = []
    for corner in coefficients:
        corner_pwl = replace(pwl, coefficient_codes=corner)
        values.extend(
            correct_fixed(code, corner_pwl).corrected_code_scaled
            for code in candidates
        )
    return IntegerInterval(min(values), max(values))


def _magnitude_bounds(value: IntegerInterval) -> tuple[int, int]:
    minimum = 0 if value.lower <= 0 <= value.upper else min(abs(value.lower), abs(value.upper))
    return minimum, max(abs(value.lower), abs(value.upper))


def _updated_bank(
    accumulators: tuple[IntegerInterval, ...],
    coefficients: tuple[tuple[int, ...], tuple[int, ...]],
    learning_output: IntegerInterval,
    dither: int,
    config: FixedGatedLmsConfig,
) -> tuple[IntegerInterval, ...]:
    lower_thresholds = adaptive_lower_thresholds_scaled(coefficients[0], config)
    upper_thresholds = adaptive_lower_thresholds_scaled(coefficients[1], config)
    minimum_magnitude, maximum_magnitude = _magnitude_bounds(learning_output)
    denominator_scale = 1 << (2 * config.data_fractional_bits)

    def delta(y: int, step_index: int) -> int:
        step = config.step_sizes[step_index]
        return round_fraction(
            -step.numerator * dither * y * (1 << config.accumulator_fractional_bits),
            step.denominator * denominator_scale,
            config.update_rounding,
        )

    def saturated(value: int) -> int:
        return min(max(value, 0), config.maximum_accumulator_code)

    next_intervals = []
    for index, accumulator in enumerate(accumulators):
        if index and maximum_magnitude < lower_thresholds[index]:
            change = IntegerInterval(0, 0)
        else:
            endpoints = (delta(learning_output.lower, index),
                         delta(learning_output.upper, index))
            minimum, maximum = min(endpoints), max(endpoints)
            if index and minimum_magnitude < upper_thresholds[index]:
                minimum = min(minimum, 0)
                maximum = max(maximum, 0)
            change = IntegerInterval(minimum, maximum)
        next_intervals.append(IntegerInterval(
            saturated(accumulator.lower + change.lower),
            saturated(accumulator.upper + change.upper),
        ))
    return tuple(next_intervals)


def _dither(symbol: object, mapping: object, stage: int) -> int:
    if symbol is None:
        raise ValueError("online fixed update needs two nonzero dither symbols")
    if symbol not in mapping:
        raise KeyError(f"stage {stage} dither symbol is not configured")
    value = mapping[symbol]
    if value == 0:
        raise ValueError("online fixed update needs nonzero dither copies")
    return value


def _one_step(
    sample: DigitalCalibrationSample,
    state: FixedStateBox,
    config: FixedTwoStageAdaptiveConfig,
) -> tuple[IntegerInterval, FixedStateBox]:
    cascade = config.cascade
    scale = 1 << cascade.data_fractional_bits
    if cascade.backend_weight_scaled % scale:
        raise ValueError("fractional backend weight is not supported")
    dither1 = _dither(sample.stage1_dither_symbol, cascade.dither_code_copies_scaled[0], 1)
    dither2 = _dither(sample.stage2_dither_symbol, cascade.dither_code_copies_scaled[1], 2)
    stage1_coefficients = _coefficient_bounds(state.stage1_accumulators, config.stage1_lms)
    stage2_coefficients = _coefficient_bounds(state.stage2_accumulators, config.stage2_lms)
    stage2_raw = cascade.backend_weight_scaled * sample.backend_centered_code
    stage2_corrected = _corrected_interval(
        IntegerInterval(stage2_raw, stage2_raw),
        cascade.stage2_pwl, stage2_coefficients,
    )
    stage1_raw = stage2_corrected.shifted(
        cascade.stage2_symbol_weight_scaled * sample.stage2_symbol - dither2
    )
    stage1_corrected = _corrected_interval(
        stage1_raw, cascade.stage1_pwl, stage1_coefficients
    )
    output = stage1_corrected.shifted(
        cascade.stage1_symbol_weight_scaled * sample.stage1_symbol
        - dither1 + cascade.output_offset_scaled
    )
    low, high = cascade.output_range_scaled
    if low % scale or high % scale:
        raise ValueError("integer output-code bounds are required")
    codes = IntegerInterval(
        min(max(round_fraction(output.lower, scale, "nearest_even"), low // scale),
            high // scale),
        min(max(round_fraction(output.upper, scale, "nearest_even"), low // scale),
            high // scale),
    )
    next_state = FixedStateBox(
        _updated_bank(
            state.stage1_accumulators, stage1_coefficients,
            stage1_corrected.shifted(-dither1), dither1, config.stage1_lms,
        ),
        _updated_bank(
            state.stage2_accumulators, stage2_coefficients,
            stage2_corrected.shifted(-dither2), dither2, config.stage2_lms,
        ),
    )
    return codes, next_state


def bound_fixed_online_codes(
    observation_sets: Iterable[Iterable[DigitalCalibrationSample]],
    initial_state_box: FixedStateBox,
    config: FixedTwoStageAdaptiveConfig,
) -> FixedOnlineCodeBounds:
    """Join all sample alternatives into one sound accumulator box per step.

    Work and memory grow linearly with record length for bounded alternatives
    per conversion. If an over-approximated state reaches an undefined digital
    domain, raise instead of silently discarding it. No spectrum bound is
    implied until the resulting code intervals are separately scored.
    """
    _validate_bank(initial_state_box.stage1_accumulators, config.stage1_lms)
    _validate_bank(initial_state_box.stage2_accumulators, config.stage2_lms)
    state = initial_state_box
    lower_codes = []
    upper_codes = []
    for conversion_index, alternatives in enumerate(observation_sets):
        samples = tuple(alternatives)
        if not samples:
            raise ValueError("every conversion needs at least one observation")
        if any(not isinstance(sample, DigitalCalibrationSample) for sample in samples):
            raise TypeError("alternatives must be five-field digital samples")
        possible_codes = []
        next_box = None
        for sample in samples:
            try:
                codes, branch_box = _one_step(sample, state, config)
            except (ValueError, KeyError) as error:
                raise ValueError(
                    "possible abstract state or observation has no candidate update "
                    f"at conversion {conversion_index}: {sample}"
                ) from error
            possible_codes.append(codes)
            next_box = branch_box if next_box is None else next_box.hull(branch_box)
        lower_codes.append(min(item.lower for item in possible_codes))
        upper_codes.append(max(item.upper for item in possible_codes))
        assert next_box is not None
        state = next_box
    if not lower_codes:
        raise ValueError("at least one conversion is required")
    return FixedOnlineCodeBounds(tuple(lower_codes), tuple(upper_codes), state)
