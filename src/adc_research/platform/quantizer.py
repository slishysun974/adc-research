"""Table-driven interval quantizer used by the sample-wise reference platform."""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from math import inf, isfinite
from typing import Hashable, Sequence


@dataclass(frozen=True)
class QuantizerConfig:
    thresholds: tuple[float, ...]
    output_symbols: tuple[Hashable, ...]
    input_range: tuple[float, float] = (-1.0, 1.0)

    def __post_init__(self) -> None:
        if len(self.output_symbols) != len(self.thresholds) + 1:
            raise ValueError("output_symbols must have one more item than thresholds")
        if any(
            right <= left
            for left, right in zip(
                self.thresholds, self.thresholds[1:], strict=False
            )
        ):
            raise ValueError("thresholds must be strictly increasing")
        low, high = self.input_range
        if high <= low:
            raise ValueError("input_range must be increasing")

    @classmethod
    def from_sequences(
        cls,
        thresholds: Sequence[float],
        output_symbols: Sequence[Hashable],
        *,
        input_range: tuple[float, float] = (-1.0, 1.0),
    ) -> "QuantizerConfig":
        return cls(tuple(thresholds), tuple(output_symbols), input_range)


@dataclass(frozen=True)
class QuantizerResult:
    region_index: int
    symbol: Hashable
    overload_low: bool
    overload_high: bool
    distance_to_nearest_threshold: float
    applied_threshold_offsets: tuple[float, ...]
    effective_thresholds: tuple[float, ...]


def convert(
    value: float,
    config: QuantizerConfig,
    *,
    threshold_offsets: Sequence[float] | None = None,
) -> QuantizerResult:
    """Convert one value with left-closed/right-open threshold semantics."""

    if threshold_offsets is None:
        offsets = (0.0,) * len(config.thresholds)
    else:
        offsets = tuple(threshold_offsets)
        if len(offsets) != len(config.thresholds):
            raise ValueError("threshold_offsets must match configured thresholds")
        if any(not isfinite(offset) for offset in offsets):
            raise ValueError("threshold_offsets must be finite")
    effective = tuple(
        threshold + offset
        for threshold, offset in zip(config.thresholds, offsets, strict=True)
    )
    if any(right <= left for left, right in zip(effective, effective[1:])):
        raise ValueError("effective thresholds must remain strictly increasing")

    region = bisect_right(effective, value)
    low, high = config.input_range
    distance = (
        min(abs(value - threshold) for threshold in effective)
        if effective
        else inf
    )
    return QuantizerResult(
        region_index=region,
        symbol=config.output_symbols[region],
        overload_low=value < low,
        overload_high=value >= high,
        distance_to_nearest_threshold=distance,
        applied_threshold_offsets=offsets,
        effective_thresholds=effective,
    )
