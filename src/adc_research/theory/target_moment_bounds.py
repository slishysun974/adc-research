"""Exact offline target-moment and same-record loss bounds.

Target intervals and equality groups are supplied assumptions, never inferred
from digital labels. No physical simulator or online updater is imported.
"""
from dataclasses import dataclass
from fractions import Fraction as F

from adc_research.theory.gated_mean_objective import _dot, _exact, _weights


@dataclass(frozen=True)
class TargetInterval:
    center: F
    radius: F
    lower: F
    upper: F
    minimizing_targets: tuple[F, ...]
    maximizing_targets: tuple[F, ...]


def affine_target_interval(offsets, coefficients, lower, upper, *, weights=None,
                           groups=None) -> TargetInterval:
    """Sharp interval of E[offset + coefficient*t] over a declared target box.

    Rows in one equality group share ONE target and must share its interval.
    Without groups each row is independent. Endpoints are attainable in that
    algebraic box, not necessarily in an allowed analog model family.
    Separate component extrema need not be jointly attainable.
    """
    arrays = tuple(tuple(_exact(x) for x in a)
                   for a in (offsets, coefficients, lower, upper))
    off, coef, lo, hi = arrays
    n = len(off)
    if not n or any(len(a) != n for a in arrays) or any(a > b for a, b in zip(lo, hi)):
        raise ValueError("consistent nonempty arrays and ordered target intervals required")
    p = _weights(weights, n)
    labels = tuple(range(n)) if groups is None else tuple(groups)
    if len(labels) != n:
        raise ValueError("one target equality group per row required")
    intervals, sums = {}, {}
    for label, a, b, c, w in zip(labels, lo, hi, coef, p, strict=True):
        try:
            if label in intervals and intervals[label] != (a, b):
                raise ValueError("one shared interval required within each equality group")
            intervals[label] = (a, b)
            sums[label] = sums.get(label, F(0)) + w*c
        except TypeError as exc:
            raise ValueError("target equality groups must be hashable") from exc
    center = sum((w*(o+c*(a+b)/2) for w, o, c, a, b in zip(p, off, coef, lo, hi)), F(0))
    radius = sum(((b-a)/2*abs(sums[label])
                  for label, (a, b) in intervals.items()), F(0))
    minimum = tuple(lo[i] if sums[label] >= 0 else hi[i] for i, label in enumerate(labels))
    maximum = tuple(hi[i] if sums[label] >= 0 else lo[i] for i, label in enumerate(labels))
    return TargetInterval(center, radius, center-radius, center+radius, minimum, maximum)


def loss_change_interval(old_outputs, new_outputs, lower, upper, *, weights=None,
                         groups=None) -> TargetInterval:
    """Sharp E[(Znew-t)^2-(Zold-t)^2] bounds for supplied actual readouts.

    Works for continuous, Q3, integer or clipped readouts if those exact values
    are supplied. No selector/gate preservation or infinitesimal update is
    required. This same-record intervention does not predict a future path.
    """
    old, new = (tuple(_exact(x) for x in a) for a in (old_outputs, new_outputs))
    if len(old) != len(new):
        raise ValueError("one old and new output per row required")
    d = tuple(b-a for a, b in zip(old, new))
    return affine_target_interval(tuple(x*(a+b) for x, a, b in zip(d, old, new)),
                                  tuple(-2*x for x in d), lower, upper,
                                  weights=weights, groups=groups)


@dataclass(frozen=True)
class LabelTargetSplit:
    value: F
    target_difference: F
    selection_difference: F
    probability_imbalance: F


def label_target_split(magnitude, plus_probability, plus_weight, minus_weight,
                       plus_target, minus_target) -> LabelTargetSplit:
    """One pre-injection condition: E[D*A*tau], D=+/-magnitude.

    A=q*G includes selection density and the actual gate. Conditional tag
    probability is an explicit assumption; observed global balance is not
    substituted for it. Targets here may be local rear/front targets.
    """
    d, p, ap, am, tp, tm = map(_exact, (magnitude, plus_probability, plus_weight,
                                      minus_weight, plus_target, minus_target))
    if d <= 0 or not 0 <= p <= 1 or ap < 0 or am < 0:
        raise ValueError("positive magnitude, probability in [0,1], nonnegative weights required")
    target = d*(ap+am)*(tp-tm)/4
    selection = d*(tp+tm)*(ap-am)/4
    imbalance = d*(p-F(1, 2))*(ap*tp+am*tm)
    return LabelTargetSplit(d*(p*ap*tp-(1-p)*am*tm), target, selection, imbalance)


@dataclass(frozen=True)
class CoupledTargetBounds:
    half_gradient: tuple[TargetInterval, ...]
    leakage: tuple[TargetInterval, ...]
    output_derivative_regular: bool


def coupled_target_bounds(result, coarse_codes, lower, upper, *, learning_weights=None,
                          evaluation_weights=None, groups=None) -> CoupledTargetBounds:
    """Component bounds of g=E_P[(Z-t)J] and both Gu target leakages.

    Rear/front state order follows WindowMeanMap. At a selector boundary the
    first output is a frozen-selector moment, not an ordinary derivative.
    Point leakage values require no protected gate neighborhood.
    """
    n = len(result.rows)
    coarse = tuple(_exact(x) for x in coarse_codes)
    if not n or len(coarse) != n:
        raise ValueError("one exact coarse code per row required")
    q, p = _weights(learning_weights, n), _weights(evaluation_weights, n)
    offsets_g, coefficients_g = [[] for _ in range(8)], [[] for _ in range(8)]
    offsets_l, coefficients_l = [[] for _ in range(8)], [[] for _ in range(8)]
    regular = True
    for row, base, weight in zip(result.rows, coarse, p, strict=True):
        j, slope = row.selector1, result.coefficients[4+row.selector1]
        jac = tuple(slope*x for x in row.basis2)+row.basis1
        gamma = tuple(x-(row.local2 if i == j else 0) for i, x in enumerate(row.basis1))
        constant = (row.dither1-base-_dot(result.coefficients[4:], gamma))/slope
        for i in range(8):
            offsets_g[i].append((base+row.local1)*jac[i])
            coefficients_g[i].append(-jac[i])
            if i < 4:
                label = row.dither2*int(row.gates2[i])
                offsets_l[i].append(label*constant)
                coefficients_l[i].append(label/slope)
            else:
                label = row.dither1*int(row.gates1[i-4])
                offsets_l[i].append(-label*base)
                coefficients_l[i].append(label)
        if weight:
            regular &= row.selector_margin1 > 0 and row.domain_margin1 > 0
    gradient = tuple(affine_target_interval(o, c, lower, upper, weights=p, groups=groups)
                     for o, c in zip(offsets_g, coefficients_g))
    leakage = tuple(affine_target_interval(o, c, lower, upper, weights=q, groups=groups)
                    for o, c in zip(offsets_l, coefficients_l))
    return CoupledTargetBounds(gradient, leakage, regular)
