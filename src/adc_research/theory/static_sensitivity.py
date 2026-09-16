"""Continuous Fourier sensitivity to one moving first-stage flash threshold.

This module treats the final integer-code waveform. Within a fixed phase cell
its code is constant, so the interior contribution to the derivative is zero.
The formulas apply only while the partition topology remains unchanged and the
sine tone crosses the threshold transversely.
"""

from __future__ import annotations

from cmath import exp
from dataclasses import dataclass
from math import asin, isfinite, pi, sqrt
from typing import Iterable

from adc_research.theory.static_transfer import (
    StaticPipelineTheoryConfig,
    StaticTransferPrediction,
)


@dataclass(frozen=True)
class ThresholdSpectrumSensitivity:
    threshold_index: int
    input_boundary: float
    nearest_other_boundary_distance: float
    left_code: int
    right_code: int
    phase_rising: float
    phase_falling: float
    orders: tuple[int, ...]
    derivatives: tuple[complex, ...]

    def coefficient_derivative(self, order: int) -> complex:
        try:
            return self.derivatives[self.orders.index(order)]
        except ValueError as error:
            raise KeyError(f"Fourier order {order} was not requested") from error


def moving_step_fourier_derivatives(
    *,
    input_boundary: float,
    input_boundary_derivative: float,
    code_jump_with_increasing_input: float,
    amplitude_peak: float,
    offset: float = 0.0,
    orders: Iterable[int] = (0, 1, 2, 3),
) -> tuple[tuple[complex, ...], float, float]:
    """Differentiate a two-sided code jump under a sinusoidal input.

    ``code_jump_with_increasing_input`` is right-code minus left-code in the
    input coordinate. Both sine-phase crossings of the boundary are included.
    This is a continuous-period derivative, not a fixed-record DFT derivative.
    """

    requested = tuple(orders)
    if not requested or len(set(requested)) != len(requested):
        raise ValueError("orders must be nonempty and unique")
    if any(not isinstance(order, int) or order < 0 for order in requested):
        raise ValueError("orders must be nonnegative integers")
    scalars = (
        input_boundary,
        input_boundary_derivative,
        code_jump_with_increasing_input,
        amplitude_peak,
        offset,
    )
    if any(not isfinite(value) for value in scalars) or amplitude_peak <= 0:
        raise ValueError("parameters must be finite and amplitude_peak positive")
    normalized = (input_boundary - offset) / amplitude_peak
    if abs(normalized) >= 1:
        raise ValueError("threshold must be crossed transversely inside the tone range")

    phase_rising = asin(normalized) % (2 * pi)
    phase_falling = (pi - asin(normalized)) % (2 * pi)
    phase_speed = input_boundary_derivative / (
        amplitude_peak * sqrt(1 - normalized * normalized)
    )
    scale = -code_jump_with_increasing_input * phase_speed / (2 * pi)
    derivatives = tuple(
        scale
        * (exp(-1j * order * phase_rising) + exp(-1j * order * phase_falling))
        for order in requested
    )
    return derivatives, phase_rising, phase_falling


def first_stage_threshold_sensitivity(
    transfer: StaticTransferPrediction,
    config: StaticPipelineTheoryConfig,
    *,
    threshold_index: int,
    amplitude_peak: float,
    offset: float = 0.0,
    orders: Iterable[int] = (0, 1, 2, 3),
) -> ThresholdSpectrumSensitivity:
    """Predict continuous code-spectrum sensitivity to one threshold offset.

    The effective first-stage threshold is ``nominal + offset_parameter``.
    Its input-coordinate derivative is 1 / auxiliary_gain_ratio. Neighboring
    final codes are taken from the unperturbed complete transfer partition.
    """

    stage = config.stage1
    if not 0 <= threshold_index < len(stage.thresholds):
        raise IndexError("first-stage threshold index is out of range")
    effective = stage.effective_thresholds[threshold_index]
    boundary = (effective - stage.auxiliary_offset) / stage.auxiliary_gain_ratio
    tolerance = 1e-11
    pairs = [
        (left, right)
        for left, right in zip(transfer.segments, transfer.segments[1:])
        if abs(left.input_upper - boundary) <= tolerance
        and abs(right.input_lower - boundary) <= tolerance
    ]
    if len(pairs) != 1:
        raise ValueError("first-stage threshold is not an isolated transfer boundary")
    left, right = pairs[0]
    if left.stage1_symbol == right.stage1_symbol:
        raise ValueError("selected boundary does not change first-stage decision")
    other_edges = (
        edge
        for segment in transfer.segments
        for edge in (segment.input_lower, segment.input_upper)
        if abs(edge - boundary) > tolerance
    )
    nearest = min((abs(edge - boundary) for edge in other_edges), default=float("inf"))
    requested = tuple(orders)
    derivatives, phase_rising, phase_falling = moving_step_fourier_derivatives(
        input_boundary=boundary,
        input_boundary_derivative=1 / stage.auxiliary_gain_ratio,
        code_jump_with_increasing_input=right.output_code - left.output_code,
        amplitude_peak=amplitude_peak,
        offset=offset,
        orders=requested,
    )
    return ThresholdSpectrumSensitivity(
        threshold_index=threshold_index,
        input_boundary=boundary,
        nearest_other_boundary_distance=nearest,
        left_code=left.output_code,
        right_code=right.output_code,
        phase_rising=phase_rising,
        phase_falling=phase_falling,
        orders=requested,
        derivatives=derivatives,
    )
