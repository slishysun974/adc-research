"""Exact offline comparator-offset controls, independent of the platform.

Offsets move decision boundaries only; CDAC levels and analog transfers are
unchanged. This is a specified candidate, not a measured offset distribution.
"""
from dataclasses import dataclass
from fractions import Fraction as F

from .static_auxiliary_mismatch import CubicTransfer, StaticTrace


def thresholds(offsets: tuple[F, ...]) -> tuple[F, ...]:
    if len(offsets) != 8:
        raise ValueError('eight comparator offsets required')
    result = tuple(F(2*j-7, 8)+v for j, v in enumerate(offsets))
    if any(a >= b for a, b in zip(result, result[1:])):
        raise ValueError('effective thresholds must remain ordered')
    if not (-1 < result[0] and result[-1] < 1):
        raise ValueError('thresholds must lie inside the input domain')
    return result


def flash(value: F, offsets: tuple[F, ...]) -> int:
    return sum(value >= t for t in thresholds(offsets))-4


def convert(x: F, d1: int, d2: int, first: CubicTransfer, second: CubicTransfer,
            offsets1: tuple[F, ...], offsets2: tuple[F, ...]) -> StaticTrace:
    if not -1 <= x < 1 or d1 not in (-1, 1) or d2 not in (-1, 1):
        raise ValueError('legal input and bipolar tags required')
    q1 = flash(x, offsets1)
    z1 = 4*(x-F(q1, 4)+F(d1, 32)); m = first(z1)
    q2 = flash(m, offsets2)
    z2 = 4*(m-F(q2, 4)+F(d2, 32)); r2 = second(z2)
    if not -1 <= m < 1 or not -1 <= r2 < 1:
        raise ValueError('main-path overload')
    backend = (128*(r2+1)).__floor__()-128
    return StaticTrace(q1, q2, z1, m, m, z2, r2, backend)


@dataclass(frozen=True)
class SafetyBounds:
    residual_radius1: F
    residual_radius2: F
    nominal_output_radius1: F
    main_radius1: F
    nominal_output_radius2: F
    main_radius2: F
    backend_magnitude: int
    unit_front_raw_magnitude: F


def safety(first: CubicTransfer, second: CubicTransfer,
           offsets1: tuple[F, ...], offsets2: tuple[F, ...]) -> SafetyBounds:
    thresholds(offsets1); thresholds(offsets2)
    # Conservative all-cell radii, including the two truncated edge cells.
    r1 = F(1, 8)+max(map(abs, offsets1)); r2 = F(1, 8)+max(map(abs, offsets2))
    z1, z2 = 4*r1+F(1, 8), 4*r2+F(1, 8)
    if z1 > 1 or z2 > 1:
        raise ValueError('outside declared amplifier domains')
    m1, m2 = first(z1), second(z2)
    if m1 >= 1 or m2 >= 1:
        raise ValueError('main-path range not protected')
    # SAR floor error lies in [-1,0); no universal 1/12 noise assumption.
    be = (128*m2).__ceil__()
    rear_error = 128*(abs(second.linear-1)*z2+abs(second.cubic)*z2**3)+1
    return SafetyBounds(r1, r2, z1, m1, z2, m2, be, 512*m1+rear_error)


def branch_shift(q1_difference: int, q2_difference: int, main_difference: F) -> tuple[F, F]:
    """Same input/tags and unchanged CDAC: z1 shift, z2 shift."""
    return F(-q1_difference), 4*main_difference-q2_difference
