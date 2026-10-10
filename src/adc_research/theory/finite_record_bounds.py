"""Conditional SNDR and SFDR bounds from final-code envelopes.

The envelopes must already contain every admissible final-code record.  This
module does not infer them from an analog model or from training observations.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import inf, isfinite, log10, sqrt
from typing import Iterable

import numpy as np


@dataclass(frozen=True)
class DecibelInterval:
    lower: float
    upper: float


@dataclass(frozen=True)
class FiniteRecordToneBounds:
    sample_count: int
    fundamental_bin: int
    rms_code_uncertainty: float
    sndr_db: DecibelInterval
    sfdr_dbc: DecibelInterval


@dataclass(frozen=True)
class BinwiseSfdrBounds:
    """SFDR enclosure using a separate error radius for each FFT bin."""

    sample_count: int
    fundamental_bin: int
    sum_code_halfwidths: float
    sfdr_dbc: DecibelInterval


@dataclass(frozen=True)
class SpectralCodeUncertaintyBudget:
    """Largest RMS code radius allowed by requested lower spectral bounds."""

    sample_count: int
    fundamental_bin: int
    minimum_sndr_db: float | None
    minimum_sfdr_dbc: float | None
    sndr_rms_budget: float | None
    sfdr_rms_budget: float | None
    joint_rms_budget: float


def _ratio_interval(
    numerator_lower: float,
    numerator_upper: float,
    denominator_lower: float,
    denominator_upper: float,
) -> DecibelInterval:
    lower = (
        -inf if numerator_lower <= 0.0 else
        inf if denominator_upper <= 0.0 else
        20.0 * log10(numerator_lower / denominator_upper)
    )
    upper = (
        inf if denominator_lower <= 0.0 else
        -inf if numerator_upper <= 0.0 else
        20.0 * log10(numerator_upper / denominator_lower)
    )
    return DecibelInterval(lower=lower, upper=upper)


def _reference_components(reference: np.ndarray, fundamental_bin: int) -> tuple[float, float, float]:
    spectrum = np.fft.rfft(reference - np.mean(reference)) / reference.size
    bin_rms = np.abs(spectrum)
    bin_rms[1:-1] *= sqrt(2.0)
    bin_rms[0] = 0.0
    fundamental = float(bin_rms[fundamental_bin])
    spur_rms = np.delete(bin_rms[1:], fundamental_bin - 1)
    return fundamental, float(np.linalg.norm(spur_rms)), float(np.max(spur_rms))


def _validated_reference(reference_codes: Iterable[float], fundamental_bin: int) -> np.ndarray:
    reference = np.asarray(tuple(reference_codes), dtype=float)
    if reference.ndim != 1 or reference.size < 4 or reference.size % 2:
        raise ValueError("spectral record length must be even and at least four")
    if not 0 < fundamental_bin < reference.size // 2:
        raise ValueError("fundamental bin must be inside the first Nyquist zone")
    if not np.all(np.isfinite(reference)):
        raise ValueError("reference codes must be finite")
    return reference


def _rms_budget(signal: float, unwanted: float, minimum_db: float) -> float:
    if not isfinite(minimum_db):
        raise ValueError("minimum spectral level must be finite")
    ratio = 10.0 ** (minimum_db / 20.0)
    if not isfinite(ratio) or ratio <= 0.0:
        raise ValueError("minimum spectral level is outside the supported numeric range")
    if signal < ratio * unwanted:
        raise ValueError("reference record already falls below the requested spectral floor")
    return max(0.0, (signal - ratio * unwanted) / (1.0 + ratio))


def code_uncertainty_budget_for_floors(
    reference_codes: Iterable[float],
    *,
    fundamental_bin: int,
    minimum_sndr_db: float | None = None,
    minimum_sfdr_dbc: float | None = None,
) -> SpectralCodeUncertaintyBudget:
    """Invert the finite-record lower-bound formula for evidence planning.

    A covered code envelope with RMS radius at most ``joint_rms_budget``
    guarantees both requested *formula* lower bounds. This does not infer a
    physical code envelope or show that an envelope meeting the budget exists.
    """
    if minimum_sndr_db is None and minimum_sfdr_dbc is None:
        raise ValueError("at least one spectral floor is required")
    reference = _validated_reference(reference_codes, fundamental_bin)
    signal, distortion, spur = _reference_components(reference, fundamental_bin)
    if signal <= 0.0:
        raise ValueError("reference fundamental must have nonzero amplitude")
    sndr_budget = (
        None if minimum_sndr_db is None else
        _rms_budget(signal, distortion, minimum_sndr_db)
    )
    sfdr_budget = (
        None if minimum_sfdr_dbc is None else
        _rms_budget(signal, spur, minimum_sfdr_dbc)
    )
    available = [value for value in (sndr_budget, sfdr_budget) if value is not None]
    return SpectralCodeUncertaintyBudget(
        sample_count=reference.size,
        fundamental_bin=fundamental_bin,
        minimum_sndr_db=minimum_sndr_db,
        minimum_sfdr_dbc=minimum_sfdr_dbc,
        sndr_rms_budget=sndr_budget,
        sfdr_rms_budget=sfdr_budget,
        joint_rms_budget=min(available),
    )


def bound_finite_coherent_tone(
    reference_codes: Iterable[float],
    lower_codes: Iterable[float],
    upper_codes: Iterable[float],
    *,
    fundamental_bin: int,
) -> FiniteRecordToneBounds:
    """Bound the repository's rectangular-window coherent-tone SNDR/SFDR.

    For every sample, the actual final code must lie in [lower, upper].  The
    interval may be conservative and the codes may be correlated across time.
    The input record and tone bin must be fixed. Coefficients may update during
    the record if the envelopes cover every resulting integer-code history;
    see evaluation.online_code_reachability for short candidate records. No
    statistical independence or analog PWL model is assumed.
    """
    reference = _validated_reference(reference_codes, fundamental_bin)
    lower = np.asarray(tuple(lower_codes), dtype=float)
    upper = np.asarray(tuple(upper_codes), dtype=float)
    if lower.shape != reference.shape or upper.shape != reference.shape:
        raise ValueError("reference and code envelopes must be equal-length vectors")
    sample_count = reference.size
    if not (np.all(np.isfinite(lower)) and np.all(np.isfinite(upper))):
        raise ValueError("codes and envelopes must be finite")
    if np.any(lower > reference) or np.any(reference > upper):
        raise ValueError("the reference record must lie inside every code envelope")

    radius = np.maximum(reference - lower, upper - reference)
    uncertainty = float(np.linalg.norm(radius) / sqrt(sample_count))

    fundamental, residual, largest_spur = _reference_components(reference, fundamental_bin)

    signal_lower = max(0.0, fundamental - uncertainty)
    signal_upper = fundamental + uncertainty
    distortion_lower = max(0.0, residual - uncertainty)
    distortion_upper = residual + uncertainty
    spur_lower = max(0.0, largest_spur - uncertainty)
    spur_upper = largest_spur + uncertainty
    return FiniteRecordToneBounds(
        sample_count=sample_count,
        fundamental_bin=fundamental_bin,
        rms_code_uncertainty=uncertainty,
        sndr_db=_ratio_interval(
            signal_lower, signal_upper, distortion_lower, distortion_upper
        ),
        sfdr_dbc=_ratio_interval(
            signal_lower, signal_upper, spur_lower, spur_upper
        ),
    )


def bound_finite_coherent_sfdr_binwise(
    lower_codes: Iterable[float],
    upper_codes: Iterable[float],
    *,
    fundamental_bin: int,
) -> BinwiseSfdrBounds:
    """Bound SFDR from final-code intervals using individual FFT-bin radii.

    This encloses every record in the Cartesian product of the intervals,
    including arbitrarily correlated code histories. It assumes the same
    rectangular-window coherent-tone metric as ``bound_finite_coherent_tone``.
    Floating-point FFT error is not certified by this function.
    """
    lower = np.asarray(tuple(lower_codes), dtype=float)
    upper = np.asarray(tuple(upper_codes), dtype=float)
    if lower.ndim != 1 or upper.shape != lower.shape:
        raise ValueError("code envelopes must be equal-length vectors")
    size = lower.size
    if size < 4 or size % 2 or not 0 < fundamental_bin < size // 2:
        raise ValueError("invalid spectral record length or fundamental bin")
    if not (np.all(np.isfinite(lower)) and np.all(np.isfinite(upper))):
        raise ValueError("code envelopes must be finite")
    if np.any(lower > upper):
        raise ValueError("each lower code must not exceed its upper code")

    midpoint = lower + (upper - lower) / 2.0
    halfwidth_sum = float(np.sum((upper - lower) / 2.0))
    spectrum = np.fft.rfft(midpoint - np.mean(midpoint)) / size
    bin_rms = np.abs(spectrum)
    bin_rms[1:-1] *= sqrt(2.0)
    bin_rms[0] = 0.0

    bin_radius = np.full(size // 2 + 1, sqrt(2.0) * halfwidth_sum / size)
    bin_radius[-1] = halfwidth_sum / size
    signal = float(bin_rms[fundamental_bin])
    signal_radius = float(bin_radius[fundamental_bin])
    spur_bins = np.delete(bin_rms[1:], fundamental_bin - 1)
    spur_radii = np.delete(bin_radius[1:], fundamental_bin - 1)
    spur_lower = float(np.max(np.maximum(0.0, spur_bins - spur_radii)))
    spur_upper = float(np.max(spur_bins + spur_radii))
    return BinwiseSfdrBounds(
        sample_count=size,
        fundamental_bin=fundamental_bin,
        sum_code_halfwidths=halfwidth_sum,
        sfdr_dbc=_ratio_interval(
            max(0.0, signal - signal_radius), signal + signal_radius,
            spur_lower, spur_upper,
        ),
    )
