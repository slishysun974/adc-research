"""Exact, offline checks of the static Gu candidate's numerical contract.

No platform, calibration implementation, analog truth or oracle imports.
The caller supplies a digital word and declared coefficients. Fractional
backend words are allowed ONLY for offline continuous-reference controls.
"""

from dataclasses import dataclass
from fractions import Fraction as F


def nearest_even(value: F) -> int:
    """Independent rational rounding, including negative ties."""
    lower = value.numerator // value.denominator
    remainder = value - lower
    return lower + int(remainder > F(1, 2) or
                       (remainder == F(1, 2) and lower % 2 != 0))


def q3(value: F) -> F:
    return F(nearest_even(8 * value), 8)


def export(accumulators: tuple[int, ...]) -> tuple[int, ...]:
    return tuple(min(2047, max(0, nearest_even(F(a, 4096))))
                 for a in accumulators)


def basis(raw: F, width: int) -> tuple[F, ...]:
    if not -4 * width <= raw < 4 * width:
        raise ValueError("outside declared signed PWL domain")
    sign = 1 if raw > 0 else -1 if raw < 0 else 0
    return tuple(sign * min(max(abs(raw) - j * width, F(0)), F(width))
                 for j in range(4))


def pwl(raw: F, width: int, coefficients: tuple[F, ...], data_q3: bool) -> F:
    psi = basis(raw, width)
    if not data_q3:
        return sum((p * k for p, k in zip(psi, coefficients, strict=True)), F(0))
    # Offset and local product round separately. The negative endpoint uses
    # the fourth slope with a full local segment, as in the declared policy.
    segment = min(int(abs(raw) // width), 3)
    local = abs(raw) - segment * width
    offset = q3(width * sum(coefficients[:segment], F(0)))
    product = q3(local * coefficients[segment])
    sign = 1 if raw > 0 else -1 if raw < 0 else 0
    return sign * (offset + product)


@dataclass(frozen=True)
class Readout:
    raw1: F
    y1: F
    y2: F
    output: F
    thresholds: tuple[tuple[F, ...], tuple[F, ...]]
    gates: tuple[tuple[bool, ...], tuple[bool, ...]]
    support: tuple[tuple[bool, ...], tuple[bool, ...]]


def readout(q1: int, q2: int, backend: F, d1: int, d2: int,
            coefficients: tuple[F, ...], *, data_q3: bool) -> Readout:
    if len(coefficients) != 8 or d1 not in (-1, 1) or d2 not in (-1, 1):
        raise ValueError("eight coefficients and two bipolar tags required")
    p2 = pwl(backend, 32, coefficients[4:], data_q3)
    raw1 = 128 * q2 + p2 - 16 * d2
    y2 = p2 - 16 * d2
    y1 = pwl(raw1, 128, coefficients[:4], data_q3) - 64 * d1
    thresholds = []
    for width, bank in ((128, coefficients[:4]), (32, coefficients[4:])):
        values = tuple(width * sum(bank[:j], F(0)) for j in range(4))
        thresholds.append(tuple(q3(v) for v in values) if data_q3 else values)
    gates = tuple(tuple(j == 0 or abs(y) >= t for j, t in enumerate(ts))
                  for y, ts in zip((y1, y2), thresholds, strict=True))
    support = (tuple(p != 0 for p in basis(raw1, 128)),
               tuple(p != 0 for p in basis(backend, 32)))
    return Readout(raw1, y1, y2, 2048 + 512 * q1 + y1,
                   tuple(thresholds), gates, support)


def commit(accumulators: tuple[int, ...], products: tuple[F, ...],
           multiplier: int, steps: tuple[F, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """One simultaneous window commit; products use physical code units."""
    requests = tuple(nearest_even(-mu * multiplier * product * (1 << 22))
                     for mu, product in zip(steps, products, strict=True))
    after = tuple(min(2047 * 4096, max(0, a + d))
                  for a, d in zip(accumulators, requests, strict=True))
    return requests, after


def local_error_bounds(raw1: F, backend: F, max_front_slope: F,
                       front_export_error: F = F(1, 2048),
                       rear_export_error: F = F(1, 2048)) -> tuple[F, F]:
    """Same source state/SAR word, then Q1.10 + Q3; no state feedback.

    Both raw1 domains must be legal, coefficients unsaturated. Stage-1
    offset rounding is exactly zero for b1=128 and Q1.10 coefficients.
    """
    e2 = abs(backend) * rear_export_error + F(1, 8)
    e1 = abs(raw1) * front_export_error + (max_front_slope + front_export_error) * e2 + F(1, 16)
    return e1, e2


def gate_error_bounds(front_export_error: F = F(1, 2048),
                      rear_export_error: F = F(1, 2048)) -> tuple[tuple[F, ...], tuple[F, ...]]:
    return (tuple(128 * j * front_export_error for j in range(4)),
            tuple(32 * j * rear_export_error + (F(1, 16) if j else 0)
                  for j in range(4)))


def protected(margin: F, output_error: F, threshold_error: F) -> bool:
    return abs(margin) > output_error + threshold_error


@dataclass(frozen=True)
class OutputRangeBound:
    """Same-word sufficient range bound, not a learning invariant."""

    front_raw_radius: F
    output_radius: F

    @property
    def front_domain_safe(self) -> bool:
        # Positive full scale is excluded by the signed PWL contract.
        return self.front_raw_radius < 512

    @property
    def no_saturation(self) -> bool:
        return self.front_domain_safe and self.output_radius <= 2047


def output_range_bound(q1_radius: int, q2_radius: int, backend_radius: int,
                       front_max_code: int, rear_max_code: int) -> OutputRangeBound:
    """Q1.10 nonnegative banks; Q3 offset/product rounding kept separately.

    Digital radii must be justified independently by the caller. Rear
    rounding contributes at most 1/8; front offsets are exact in Q3 for
    width128, so only its product contributes 1/16. No platform imports.
    """
    if not (0 <= q1_radius <= 4 and 0 <= q2_radius <= 4 and
            0 <= backend_radius < 128):
        raise ValueError("invalid digital radii")
    if not (0 <= front_max_code <= 2047 and 0 <= rear_max_code <= 2047):
        raise ValueError("invalid Q1.10 slope maximum")
    raw = 128*q2_radius + F(rear_max_code, 1024)*backend_radius + F(1, 8) + 16
    radius = 512*q1_radius + F(front_max_code, 1024)*raw + F(1, 16) + 64
    return OutputRangeBound(raw, radius)


def saturated_integer(value: F, low: int = 0, high: int = 4095) -> int:
    """Saturate the Q3/real readout before final nearest-even integerization."""
    if low > high:
        raise ValueError("invalid output range")
    return nearest_even(min(F(high), max(F(low), value)))


def saturation_loss_change(value: F, target: F,
                           low: int = 0, high: int = 4095) -> F:
    """Exact signed integer-MSE change; target need not lie inside the range."""
    raw = nearest_even(value)
    final = saturated_integer(value, low, high)
    return (final-target)**2 - (raw-target)**2
