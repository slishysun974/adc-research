"""Explicit exact non-PWL counterexamples, not physical transfer assumptions."""

from fractions import Fraction as F
from adc_research.theory.paired_dither_conditions import PairedDitherObservation as Pair


def periodic_cubic_error(value, half_period=F(64), scale=F(8)):
    """C1 odd periodic cubic: q in [-L,L), h=a*(q/L)*(1-(q/L)^2).

    Its derivative is in [-2a/L,a/L]. Thus g=t+h is strictly increasing
    when 0<a<L/2. Endpoint values and endpoint derivatives agree.
    """
    if any(not isinstance(v, F) for v in (value, half_period, scale)):
        raise TypeError("exact values required")
    if half_period <= 0 or not 0 < scale < half_period/2:
        raise ValueError("positive half period and monotone-transfer scale required")
    period = 2*half_period
    q = value-period*((value+half_period)//period)
    z = q/half_period
    return scale*z*(1-z*z)


def periodic_counterexample(centers, magnitudes=(F(64),), half_period=F(64), scale=F(8)):
    pairs, targets = [], []
    for center in centers:
        for d in magnitudes:
            plus, minus = center+d, center-d
            raw_plus = plus+periodic_cubic_error(plus, half_period, scale)
            raw_minus = minus+periodic_cubic_error(minus, half_period, scale)
            pairs.append(Pair(raw_plus, raw_minus, d))
            targets.append(center)
    return tuple(pairs), tuple(targets)
