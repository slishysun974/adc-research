"""Integer fixed-point primitives with explicit rounding and overflow rules."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite
from typing import Literal


RoundingMode = Literal["floor", "nearest_even", "toward_zero"]
OverflowMode = Literal["raise", "saturate"]


def round_shift(value: int, shift: int, mode: RoundingMode) -> int:
    """Divide an integer by ``2**shift`` using the selected rounding rule."""

    if shift < 0:
        return value << -shift
    if shift == 0:
        return value
    divisor = 1 << shift
    if mode == "floor":
        return value // divisor
    if mode == "toward_zero":
        return (abs(value) // divisor) * (-1 if value < 0 else 1)
    if mode != "nearest_even":
        raise ValueError(f"unsupported rounding mode: {mode}")

    magnitude = abs(value)
    quotient, remainder = divmod(magnitude, divisor)
    half = divisor >> 1
    if remainder > half or (remainder == half and quotient & 1):
        quotient += 1
    return quotient * (-1 if value < 0 else 1)


def round_fraction(
    numerator: int,
    denominator: int,
    mode: RoundingMode,
) -> int:
    """Round an exact rational number using the selected rounding rule."""

    if denominator <= 0:
        raise ValueError("denominator must be positive")
    if mode == "floor":
        return numerator // denominator
    if mode == "toward_zero":
        return (abs(numerator) // denominator) * (-1 if numerator < 0 else 1)
    if mode != "nearest_even":
        raise ValueError(f"unsupported rounding mode: {mode}")

    magnitude = abs(numerator)
    quotient, remainder = divmod(magnitude, denominator)
    doubled_remainder = 2 * remainder
    if doubled_remainder > denominator or (
        doubled_remainder == denominator and quotient & 1
    ):
        quotient += 1
    return quotient * (-1 if numerator < 0 else 1)


def signed_bits_required(value: int) -> int:
    """Return the smallest two's-complement width that represents ``value``."""

    if value >= 0:
        return value.bit_length() + 1
    return (~value).bit_length() + 1


@dataclass(frozen=True)
class UnsignedFixedFormat:
    """Unsigned fixed-point format described by total and fractional bits."""

    total_bits: int
    fractional_bits: int

    def __post_init__(self) -> None:
        if self.total_bits <= 0:
            raise ValueError("total_bits must be positive")
        if self.fractional_bits < 0:
            raise ValueError("fractional_bits must be nonnegative")
        if self.fractional_bits >= self.total_bits:
            raise ValueError("unsigned format requires at least one integer bit")

    @property
    def scale(self) -> int:
        return 1 << self.fractional_bits

    @property
    def maximum_code(self) -> int:
        return (1 << self.total_bits) - 1

    @property
    def maximum_value(self) -> float:
        return self.maximum_code / self.scale

    def quantize(
        self,
        value: float,
        *,
        rounding: RoundingMode,
        overflow: OverflowMode,
    ) -> tuple[int, bool]:
        """Quantize a nonnegative value and report whether it saturated."""

        if not isfinite(value) or value < 0:
            raise ValueError("unsigned fixed-point value must be finite and nonnegative")
        scaled = value * self.scale
        if rounding == "floor":
            code = floor(scaled)
        elif rounding == "toward_zero":
            code = floor(scaled)
        elif rounding == "nearest_even":
            code = round(scaled)
        else:
            raise ValueError(f"unsupported rounding mode: {rounding}")
        saturated = code > self.maximum_code
        if saturated:
            if overflow == "raise":
                raise OverflowError("value exceeds unsigned fixed-point range")
            if overflow != "saturate":
                raise ValueError(f"unsupported overflow mode: {overflow}")
            code = self.maximum_code
        return int(code), saturated


def fixed_to_float(code: int, fractional_bits: int) -> float:
    if fractional_bits < 0:
        raise ValueError("fractional_bits must be nonnegative")
    return code / (1 << fractional_bits)
