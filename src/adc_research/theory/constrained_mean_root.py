"""Weighted digital empirical mean and a uniform box around a constrained root."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F

from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.theory.window_mean_map import WindowMeanMap, analyze_window_mean
from adc_research.theory.window_excitation import restricted_transition


@dataclass(frozen=True)
class WeightedMean:
    base: WindowMeanMap
    counts: tuple[int, ...]
    mean_products: tuple[F, ...]
    jacobian: tuple[tuple[F, ...], ...]


def weighted_cascade_mean(record, coefficients):
    """Preserve empirical weights while evaluating analytic digital rows."""
    record = tuple(record)
    if not record or any(not isinstance(sample, DigitalCalibrationSample) or
            not isinstance(count, int) or isinstance(count, bool) or count <= 0
            for sample, count in record):
        raise ValueError("weighted decoded observations with positive integer counts are required")
    base = analyze_window_mean(tuple(sample for sample, count in record), coefficients)
    counts = tuple(count for sample, count in record)
    total = sum(counts)
    sums, jacobian = [F(0)]*8, [[F(0)]*8 for _ in range(8)]
    for row, count in zip(base.rows, counts):
        for i in range(4):
            if row.gates2[i]:
                sums[i] += count*row.dither2*row.local2
                for j in range(4):
                    jacobian[i][j] += count*row.dither2*row.basis2[j]
            if row.gates1[i]:
                sums[4+i] += count*row.dither1*row.local1
                for j in range(4):
                    jacobian[4+i][j] += count*row.dither1*base.coefficients[4+row.selector1]*row.basis2[j]
                    jacobian[4+i][4+j] += count*row.dither1*row.basis1[j]
    return WeightedMean(base, counts, tuple(x/total for x in sums),
                        tuple(tuple(x/total for x in row) for row in jacobian))


def low4_cell_stable(mean: WeightedMean, radius: F):
    """Protect the clamped subspace, allowing an identically equal gate.

    A full-space boundary may be constant when high slopes are fixed. Such
    a >= gate stays on. A tie that varies in a free direction is rejected.
    """
    if not isinstance(radius, F) or radius < 0:
        raise ValueError("a nonnegative exact radius is required")
    k, geometry = mean.base.coefficients, mean.base.geometry
    if any(radius >= min(k[i], 2-k[i]) for i in (0, 1, 4, 5)):
        return False
    for row in mean.base.rows:
        back_sensitivity = sum(abs(x) for x in row.basis2[:2])
        error2 = back_sensitivity*radius
        error1 = sum(abs(x) for x in row.basis1[:2])*radius+(max(k[4:])+radius)*error2
        for i, margin in enumerate(row.gate_margins2, 1):
            sign = (row.local2 > 0)-(row.local2 < 0)
            invariant_tie = margin == 0 and all(
                sign*row.basis2[j] == geometry.stage2_width*int(j < i) for j in (0, 1))
            if not invariant_tie and margin <= error2+min(i, 2)*geometry.stage2_width*radius:
                return False
        for i, margin in enumerate(row.gate_margins1, 1):
            sign = (row.local1 > 0)-(row.local1 < 0)
            invariant_tie = margin == 0 and back_sensitivity == 0 and all(
                sign*row.basis1[j] == geometry.stage1_width*int(j < i) for j in (0, 1))
            if not invariant_tie and margin <= error1+min(i, 2)*geometry.stage1_width*radius:
                return False
        if back_sensitivity and (row.selector_margin1 <= error2 or row.domain_margin1 <= error2):
            return False
    return True


def certify_low4_root(mean: WeightedMean, steps):
    """Certify a uniform infinity-norm bound in a finite-record fixed cell.

    Coordinates 0,1,4,5 can move; other slopes remain clamped. Gu's full
    empirical map has the same invariant box only if those other gates all
    stay closed. This is not the stochastic/window-varying Q22 algorithm.
    """
    active = (0, 1, 4, 5)
    if any(mean.mean_products[i] != 0 for i in active):
        raise ValueError("the four declared correlations must be exactly zero")
    transition = restricted_transition(mean.jacobian, steps, active)
    row_norms = tuple(sum(abs(x) for x in row) for row in transition.transition)
    outside = (2, 3, 6, 7)
    frozen_closed = all(not row.gates2[2] and not row.gates2[3] and
                        not row.gates1[2] and not row.gates1[3] for row in mean.base.rows)
    constants = [F(0)]*4
    total = sum(mean.counts)
    for i in (0, 1):
        constant = sum((count*abs(row.dither1)*int(row.gates1[i])*
                        sum(abs(x) for x in row.basis2[:2])
                        for row, count in zip(mean.base.rows, mean.counts)), F(0))/total
        # Two front columns vary through raw1, plus the back/front coupling.
        constants[2+i] = 3*steps[4+i]*constant
    radius, stable = F(1, 1024), False
    q = max(row_norms)
    relative_regular = low4_cell_stable(mean, F(0))
    if relative_regular:
        for attempt in range(80):
            stable = low4_cell_stable(mean, radius)
            q = max(norm+constant*radius for norm, constant in zip(row_norms, constants))
            if stable and (max(row_norms) >= 1 or q < 1):
                break
            radius /= 2
        else:
            radius, stable = F(0), False
    else:
        radius = F(0)
    constrained = stable and q < 1
    front = tuple(tuple(transition.transition[i][j] for j in (2, 3)) for i in (2, 3))
    characteristic_at_one = (1-front[0][0])*(1-front[1][1])-front[0][1]*front[1][0]
    return {"active_coordinates": active, "open_cell_regular": mean.base.open_cell_regular,
        "regular_on_clamped_subspace": relative_regular,
        "clamped_transition": transition.transition, "center_norm": max(row_norms),
        "uniform_row_variation_constants": tuple(constants), "box_radius": radius,
        "all_masks_and_domains_stable": stable, "uniform_norm_bound": q,
        "constrained_empirical_map_locally_contracts": constrained,
        "gu_linear_subspace_invariant": transition.invariant,
        "frozen_gates_all_closed": frozen_closed,
        "frozen_correlations_exactly_zero": all(mean.mean_products[i] == 0 for i in outside),
        "full_gu_empirical_map_has_same_invariant_box": constrained and frozen_closed,
        "front_characteristic_polynomial_at_one": characteristic_at_one,
        "front_linearized_eigenvalue_above_one_proved": relative_regular and characteristic_at_one < 0,
        "coefficient_export_half_lsb_fits_box": stable and radius >= F(1, 2048),
        "q22_algorithm_convergence_certified": False}
