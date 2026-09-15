"""Ideal backend SAR model for the sample-wise reference platform."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite


@dataclass(frozen=True)
class SarConfig:
    """Configuration for a uniform offset-binary SAR quantizer."""

    bits: int
    input_range: tuple[float, float] = (-1.0, 1.0)
    channels: int = 1

    def __post_init__(self) -> None:
        if self.bits <= 0:
            raise ValueError("bits must be positive")
        if self.channels <= 0:
            raise ValueError("channels must be positive")
        low, high = self.input_range
        if not (isfinite(low) and isfinite(high)) or high <= low:
            raise ValueError("input_range must be finite and increasing")

    @property
    def code_count(self) -> int:
        return 1 << self.bits

    @property
    def step(self) -> float:
        low, high = self.input_range
        return (high - low) / self.code_count


@dataclass(frozen=True)
class SarResult:
    input_value: float
    channel_index: int
    raw_code: int
    centered_code: int
    quantized_value: float
    step: float
    overload_low: bool
    overload_high: bool


def convert(
    value: float,
    config: SarConfig,
    *,
    sample_index: int = 0,
) -> SarResult:
    """Convert one sample using left-closed/right-open midrise bins.

    Values outside the configured range are clipped to an endpoint code, while
    the overload flags preserve the fact that clipping occurred.  Four-channel
    TI operation is represented by deterministic round-robin channel ownership;
    channel mismatch and timing skew belong to later fidelity layers.
    """

    if not isfinite(value):
        raise ValueError("SAR input must be finite")
    if sample_index < 0:
        raise ValueError("sample_index must be nonnegative")

    low, high = config.input_range
    raw_unclipped = floor((value - low) / config.step)
    raw_code = min(max(raw_unclipped, 0), config.code_count - 1)
    centered_zero = config.code_count // 2
    return SarResult(
        input_value=value,
        channel_index=sample_index % config.channels,
        raw_code=raw_code,
        centered_code=raw_code - centered_zero,
        quantized_value=low + (raw_code + 0.5) * config.step,
        step=config.step,
        overload_low=value < low,
        overload_high=value >= high,
    )
