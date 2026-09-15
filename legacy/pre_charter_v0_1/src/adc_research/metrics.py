"""Coherent-record spectral metrics for the behavioral ADC experiments."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
from numpy.typing import NDArray


FloatArray = NDArray[np.float64]


@dataclass(frozen=True)
class SpectrumMetrics:
    sfdr_db: float
    sndr_db: float
    enob_bits: float
    signal_bin: int
    worst_spur_bin: int
    worst_spur_dbc: float

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


def spectrum_metrics(output: FloatArray, tone_bin: int) -> SpectrumMetrics:
    """Return single-bin coherent SFDR and SNDR metrics.

    The caller must provide a coherent, unwindowed record.  DC is excluded.
    The Nyquist bin is retained when present.  This routine is deliberately
    explicit so later IEEE-1241 protocol refinements can be versioned.
    """

    values = np.asarray(output, dtype=float)
    if values.ndim != 1 or values.size < 16:
        raise ValueError("output must be a one-dimensional record of length >= 16.")
    if tone_bin <= 0 or tone_bin >= values.size // 2:
        raise ValueError("tone_bin must be inside the positive Nyquist band.")

    centered = values - np.mean(values)
    spectrum = np.fft.rfft(centered)
    power = np.abs(spectrum) ** 2
    signal_power = float(power[tone_bin])
    if signal_power <= 0.0:
        raise ValueError("The requested signal bin has zero power.")

    spur_power = power.copy()
    spur_power[0] = 0.0
    spur_power[tone_bin] = 0.0
    worst_spur_bin = int(np.argmax(spur_power))
    worst_spur_power = float(spur_power[worst_spur_bin])

    noise_and_distortion = float(np.sum(spur_power))
    tiny = np.finfo(float).tiny
    sfdr_db = 10.0 * np.log10(signal_power / max(worst_spur_power, tiny))
    sndr_db = 10.0 * np.log10(signal_power / max(noise_and_distortion, tiny))
    return SpectrumMetrics(
        sfdr_db=float(sfdr_db),
        sndr_db=float(sndr_db),
        enob_bits=float((sndr_db - 1.76) / 6.02),
        signal_bin=tone_bin,
        worst_spur_bin=worst_spur_bin,
        worst_spur_dbc=float(-sfdr_db),
    )

