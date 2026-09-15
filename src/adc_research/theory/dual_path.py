"""Analytical margins for a main/auxiliary inter-stage signal split.

This module remains independent of the sample-wise platform.  It refers an
auxiliary flash decision back to the main-path coordinate and intersects the
per-boundary redundancy windows derived in :mod:`redundancy`.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

from adc_research.theory.redundancy import (
    BoundaryWindow,
    correctable_boundary_window,
    effective_boundary,
)


@dataclass(frozen=True)
class OffsetInterval:
    """Allowed common auxiliary offset for one or more flash boundaries."""

    lower: float
    upper: float

    @property
    def feasible(self) -> bool:
        return self.lower <= self.upper

    @property
    def center(self) -> float:
        return (self.lower + self.upper) / 2

    @property
    def half_width(self) -> float:
        return (self.upper - self.lower) / 2

    def contains(self, offset: float) -> bool:
        return self.lower <= offset <= self.upper


@dataclass(frozen=True)
class AuxiliaryBoundaryAudit:
    nominal_threshold: float
    effective_boundary: float
    redundancy_window: BoundaryWindow
    margin_to_lower: float
    margin_to_upper: float

    @property
    def minimum_margin(self) -> float:
        return min(self.margin_to_lower, self.margin_to_upper)

    @property
    def correctable(self) -> bool:
        return self.minimum_margin >= 0


def offset_interval_for_boundary(
    nominal_threshold: float,
    left_dac_level: float,
    right_dac_level: float,
    *,
    auxiliary_gain_ratio: float,
    interstage_gain: float,
    dither_half_amplitude: float = 0.0,
    threshold_offset: float = 0.0,
) -> OffsetInterval:
    """Return auxiliary offsets that keep one decision boundary correctable.

    With ``x_aux=rho*x_main+o`` and comparator threshold ``t+theta``, the
    main-referred boundary is ``B=(t+theta-o)/rho``.  Solving the redundancy
    window for ``o`` gives the returned interval.
    """

    if auxiliary_gain_ratio <= 0 or not isfinite(auxiliary_gain_ratio):
        raise ValueError("auxiliary_gain_ratio must be finite and positive")
    window = correctable_boundary_window(
        left_dac_level,
        right_dac_level,
        interstage_gain=interstage_gain,
        dither_half_amplitude=dither_half_amplitude,
    )
    threshold = nominal_threshold + threshold_offset
    return OffsetInterval(
        lower=threshold - auxiliary_gain_ratio * window.upper,
        upper=threshold - auxiliary_gain_ratio * window.lower,
    )


def joint_auxiliary_offset_interval(
    thresholds: Sequence[float],
    dac_levels: Sequence[float],
    *,
    auxiliary_gain_ratio: float,
    interstage_gain: float,
    dither_half_amplitude: float = 0.0,
    threshold_offsets: Sequence[float] | None = None,
) -> OffsetInterval:
    """Intersect the common-offset intervals for aligned adjacent states."""

    if not thresholds:
        raise ValueError("at least one threshold is required")
    if len(dac_levels) != len(thresholds) + 1:
        raise ValueError("dac_levels must have one more item than thresholds")
    offsets = (
        tuple(0.0 for _ in thresholds)
        if threshold_offsets is None
        else tuple(threshold_offsets)
    )
    if len(offsets) != len(thresholds):
        raise ValueError("threshold_offsets must match thresholds")

    intervals = tuple(
        offset_interval_for_boundary(
            threshold,
            dac_levels[index],
            dac_levels[index + 1],
            auxiliary_gain_ratio=auxiliary_gain_ratio,
            interstage_gain=interstage_gain,
            dither_half_amplitude=dither_half_amplitude,
            threshold_offset=offsets[index],
        )
        for index, threshold in enumerate(thresholds)
    )
    return OffsetInterval(
        lower=max(interval.lower for interval in intervals),
        upper=min(interval.upper for interval in intervals),
    )


def audit_auxiliary_boundaries(
    thresholds: Sequence[float],
    dac_levels: Sequence[float],
    *,
    auxiliary_gain_ratio: float,
    auxiliary_offset: float,
    interstage_gain: float,
    dither_half_amplitude: float = 0.0,
    threshold_offsets: Sequence[float] | None = None,
) -> tuple[AuxiliaryBoundaryAudit, ...]:
    """Return signed redundancy margin for every supplied boundary."""

    if len(dac_levels) != len(thresholds) + 1:
        raise ValueError("dac_levels must have one more item than thresholds")
    offsets = (
        tuple(0.0 for _ in thresholds)
        if threshold_offsets is None
        else tuple(threshold_offsets)
    )
    if len(offsets) != len(thresholds):
        raise ValueError("threshold_offsets must match thresholds")

    audits = []
    for index, threshold in enumerate(thresholds):
        window = correctable_boundary_window(
            dac_levels[index],
            dac_levels[index + 1],
            interstage_gain=interstage_gain,
            dither_half_amplitude=dither_half_amplitude,
        )
        boundary = effective_boundary(
            threshold,
            auxiliary_gain_ratio=auxiliary_gain_ratio,
            threshold_offset=offsets[index],
            auxiliary_offset=auxiliary_offset,
        )
        audits.append(
            AuxiliaryBoundaryAudit(
                nominal_threshold=threshold,
                effective_boundary=boundary,
                redundancy_window=window,
                margin_to_lower=boundary - window.lower,
                margin_to_upper=window.upper - boundary,
            )
        )
    return tuple(audits)
