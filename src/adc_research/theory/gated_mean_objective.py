"""Exact offline fixed-state selection and affine objective moments.

The input law is supplied explicitly. No platform, online updater, PRNG
independence, stationary law or target acquisition is inferred here. Targets
belong to offline scoring only; masks are values at the declared base state.
"""
from dataclasses import dataclass
from fractions import Fraction as F
from typing import Sequence


def _exact(value):
    if isinstance(value, F):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return F(value)
    raise TypeError("use integers or explicit Fractions")


def _weights(weights, size):
    values = (F(1),)*size if weights is None else tuple(_exact(x) for x in weights)
    if len(values) != size or any(x < 0 for x in values) or not sum(values):
        raise ValueError("one nonnegative weight per row and positive total required")
    total = sum(values)
    return tuple(x/total for x in values)


def _dot(a, b):
    return sum((x*y for x, y in zip(a, b, strict=True)), F(0))


@dataclass(frozen=True)
class PhaseSelectionMoments:
    full_mean: tuple[F, ...]
    selected_mean: tuple[F, ...]
    bias: tuple[F, ...]
    covariance: tuple[tuple[F, ...], ...]
    phase_means: tuple[tuple[F, ...], ...]


def phase_selection_moments(products: Sequence[Sequence[F]],
                            probabilities: Sequence[F] | None = None,
                            phase_size: int = 4) -> PhaseSelectionMoments:
    """Selector expectation conditional on ALL products and the old state.

    Mean units are per conversion: multiply by the full row count for window
    sums. Covariance is only that due to drawing a phase from the given law,
    not sample noise, closed-loop coefficient covariance or PRNG evidence.
    """
    rows = tuple(tuple(_exact(x) for x in row) for row in products)
    if (not rows or not isinstance(phase_size, int) or isinstance(phase_size, bool)
            or phase_size <= 0 or len(rows) % phase_size or not rows[0]
            or any(len(row) != len(rows[0]) for row in rows)):
        raise ValueError("complete equal-size phases of nonempty product vectors required")
    count, dimension = len(rows)//phase_size, len(rows[0])
    probabilities = ((F(1, count),)*count if probabilities is None else
                     tuple(_exact(x) for x in probabilities))
    if len(probabilities) != count or any(x < 0 for x in probabilities) or sum(probabilities) != 1:
        raise ValueError("phase probabilities must be nonnegative and sum exactly to one")
    phases = tuple(tuple(sum((rows[n][j] for n in range(p*phase_size, (p+1)*phase_size)), F(0))/phase_size
                         for j in range(dimension)) for p in range(count))
    full = tuple(sum((row[j] for row in rows), F(0))/len(rows) for j in range(dimension))
    selected = tuple(sum((weight*row[j] for weight, row in zip(probabilities, phases)), F(0))
                     for j in range(dimension))
    covariance = tuple(tuple(sum((weight*(row[i]-selected[i])*(row[j]-selected[j])
                                 for weight, row in zip(probabilities, phases)), F(0))
                             for j in range(dimension)) for i in range(dimension))
    return PhaseSelectionMoments(full, selected, tuple(x-y for x, y in zip(selected, full)),
                                 covariance, phases)


@dataclass(frozen=True)
class GatedAffineMoments:
    instrument_matrix: tuple[tuple[F, ...], ...]
    dither_square: tuple[F, ...]
    gram: tuple[tuple[F, ...], ...]
    target_moment: tuple[F, ...]
    correlations: tuple[F, ...]
    half_gradient: tuple[F, ...]
    instrument_target: tuple[F, ...]
    instrument_residual: tuple[F, ...]
    mse: F


def gated_affine_moments(basis, dither, gates, coefficients, targets,
                         learning_weights=None, evaluation_weights=None) -> GatedAffineMoments:
    """For Y=psi*k-D, C=E_learn[D G Y], L=E_eval[(Y-T)^2].

    The matrix of C holds the supplied gates fixed. It describes the actual
    mean map in a neighborhood only if its masks stay valid. The output loss
    polynomial needs fixed basis/observation law, not fixed learning gates.
    This API never interprets masks as derivatives of discontinuous gates.
    """
    phi = tuple(tuple(_exact(x) for x in row) for row in basis)
    k = tuple(_exact(x) for x in coefficients)
    d = tuple(_exact(x) for x in dither)
    t = tuple(_exact(x) for x in targets)
    masks = tuple(tuple(row) for row in gates)
    n, p = len(phi), len(k)
    if (not n or not p or len(d) != n or len(t) != n or len(masks) != n
            or any(len(row) != p for row in phi)
            or any(len(row) != p or any(type(x) is not bool for x in row) for row in masks)):
        raise ValueError("consistent nonempty basis, Boolean masks, dither, target and coefficients required")
    learn, evaluate = _weights(learning_weights, n), _weights(evaluation_weights, n)
    y = tuple(_dot(row, k)-di for row, di in zip(phi, d))
    error = tuple(yi-ti for yi, ti in zip(y, t))
    instrument = tuple(tuple(di*int(active) for active in row) for di, row in zip(d, masks))
    matrix = tuple(tuple(sum((w*v[i]*row[j] for w, v, row in zip(learn, instrument, phi)), F(0))
                         for j in range(p)) for i in range(p))
    square = tuple(sum((w*v[i]*di for w, v, di in zip(learn, instrument, d)), F(0)) for i in range(p))
    gram = tuple(tuple(sum((w*row[i]*row[j] for w, row in zip(evaluate, phi)), F(0))
                       for j in range(p)) for i in range(p))
    target = tuple(sum((w*row[i]*(di+ti) for w, row, di, ti in zip(evaluate, phi, d, t)), F(0))
                   for i in range(p))
    correlations = tuple(_dot(row, k)-bi for row, bi in zip(matrix, square))
    gradient = tuple(_dot(row, k)-hi for row, hi in zip(gram, target))
    target_instrument = tuple(sum((w*v[i]*ti for w, v, ti in zip(learn, instrument, t)), F(0)) for i in range(p))
    residual_instrument = tuple(sum((w*v[i]*ei for w, v, ei in zip(learn, instrument, error)), F(0)) for i in range(p))
    loss = sum((w*ei*ei for w, ei in zip(evaluate, error)), F(0))
    return GatedAffineMoments(matrix, square, gram, target, correlations, gradient,
                             target_instrument, residual_instrument, loss)


def affine_loss_change(moments: GatedAffineMoments, delta: Sequence[F]) -> F:
    """Exact finite continuous loss change for the same fixed affine output."""
    change = tuple(_exact(x) for x in delta)
    if len(change) != len(moments.half_gradient):
        raise ValueError("one coefficient change per basis direction required")
    return 2*_dot(moments.half_gradient, change)+sum(
        (change[i]*value*change[j] for i, row in enumerate(moments.gram)
         for j, value in enumerate(row)), F(0))
