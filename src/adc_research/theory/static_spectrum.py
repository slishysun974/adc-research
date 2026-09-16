"""Independent single-tone prediction from a static ADC transfer partition.

The continuous path maps every input-code interval onto exact sine-phase
intervals and integrates selected Fourier-series coefficients in closed form.
The finite-record path evaluates the same frozen transfer at coherent sample
phases and applies the common spectral metric protocol.  Neither path imports
or calls the sample-wise reference platform.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import asin, gcd, isfinite, log10, pi, sin
from typing import Iterable

import numpy as np

from adc_research.metrics.spectral import (
    CoherentSpectrumResult,
    analyze_coherent_tone,
)
from adc_research.theory.static_transfer import StaticTransferPrediction


_PHASE_TOLERANCE = 1e-13
_TWO_PI = 2.0 * pi


@dataclass(frozen=True)
class PhaseInterval:
    """One half-open phase interval with a constant predicted output code."""

    phase_lower: float
    phase_upper: float
    output_code: int
    correctable: bool

    @property
    def width(self) -> float:
        return self.phase_upper - self.phase_lower


@dataclass(frozen=True)
class ContinuousTonePrediction:
    """Exact phase partition and selected continuous Fourier coefficients.

    ``fourier_coefficients[k]`` is

    ``(1 / 2 pi) integral(q(offset + amplitude sin(theta)) exp(-j k theta))``.

    Only explicitly requested nonnegative orders are returned.  Total AC power
    is exact by direct phase integration and Parseval; it therefore also
    includes harmonics that were not requested.
    """

    amplitude_peak: float
    offset: float
    phase_intervals: tuple[PhaseInterval, ...]
    harmonic_orders: tuple[int, ...]
    fourier_coefficients: tuple[complex, ...]
    dc_code: float
    mean_square_code: float
    total_ac_power: float
    correctable_phase_fraction: float

    def coefficient(self, order: int) -> complex:
        try:
            index = self.harmonic_orders.index(order)
        except ValueError as error:
            raise KeyError(f"Fourier order {order} was not requested") from error
        return self.fourier_coefficients[index]

    def single_sided_power(self, order: int) -> float:
        coefficient = self.coefficient(order)
        return abs(coefficient) ** 2 if order == 0 else 2.0 * abs(coefficient) ** 2


@dataclass(frozen=True)
class ContinuousToneMetrics:
    """Infinite-band power metrics for a periodic static-transfer output.

    SFDR is intentionally absent: a discontinuous staircase has infinitely
    many Fourier lines, so an exact global maximum cannot be inferred from a
    finite requested-order set.  The finite coherent prediction supplies the
    protocol-aligned, first-Nyquist-zone SFDR.
    """

    harmonic_orders: tuple[int, ...]
    dc_code: float
    fundamental_rms: float
    fundamental_dbfs: float | None
    total_ac_power: float
    residual_power: float
    harmonic_power: float
    noise_power: float
    sndr_db: float
    snr_db: float
    thd_db: float
    enob_bits: float


@dataclass(frozen=True)
class FiniteCoherentTonePrediction:
    """Theory-side coherent record, complex DFT bins, and common metrics."""

    input_values: tuple[float, ...]
    output_codes: tuple[int, ...]
    complex_spectrum: tuple[complex, ...]
    spectrum: CoherentSpectrumResult


def _validate_tone_range(
    transfer: StaticTransferPrediction,
    amplitude_peak: float,
    offset: float,
) -> None:
    if not isfinite(amplitude_peak) or amplitude_peak <= 0:
        raise ValueError("amplitude_peak must be finite and positive")
    if not isfinite(offset):
        raise ValueError("offset must be finite")
    low, high = transfer.input_range
    if offset - amplitude_peak < low:
        raise ValueError("sine tone exceeds the lower transfer limit")
    if offset + amplitude_peak >= high:
        raise ValueError("sine tone reaches or exceeds the upper transfer limit")


def _unique_sorted(values: Iterable[float]) -> tuple[float, ...]:
    ordered = sorted(values)
    unique: list[float] = []
    for value in ordered:
        if not unique or value - unique[-1] > _PHASE_TOLERANCE:
            unique.append(value)
        else:
            unique[-1] = max(unique[-1], value)
    return tuple(unique)


def sine_phase_intervals(
    transfer: StaticTransferPrediction,
    *,
    amplitude_peak: float,
    offset: float = 0.0,
) -> tuple[PhaseInterval, ...]:
    """Map the static input partition onto one sine period.

    Transfer boundaries at the two sine extrema affect only isolated points and
    therefore do not need to split a positive-measure phase interval.
    """

    _validate_tone_range(transfer, amplitude_peak, offset)
    sine_low = offset - amplitude_peak
    sine_high = offset + amplitude_peak
    phase_cuts = [0.0, _TWO_PI]
    input_boundaries = (segment.input_lower for segment in transfer.segments[1:])
    for boundary in input_boundaries:
        if not sine_low < boundary < sine_high:
            continue
        normalized = (boundary - offset) / amplitude_peak
        angle = asin(min(max(normalized, -1.0), 1.0))
        phase_cuts.extend((angle % _TWO_PI, (pi - angle) % _TWO_PI))

    cuts = _unique_sorted(phase_cuts)
    intervals: list[PhaseInterval] = []
    for lower, upper in zip(cuts, cuts[1:]):
        if upper - lower <= _PHASE_TOLERANCE:
            continue
        midpoint = (lower + upper) / 2.0
        input_value = offset + amplitude_peak * sin(midpoint)
        segment = transfer.segment_at(input_value)
        interval = PhaseInterval(
            phase_lower=lower,
            phase_upper=upper,
            output_code=segment.output_code,
            correctable=segment.correctable,
        )
        if (
            intervals
            and intervals[-1].output_code == interval.output_code
            and intervals[-1].correctable == interval.correctable
            and abs(intervals[-1].phase_upper - lower) <= _PHASE_TOLERANCE
        ):
            previous = intervals[-1]
            intervals[-1] = PhaseInterval(
                phase_lower=previous.phase_lower,
                phase_upper=upper,
                output_code=previous.output_code,
                correctable=previous.correctable,
            )
        else:
            intervals.append(interval)

    coverage = sum(interval.width for interval in intervals)
    if abs(coverage - _TWO_PI) > 1e-11:
        raise RuntimeError("phase intervals do not cover one complete period")
    return tuple(intervals)


def predict_continuous_tone(
    transfer: StaticTransferPrediction,
    *,
    amplitude_peak: float,
    offset: float = 0.0,
    harmonic_orders: Iterable[int] = (0, 1, 2, 3, 4, 5),
) -> ContinuousTonePrediction:
    """Integrate selected Fourier-series coefficients over exact phase cells."""

    orders = tuple(int(order) for order in harmonic_orders)
    if not orders or len(set(orders)) != len(orders):
        raise ValueError("harmonic_orders must be nonempty and unique")
    if any(order < 0 for order in orders):
        raise ValueError("harmonic_orders must be nonnegative")
    intervals = sine_phase_intervals(
        transfer,
        amplitude_peak=amplitude_peak,
        offset=offset,
    )

    coefficients: list[complex] = []
    for order in orders:
        if order == 0:
            integral = sum(
                interval.output_code * interval.width for interval in intervals
            )
            coefficients.append(complex(integral / _TWO_PI))
            continue
        integral = sum(
            interval.output_code
            * (
                np.exp(-1j * order * interval.phase_lower)
                - np.exp(-1j * order * interval.phase_upper)
            )
            / (1j * order)
            for interval in intervals
        )
        coefficients.append(complex(integral / _TWO_PI))

    dc_code = sum(
        interval.output_code * interval.width for interval in intervals
    ) / _TWO_PI
    mean_square = sum(
        interval.output_code**2 * interval.width for interval in intervals
    ) / _TWO_PI
    total_ac_power = max(mean_square - dc_code**2, 0.0)
    correctable_width = sum(
        interval.width for interval in intervals if interval.correctable
    )
    return ContinuousTonePrediction(
        amplitude_peak=amplitude_peak,
        offset=offset,
        phase_intervals=intervals,
        harmonic_orders=orders,
        fourier_coefficients=tuple(coefficients),
        dc_code=dc_code,
        mean_square_code=mean_square,
        total_ac_power=total_ac_power,
        correctable_phase_fraction=correctable_width / _TWO_PI,
    )


def _power_ratio_db(numerator: float, denominator: float) -> float:
    if numerator < 0 or denominator < 0:
        raise ValueError("power must be nonnegative")
    if numerator == 0:
        return float("-inf")
    if denominator == 0:
        return float("inf")
    return 10.0 * log10(numerator / denominator)


def continuous_tone_metrics(
    prediction: ContinuousTonePrediction,
    *,
    harmonic_orders: tuple[int, ...] = (2, 3, 4, 5),
    full_scale_peak: float | None = None,
) -> ContinuousToneMetrics:
    """Derive exact infinite-band SNDR/SNR/THD from phase integrals."""

    if len(set(harmonic_orders)) != len(harmonic_orders):
        raise ValueError("harmonic_orders must be unique")
    if any(order < 2 for order in harmonic_orders):
        raise ValueError("harmonic_orders must start at two")
    fundamental_power = prediction.single_sided_power(1)
    if fundamental_power <= 0:
        raise ValueError("fundamental harmonic has zero power")
    harmonic_power = sum(
        prediction.single_sided_power(order) for order in harmonic_orders
    )
    residual_power = max(prediction.total_ac_power - fundamental_power, 0.0)
    noise_power = max(residual_power - harmonic_power, 0.0)
    fundamental_dbfs = None
    if full_scale_peak is not None:
        if not isfinite(full_scale_peak) or full_scale_peak <= 0:
            raise ValueError("full_scale_peak must be finite and positive")
        fundamental_dbfs = _power_ratio_db(
            fundamental_power,
            full_scale_peak * full_scale_peak / 2.0,
        )
    sndr_db = _power_ratio_db(fundamental_power, residual_power)
    return ContinuousToneMetrics(
        harmonic_orders=harmonic_orders,
        dc_code=prediction.dc_code,
        fundamental_rms=fundamental_power**0.5,
        fundamental_dbfs=fundamental_dbfs,
        total_ac_power=prediction.total_ac_power,
        residual_power=residual_power,
        harmonic_power=harmonic_power,
        noise_power=noise_power,
        sndr_db=sndr_db,
        snr_db=_power_ratio_db(fundamental_power, noise_power),
        thd_db=_power_ratio_db(harmonic_power, fundamental_power),
        enob_bits=(sndr_db - 1.76) / 6.02,
    )


def predict_finite_coherent_tone(
    transfer: StaticTransferPrediction,
    *,
    sample_rate_hz: float,
    sample_count: int,
    fundamental_bin: int,
    amplitude_peak: float,
    offset: float = 0.0,
    phase_radians: float = 0.0,
    harmonic_orders: tuple[int, ...] = (2, 3, 4, 5),
    full_scale_peak: float | None = None,
    require_full_phase_set: bool = True,
) -> FiniteCoherentTonePrediction:
    """Predict a finite coherent FFT record without calling the platform."""

    _validate_tone_range(transfer, amplitude_peak, offset)
    if not isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be finite and positive")
    if sample_count < 4 or sample_count % 2:
        raise ValueError("sample_count must be an even integer of at least four")
    if fundamental_bin <= 0 or fundamental_bin >= sample_count // 2:
        raise ValueError("fundamental_bin must lie inside the first Nyquist zone")
    if require_full_phase_set and gcd(fundamental_bin, sample_count) != 1:
        raise ValueError("fundamental_bin and sample_count must be coprime")
    if not isfinite(phase_radians):
        raise ValueError("phase_radians must be finite")

    indices = np.arange(sample_count, dtype=float)
    phases = (
        _TWO_PI * fundamental_bin * indices / sample_count + phase_radians
    )
    input_values_array = offset + amplitude_peak * np.sin(phases)
    output_codes = tuple(
        transfer.code_at(float(value)) for value in input_values_array
    )
    spectrum = analyze_coherent_tone(
        output_codes,
        sample_rate_hz=sample_rate_hz,
        fundamental_bin=fundamental_bin,
        harmonic_orders=harmonic_orders,
        full_scale_peak=full_scale_peak,
    )
    centered = np.asarray(output_codes, dtype=float) - spectrum.metrics.dc_code
    complex_spectrum = np.fft.rfft(centered) / sample_count
    return FiniteCoherentTonePrediction(
        input_values=tuple(float(value) for value in input_values_array),
        output_codes=output_codes,
        complex_spectrum=tuple(complex(value) for value in complex_spectrum),
        spectrum=spectrum,
    )
