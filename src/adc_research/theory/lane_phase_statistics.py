"""Conditional offline moments for equal-marginal four-lane selectors.

All products at the same old coefficient state are supplied by the caller.
These are ideal selection laws, not an online scheduler or a PRNG claim.
"""
from dataclasses import dataclass
from fractions import Fraction as F


def _exact(value):
    if isinstance(value, F):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return F(value)
    raise TypeError('use integers or explicit Fractions')


@dataclass(frozen=True)
class LanePhaseMoments:
    full_mean: tuple[F, ...]
    lane_means: tuple[tuple[F, ...], ...]
    shared_covariance: tuple[tuple[F, ...], ...]
    independent_covariance: tuple[tuple[F, ...], ...]
    cross_contribution: tuple[tuple[F, ...], ...]


def lane_phase_moments(products, lanes=4):
    """Rows are phase-major: row = lanes*phase + lane.

    Each lane's phase has a uniform marginal. Either one common phase is
    used for all lanes, or the lane phases are mutually independent.
    Covariance units are per-observation means, conditional on ALL rows.
    """
    rows = tuple(tuple(_exact(x) for x in row) for row in products)
    if (type(lanes) is not int or lanes <= 0 or not rows or not rows[0]
            or len(rows) % lanes or any(len(r) != len(rows[0]) for r in rows)):
        raise ValueError('complete equal-length lanes and nonempty product vectors required')
    phases, dim = len(rows)//lanes, len(rows[0])
    means = tuple(tuple(sum((rows[p*lanes+l][i] for p in range(phases)), F(0))/phases
                        for i in range(dim)) for l in range(lanes))
    full = tuple(sum((mean[i] for mean in means), F(0))/lanes for i in range(dim))
    phase_means = tuple(tuple(sum((rows[p*lanes+l][i] for l in range(lanes)), F(0))/lanes
                              for i in range(dim)) for p in range(phases))
    shared = tuple(tuple(sum(((mean[i]-full[i])*(mean[j]-full[j])
                              for mean in phase_means), F(0))/phases
                         for j in range(dim)) for i in range(dim))
    independent = tuple(tuple(sum((
        (rows[p*lanes+l][i]-means[l][i])*(rows[p*lanes+l][j]-means[l][j])
        for l in range(lanes) for p in range(phases)), F(0))/(phases*lanes**2)
                              for j in range(dim)) for i in range(dim))
    cross = tuple(tuple(shared[i][j]-independent[i][j] for j in range(dim)) for i in range(dim))
    return LanePhaseMoments(full, means, shared, independent, cross)


def is_positive_semidefinite(matrix):
    """Exact symmetric PSD test by positive pivots and Schur complements."""
    a = [list(map(_exact, row)) for row in matrix]
    n = len(a)
    if not n or any(len(r) != n for r in a):
        raise ValueError('nonempty square matrix required')
    if any(a[i][j] != a[j][i] for i in range(n) for j in range(n)):
        raise ValueError('symmetric matrix required')
    while a:
        n = len(a)
        if any(a[i][i] < 0 for i in range(n)):
            return False
        pivot = next((i for i in range(n) if a[i][i] > 0), None)
        if pivot is None:
            return all(x == 0 for row in a for x in row)
        rest = [i for i in range(n) if i != pivot]
        scale = a[pivot][pivot]
        a = [[a[i][j]-a[i][pivot]*a[pivot][j]/scale for j in rest] for i in rest]
    return True
