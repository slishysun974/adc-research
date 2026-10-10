"""Exact two-active-slope correlation roots, including gate discontinuities.

The first correlation is affine and always ungated. Elimination reduces the
two unknown slopes to a line. All second-gate breakpoints on that legal line
are swept with rational arithmetic; sign changes across jumps are not roots.
This module only accepts digital-domain raw values and dither copies.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F
from typing import Sequence


def _exact(value):
    if isinstance(value, F):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return F(value)
    raise TypeError("values must be integers or explicit Fractions")


@dataclass(frozen=True)
class WeightedStageRow:
    raw: F
    dither: F
    count: int = 1

    def __post_init__(self):
        if not isinstance(self.raw, F) or not isinstance(self.dither, F) or self.dither == 0:
            raise ValueError("raw and nonzero dither require explicit Fractions")
        if not isinstance(self.count, int) or isinstance(self.count, bool) or self.count <= 0:
            raise ValueError("count must be a positive integer")


def stage_basis(raw: F, width: F):
    raw, width = _exact(raw), _exact(width)
    if width <= 0 or not -4*width <= raw < 4*width:
        raise ValueError("raw is outside the declared signed digital PWL domain")
    sign = (raw > 0)-(raw < 0)
    return tuple(sign*min(max(abs(raw)-i*width, F(0)), width) for i in range(4))


def stage_correlations(rows: Sequence[WeightedStageRow], coefficients, width):
    rows, coefficients, width = tuple(rows), tuple(_exact(x) for x in coefficients), _exact(width)
    if not rows or len(coefficients) != 4 or any(not 0 < x < 2 for x in coefficients):
        raise ValueError("nonempty rows and four slopes inside (0,2) are required")
    sums = [F(0)]*4
    for row in rows:
        basis = stage_basis(row.raw, width)
        local = sum((a*b for a, b in zip(coefficients, basis)), F(0))-row.dither
        for i in range(4):
            threshold = width*sum(coefficients[:i], F(0))
            if i == 0 or abs(local) >= threshold:
                sums[i] += row.count*row.dither*local
    total = sum(row.count for row in rows)
    return tuple(x/total for x in sums)


@dataclass(frozen=True)
class ScalarCell:
    low: F
    high: F
    correlation_slope: F
    correlation_intercept: F


@dataclass(frozen=True)
class GateBoundary:
    parameter: F
    left_limit: F
    value: F
    right_limit: F
    crossing_rows: int


@dataclass(frozen=True)
class IsolatedRoot:
    parameter: F
    coefficients: tuple[F, ...]
    at_gate_boundary: bool


@dataclass(frozen=True)
class TwoSlopeRootScan:
    status: str
    complete_on_declared_domain: bool
    primary_coefficients: tuple[F, F]
    primary_constant: F
    coefficient_line_slopes: tuple[F, F] | None
    coefficient_line_intercepts: tuple[F, F] | None
    parameter_interval: tuple[F, F] | None
    roots: tuple[IsolatedRoot, ...]
    zero_intervals: tuple[tuple[F, F], ...]
    cells: tuple[ScalarCell, ...]
    boundaries: tuple[GateBoundary, ...]


def scan_two_slope_roots(rows: Sequence[WeightedStageRow], width,
                        fixed_high=(F(1), F(1))) -> TwoSlopeRootScan:
    """Enumerate C0=C1=0 with the third/fourth slopes held fixed.

    The legal domain is 0<k0,k1<2, with fixed high slopes also in (0,2).
    Equality gates use >=. No floating root tolerance or smoothness
    assumption is used. A zero primary equation leaves a two-dimensional
    problem and is explicitly reported as not completed by this solver.
    """
    rows, width = tuple(rows), _exact(width)
    fixed = tuple(_exact(x) for x in fixed_high)
    if not rows or any(not isinstance(row, WeightedStageRow) for row in rows):
        raise TypeError("a nonempty weighted digital stage record is required")
    if width <= 0 or len(fixed) != 2 or any(not 0 < x < 2 for x in fixed):
        raise ValueError("positive width and two fixed slopes inside (0,2) are required")
    bases = tuple(stage_basis(row.raw, width) for row in rows)
    total = sum(row.count for row in rows)
    primary = tuple(sum((row.count*row.dither*basis[i] for row, basis in zip(rows, bases)), F(0))
                    for i in range(2))
    constant = sum((row.count*row.dither*(fixed[0]*basis[2]+fixed[1]*basis[3]-row.dither)
                    for row, basis in zip(rows, bases)), F(0))

    def result(status, complete, slopes=None, intercepts=None, interval=None,
               roots=(), zero_intervals=(), cells=(), boundaries=()):
        return TwoSlopeRootScan(status, complete, tuple(x/total for x in primary), constant/total,
                                slopes, intercepts, interval, tuple(roots), tuple(zero_intervals),
                                tuple(cells), tuple(boundaries))

    if not any(primary):
        return result("primary_has_no_zero" if constant else "primary_identically_zero",
                      bool(constant))
    pivot = 0 if primary[0] else 1
    free = 1-pivot
    p, q = [F(0)]*2, [F(0)]*2
    p[free] = F(1)
    p[pivot], q[pivot] = -primary[free]/primary[pivot], -constant/primary[pivot]
    low, high = F(0), F(2)
    if p[pivot] == 0:
        if not 0 < q[pivot] < 2:
            return result("primary_line_misses_domain", True, tuple(p), tuple(q))
    else:
        endpoints = sorted((-q[pivot]/p[pivot], (2-q[pivot])/p[pivot]))
        low, high = max(low, endpoints[0]), min(high, endpoints[1])
        if low >= high:
            return result("primary_line_misses_domain", True, tuple(p), tuple(q))
    threshold_a, threshold_b = width*p[0], width*q[0]
    terms, events = [], {}
    for n, (row, basis) in enumerate(zip(rows, bases)):
        a = sum((p[i]*basis[i] for i in range(2)), F(0))
        b = sum((q[i]*basis[i] for i in range(2)), F(0))+fixed[0]*basis[2]+fixed[1]*basis[3]-row.dither
        terms.append((a, b, row.count*row.dither/total))
        for sign in (-1, 1):
            slope, offset = a-sign*threshold_a, b-sign*threshold_b
            if slope:
                point = -offset/slope
                if low < point < high:
                    events.setdefault(point, set()).add(n)
    points = sorted(events)
    initial = (low+(points[0] if points else high))/2
    gates = [abs(a*initial+b) >= threshold_a*initial+threshold_b for a, b, weight in terms]
    slope = sum((weight*a for gate, (a, b, weight) in zip(gates, terms) if gate), F(0))
    intercept = sum((weight*b for gate, (a, b, weight) in zip(gates, terms) if gate), F(0))
    roots, intervals, cells, boundaries = [], [], [], []

    def coefficients(point):
        return (*(p[i]*point+q[i] for i in range(2)), *fixed)

    def process_cell(left, right):
        cells.append(ScalarCell(left, right, slope, intercept))
        if slope:
            point = -intercept/slope
            if left < point < right:
                roots.append(IsolatedRoot(point, coefficients(point), False))
        elif intercept == 0:
            intervals.append((left, right))

    start = low
    for point in points:
        process_cell(start, point)
        left_value = slope*point+intercept
        boundary_value = left_value
        for n in events[point]:
            a, b, weight = terms[n]
            if not gates[n]:
                boundary_value += weight*(a*point+b)
        if boundary_value == 0:
            roots.append(IsolatedRoot(point, coefficients(point), True))
        for n in events[point]:
            a, b, weight = terms[n]
            direction = -1 if gates[n] else 1
            slope += direction*weight*a
            intercept += direction*weight*b
            gates[n] = not gates[n]
        boundaries.append(GateBoundary(point, left_value, boundary_value,
                                       slope*point+intercept, len(events[point])))
        start = point
    process_cell(start, high)
    status = "zero_intervals_present" if intervals else "isolated_roots" if roots else "no_roots"
    return result(status, True, tuple(p), tuple(q), (low, high), roots, intervals, cells, boundaries)
