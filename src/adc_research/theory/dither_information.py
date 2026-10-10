"""Conditional dither information and exact moments of a scalar control.

No platform, targets or fitted chip parameters are imported. These identities
do not certify a gated nonlinear, quantized, coupled ADC calibration.
"""

from dataclasses import dataclass
import math


def binary_conditional_correlation(positive_output: float, negative_output: float,
                                   threshold: float | None = None) -> float:
    """E[s*Y*G | fixed undithered input/history], equiprobable s=+/-1."""
    if threshold is not None and threshold < 0:
        raise ValueError("lower magnitude threshold must be nonnegative")
    def gated(value):
        return value if threshold is None or abs(value) >= threshold else 0.0
    return (gated(positive_output)-gated(negative_output))/2


@dataclass(frozen=True)
class ScalarDitherMoments:
    mean_coefficient: float
    coefficient_variance: float
    mean_contraction_per_window: float
    stationary_variance: float | None


def scalar_window_moments(*, gain: float, dither: float, residue_variance: float,
                          step: float, selected: int, multiplier: int, windows: int,
                          initial: float = 1.0) -> ScalarDitherMoments:
    """Exact first/second moments, iid residues independent of iid +/- dither.

    Y=k*gain*(X+D)-D; k'=k-step*multiplier*sum(D*Y), frozen within
    a selected-sample window. No quantization, gate or saturation is included.
    """
    if gain <= 0 or dither <= 0 or step <= 0 or residue_variance < 0:
        raise ValueError("gain, amplitude and step must be positive; variance nonnegative")
    if selected <= 0 or multiplier <= 0 or windows < 0:
        raise ValueError("invalid sample or window count")
    if not all(math.isfinite(v) for v in (gain, dither, residue_variance, step, initial)):
        raise ValueError("finite scalar parameters required")
    alpha = step*multiplier
    c = alpha*selected*dither*dither
    r = 1-c*gain
    v = alpha*alpha*gain*gain*selected*dither*dither*residue_variance
    mean, variance = initial, 0.0
    for _ in range(windows):
        variance = (r*r+v)*variance+v*mean*mean
        mean = r*mean+c
    stationary = v/(gain*gain*(1-r*r-v)) if r*r+v < 1 else None
    return ScalarDitherMoments(mean, variance, r, stationary)
