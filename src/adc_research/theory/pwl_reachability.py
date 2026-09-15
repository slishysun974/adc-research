"""Independent reachability bounds for PWL slices in a radix stage."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True)
class PwlSliceReachability:
    slice_lower_edge: float
    nominal_residue_output_half_range: float
    interstage_gain: float
    minimum_preamp_dither_infimum: float
    maximum_preamp_dither_without_nominal_overload: float

    @property
    def feasible_below_nominal_overload(self) -> bool:
        return (
            self.minimum_preamp_dither_infimum
            < self.maximum_preamp_dither_without_nominal_overload
        )

    def reached_by(self, preamp_dither_magnitude: float) -> bool:
        """Return whether the open residue supremum crosses the slice edge."""

        if preamp_dither_magnitude < 0 or not isfinite(preamp_dither_magnitude):
            raise ValueError("preamp dither magnitude must be finite and nonnegative")
        return preamp_dither_magnitude > self.minimum_preamp_dither_infimum


def pwl_slice_reachability(
    slice_lower_edge: float,
    *,
    nominal_residue_output_half_range: float,
    interstage_gain: float,
    next_stage_half_range: float = 1.0,
) -> PwlSliceReachability:
    """Bound dither needed to reach a PWL slice without nominal overload.

    ``nominal_residue_output_half_range`` is measured after the nominal linear
    gain, while dither is measured at the preamplifier residue summing node.
    The reachable output-magnitude supremum is therefore ``R + G*d``.
    """

    values = (
        slice_lower_edge,
        nominal_residue_output_half_range,
        interstage_gain,
        next_stage_half_range,
    )
    if any(not isfinite(value) for value in values):
        raise ValueError("reachability inputs must be finite")
    if slice_lower_edge < 0 or nominal_residue_output_half_range < 0:
        raise ValueError("slice and residue magnitudes must be nonnegative")
    if interstage_gain <= 0 or next_stage_half_range <= 0:
        raise ValueError("gain and next-stage range must be positive")
    if nominal_residue_output_half_range > next_stage_half_range:
        raise ValueError("nominal residue already exceeds the next-stage range")

    minimum = max(
        0.0,
        (slice_lower_edge - nominal_residue_output_half_range) / interstage_gain,
    )
    maximum = (
        next_stage_half_range - nominal_residue_output_half_range
    ) / interstage_gain
    return PwlSliceReachability(
        slice_lower_edge=slice_lower_edge,
        nominal_residue_output_half_range=nominal_residue_output_half_range,
        interstage_gain=interstage_gain,
        minimum_preamp_dither_infimum=minimum,
        maximum_preamp_dither_without_nominal_overload=maximum,
    )
