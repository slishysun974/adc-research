"""Exact offline controls for independent static main/auxiliary transfers.

This specified candidate is not an identified circuit. It imports neither the
sample-wise platform nor the online calibration implementation. Rational SAR
floor is a mathematical control, not a claim about double endpoint arithmetic.
"""

from dataclasses import dataclass
from fractions import Fraction as F


@dataclass(frozen=True)
class CubicTransfer:
    linear: F
    cubic: F = F(0)

    def __post_init__(self):
        if self.linear + 3 * min(self.cubic, F(0)) <= 0:
            raise ValueError("transfer must increase on the declared [-1,1] domain")

    def __call__(self, z: F) -> F:
        if abs(z) > 1:
            raise ValueError("outside declared nominal-output domain")
        return self.linear * z + self.cubic * z**3


def flash(value: F) -> int:
    return sum(value >= F(2 * j - 7, 8) for j in range(8)) - 4


@dataclass(frozen=True)
class StaticTrace:
    q1: int
    q2: int
    z1: F
    main1: F
    auxiliary1: F
    z2: F
    main2: F
    backend: int


def convert(x: F, d1: int, d2: int, main1: CubicTransfer,
            auxiliary1: CubicTransfer, main2: CubicTransfer,
            auxiliary_offset: F = F(0)) -> StaticTrace:
    if not -1 <= x < 1 or d1 not in (-1, 1) or d2 not in (-1, 1):
        raise ValueError("legal input and bipolar dither required")
    q1 = flash(x)
    z1 = 4 * (x - F(q1, 4) + F(d1, 32))
    m = main1(z1)
    a = auxiliary1(z1) + auxiliary_offset
    q2 = flash(a)
    z2 = 4 * (m - F(q2, 4) + F(d2, 32))
    r2 = main2(z2)
    if not -1 <= m < 1 or not -1 <= r2 < 1:
        raise ValueError("main-path overload")
    c3 = (128 * (r2 + 1)).__floor__() - 128
    return StaticTrace(q1, q2, z1, m, a, z2, r2, c3)


def rear_reconstruction_error(trace: StaticTrace, d2: int,
                              corrected_backend: F) -> tuple[F, F]:
    """Return raw1 and its deviation from 512*main1 for any supplied P2.

    corrected_backend may contain quantization, representation and arithmetic
    error. The identity itself requires no inverse or auxiliary matching.
    """
    if d2 not in (-1, 1):
        raise ValueError("bipolar stage-2 dither required")
    delta2 = corrected_backend - 128 * trace.z2
    raw1 = 128 * trace.q2 + corrected_backend - 16 * d2
    return raw1, delta2


def linear_branch_difference(q_difference: int, rear_slope: F,
                             rear_scale: F, epsilon_difference: F,
                             arithmetic_difference: F = F(0)) -> F:
    """Same main input/d2, linear rear, no overload: raw1' - raw1.

    epsilon is SAR centered code minus 128*main2; arithmetic_difference is
    P2(code) minus rear_slope*code in the two branches, differenced.
    """
    return (128 * q_difference * (1 - rear_scale * rear_slope)
            + rear_slope * epsilon_difference + arithmetic_difference)
