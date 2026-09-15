"""Analytical redundancy-coverage relations for table-driven pipeline stages.

The functions in this module do not call the sample-wise platform.  They express
the interval conditions that a stage decision region must satisfy so that the
following stage is not overloaded.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BoundaryWindow:
    """Allowed location of a boundary between two adjacent stage symbols."""

    lower: float
    upper: float

    @property
    def center(self) -> float:
        return (self.lower + self.upper) / 2

    @property
    def half_width(self) -> float:
        return (self.upper - self.lower) / 2

    @property
    def feasible(self) -> bool:
        return self.lower <= self.upper

    def contains(self, boundary: float) -> bool:
        return self.lower <= boundary <= self.upper


def effective_boundary(
    nominal_threshold: float,
    *,
    auxiliary_gain_ratio: float = 1.0,
    threshold_offset: float = 0.0,
    auxiliary_offset: float = 0.0,
) -> float:
    """Refer an auxiliary-path comparator threshold to the main-path input.

    The auxiliary signal is defined as ``x_aux = rho*x_main + offset`` and the
    comparator changes state at ``x_aux = nominal_threshold + threshold_offset``.
    """

    if auxiliary_gain_ratio <= 0:
        raise ValueError("auxiliary_gain_ratio must be positive")
    return (
        nominal_threshold + threshold_offset - auxiliary_offset
    ) / auxiliary_gain_ratio


def correctable_boundary_window(
    left_dac_level: float,
    right_dac_level: float,
    *,
    interstage_gain: float,
    dither_half_amplitude: float = 0.0,
) -> BoundaryWindow:
    """Return the no-overload window for an adjacent decision boundary.

    For residue ``z = G*(x - a_q + d)`` and ``|d| <= d0``, the boundary between
    a left symbol with DAC level ``a_q`` and a right symbol with level
    ``a_(q+1)`` must obey

    ``a_(q+1) + d0 - 1/G <= B <= a_q - d0 + 1/G``.

    The returned window may be infeasible; callers should inspect ``feasible``.
    """

    if interstage_gain <= 0:
        raise ValueError("interstage_gain must be positive")
    if dither_half_amplitude < 0:
        raise ValueError("dither_half_amplitude must be nonnegative")

    inverse_gain = 1 / interstage_gain
    return BoundaryWindow(
        lower=right_dac_level + dither_half_amplitude - inverse_gain,
        upper=left_dac_level - dither_half_amplitude + inverse_gain,
    )


def residue_extrema(
    region_lower: float,
    region_upper: float,
    dac_level: float,
    *,
    interstage_gain: float,
    dither_half_amplitude: float = 0.0,
) -> tuple[float, float]:
    """Return the infimum/supremum residue over a region and both dither signs."""

    if region_upper < region_lower:
        raise ValueError("region_upper must not be below region_lower")
    if interstage_gain <= 0:
        raise ValueError("interstage_gain must be positive")
    if dither_half_amplitude < 0:
        raise ValueError("dither_half_amplitude must be nonnegative")

    return (
        interstage_gain
        * (region_lower - dac_level - dither_half_amplitude),
        interstage_gain
        * (region_upper - dac_level + dither_half_amplitude),
    )
