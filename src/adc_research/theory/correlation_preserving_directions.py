"""Exact offline tangent, straight-line and second-jet correlation tests.

No root fitting, simulator, target acquisition or online update is performed.
All polynomial claims require the declared masks and front segments to stay.
"""
from dataclasses import dataclass
from fractions import Fraction as F

from adc_research.theory.gated_mean_objective import _dot, _exact, _weights


def _rref(matrix, rhs=None):
    rows = [[_exact(x) for x in row] for row in matrix]
    if not rows or not rows[0] or any(len(r) != len(rows[0]) for r in rows):
        raise ValueError("nonempty rectangular matrix required")
    n = len(rows[0])
    if rhs is not None:
        values = tuple(_exact(x) for x in rhs)
        if len(values) != len(rows):
            raise ValueError("one right-hand side per row required")
        rows = [row+[value] for row, value in zip(rows, values)]
    pivots = []
    for col in range(n):
        index = next((i for i in range(len(pivots), len(rows)) if rows[i][col]), None)
        if index is None:
            continue
        pos = len(pivots)
        rows[pos], rows[index] = rows[index], rows[pos]
        divisor = rows[pos][col]
        rows[pos] = [x/divisor for x in rows[pos]]
        for i in range(len(rows)):
            if i != pos:
                factor = rows[i][col]
                rows[i] = [x-factor*y for x, y in zip(rows[i], rows[pos])]
        pivots.append(col)
    return rows, tuple(pivots), n


def exact_nullspace(matrix):
    """Canonical rational basis, ascending free columns, free coordinate=1."""
    rows, pivots, n = _rref(matrix)
    result = []
    for free in range(n):
        if free not in pivots:
            v = [F(0)]*n
            v[free] = F(1)
            for i, col in enumerate(pivots):
                v[col] = -rows[i][free]
            result.append(tuple(v))
    return tuple(result)


def exact_linear_solution(matrix, rhs):
    """One exact solution with free coordinates zero; None if inconsistent.

    Solves a supplied linear derivative/jet equation, never the full nonlinear
    eight-state Gu root problem. A solution of a second jet is not a root curve.
    """
    rows, pivots, n = _rref(matrix, rhs)
    if any(not any(row[:n]) and row[n] for row in rows):
        return None
    answer = [F(0)]*n
    for i, col in enumerate(pivots):
        answer[col] = rows[i][n]
    return tuple(answer)


@dataclass(frozen=True)
class CorrelationGeometry:
    correlations: tuple[F, ...]
    jacobian: tuple[tuple[F, ...], ...]
    mixed: tuple[tuple[tuple[F, ...], ...], ...]
    correlation_derivative_regular: bool
    output_derivative_regular: bool


def correlation_geometry(result, learning_weights=None):
    """Analytic fixed-mask moments; rear/front state order."""
    q = _weights(learning_weights, len(result.rows))
    c, matrix = [F(0)]*8, [[F(0)]*8 for _ in range(8)]
    mixed = [[[F(0)]*4 for _ in range(4)] for _ in range(4)]
    regular = True
    for row, weight in zip(result.rows, q, strict=True):
        j = row.selector1
        jac = tuple(result.coefficients[4+j]*x for x in row.basis2)+row.basis1
        if weight:
            regular &= (row.selector_margin1 > 0 and row.domain_margin1 > 0
                        and all(x > 0 for x in (*row.gate_margins1, *row.gate_margins2)))
        for i in range(4):
            rear, front = row.dither2*int(row.gates2[i]), row.dither1*int(row.gates1[i])
            c[i] += weight*rear*row.local2
            c[4+i] += weight*front*row.local1
            for a in range(4):
                matrix[i][a] += weight*rear*row.basis2[a]
                mixed[i][a][j] += weight*front*row.basis2[a]
            for a in range(8):
                matrix[4+i][a] += weight*front*jac[a]
    return CorrelationGeometry(tuple(c), tuple(tuple(r) for r in matrix),
        tuple(tuple(tuple(r) for r in a) for a in mixed), regular,
        all(r.selector_margin1 > 0 and r.domain_margin1 > 0 for r in result.rows))


@dataclass(frozen=True)
class DirectionPolynomial:
    linear_correlations: tuple[F, ...]
    quadratic_correlations: tuple[F, ...]
    linear_outputs: tuple[F, ...]
    quadratic_outputs: tuple[F, ...]
    first_order_neutral: bool
    straight_line_preserves_correlations: bool
    first_order_output_invariant: bool
    straight_line_preserves_output: bool
    second_jet_acceleration: tuple[F, ...] | None


def direction_polynomial(result, geometry, direction):
    """C(k+u*v)-C(k)=u*M*v+u^2*n(v); output likewise row by row.

    The second-jet equation M*a=-2*n(v) is only a necessary condition for a
    twice differentiable correlation-level curve with initial velocity v.
    Boundary values are frozen-polynomial diagnostics, not derivatives.
    """
    v = tuple(_exact(x) for x in direction)
    if len(v) != 8:
        raise ValueError("eight coefficient directions required")
    linear_c = tuple(_dot(row, v) for row in geometry.jacobian)
    quadratic_c = (F(0),)*4+tuple(sum((v[a]*v[4+b]*geometry.mixed[i][a][b]
                            for a in range(4) for b in range(4)), F(0)) for i in range(4))
    linear_z, quadratic_z = [], []
    for row in result.rows:
        rear_change = _dot(row.basis2, v[:4])
        linear_z.append(result.coefficients[4+row.selector1]*rear_change+_dot(row.basis1, v[4:]))
        quadratic_z.append(v[4+row.selector1]*rear_change)
    neutral, flat_c = not any(linear_c), not any(linear_c+quadratic_c)
    flat_z = not any(linear_z)
    acceleration = (exact_linear_solution(geometry.jacobian, tuple(-2*x for x in quadratic_c))
                    if neutral else None)
    return DirectionPolynomial(linear_c, quadratic_c, tuple(linear_z), tuple(quadratic_z),
        neutral, flat_c, flat_z, flat_z and not any(quadratic_z), acceleration)


def mixed_direction_terms(result, geometry, left, right):
    """n(v+w)-n(v)-n(w), and the analogous row output product term.

    Testing only individual nullspace basis vectors misses cross terms of
    their combinations. Together with diagonals these determine the whole
    quadratic restriction to a declared linear subspace.
    """
    v, w = tuple(_exact(x) for x in left), tuple(_exact(x) for x in right)
    if len(v) != 8 or len(w) != 8:
        raise ValueError("two eight-coordinate directions required")
    c = (F(0),)*4+tuple(sum(((v[a]*w[4+b]+w[a]*v[4+b])*geometry.mixed[i][a][b]
                           for a in range(4) for b in range(4)), F(0)) for i in range(4))
    z = tuple(v[4+r.selector1]*_dot(r.basis2, w[:4])
              +w[4+r.selector1]*_dot(r.basis2, v[:4]) for r in result.rows)
    return c, z
