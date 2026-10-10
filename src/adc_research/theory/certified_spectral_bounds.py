"""Outward rational enclosures of finite-record SNDR and SFDR.

This is an offline certificate for covered integer-code records, not an FFT
error estimate or a source of physical envelopes. No floating-point operation
is used. The metric is the repository's even-length rectangular-window,
one-sided power convention, with DC excluded and Nyquist counted once.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F
from functools import lru_cache
from math import factorial, isqrt
from numbers import Integral
from typing import Iterable, Literal


Extended = F | Literal["-inf", "+inf"]


def _integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise TypeError(f"{name} must be an integer; rounded floats are not exact source codes")
    return int(value)


def _precision(bits: int) -> int:
    bits = _integer(bits, "precision bits")
    if not 32 <= bits <= 256:
        raise ValueError("precision bits must be between 32 and 256")
    return bits


@dataclass(frozen=True)
class RationalInterval:
    lower: F
    upper: F

    def __post_init__(self) -> None:
        if not isinstance(self.lower, F) or not isinstance(self.upper, F):
            raise TypeError("rational interval endpoints must be explicit Fractions")
        if self.lower > self.upper:
            raise ValueError("lower endpoint exceeds upper endpoint")

    @classmethod
    def point(cls, value: F | int) -> RationalInterval:
        if not isinstance(value, F):
            value = _integer(value, "rational point")
        value = F(value)
        return cls(value, value)

    def add(self, other: RationalInterval) -> RationalInterval:
        return RationalInterval(self.lower + other.lower, self.upper + other.upper)

    def negate(self) -> RationalInterval:
        return RationalInterval(-self.upper, -self.lower)

    def scale(self, value: F | int) -> RationalInterval:
        if not isinstance(value, F):
            value = _integer(value, "rational scale")
        a, b = self.lower * value, self.upper * value
        return RationalInterval(min(a, b), max(a, b))

    def multiply(self, other: RationalInterval) -> RationalInterval:
        corners = tuple(a * b for a in (self.lower, self.upper)
                        for b in (other.lower, other.upper))
        return RationalInterval(min(corners), max(corners))

    def square(self) -> RationalInterval:
        lower = F(0) if self.lower <= 0 <= self.upper else min(self.lower**2, self.upper**2)
        return RationalInterval(lower, max(self.lower**2, self.upper**2))

    def rounded(self, bits: int) -> RationalInterval:
        scale = 1 << bits
        low = (self.lower.numerator * scale) // self.lower.denominator
        high = -((-self.upper.numerator * scale) // self.upper.denominator)
        return RationalInterval(F(low, scale), F(high, scale))

    def intersect(self, other: RationalInterval) -> RationalInterval:
        return RationalInterval(max(self.lower, other.lower), min(self.upper, other.upper))


@dataclass(frozen=True)
class ExtendedInterval:
    """Exact rational endpoints or explicit infinity tokens, suitable for JSON."""

    lower: Extended
    upper: Extended


@dataclass(frozen=True)
class CertifiedToneBounds:
    sample_count: int
    fundamental_bin: int
    precision_bits: int
    fundamental_guaranteed_nonzero: bool
    sndr_power_ratio: ExtendedInterval
    sfdr_power_ratio: ExtendedInterval
    sndr_db: ExtendedInterval
    sfdr_dbc: ExtendedInterval
    midpoint_bin_power: tuple[RationalInterval, ...]
    binwise_record_power: tuple[RationalInterval, ...]
    mean_squared_code_halfwidth: F
    sum_code_halfwidths: F


def _atan_small(value: F, terms: int) -> RationalInterval:
    # Alternating series: remainder lies between zero and the next term.
    total = sum(((-1)**j * value**(2*j+1) / (2*j+1)
                 for j in range(terms)), F(0))
    next_term = (-1)**terms * value**(2*terms+1) / (2*terms+1)
    return RationalInterval(min(total, total + next_term), max(total, total + next_term))


@lru_cache(maxsize=8)
def certified_pi(bits: int = 72) -> RationalInterval:
    """Machin identity and alternating remainders, rounded outward to dyadics."""
    bits = _precision(bits)
    terms = bits // 3 + 8
    return _atan_small(F(1, 5), terms).scale(16).add(
        _atan_small(F(1, 239), terms).scale(-4)
    ).rounded(bits)


def _first_quadrant(angle: RationalInterval, bits: int) -> tuple[RationalInterval, RationalInterval]:
    terms = bits // 4 + 5
    squared = angle.square().rounded(bits)
    sine_term, cosine_term = angle, RationalInterval.point(1)
    sine, cosine = RationalInterval.point(0), RationalInterval.point(0)
    for j in range(terms):
        sine = sine.add(sine_term.scale((-1)**j)).rounded(bits)
        cosine = cosine.add(cosine_term.scale((-1)**j)).rounded(bits)
        sine_term = sine_term.multiply(squared).scale(F(1, (2*j+2)*(2*j+3))).rounded(bits)
        cosine_term = cosine_term.multiply(squared).scale(F(1, (2*j+1)*(2*j+2))).rounded(bits)
    # Taylor's theorem, using |all derivatives| <= 1. The intervening
    # zero coefficient gives degree 2m for sin and degree 2m-1 for cos.
    sine_error = angle.upper**(2*terms+1) / factorial(2*terms+1)
    cosine_error = angle.upper**(2*terms) / factorial(2*terms)
    unit = RationalInterval(F(-1), F(1))
    sine = sine.add(RationalInterval(-sine_error, sine_error)).rounded(bits).intersect(unit)
    cosine = cosine.add(RationalInterval(-cosine_error, cosine_error)).rounded(bits).intersect(unit)
    return cosine, sine


@lru_cache(maxsize=8)
def _twiddles(size: int, bits: int) -> tuple[tuple[int, int, int, int], ...]:
    scale = 1 << bits
    table = []
    for phase in range(size):
        quadrant, remainder = divmod(4*phase, size)
        if remainder == 0:
            cosine, sine = RationalInterval.point(1), RationalInterval.point(0)
        else:
            angle = certified_pi(bits).scale(F(remainder, 2*size)).rounded(bits)
            cosine, sine = _first_quadrant(angle, bits)
        if quadrant == 1:
            cosine, sine = sine.negate(), cosine
        elif quadrant == 2:
            cosine, sine = cosine.negate(), sine.negate()
        elif quadrant == 3:
            cosine, sine = sine, cosine.negate()
        table.append(tuple(int(endpoint * scale) for endpoint in
                           (cosine.lower, cosine.upper, sine.lower, sine.upper)))
    return tuple(table)


def certified_phase(phase: int, period: int, *, bits: int = 72) -> tuple[RationalInterval, RationalInterval]:
    """Enclose cos and sin of 2*pi*phase/period without a float phase input."""
    phase = _integer(phase, "phase index")
    period = _integer(period, "phase period")
    bits = _precision(bits)
    if period <= 0:
        raise ValueError("phase period must be positive")
    cl, cu, sl, su = _twiddles(period, bits)[phase % period]
    scale = 1 << bits
    return RationalInterval(F(cl, scale), F(cu, scale)), RationalInterval(F(sl, scale), F(su, scale))


def _sqrt_point(value: F, bits: int) -> RationalInterval:
    if value < 0:
        raise ValueError("square root argument must be nonnegative")
    scale = 1 << bits
    numerator = value.numerator * scale**2
    low = isqrt(numerator // value.denominator)
    high = low if low**2 * value.denominator == numerator else low + 1
    return RationalInterval(F(low, scale), F(high, scale))


def _sqrt(interval: RationalInterval, bits: int) -> RationalInterval:
    return RationalInterval(_sqrt_point(interval.lower, bits).lower,
                            _sqrt_point(interval.upper, bits).upper)


def _ln_series(value: F, bits: int) -> RationalInterval:
    # 1 <= value <= 2, hence 0 <= z <= 1/3. The remaining positive
    # series is <= 2*z^(2m+1)/((2m+1)*(1-z^2)).
    z = (value - 1) / (value + 1)
    if not 0 <= z <= F(1, 3):
        raise ValueError("logarithm series requires a mantissa in [1,2]")
    terms = bits // 3 + 8
    power = RationalInterval.point(z).rounded(bits)
    factor = RationalInterval.point(z*z).rounded(bits)
    total = RationalInterval.point(0)
    for j in range(terms):
        total = total.add(power.scale(F(2, 2*j+1))).rounded(bits)
        power = power.multiply(factor).rounded(bits)
    remainder = 2 * z**(2*terms+1) / ((2*terms+1)*(1-z*z))
    return total.add(RationalInterval(F(0), remainder)).rounded(bits)


@lru_cache(maxsize=8)
def _ln_two(bits: int) -> RationalInterval:
    return _ln_series(F(2), bits)


def _ln(value: F, bits: int) -> RationalInterval:
    if value <= 0:
        raise ValueError("logarithm argument must be positive")
    exponent = value.numerator.bit_length() - value.denominator.bit_length()
    power_two = F(2)**exponent
    if value < power_two:
        exponent -= 1
        power_two /= 2
    mantissa = value / power_two
    return _ln_series(mantissa, bits).add(_ln_two(bits).scale(exponent)).rounded(bits)


@lru_cache(maxsize=8)
def _ln_ten(bits: int) -> RationalInterval:
    return _ln(F(10), bits)


def certified_power_db(value: F, *, bits: int = 72) -> RationalInterval:
    """Enclose 10*log10 of an explicitly positive rational power ratio."""
    bits = _precision(bits)
    if not isinstance(value, F):
        raise TypeError("power ratio must be an explicit Fraction")
    if value == 1:
        return RationalInterval.point(0)
    numerator, denominator = _ln(value, bits).scale(10), _ln_ten(bits)
    corners = tuple(a/b for a in (numerator.lower, numerator.upper)
                    for b in (denominator.lower, denominator.upper))
    return RationalInterval(min(corners), max(corners)).rounded(bits)


def _db(interval: ExtendedInterval, bits: int) -> ExtendedInterval:
    def endpoint(value: Extended, lower: bool) -> Extended:
        if isinstance(value, str):
            return value
        if value == 0:
            return "-inf"
        result = certified_power_db(value, bits=bits)
        return result.lower if lower else result.upper
    return ExtendedInterval(endpoint(interval.lower, True), endpoint(interval.upper, False))


def _power_ratio(signal: RationalInterval, unwanted: RationalInterval) -> ExtendedInterval:
    # Degenerate zero/zero possibilities are left unbounded, never silently
    # scored as infinite performance. Only records with nonzero fundamental
    # have defined metrics; the public result explicitly reports that gate.
    if signal.upper == 0:
        raise ValueError("record family has no fundamental power")
    lower: Extended = (F(0) if signal.lower == 0 else "+inf" if unwanted.upper == 0
                       else signal.lower / unwanted.upper)
    upper: Extended = "+inf" if unwanted.lower == 0 else signal.upper / unwanted.lower
    return ExtendedInterval(lower, upper)


def _amplitude_envelope(center: RationalInterval, radius: RationalInterval) -> RationalInterval:
    return RationalInterval(max(F(0), center.lower - radius.upper), center.upper + radius.upper)


def _midpoint_powers(lower: tuple[int, ...], upper: tuple[int, ...], bits: int) -> tuple[RationalInterval, ...]:
    size = len(lower)
    doubled = tuple(a+b for a, b in zip(lower, upper))
    total = sum(doubled)
    # Exact mean removal reduces interval error from large DC code offsets.
    weights = tuple(size*c-total for c in doubled)
    table = _twiddles(size, bits)
    denominator = 2*size*size*(1 << bits)
    powers = [RationalInterval.point(0)]
    for k in range(1, size//2+1):
        rl = ru = il = iu = 0
        for n, weight in enumerate(weights):
            cl, cu, sl, su = table[(k*n) % size]
            if weight >= 0:
                rl += weight*cl
                ru += weight*cu
                il -= weight*su
                iu -= weight*sl
            else:
                rl += weight*cu
                ru += weight*cl
                il -= weight*sl
                iu -= weight*su
        real = RationalInterval(F(rl, denominator), F(ru, denominator))
        imag = RationalInterval(F(il, denominator), F(iu, denominator))
        weight = 1 if k == size//2 else 2
        powers.append(real.square().add(imag.square()).scale(weight))
    return tuple(powers)


def bound_certified_coherent_tone(
    lower_codes: Iterable[int], upper_codes: Iterable[int], *,
    fundamental_bin: int, bits: int = 72,
) -> CertifiedToneBounds:
    """Enclose every nonzero-tone record inside given integer-code intervals.

    Uses Parseval for SNDR, and intersects Parseval and individual-bin SFDR
    enclosures. Arbitrary correlations and online coefficient histories are
    allowed if the code intervals already cover them. Floating-point inputs
    are rejected. The direct DFT costs O(N^2), with no long-record FFT claim.
    """
    bits = _precision(bits)
    lower = tuple(_integer(x, "lower code") for x in lower_codes)
    upper = tuple(_integer(x, "upper code") for x in upper_codes)
    size = len(lower)
    fundamental_bin = _integer(fundamental_bin, "fundamental bin")
    if size < 4 or size % 2 or len(upper) != size:
        raise ValueError("code envelopes must have equal even length of at least four")
    if not 0 < fundamental_bin < size//2:
        raise ValueError("fundamental bin must be inside the first Nyquist zone")
    if any(a > b for a, b in zip(lower, upper)):
        raise ValueError("each lower code must not exceed its upper code")

    halfwidths = tuple(F(b-a, 2) for a, b in zip(lower, upper))
    mean_square = sum((h*h for h in halfwidths), F(0)) / size
    halfwidth_sum = sum(halfwidths, F(0))
    delta = _sqrt_point(mean_square, bits)
    raw_bin_radius = RationalInterval.point(halfwidth_sum / size)
    midpoint = tuple(F(a+b, 2) for a, b in zip(lower, upper))
    mean = sum(midpoint, F(0)) / size
    total_power = sum(((c-mean)**2 for c in midpoint), F(0)) / size
    powers = _midpoint_powers(lower, upper, bits)
    signal_center = _sqrt(powers[fundamental_bin], bits)
    residual_center = _sqrt(RationalInterval(
        max(F(0), total_power-powers[fundamental_bin].upper),
        max(F(0), total_power-powers[fundamental_bin].lower),
    ), bits)
    signal = _amplitude_envelope(signal_center, delta).square()
    residual = _amplitude_envelope(residual_center, delta).square()
    sndr_ratio = _power_ratio(signal, residual)

    binwise = [RationalInterval.point(0)]
    for k, power in enumerate(powers[1:], 1):
        factor = 1 if k == size//2 else 2
        center = _sqrt(power.scale(F(1, factor)), bits)
        binwise.append(_amplitude_envelope(center, raw_bin_radius).square().scale(factor))
    unwanted_bins = tuple(k for k in range(1, size//2+1) if k != fundamental_bin)
    largest_center = RationalInterval(
        max(powers[k].lower for k in unwanted_bins),
        max(powers[k].upper for k in unwanted_bins),
    )
    parseval_spur = _amplitude_envelope(_sqrt(largest_center, bits), delta).square()
    binwise_spur = RationalInterval(
        max(binwise[k].lower for k in unwanted_bins),
        max(binwise[k].upper for k in unwanted_bins),
    )
    sfdr_signal = signal.intersect(binwise[fundamental_bin])
    sfdr_spur = parseval_spur.intersect(binwise_spur)
    sfdr_ratio = _power_ratio(sfdr_signal, sfdr_spur)
    return CertifiedToneBounds(
        size, fundamental_bin, bits, signal.lower > 0 or sfdr_signal.lower > 0,
        sndr_ratio, sfdr_ratio, _db(sndr_ratio, bits), _db(sfdr_ratio, bits),
        powers, tuple(binwise), mean_square, halfwidth_sum,
    )
