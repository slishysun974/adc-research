"""Floating-reference piecewise-linear magnitude correction.

The implementation follows Gu et al.'s unsigned magnitude decomposition: the
two most-significant magnitude bits select one of four slopes, the remaining
bits form a local code, and cumulative offsets keep adjacent slices continuous.
It deliberately does not claim the chip's unpublished bit-true endpoint logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, log2
from typing import Literal, Sequence


NegativeFullScalePolicy = Literal["extend_last_slice", "reject"]


def slice_width_from_unsigned_bits(
    unsigned_magnitude_bits: int,
    *,
    slice_count: int = 4,
) -> int:
    """Return ``b0`` for an equal-width power-of-two slice partition."""

    if unsigned_magnitude_bits <= 0:
        raise ValueError("unsigned_magnitude_bits must be positive")
    if slice_count <= 0 or slice_count & (slice_count - 1):
        raise ValueError("slice_count must be a positive power of two")
    selector_bits = int(log2(slice_count))
    if unsigned_magnitude_bits <= selector_bits:
        raise ValueError("magnitude word must include at least one local-code bit")
    return 1 << (unsigned_magnitude_bits - selector_bits)


@dataclass(frozen=True)
class PwlConfig:
    slice_width: float
    slopes: tuple[float, ...]
    negative_full_scale_policy: NegativeFullScalePolicy = "extend_last_slice"

    def __post_init__(self) -> None:
        if self.slice_width <= 0 or not isfinite(self.slice_width):
            raise ValueError("slice_width must be finite and positive")
        if not self.slopes:
            raise ValueError("at least one PWL slope is required")
        if any(slope < 0 or not isfinite(slope) for slope in self.slopes):
            raise ValueError("PWL slopes must be finite and nonnegative")
        if self.negative_full_scale_policy not in (
            "extend_last_slice",
            "reject",
        ):
            raise ValueError("unsupported negative full-scale policy")

    @classmethod
    def from_sequence(
        cls,
        slice_width: float,
        slopes: Sequence[float],
        *,
        negative_full_scale_policy: NegativeFullScalePolicy = "extend_last_slice",
    ) -> "PwlConfig":
        return cls(slice_width, tuple(slopes), negative_full_scale_policy)

    @property
    def slice_count(self) -> int:
        return len(self.slopes)

    @property
    def full_scale_magnitude(self) -> float:
        return self.slice_width * self.slice_count

    @property
    def slice_offsets(self) -> tuple[float, ...]:
        cumulative = 0.0
        offsets = []
        for slope in self.slopes:
            offsets.append(cumulative)
            cumulative += self.slice_width * slope
        return tuple(offsets)


@dataclass(frozen=True)
class PwlResult:
    raw_code: float
    sign: int
    magnitude: float
    slice_index: int
    local_code: float
    selected_slope: float
    slice_offset: float
    corrected_magnitude: float
    corrected_code: float
    negative_full_scale_extension: bool


def correct(raw_code: float, config: PwlConfig) -> PwlResult:
    """Apply symmetric floating PWL correction to one centered raw code.

    The regular signed domain is ``[-N*b0, N*b0)``.  The most-negative code
    has an absolute magnitude of ``N*b0``, one count beyond the regular unsigned
    magnitude field.  The default behavioral policy continuously extends the
    final slice to that endpoint; callers may select ``reject`` while auditing
    an alternative bit-true convention.
    """

    if not isfinite(raw_code):
        raise ValueError("raw_code must be finite")
    full_scale = config.full_scale_magnitude
    if raw_code < -full_scale or raw_code >= full_scale:
        raise ValueError("raw_code lies outside the signed PWL domain")

    negative_endpoint = raw_code == -full_scale
    if negative_endpoint and config.negative_full_scale_policy == "reject":
        raise ValueError("negative full-scale code is unresolved by this policy")

    sign = -1 if raw_code < 0 else (1 if raw_code > 0 else 0)
    magnitude = abs(raw_code)
    if negative_endpoint:
        slice_index = config.slice_count - 1
        local_code = config.slice_width
    else:
        slice_index = min(
            int(magnitude // config.slice_width),
            config.slice_count - 1,
        )
        local_code = magnitude - slice_index * config.slice_width

    slope = config.slopes[slice_index]
    offset = config.slice_offsets[slice_index]
    corrected_magnitude = offset + slope * local_code
    corrected_code = sign * corrected_magnitude
    return PwlResult(
        raw_code=raw_code,
        sign=sign,
        magnitude=magnitude,
        slice_index=slice_index,
        local_code=local_code,
        selected_slope=slope,
        slice_offset=offset,
        corrected_magnitude=corrected_magnitude,
        corrected_code=corrected_code,
        negative_full_scale_extension=negative_endpoint,
    )
