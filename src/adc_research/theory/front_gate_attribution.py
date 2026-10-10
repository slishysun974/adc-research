"""Exact digital gate attribution, independent of targets and analog truth."""

from dataclasses import dataclass
from fractions import Fraction as F

from adc_research.theory.gated_correlation_roots import WeightedStageRow, stage_basis


@dataclass(frozen=True)
class StageGateFrame:
    observation: WeightedStageRow
    basis: tuple[F, ...]
    local: F
    gates: tuple[bool, ...]


def stage_gate_frames(rows, coefficients, width):
    rows, coefficients = tuple(rows), tuple(coefficients)
    if not isinstance(width, F) or width <= 0:
        raise ValueError("positive explicit Fraction width required")
    if (not rows or any(not isinstance(row, WeightedStageRow) for row in rows)
            or len(coefficients) != 4
            or any(not isinstance(k, F) or not 0 < k < 2 for k in coefficients)):
        raise ValueError("digital rows and four explicit slopes inside (0,2) required")
    frames = []
    thresholds = tuple(width*sum(coefficients[:i], F(0)) for i in range(4))
    for row in rows:
        basis = stage_basis(row.raw, width)
        local = sum((k*p for k, p in zip(coefficients, basis)), F(0))-row.dither
        gates = tuple(i == 0 or abs(local) >= thresholds[i] for i in range(4))
        frames.append(StageGateFrame(row, basis, local, gates))
    return tuple(frames)


def inner_second_gate(raw, dither, first_slope, width):
    """Exact identity on |raw|<=width, including the >= boundary.

    The second basis is zero. Its gate opens iff sign(dither)*raw <=
    |dither|/first_slope-width. Every open row has dither*local <=
    -|dither|*width*first_slope < 0. If first_slope <= |dither|/(2*width),
    every inner row opens regardless of dither polarity.
    """
    if any(not isinstance(x, F) for x in (raw, dither, first_slope, width)):
        raise TypeError("explicit Fraction values required")
    if dither == 0 or first_slope <= 0 or width <= 0 or abs(raw) > width:
        raise ValueError("nonzero dither, positive slope/width, inner raw required")
    sign = (dither > 0)-(dither < 0)
    return sign*raw <= abs(dither)/first_slope-width


def gate_sources(frames):
    """Contributions use the whole-record denominator, so groups add exactly."""
    frames = tuple(frames)
    if not frames:
        raise ValueError("nonempty digital frames required")
    total = sum(f.observation.count for f in frames)
    result = []
    for i in range(4):
        groups = []
        for supported in (False, True):
            selected = tuple(f for f in frames if f.gates[i] and (f.basis[i] != 0) == supported)
            count = sum(f.observation.count for f in selected)
            correlation = sum((f.observation.count*f.observation.dither*f.local
                               for f in selected), F(0))/total
            groups.append({"basis_nonzero": supported, "count": count,
                           "positive_dither_count": sum(f.observation.count for f in selected
                                                        if f.observation.dither > 0),
                           "negative_dither_count": sum(f.observation.count for f in selected
                                                        if f.observation.dither < 0),
                           "correlation": correlation,
                           "self_sensitivity": sum((f.observation.count*f.observation.dither*f.basis[i]
                                                    for f in selected), F(0))/total})
        result.append({"gate_index": i, "open_count": sum(g["count"] for g in groups),
                       "correlation": sum((g["correlation"] for g in groups), F(0)),
                       "groups": groups})
    matrix = tuple(tuple(sum((f.observation.count*f.observation.dither*f.basis[j]
                             for f in frames if f.gates[i]), F(0))/total
                         for j in range(2)) for i in range(2))
    return {"total": total, "gates": result, "fixed_mask_low_matrix": matrix,
            "fixed_mask_low_determinant": matrix[0][0]*matrix[1][1]-matrix[0][1]*matrix[1][0]}


def compare_gate_masks(left, right, index=1):
    left, right = tuple(left), tuple(right)
    if not left or len(left) != len(right) or index not in range(4):
        raise ValueError("aligned nonempty frames and legal gate index required")
    if any(a.observation != b.observation or a.basis != b.basis
           for a, b in zip(left, right)):
        raise ValueError("both branches must use the same digital raw/dither rows")
    total = sum(f.observation.count for f in left)
    counts = {"neither": 0, "left_only": 0, "right_only": 0, "both": 0}
    for a, b in zip(left, right):
        key = "both" if a.gates[index] and b.gates[index] else (
            "left_only" if a.gates[index] else "right_only" if b.gates[index] else "neither")
        counts[key] += a.observation.count
    # Matrix [mask branch][output branch]; observations share exact weights.
    cross = tuple(tuple(sum((a.observation.count*a.observation.dither*(a if value == 0 else b).local
                            for a, b in zip(left, right)
                            if (a if mask == 0 else b).gates[index]), F(0))/total
                        for value in range(2)) for mask in range(2))
    difference = sum((a.observation.count*a.observation.dither*(b.local-a.local)
                      for a, b in zip(left, right)), F(0))/total
    return {"gate_index": index, "membership_counts": counts,
            "cross_mask_correlations": cross,
            "ungated_output_difference_correlation": difference}
