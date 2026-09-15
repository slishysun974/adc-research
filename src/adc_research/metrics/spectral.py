"""Coherent single-tone FFT metrics for uniformly sampled ADC records."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log10
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class CoherentToneMetrics:
    sample_count: int
    sample_rate_hz: float
    fundamental_bin: int
    fundamental_frequency_hz: float
    harmonic_orders: tuple[int, ...]
    harmonic_bins: tuple[int, ...]
    dc_code: float
    fundamental_rms: float
    fundamental_dbfs: float | None
    sndr_db: float
    snr_db: float
    thd_db: float
    sfdr_dbc: float
    enob_bits: float
    worst_spur_bin: int
    worst_spur_frequency_hz: float


@dataclass(frozen=True)
class CoherentSpectrumResult:
    frequencies_hz: tuple[float, ...]
    rms_power: tuple[float, ...]
    metrics: CoherentToneMetrics


def _power_ratio_db(numerator: float, denominator: float) -> float:
    if numerator < 0 or denominator < 0:
        raise ValueError("power must be nonnegative")
    if numerator == 0:
        return float("-inf")
    if denominator == 0:
        return float("inf")
    return 10.0 * log10(numerator / denominator)


def folded_bin(order: int, fundamental_bin: int, sample_count: int) -> int:
    """Return the Nyquist-zone bin of an aliased harmonic."""

    if order <= 0:
        raise ValueError("harmonic order must be positive")
    if fundamental_bin <= 0 or fundamental_bin >= sample_count // 2:
        raise ValueError("fundamental bin must lie strictly inside the first Nyquist zone")
    remainder = (order * fundamental_bin) % sample_count
    return min(remainder, sample_count - remainder)


def analyze_coherent_tone(
    samples: Iterable[float],
    *,
    sample_rate_hz: float,
    fundamental_bin: int,
    harmonic_orders: tuple[int, ...] = (2, 3, 4, 5),
    full_scale_peak: float | None = None,
) -> CoherentSpectrumResult:
    """Evaluate a rectangular-window coherent single-tone record.

    DC is removed before the FFT.  SINAD includes all non-DC bins except the
    fundamental.  SNR additionally excludes the requested aliased harmonic
    bins.  SFDR uses the largest non-DC bin other than the fundamental.
    """

    values = np.asarray(tuple(samples), dtype=float)
    if values.ndim != 1 or values.size < 4:
        raise ValueError("spectral record must be one-dimensional and nonempty")
    if values.size % 2:
        raise ValueError("spectral record length must be even")
    if not np.all(np.isfinite(values)):
        raise ValueError("spectral samples must be finite")
    if not isfinite(sample_rate_hz) or sample_rate_hz <= 0:
        raise ValueError("sample_rate_hz must be finite and positive")
    sample_count = int(values.size)
    if fundamental_bin <= 0 or fundamental_bin >= sample_count // 2:
        raise ValueError("fundamental bin must lie strictly inside the first Nyquist zone")
    if len(set(harmonic_orders)) != len(harmonic_orders):
        raise ValueError("harmonic orders must be unique")
    if any(order < 2 for order in harmonic_orders):
        raise ValueError("harmonic orders must start at two")

    dc_code = float(np.mean(values))
    centered = values - dc_code
    spectrum = np.fft.rfft(centered) / sample_count
    power = np.abs(spectrum) ** 2
    if sample_count > 2:
        power[1:-1] *= 2.0
    power[0] = 0.0

    harmonic_bins_raw = tuple(
        folded_bin(order, fundamental_bin, sample_count)
        for order in harmonic_orders
    )
    if any(bin_index in (0, fundamental_bin) for bin_index in harmonic_bins_raw):
        raise ValueError("a requested harmonic aliases to DC or the fundamental")
    harmonic_bins = tuple(dict.fromkeys(harmonic_bins_raw))

    fundamental_power = float(power[fundamental_bin])
    if fundamental_power <= 0:
        raise ValueError("fundamental bin has zero power")
    non_dc_power = float(np.sum(power[1:]))
    residual_power = max(non_dc_power - fundamental_power, 0.0)
    harmonic_power = float(sum(power[index] for index in harmonic_bins))
    noise_power = max(residual_power - harmonic_power, 0.0)

    spur_power = power.copy()
    spur_power[0] = 0.0
    spur_power[fundamental_bin] = 0.0
    worst_spur_bin = int(np.argmax(spur_power))
    worst_spur_power = float(spur_power[worst_spur_bin])
    sndr_db = _power_ratio_db(fundamental_power, residual_power)
    snr_db = _power_ratio_db(fundamental_power, noise_power)
    thd_db = _power_ratio_db(harmonic_power, fundamental_power)
    sfdr_dbc = _power_ratio_db(fundamental_power, worst_spur_power)
    fundamental_rms = fundamental_power**0.5
    if full_scale_peak is None:
        fundamental_dbfs = None
    else:
        if not isfinite(full_scale_peak) or full_scale_peak <= 0:
            raise ValueError("full_scale_peak must be finite and positive")
        full_scale_rms_power = full_scale_peak * full_scale_peak / 2.0
        fundamental_dbfs = _power_ratio_db(
            fundamental_power,
            full_scale_rms_power,
        )

    frequencies = np.fft.rfftfreq(sample_count, d=1.0 / sample_rate_hz)
    metrics = CoherentToneMetrics(
        sample_count=sample_count,
        sample_rate_hz=sample_rate_hz,
        fundamental_bin=fundamental_bin,
        fundamental_frequency_hz=float(frequencies[fundamental_bin]),
        harmonic_orders=harmonic_orders,
        harmonic_bins=harmonic_bins_raw,
        dc_code=dc_code,
        fundamental_rms=fundamental_rms,
        fundamental_dbfs=fundamental_dbfs,
        sndr_db=sndr_db,
        snr_db=snr_db,
        thd_db=thd_db,
        sfdr_dbc=sfdr_dbc,
        enob_bits=(sndr_db - 1.76) / 6.02,
        worst_spur_bin=worst_spur_bin,
        worst_spur_frequency_hz=float(frequencies[worst_spur_bin]),
    )
    return CoherentSpectrumResult(
        frequencies_hz=tuple(float(value) for value in frequencies),
        rms_power=tuple(float(value) for value in power),
        metrics=metrics,
    )
