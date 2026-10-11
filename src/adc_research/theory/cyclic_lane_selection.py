"""Offline cyclic lane-offset statistics on a complete fixed window.

Every product is supplied by the caller. This is neither an online selector
nor a claim that a deterministic rotating control is conditionally uniform.
"""
from dataclasses import dataclass
from fractions import Fraction as F

from adc_research.theory.lane_phase_statistics import _exact
from adc_research.theory.selection_output_response import vector_moments


# Derived from nearly quarter-spaced physical slots, with one slot per lane.
# phase-major slots at base0: (0,61,30,91); sorted gaps (30,31,30,29).
FOUR_LANE_OFFSETS = (0,15,7,22)


def cyclic_indices(base, offsets=FOUR_LANE_OFFSETS, phases=30):
    """Mathematical same-window indices; does not advance a control state."""
    offsets = tuple(offsets)
    if (type(phases) is not int or phases <= 0 or type(base) is not int
            or not 0 <= base < phases or not offsets
            or any(type(x) is not int or not 0 <= x < phases for x in offsets)):
        raise ValueError('valid phase count, base and integer lane offsets required')
    lanes = len(offsets)
    return tuple(lanes*((base+shift)%phases)+lane for lane,shift in enumerate(offsets))


@dataclass(frozen=True)
class CyclicLaneMoments:
    full_mean: tuple[F, ...]
    selected_mean: tuple[F, ...]
    covariance: tuple[tuple[F, ...], ...]
    phase_means: tuple[tuple[F, ...], ...]
    indices: tuple[tuple[int, ...], ...]


def cyclic_lane_moments(products, offsets=FOUR_LANE_OFFSETS):
    """Ideal UNIFORM common base with fixed lane offsets, old state fixed."""
    rows = tuple(tuple(_exact(x) for x in row) for row in products)
    shifts = tuple(offsets)
    if (not shifts or not rows or not rows[0] or len(rows)%len(shifts)
            or any(len(row)!=len(rows[0]) for row in rows)):
        raise ValueError('complete phase-major products and equal dimensions required')
    lanes,phases,dim=len(shifts),len(rows)//len(shifts),len(rows[0])
    indices=tuple(cyclic_indices(base,shifts,phases) for base in range(phases))
    phase_means=tuple(tuple(sum((rows[i][j] for i in chosen),F(0))/lanes
                            for j in range(dim)) for chosen in indices)
    mean,cov=vector_moments(phase_means)
    full=tuple(sum((row[j] for row in rows),F(0))/len(rows) for j in range(dim))
    return CyclicLaneMoments(full,mean,cov,phase_means,indices)


def lag_covariance_sum(products, offsets):
    """Independent cross-lag formula, intended for small exact controls.

    V=1/L^2 sum_l,m K_l,m(offset_m-offset_l). This is exact but can be
    expensive for large vector dimensions; no interpolation or fit is used.
    """
    rows=tuple(tuple(_exact(x) for x in row) for row in products)
    shifts=tuple(offsets)
    if (not shifts or not rows or not rows[0] or len(rows)%len(shifts)
            or any(len(row)!=len(rows[0]) for row in rows)):
        raise ValueError('complete phase-major equal-length products required')
    lanes,phases,dim=len(shifts),len(rows)//len(shifts),len(rows[0])
    cyclic_indices(0,shifts,phases)
    means=tuple(tuple(sum((rows[lanes*p+l][j] for p in range(phases)),F(0))/phases
                      for j in range(dim)) for l in range(lanes))
    return tuple(tuple(sum(((rows[lanes*p+l][i]-means[l][i])*
                            (rows[lanes*((p+shifts[m]-shifts[l])%phases)+m][j]-means[m][j])
                            for l in range(lanes) for m in range(lanes) for p in range(phases)),F(0))
                        /(phases*lanes**2) for j in range(dim)) for i in range(dim))
