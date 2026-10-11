"""Independent offline equations for the specified three-path two-phase ADC.

No platform or online calibration imports. Scalars can be floats (declared
operation order) or Fractions (exact mathematical controls). This candidate
does not identify circuit poles, reset semantics or chip parameters.
"""

from dataclasses import dataclass
from fractions import Fraction as F
from math import floor


def phase(previous, target, amplification, tracking, reset=0):
    if not 0 <= amplification < 1 or not 0 <= tracking <= 1:
        raise ValueError("invalid phase factors")
    start = reset + tracking * (previous - reset)
    return start, target + amplification * (start - target)


def expanded(previous, target, amplification, tracking, reset=0):
    return ((1 - amplification) * target
            + amplification * (1 - tracking) * reset
            + amplification * tracking * previous)


def unroll(targets, initial, amplification, tracking, reset=0):
    """Finite convolution, evaluated independently of the step recurrence."""
    kappa = amplification * tracking
    n = len(targets)
    return kappa**n * initial + sum(
        kappa**(n - 1 - j) * ((1 - amplification) * value
                              + amplification * (1 - tracking) * reset)
        for j, value in enumerate(targets))


def flash(value):
    return sum(value >= F(2 * j - 7, 8) for j in range(8)) - 4


@dataclass(frozen=True)
class DynamicTrace:
    q1: int
    q2: int
    backend: int
    nominal: tuple
    starts: tuple
    targets: tuple
    outputs: tuple


def convert(x, d1, d2, case, factors, tracking, previous, resets=None):
    """Advance ALL three analog paths by one conversion, then quantize.

    case contains stage1/auxiliary/stage2 (linear,cubic) coefficients. Their
    polynomial domain is the nominal amplified residue [-1,1].
    """
    if not -1 <= x < 1 or d1 not in (-1, 1) or d2 not in (-1, 1):
        raise ValueError("legal input and bipolar dither required")
    if len(previous) != 3 or len(factors) != 3:
        raise ValueError("three physical paths required")
    # Divide integers exactly for Fractions, but retain the platform's native
    # double operation order in the floating reference.
    scalar = F if isinstance(x, F) else float
    resets = (scalar(0),) * 3 if resets is None else resets
    q1 = flash(x)
    z1 = 4 * (x - scalar(q1) / 4 + scalar(d1) / 32)
    if abs(z1) > 1:
        raise ValueError("stage1 nominal residue outside cubic domain")
    a1, b1 = case['stage1']; aa, ba = case['auxiliary']; a2, b2 = case['stage2']
    t1 = a1 * z1 + b1 * z1**3
    ta = aa * z1 + ba * z1**3
    sm, m = phase(previous[0], t1, factors[0], tracking, resets[0])
    sa, aux = phase(previous[1], ta, factors[1], tracking, resets[1])
    q2 = flash(aux)
    z2 = 4 * (m - scalar(q2) / 4 + scalar(d2) / 32)
    if abs(z2) > 1:
        raise ValueError("stage2 nominal residue outside cubic domain")
    t2 = a2 * z2 + b2 * z2**3
    s2, rear = phase(previous[2], t2, factors[2], tracking, resets[2])
    if not -1 <= m < 1 or not -1 <= rear < 1:
        raise ValueError("main-path overload")
    backend = floor((rear + 1) * 128) - 128
    return DynamicTrace(q1, q2, backend, (z1, z2), (sm, sa, s2),
                        (t1, ta, t2), (m, aux, rear))


def scalar_current_correlation(gain, inverse, amplification, dither_power):
    """E[D*(K*r-D)] under centered current D independent of X and past r.

    Ungated, unquantized affine scalar control ONLY; not a two-stage mean root.
    """
    return (inverse * (1 - amplification) * gain - 1) * dither_power
