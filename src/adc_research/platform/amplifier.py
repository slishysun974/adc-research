"""Residue-amplifier models for the sample-wise reference platform."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class AmplifierResult:
    input_value: float
    output_value: float
    nominal_gain: float
    actual_gain: float


@dataclass(frozen=True)
class StaticPwlTruthConfig:
    """Odd-symmetric, monotone PWL truth in normalized output coordinates.

    ``ideal_output_edges`` describe the output of the nominal linear amplifier;
    ``distorted_output_edges`` describe the corresponding physical output after
    gain error and nonlinearity.  Both tuples cover the nonnegative half only
    and must start at zero.  Defining the truth through paired edges keeps it
    independent of the digital correction implementation while making its
    exact inverse identifiable.
    """

    ideal_output_edges: tuple[float, ...]
    distorted_output_edges: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.ideal_output_edges) < 2:
            raise ValueError("PWL truth requires at least one segment")
        if len(self.ideal_output_edges) != len(self.distorted_output_edges):
            raise ValueError("ideal and distorted PWL edges must have equal length")
        for name, edges in (
            ("ideal", self.ideal_output_edges),
            ("distorted", self.distorted_output_edges),
        ):
            if any(not isfinite(edge) for edge in edges):
                raise ValueError(f"{name} PWL edges must be finite")
            if edges[0] != 0:
                raise ValueError(f"{name} PWL edges must start at zero")
            if any(right <= left for left, right in zip(edges, edges[1:])):
                raise ValueError(f"{name} PWL edges must be strictly increasing")

    @property
    def slice_count(self) -> int:
        return len(self.ideal_output_edges) - 1

    @property
    def forward_slopes(self) -> tuple[float, ...]:
        return tuple(
            (distorted_right - distorted_left) / (ideal_right - ideal_left)
            for ideal_left, ideal_right, distorted_left, distorted_right in zip(
                self.ideal_output_edges[:-1],
                self.ideal_output_edges[1:],
                self.distorted_output_edges[:-1],
                self.distorted_output_edges[1:],
                strict=True,
            )
        )


@dataclass(frozen=True)
class PwlAmplifierResult:
    input_value: float
    nominal_output_value: float
    ideal_output_value: float
    output_value: float
    nominal_gain: float
    actual_gain: float
    sign: int
    ideal_output_magnitude: float
    slice_index: int
    local_ideal_output: float
    distorted_slice_offset: float
    forward_slope: float


def amplify_ideal_static(
    residue_input: float,
    *,
    nominal_gain: float,
    actual_gain: float | None = None,
) -> AmplifierResult:
    """Apply a memoryless linear gain; actual_gain supports controlled scans."""

    gain = nominal_gain if actual_gain is None else actual_gain
    if nominal_gain <= 0 or gain <= 0:
        raise ValueError("amplifier gains must be positive")
    return AmplifierResult(
        input_value=residue_input,
        output_value=gain * residue_input,
        nominal_gain=nominal_gain,
        actual_gain=gain,
    )


def amplify_static_pwl_truth(
    residue_input: float,
    *,
    nominal_gain: float,
    truth: StaticPwlTruthConfig,
    actual_gain: float | None = None,
) -> PwlAmplifierResult:
    """Apply a memoryless PWL truth after the configured linear gain.

    The truth is deliberately an analog/platform model.  Oracle correction
    coefficients are derived separately in :mod:`adc_research.calibration`.
    When ``actual_gain`` is provided, linear gain error precedes the PWL shape.
    """

    if not isfinite(residue_input):
        raise ValueError("amplifier input must be finite")
    gain = nominal_gain if actual_gain is None else actual_gain
    if any(not isfinite(value) or value <= 0 for value in (nominal_gain, gain)):
        raise ValueError("amplifier gains must be finite and positive")

    nominal_output = nominal_gain * residue_input
    ideal_output = gain * residue_input
    sign = -1 if ideal_output < 0 else (1 if ideal_output > 0 else 0)
    magnitude = abs(ideal_output)
    maximum = truth.ideal_output_edges[-1]
    if magnitude > maximum:
        raise ValueError("ideal amplifier output lies outside the PWL truth domain")

    slice_index = min(
        bisect_right(truth.ideal_output_edges, magnitude) - 1,
        truth.slice_count - 1,
    )
    ideal_offset = truth.ideal_output_edges[slice_index]
    distorted_offset = truth.distorted_output_edges[slice_index]
    local_ideal = magnitude - ideal_offset
    slope = truth.forward_slopes[slice_index]
    distorted_magnitude = distorted_offset + slope * local_ideal
    output = sign * distorted_magnitude
    return PwlAmplifierResult(
        input_value=residue_input,
        nominal_output_value=nominal_output,
        ideal_output_value=ideal_output,
        output_value=output,
        nominal_gain=nominal_gain,
        actual_gain=gain,
        sign=sign,
        ideal_output_magnitude=magnitude,
        slice_index=slice_index,
        local_ideal_output=local_ideal,
        distorted_slice_offset=distorted_offset,
        forward_slope=slope,
    )
