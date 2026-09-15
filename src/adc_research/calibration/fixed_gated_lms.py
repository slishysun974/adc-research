"""Fixed-point gated LMS with a wider coefficient-update accumulator.

The correction interface remains unsigned Q1.10.  The accumulator fractional
resolution, update rounding, threshold rounding, and saturation behavior are
explicit research assumptions because Gu et al. do not report these details.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from adc_research.calibration.fixed_point import (
    RoundingMode,
    UnsignedFixedFormat,
    fixed_to_float,
    round_fraction,
    round_shift,
)


@dataclass(frozen=True)
class FixedGatedLmsConfig:
    """Configuration for one fixed-point symmetric PWL coefficient bank."""

    slice_width_scaled: int
    step_sizes: tuple[Fraction, ...]
    coefficient_format: UnsignedFixedFormat = UnsignedFixedFormat(11, 10)
    data_fractional_bits: int = 3
    accumulator_fractional_bits: int = 22
    update_rounding: RoundingMode = "nearest_even"
    coefficient_export_rounding: RoundingMode = "nearest_even"
    threshold_rounding: RoundingMode = "nearest_even"

    def __post_init__(self) -> None:
        if self.slice_width_scaled <= 0:
            raise ValueError("slice_width_scaled must be positive")
        if not self.step_sizes:
            raise ValueError("at least one step size is required")
        if any(not isinstance(step, Fraction) or step <= 0 for step in self.step_sizes):
            raise ValueError("step sizes must be positive Fraction values")
        if self.data_fractional_bits < 0:
            raise ValueError("data_fractional_bits must be nonnegative")
        if (
            self.accumulator_fractional_bits
            < self.coefficient_format.fractional_bits
        ):
            raise ValueError(
                "accumulator fractional bits must not be smaller than "
                "coefficient fractional bits"
            )

    @property
    def coefficient_count(self) -> int:
        return len(self.step_sizes)

    @property
    def guard_fractional_bits(self) -> int:
        return (
            self.accumulator_fractional_bits
            - self.coefficient_format.fractional_bits
        )

    @property
    def maximum_accumulator_code(self) -> int:
        return (
            self.coefficient_format.maximum_code
            << self.guard_fractional_bits
        )


@dataclass(frozen=True)
class FixedGatedLmsState:
    """Persistent accumulator values and fixed-point update counters."""

    accumulator_codes: tuple[int, ...]
    gate_counts: tuple[int, ...]
    nonzero_update_counts: tuple[int, ...]
    coefficient_change_counts: tuple[int, ...]
    sample_count: int = 0

    def __post_init__(self) -> None:
        count = len(self.accumulator_codes)
        if count == 0:
            raise ValueError("at least one accumulator is required")
        if not all(
            len(values) == count
            for values in (
                self.gate_counts,
                self.nonzero_update_counts,
                self.coefficient_change_counts,
            )
        ):
            raise ValueError("all state vectors must have the same length")
        if any(value < 0 for value in self.accumulator_codes):
            raise ValueError("accumulator codes must be nonnegative")
        if any(
            value < 0
            for values in (
                self.gate_counts,
                self.nonzero_update_counts,
                self.coefficient_change_counts,
            )
            for value in values
        ):
            raise ValueError("state counters must be nonnegative")
        if self.sample_count < 0:
            raise ValueError("sample count must be nonnegative")

    @classmethod
    def unity(cls, config: FixedGatedLmsConfig) -> "FixedGatedLmsState":
        count = config.coefficient_count
        return cls(
            accumulator_codes=(1 << config.accumulator_fractional_bits,) * count,
            gate_counts=(0,) * count,
            nonzero_update_counts=(0,) * count,
            coefficient_change_counts=(0,) * count,
        )


@dataclass(frozen=True)
class FixedGatedLmsUpdate:
    """Trace for one simultaneous fixed-point gated-LMS update."""

    accumulator_codes_before: tuple[int, ...]
    coefficient_codes_before: tuple[int, ...]
    adaptive_lower_thresholds_scaled: tuple[int, ...]
    gate_mask: tuple[bool, ...]
    requested_accumulator_deltas: tuple[int, ...]
    applied_accumulator_deltas: tuple[int, ...]
    accumulator_codes_after: tuple[int, ...]
    coefficient_codes_after: tuple[int, ...]
    dither_code_scaled: int
    corrected_output_scaled: int
    state: FixedGatedLmsState


def exported_coefficient_codes(
    state: FixedGatedLmsState,
    config: FixedGatedLmsConfig,
) -> tuple[int, ...]:
    """Round accumulator values to the configured coefficient interface."""

    if len(state.accumulator_codes) != config.coefficient_count:
        raise ValueError("state and config coefficient counts must match")
    maximum = config.coefficient_format.maximum_code
    return tuple(
        min(
            max(
                round_shift(
                    value,
                    config.guard_fractional_bits,
                    config.coefficient_export_rounding,
                ),
                0,
            ),
            maximum,
        )
        for value in state.accumulator_codes
    )


def accumulator_values(
    state: FixedGatedLmsState,
    config: FixedGatedLmsConfig,
) -> tuple[float, ...]:
    """Return accumulator values in coefficient units for reporting."""

    return tuple(
        fixed_to_float(value, config.accumulator_fractional_bits)
        for value in state.accumulator_codes
    )


def adaptive_lower_thresholds_scaled(
    coefficient_codes: tuple[int, ...],
    config: FixedGatedLmsConfig,
) -> tuple[int, ...]:
    """Form Q-data thresholds from the pre-update coefficient interface."""

    if len(coefficient_codes) != config.coefficient_count:
        raise ValueError("coefficient codes and config counts must match")
    thresholds = [0]
    cumulative_codes = 0
    coefficient_fractional_bits = config.coefficient_format.fractional_bits
    for coefficient_code in coefficient_codes[:-1]:
        cumulative_codes += coefficient_code
        thresholds.append(
            round_shift(
                config.slice_width_scaled * cumulative_codes,
                coefficient_fractional_bits,
                config.threshold_rounding,
            )
        )
    return tuple(thresholds)


def _accumulator_delta(
    step_size: Fraction,
    dither_code_scaled: int,
    corrected_output_scaled: int,
    config: FixedGatedLmsConfig,
) -> int:
    numerator = (
        -step_size.numerator
        * dither_code_scaled
        * corrected_output_scaled
        * (1 << config.accumulator_fractional_bits)
    )
    denominator = step_size.denominator * (
        1 << (2 * config.data_fractional_bits)
    )
    return round_fraction(numerator, denominator, config.update_rounding)


def update_fixed(
    state: FixedGatedLmsState,
    *,
    dither_code_scaled: int,
    corrected_output_scaled: int,
    config: FixedGatedLmsConfig,
) -> FixedGatedLmsUpdate:
    """Apply one lower-bound-only update using integer observations."""

    if len(state.accumulator_codes) != config.coefficient_count:
        raise ValueError("state and config coefficient counts must match")
    if any(value > config.maximum_accumulator_code for value in state.accumulator_codes):
        raise ValueError("state accumulator lies outside configured range")

    coefficient_codes_before = exported_coefficient_codes(state, config)
    thresholds = adaptive_lower_thresholds_scaled(
        coefficient_codes_before,
        config,
    )
    magnitude = abs(corrected_output_scaled)
    gates = tuple(
        True if index == 0 else magnitude >= threshold
        for index, threshold in enumerate(thresholds)
    )
    requested_deltas = tuple(
        _accumulator_delta(
            step,
            dither_code_scaled,
            corrected_output_scaled,
            config,
        )
        if gate
        else 0
        for step, gate in zip(config.step_sizes, gates, strict=True)
    )
    accumulator_codes_after = tuple(
        min(
            max(value + delta, 0),
            config.maximum_accumulator_code,
        )
        for value, delta in zip(
            state.accumulator_codes,
            requested_deltas,
            strict=True,
        )
    )
    applied_deltas = tuple(
        after - before
        for before, after in zip(
            state.accumulator_codes,
            accumulator_codes_after,
            strict=True,
        )
    )
    provisional_state = FixedGatedLmsState(
        accumulator_codes=accumulator_codes_after,
        gate_counts=state.gate_counts,
        nonzero_update_counts=state.nonzero_update_counts,
        coefficient_change_counts=state.coefficient_change_counts,
        sample_count=state.sample_count,
    )
    coefficient_codes_after = exported_coefficient_codes(provisional_state, config)
    next_state = FixedGatedLmsState(
        accumulator_codes=accumulator_codes_after,
        gate_counts=tuple(
            count + int(gate)
            for count, gate in zip(state.gate_counts, gates, strict=True)
        ),
        nonzero_update_counts=tuple(
            count + int(delta != 0)
            for count, delta in zip(
                state.nonzero_update_counts,
                applied_deltas,
                strict=True,
            )
        ),
        coefficient_change_counts=tuple(
            count + int(before != after)
            for count, before, after in zip(
                state.coefficient_change_counts,
                coefficient_codes_before,
                coefficient_codes_after,
                strict=True,
            )
        ),
        sample_count=state.sample_count + 1,
    )
    return FixedGatedLmsUpdate(
        accumulator_codes_before=state.accumulator_codes,
        coefficient_codes_before=coefficient_codes_before,
        adaptive_lower_thresholds_scaled=thresholds,
        gate_mask=gates,
        requested_accumulator_deltas=requested_deltas,
        applied_accumulator_deltas=applied_deltas,
        accumulator_codes_after=accumulator_codes_after,
        coefficient_codes_after=coefficient_codes_after,
        dither_code_scaled=dither_code_scaled,
        corrected_output_scaled=corrected_output_scaled,
        state=next_state,
    )
