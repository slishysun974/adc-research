"""Floating-reference gated-LMS extraction for PWL coefficients.

The update follows Gu et al.'s lower-bound-only gating rule.  The first
coefficient uses every sample.  Coefficient ``i > 1`` is updated only when the
absolute corrected output is at or above the cumulative, coefficient-dependent
boundary formed by the preceding slices.  All gates and thresholds are
evaluated from the pre-update state so the coefficient bank changes
simultaneously for one sample.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence


@dataclass(frozen=True)
class GatedLmsConfig:
    """Configuration for one symmetric PWL coefficient bank."""

    slice_width: float
    step_sizes: tuple[float, ...]
    coefficient_bounds: tuple[float, float] = (0.0, 2.0)

    def __post_init__(self) -> None:
        if not isfinite(self.slice_width) or self.slice_width <= 0:
            raise ValueError("slice_width must be finite and positive")
        if not self.step_sizes:
            raise ValueError("at least one step size is required")
        if any(not isfinite(step) or step <= 0 for step in self.step_sizes):
            raise ValueError("step sizes must be finite and positive")
        low, high = self.coefficient_bounds
        if not (isfinite(low) and isfinite(high)) or high <= low:
            raise ValueError("coefficient bounds must be finite and increasing")

    @classmethod
    def from_sequence(
        cls,
        slice_width: float,
        step_sizes: Sequence[float],
        *,
        coefficient_bounds: tuple[float, float] = (0.0, 2.0),
    ) -> "GatedLmsConfig":
        return cls(slice_width, tuple(step_sizes), coefficient_bounds)

    @property
    def coefficient_count(self) -> int:
        return len(self.step_sizes)


@dataclass(frozen=True)
class GatedLmsState:
    """Persistent floating coefficients and per-slice excitation counts."""

    coefficients: tuple[float, ...]
    gate_counts: tuple[int, ...]
    sample_count: int = 0

    def __post_init__(self) -> None:
        if not self.coefficients:
            raise ValueError("at least one coefficient is required")
        if len(self.gate_counts) != len(self.coefficients):
            raise ValueError("gate counts must match coefficients")
        if any(not isfinite(value) for value in self.coefficients):
            raise ValueError("coefficients must be finite")
        if any(count < 0 for count in self.gate_counts):
            raise ValueError("gate counts must be nonnegative")
        if self.sample_count < 0:
            raise ValueError("sample count must be nonnegative")

    @classmethod
    def unity(cls, coefficient_count: int) -> "GatedLmsState":
        if coefficient_count <= 0:
            raise ValueError("coefficient_count must be positive")
        return cls(
            coefficients=(1.0,) * coefficient_count,
            gate_counts=(0,) * coefficient_count,
        )


@dataclass(frozen=True)
class GatedLmsUpdate:
    """Trace for one simultaneous gated-LMS coefficient update."""

    coefficients_before: tuple[float, ...]
    adaptive_lower_thresholds: tuple[float, ...]
    gate_mask: tuple[bool, ...]
    coefficient_deltas: tuple[float, ...]
    coefficients_after: tuple[float, ...]
    dither_code: float
    corrected_output: float
    state: GatedLmsState


@dataclass(frozen=True)
class GatedLmsBlockUpdate:
    """Trace for one block-mean gated-LMS coefficient update.

    The adaptive thresholds and coefficients are held fixed throughout the
    block. Each coefficient uses the arithmetic mean of its gated
    ``dither_code * corrected_output`` products, with inactive observations
    contributing zero. This estimates the same unconditional gated
    correlation used by the instantaneous update.
    """

    coefficients_before: tuple[float, ...]
    adaptive_lower_thresholds: tuple[float, ...]
    observation_count: int
    gate_counts: tuple[int, ...]
    mean_gated_products: tuple[float, ...]
    coefficient_deltas: tuple[float, ...]
    coefficients_after: tuple[float, ...]
    state: GatedLmsState


def adaptive_lower_thresholds(
    coefficients: Sequence[float],
    slice_width: float,
) -> tuple[float, ...]:
    """Return ``(0, b1, ..., bN-1)`` from the current PWL coefficients."""

    values = tuple(coefficients)
    if not values:
        raise ValueError("at least one coefficient is required")
    if any(not isfinite(value) for value in values):
        raise ValueError("coefficients must be finite")
    if not isfinite(slice_width) or slice_width <= 0:
        raise ValueError("slice_width must be finite and positive")

    thresholds = [0.0]
    cumulative = 0.0
    for coefficient in values[:-1]:
        cumulative += slice_width * coefficient
        thresholds.append(cumulative)
    return tuple(thresholds)


def update(
    state: GatedLmsState,
    *,
    dither_code: float,
    corrected_output: float,
    config: GatedLmsConfig,
) -> GatedLmsUpdate:
    """Apply one lower-bound-only gated-LMS update.

    ``corrected_output`` is the PWL-corrected output after subtraction of the
    corresponding digital dither copy.  Equality belongs to the active range,
    matching the half-open convention selected for the behavioral model.
    """

    if len(state.coefficients) != config.coefficient_count:
        raise ValueError("state and config coefficient counts must match")
    if any(
        coefficient < config.coefficient_bounds[0]
        or coefficient > config.coefficient_bounds[1]
        for coefficient in state.coefficients
    ):
        raise ValueError("state coefficient lies outside configured bounds")
    if not isfinite(dither_code) or not isfinite(corrected_output):
        raise ValueError("dither and corrected output must be finite")

    thresholds = adaptive_lower_thresholds(
        state.coefficients,
        config.slice_width,
    )
    magnitude = abs(corrected_output)
    gates = tuple(
        True if index == 0 else magnitude >= threshold
        for index, threshold in enumerate(thresholds)
    )
    low, high = config.coefficient_bounds
    raw_deltas = tuple(
        -step * dither_code * corrected_output if gate else 0.0
        for step, gate in zip(config.step_sizes, gates, strict=True)
    )
    coefficients_after = tuple(
        min(max(coefficient + delta, low), high)
        for coefficient, delta in zip(
            state.coefficients,
            raw_deltas,
            strict=True,
        )
    )
    applied_deltas = tuple(
        after - before
        for before, after in zip(
            state.coefficients,
            coefficients_after,
            strict=True,
        )
    )
    gate_counts = tuple(
        count + int(gate)
        for count, gate in zip(state.gate_counts, gates, strict=True)
    )
    next_state = GatedLmsState(
        coefficients=coefficients_after,
        gate_counts=gate_counts,
        sample_count=state.sample_count + 1,
    )
    return GatedLmsUpdate(
        coefficients_before=state.coefficients,
        adaptive_lower_thresholds=thresholds,
        gate_mask=gates,
        coefficient_deltas=applied_deltas,
        coefficients_after=coefficients_after,
        dither_code=dither_code,
        corrected_output=corrected_output,
        state=next_state,
    )


def update_block_mean(
    state: GatedLmsState,
    *,
    observations: Sequence[tuple[float, float]],
    config: GatedLmsConfig,
) -> GatedLmsBlockUpdate:
    """Apply one update from a block-mean gated correlation estimate.

    ``observations`` contains ``(dither_code, corrected_output)`` pairs. The
    coefficient bank is not changed between observations in the block. Gate
    support is evaluated with the pre-update adaptive thresholds, and the
    resulting correlation sum is divided by the full block length rather than
    by the number of active observations.
    """

    if len(state.coefficients) != config.coefficient_count:
        raise ValueError("state and config coefficient counts must match")
    if any(
        coefficient < config.coefficient_bounds[0]
        or coefficient > config.coefficient_bounds[1]
        for coefficient in state.coefficients
    ):
        raise ValueError("state coefficient lies outside configured bounds")
    values = tuple(observations)
    if not values:
        raise ValueError("block update requires at least one observation")
    if any(
        not isfinite(dither_code) or not isfinite(corrected_output)
        for dither_code, corrected_output in values
    ):
        raise ValueError("dither and corrected output must be finite")

    thresholds = adaptive_lower_thresholds(
        state.coefficients,
        config.slice_width,
    )
    block_gate_counts = [0] * config.coefficient_count
    product_sums = [0.0] * config.coefficient_count
    for dither_code, corrected_output in values:
        magnitude = abs(corrected_output)
        for index, threshold in enumerate(thresholds):
            gate = index == 0 or magnitude >= threshold
            if gate:
                block_gate_counts[index] += 1
                product_sums[index] += dither_code * corrected_output

    observation_count = len(values)
    mean_products = tuple(value / observation_count for value in product_sums)
    low, high = config.coefficient_bounds
    raw_deltas = tuple(
        -step * mean_product
        for step, mean_product in zip(
            config.step_sizes,
            mean_products,
            strict=True,
        )
    )
    coefficients_after = tuple(
        min(max(coefficient + delta, low), high)
        for coefficient, delta in zip(
            state.coefficients,
            raw_deltas,
            strict=True,
        )
    )
    applied_deltas = tuple(
        after - before
        for before, after in zip(
            state.coefficients,
            coefficients_after,
            strict=True,
        )
    )
    gate_counts = tuple(
        previous + block
        for previous, block in zip(
            state.gate_counts,
            block_gate_counts,
            strict=True,
        )
    )
    next_state = GatedLmsState(
        coefficients=coefficients_after,
        gate_counts=gate_counts,
        sample_count=state.sample_count + observation_count,
    )
    return GatedLmsBlockUpdate(
        coefficients_before=state.coefficients,
        adaptive_lower_thresholds=thresholds,
        observation_count=observation_count,
        gate_counts=tuple(block_gate_counts),
        mean_gated_products=mean_products,
        coefficient_deltas=applied_deltas,
        coefficients_after=coefficients_after,
        state=next_state,
    )
