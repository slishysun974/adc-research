"""Exact unrounded Gu window mean and analytic fixed-mask sensitivity.

Only decoded digital observations and reviewed digital geometry are inputs.
This conditional mean map is independent of the integer updater and the
experimental analog platform. Its Jacobian is analytic, not a fitted or
finite-difference ADC predictor. Gate/selector margins delimit its use.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F
from typing import Sequence

from adc_research.calibration.observation import DigitalCalibrationSample


def _exact(value: object) -> F:
    if isinstance(value, F):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return F(value)
    raise TypeError("mean-map values must be integers or explicit Fractions")


@dataclass(frozen=True)
class MeanGeometry:
    stage2_width: F = F(32)
    stage1_width: F = F(128)
    stage2_symbol_weight: F = F(128)
    backend_weight: F = F(1)
    stage2_dither_magnitude: F = F(16)
    stage1_dither_magnitude: F = F(64)

    def __post_init__(self) -> None:
        if any(not isinstance(x, F) or x <= 0 for x in self.__dict__.values()):
            raise ValueError("geometry requires positive explicit Fractions")


@dataclass(frozen=True)
class MeanRow:
    raw2: F
    raw1: F
    basis2: tuple[F, ...]
    basis1: tuple[F, ...]
    local2: F
    local1: F
    dither2: F
    dither1: F
    gates2: tuple[bool, ...]
    gates1: tuple[bool, ...]
    gate_margins2: tuple[F, ...]
    gate_margins1: tuple[F, ...]
    selector1: int
    selector_margin1: F
    domain_margin1: F


@dataclass(frozen=True)
class WindowMeanMap:
    """State order is stage-2 four slopes, then stage-1 four slopes."""
    coefficients: tuple[F, ...]
    geometry: MeanGeometry
    mean_products: tuple[F, ...]
    fixed_mask_jacobian: tuple[tuple[F, ...], ...]
    rows: tuple[MeanRow, ...]
    open_cell_regular: bool


@dataclass(frozen=True)
class MeanCellCertificate:
    coefficient_radius: F
    gates2_stable: tuple[tuple[bool, ...], ...]
    gates1_stable: tuple[tuple[bool, ...], ...]
    selectors1_stable: tuple[bool, ...]
    domains1_stable: tuple[bool, ...]
    coefficient_domain_stable: bool
    all_masks_and_domains_stable: bool
    taylor_remainder_bounds: tuple[F, ...]


@dataclass(frozen=True)
class Q3MeanErrorCertificate:
    local_error2: F
    local_error1: F
    threshold_error: F
    mean_product_error_bounds: tuple[F, ...]
    correlation_sign_preserved: tuple[bool, ...]


def _basis(raw: F, width: F) -> tuple[F, ...]:
    if not -4*width <= raw < 4*width:
        raise ValueError("unrounded raw value is outside the declared signed PWL domain")
    sign = 1 if raw > 0 else -1 if raw < 0 else 0
    return tuple(sign*min(max(abs(raw)-i*width, F(0)), width) for i in range(4))


def _dot(a, b) -> F:
    return sum((x*y for x, y in zip(a, b, strict=True)), F(0))


def analyze_window_mean(samples: Sequence[DigitalCalibrationSample], coefficients: Sequence[F],
                        geometry: MeanGeometry = MeanGeometry()) -> WindowMeanMap:
    """Build exact mean products and the derivative with gates held fixed.

    The returned matrix is a true local Jacobian only when the reported open
    gate/selector/domain cell is regular. At a boundary it remains a named
    fixed-mask sensitivity, not a derivative of the discontinuous mean map.
    """
    observations = tuple(samples)
    if not observations or any(not isinstance(o, DigitalCalibrationSample) for o in observations):
        raise TypeError("a nonempty decoded digital observation sequence is required")
    slopes = tuple(_exact(x) for x in coefficients)
    if len(slopes) != 8 or any(not 0 < x < 2 for x in slopes):
        raise ValueError("eight slopes strictly inside (0,2) are required")
    k2, k1 = slopes[:4], slopes[4:]
    thresholds2 = tuple(geometry.stage2_width*sum(k2[:i], F(0)) for i in range(4))
    thresholds1 = tuple(geometry.stage1_width*sum(k1[:i], F(0)) for i in range(4))
    sums = [F(0)]*8
    matrix = [[F(0)]*8 for _ in range(8)]
    rows = []
    for sample in observations:
        if sample.stage1_dither_symbol not in (-1, 1) or sample.stage2_dither_symbol not in (-1, 1):
            raise ValueError("the declared mean geometry requires +/-1 dither symbols")
        d2 = geometry.stage2_dither_magnitude*_exact(sample.stage2_dither_symbol)
        d1 = geometry.stage1_dither_magnitude*_exact(sample.stage1_dither_symbol)
        raw2 = geometry.backend_weight*_exact(sample.backend_centered_code)
        psi2 = _basis(raw2, geometry.stage2_width)
        y2 = _dot(k2, psi2)-d2
        raw1 = geometry.stage2_symbol_weight*_exact(sample.stage2_symbol)+y2
        psi1 = _basis(raw1, geometry.stage1_width)
        y1 = _dot(k1, psi1)-d1
        gates2 = tuple(i == 0 or abs(y2) >= threshold for i, threshold in enumerate(thresholds2))
        gates1 = tuple(i == 0 or abs(y1) >= threshold for i, threshold in enumerate(thresholds1))
        selector = min(int(abs(raw1)//geometry.stage1_width), 3)
        selector_margin = min(abs(raw1-sign*i*geometry.stage1_width)
                              for sign in (-1, 1) for i in (1, 2, 3))
        domain_margin = min(raw1+4*geometry.stage1_width, 4*geometry.stage1_width-raw1)
        margins2 = tuple(abs(abs(y2)-threshold) for threshold in thresholds2[1:])
        margins1 = tuple(abs(abs(y1)-threshold) for threshold in thresholds1[1:])
        for i in range(4):
            if gates2[i]:
                sums[i] += d2*y2
                for j in range(4):
                    matrix[i][j] += d2*psi2[j]
            if gates1[i]:
                sums[4+i] += d1*y1
                for j in range(4):
                    matrix[4+i][j] += d1*k1[selector]*psi2[j]
                    matrix[4+i][4+j] += d1*psi1[j]
        rows.append(MeanRow(raw2, raw1, psi2, psi1, y2, y1, d2, d1, gates2, gates1,
                            margins2, margins1, selector, selector_margin, domain_margin))
    size = len(observations)
    regular = all(row.selector_margin1 > 0 and row.domain_margin1 > 0 and
                  all(x > 0 for x in (*row.gate_margins1, *row.gate_margins2)) for row in rows)
    return WindowMeanMap(slopes, geometry, tuple(x/size for x in sums),
                          tuple(tuple(x/size for x in line) for line in matrix), tuple(rows), regular)


def certify_mean_cell(result: WindowMeanMap, radius: F) -> MeanCellCertificate:
    """Sufficient mask/domain preservation and quadratic Taylor remainder.

    Every one of the eight slope perturbations is bounded by radius. This
    certificate does not promise a useful radius at a gate equality. Radius
    zero preserves the point but does not turn it into a regular open cell.
    """
    radius = _exact(radius)
    if radius < 0:
        raise ValueError("coefficient radius must be nonnegative")
    g = result.geometry
    kmax = max(result.coefficients[4:])+radius
    coefficient_safe = radius == 0 or all(radius < min(x, 2-x) for x in result.coefficients)
    gate2, gate1, selectors, domains = [], [], [], []
    remainder = [F(0)]*8
    for row in result.rows:
        error2 = abs(row.raw2)*radius
        error1 = abs(row.raw1)*radius+kmax*error2
        gate2.append(tuple(radius == 0 or margin > error2+i*g.stage2_width*radius
                           for i, margin in enumerate(row.gate_margins2, 1)))
        gate1.append(tuple(radius == 0 or margin > error1+i*g.stage1_width*radius
                           for i, margin in enumerate(row.gate_margins1, 1)))
        selectors.append(radius == 0 or row.selector_margin1 > error2)
        domains.append(radius == 0 or row.domain_margin1 > error2)
        for i, active in enumerate(row.gates1):
            if active:
                remainder[4+i] += abs(row.dither1)*abs(row.raw2)*radius**2/len(result.rows)
    stable = (coefficient_safe and all(selectors) and all(domains) and
              all(all(row) for row in (*gate2, *gate1)))
    return MeanCellCertificate(radius, tuple(gate2), tuple(gate1), tuple(selectors), tuple(domains),
                                coefficient_safe, stable, tuple(remainder))


def phase_product_means(result: WindowMeanMap) -> tuple[tuple[F, ...], ...]:
    """Four consecutive lanes per phase; their dependence is retained."""
    if len(result.rows) % 4:
        raise ValueError("phase analysis requires complete groups of four conversions")
    phases = []
    for start in range(0, len(result.rows), 4):
        sums = [F(0)]*8
        for row in result.rows[start:start+4]:
            for i in range(4):
                sums[i] += row.dither2*row.local2*int(row.gates2[i])
                sums[4+i] += row.dither1*row.local1*int(row.gates1[i])
        phases.append(tuple(x/4 for x in sums))
    return tuple(phases)


def certify_q3_mean_error(result: WindowMeanMap) -> Q3MeanErrorCertificate:
    """Bound default Q1.10/Q3 local and mean-product errors at exported slopes.

    Assumes nearest-even product/threshold rounding and offset rounding after
    the coefficient sum, with both raw inputs inside their PWL domains. It
    does not bound a differently rounded updater or coefficient export error
    relative to a hidden Q22 value. Sign preservation concerns this same
    finite unrounded correlation, not an unknown population/loss gradient.
    """
    if any((x*1024).denominator != 1 for x in result.coefficients):
        raise ValueError("Q3 comparison requires exported Q1.10 slopes")
    if any((x*8).denominator != 1 for x in result.geometry.__dict__.values()):
        raise ValueError("geometry must be exactly representable in Q3")
    error2, error1 = F(1, 8), (1+max(result.coefficients[4:]))/8
    threshold_error = F(1, 16)
    bounds = [F(0)]*8
    for row in result.rows:
        for bank, local, dither, gates, margins, error in (
            (0, row.local2, row.dither2, row.gates2, row.gate_margins2, error2),
            (1, row.local1, row.dither1, row.gates1, row.gate_margins1, error1),
        ):
            for i in range(4):
                protected = i == 0 or margins[i-1] > error+threshold_error
                contribution = error*int(gates[i]) if protected else error+abs(local)
                bounds[bank*4+i] += abs(dither)*contribution/len(result.rows)
    return Q3MeanErrorCertificate(error2, error1, threshold_error, tuple(bounds),
                                  tuple(abs(mean) > bound for mean, bound in zip(result.mean_products, bounds)))


def exact_matrix_rank(matrix: Sequence[Sequence[F]]) -> int:
    values = [[_exact(x) for x in row] for row in matrix]
    if not values or any(len(row) != len(values[0]) for row in values):
        raise ValueError("a nonempty rectangular matrix is required")
    rank = 0
    for column in range(len(values[0])):
        pivot = next((i for i in range(rank, len(values)) if values[i][column]), None)
        if pivot is None:
            continue
        values[rank], values[pivot] = values[pivot], values[rank]
        divisor = values[rank][column]
        values[rank] = [x/divisor for x in values[rank]]
        for i in range(rank+1, len(values)):
            factor = values[i][column]
            values[i] = [x-factor*y for x, y in zip(values[i], values[rank])]
        rank += 1
        if rank == len(values):
            break
    return rank


def mean_update_infinity_bound(result: WindowMeanMap, step_per_window: Sequence[F]) -> F:
    """Exact induced infinity norm of I-diag(step)*analytic sensitivity.

    A value below one is a local sufficient contraction condition only for a
    regular cell, an appropriate uniform neighborhood, and a fixed observation
    law. A finite-window matrix alone is not a convergence theorem.
    """
    steps = tuple(_exact(x) for x in step_per_window)
    if len(steps) != 8 or any(x <= 0 for x in steps):
        raise ValueError("eight positive exact window steps are required")
    return max(sum(abs(F(int(i == j))-steps[i]*value) for j, value in enumerate(row))
               for i, row in enumerate(result.fixed_mask_jacobian))
