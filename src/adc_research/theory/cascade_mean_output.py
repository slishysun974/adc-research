"""Offline exact two-bank finite output/MSE increments.

Reuses the frozen analytic digital basis, with no platform or updater imports.
"""
from dataclasses import dataclass
from fractions import Fraction as F
from typing import Sequence

from adc_research.theory.window_mean_map import WindowMeanMap, _basis, _dot, _exact


@dataclass(frozen=True)
class CascadeLossChange:
    """Offline same-record MSE change, in physical output-code units."""
    linear_changes: tuple[F, ...]
    bilinear_changes: tuple[F, ...]
    linear_error_cross: F
    linear_square: F
    bilinear_error_cross: F
    linear_bilinear_cross: F
    bilinear_square: F
    arithmetic_cross: F
    arithmetic_square: F
    mse_difference: F


def cascade_loss_change(result: WindowMeanMap, delta: Sequence[F],
                        old_errors: Sequence[F],
                        arithmetic_changes: Sequence[F] | None = None) -> CascadeLossChange:
    """Exact two-bank finite increment on a fixed digital evaluation record.

    delta uses rear/front bank order, and is an EFFECTIVE coefficient change,
    not a hidden Q22 request. old_errors are supplied by offline scoring only.
    arithmetic_changes, when supplied, are actual output changes minus the
    continuous two-bank changes. No gate preservation is needed for scoring;
    every front raw must stay in its original affine PWL segment. Reject a
    base selector boundary or a crossing, rather than suppressing its term.
    This is not a gradient of the rounded output or an online update rule.
    """
    change = tuple(_exact(x) for x in delta)
    errors = tuple(_exact(x) for x in old_errors)
    size = len(result.rows)
    arithmetic = ((F(0),)*size if arithmetic_changes is None else
                  tuple(_exact(x) for x in arithmetic_changes))
    if len(change) != 8 or len(errors) != size or len(arithmetic) != size or not size:
        raise ValueError("eight coefficient changes and one error/correction per row required")
    new_slopes = tuple(k+h for k, h in zip(result.coefficients, change))
    if any(not 0 < k < 2 for k in new_slopes):
        raise ValueError("changed slopes must remain strictly inside (0,2)")
    rear, front = change[:4], change[4:]
    linear, bilinear = [], []
    for row in result.rows:
        if row.selector_margin1 == 0 or row.domain_margin1 == 0:
            raise ValueError("base front raw lies on a selector/domain boundary")
        raw_change = _dot(row.basis2, rear)
        predicted_basis = tuple(p+(raw_change if j == row.selector1 else 0)
                                for j, p in enumerate(row.basis1))
        if _basis(row.raw1+raw_change, result.geometry.stage1_width) != predicted_basis:
            raise ValueError("front raw crosses its original affine PWL segment")
        linear.append(_dot(row.basis1, front)+
                      result.coefficients[4+row.selector1]*raw_change)
        bilinear.append(front[row.selector1]*raw_change)
    terms = [F(0)]*7
    for e, a, b, eta in zip(errors, linear, bilinear, arithmetic, strict=True):
        values = (2*e*a, a*a, 2*e*b, 2*a*b, b*b,
                  2*(e+a+b)*eta, eta*eta)
        terms = [total+value/size for total, value in zip(terms, values)]
    return CascadeLossChange(tuple(linear), tuple(bilinear), *terms, sum(terms, F(0)))
