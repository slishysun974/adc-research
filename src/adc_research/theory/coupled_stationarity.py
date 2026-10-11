"""Exact offline two-bank correlation and continuous-output moments.

The observation laws and scoring targets are explicit inputs. Targets never
enter an online updater. Fixed selector/mask polynomials at boundaries are
marked as such; no population law or conditional label balance is inferred.
"""
from dataclasses import dataclass
from fractions import Fraction as F

from adc_research.theory.gated_mean_objective import _dot, _exact, _weights
from adc_research.theory.window_mean_map import WindowMeanMap, exact_matrix_rank


@dataclass(frozen=True)
class CoupledMoments:
    correlations: tuple[F, ...]
    correlation_jacobian: tuple[tuple[F, ...], ...]
    front_mixed_moments: tuple[tuple[tuple[F, ...], ...], ...]
    output_jacobians: tuple[tuple[F, ...], ...]
    instruments: tuple[tuple[F, ...], ...]
    target_leakage: tuple[F, ...]
    instrument_residual: tuple[F, ...]
    output_cross_moment: tuple[F, ...]
    gram: tuple[tuple[F, ...], ...]
    residual_curvature: tuple[tuple[F, ...], ...]
    half_loss_hessian: tuple[tuple[F, ...], ...]
    errors: tuple[F, ...]
    evaluation_weights: tuple[F, ...]
    mse: F
    output_derivative_regular: bool
    correlation_derivative_regular: bool


def coupled_moments(result: WindowMeanMap, coarse_codes, targets,
                    learning_weights=None, evaluation_weights=None) -> CoupledMoments:
    """C, J_C, E[e J_Z], E[J_Z J_Z^T+e B_Z] on a fixed digital law.

    State order is rear/front. coarse_codes are 2048+512*q1 and targets are
    full offline output-code targets. Q must be supported on P, so its exact
    density q=Q/P exists; sparse learning with full evaluation is permitted.
    The instruments (q D2 G2/k1_selector, q D1 G1) give C=E_P[V e]+leakage.
    Output derivatives require open front selectors/domains. Correlation
    derivatives additionally require open gates on learning support. Values
    at other points describe a frozen-selector/mask polynomial only.
    """
    n = len(result.rows)
    coarse = tuple(_exact(x) for x in coarse_codes)
    target = tuple(_exact(x) for x in targets)
    if not n or len(coarse) != n or len(target) != n:
        raise ValueError("one exact coarse code and offline target per row required")
    learn, evaluate = _weights(learning_weights, n), _weights(evaluation_weights, n)
    if any(q and not p for q, p in zip(learn, evaluate)):
        raise ValueError("evaluation support must cover learning support")
    correlations = [F(0)]*8
    matrix = [[F(0)]*8 for _ in range(8)]
    mixed = [[[F(0)]*4 for _ in range(4)] for _ in range(4)]
    leak, residual, gradient = ([F(0)]*8 for _ in range(3))
    gram, curvature = ([[F(0)]*8 for _ in range(8)] for _ in range(2))
    jacobians, instruments, errors = [], [], []
    loss = F(0)
    regular_output, regular_correlation = True, True
    for row, base, t, q, p in zip(result.rows, coarse, target, learn, evaluate, strict=True):
        j, slope = row.selector1, result.coefficients[4+row.selector1]
        jac = tuple(slope*x for x in row.basis2)+row.basis1
        local_target = t-base
        e = row.local1-local_target
        # psi1 = gamma + e_selector*Y2 within the declared front segment.
        gamma = tuple(x-(row.local2 if i == j else 0) for i, x in enumerate(row.basis1))
        rear_target = (row.dither1+local_target-_dot(result.coefficients[4:], gamma))/slope
        density = q/p if p else F(0)
        v = tuple(density*row.dither2*int(g)/slope for g in row.gates2)+tuple(
            density*row.dither1*int(g) for g in row.gates1)
        jacobians.append(jac); instruments.append(v); errors.append(e)
        loss += p*e*e
        if p:
            regular_output &= row.selector_margin1 > 0 and row.domain_margin1 > 0
        if q:
            regular_correlation &= (row.selector_margin1 > 0 and row.domain_margin1 > 0
                                    and all(x > 0 for x in (*row.gate_margins1, *row.gate_margins2)))
        for i in range(8):
            gradient[i] += p*e*jac[i]
            residual[i] += p*v[i]*e
            if i < 4:
                label = row.dither2*int(row.gates2[i])
                correlations[i] += q*label*row.local2
                leak[i] += q*label*rear_target
                for a in range(4):
                    matrix[i][a] += q*label*row.basis2[a]
            else:
                label = row.dither1*int(row.gates1[i-4])
                correlations[i] += q*label*row.local1
                leak[i] += q*label*local_target
                for a in range(8):
                    matrix[i][a] += q*label*jac[a]
                for a in range(4):
                    mixed[i-4][a][j] += q*label*row.basis2[a]
            for a in range(8):
                gram[i][a] += p*jac[i]*jac[a]
        for a in range(4):
            value = p*e*row.basis2[a]
            curvature[a][4+j] += value
            curvature[4+j][a] += value
    frozen = lambda a: tuple(tuple(row) for row in a)
    hessian = tuple(tuple(x+y for x, y in zip(a, b)) for a, b in zip(gram, curvature))
    return CoupledMoments(tuple(correlations), frozen(matrix),
        tuple(frozen(a) for a in mixed), tuple(jacobians), tuple(instruments),
        tuple(leak), tuple(residual), tuple(gradient), frozen(gram), frozen(curvature),
        hessian, tuple(errors), evaluate, loss, regular_output, regular_correlation)


def correlation_polynomial_change(moments: CoupledMoments, delta) -> tuple[F, ...]:
    """Exact fixed-mask/selector correlation increment, not a crossing rule.

    Calling this at a boundary does not establish differentiability; the
    caller must preserve all masks/selectors to identify it with actual C.
    """
    h = tuple(_exact(x) for x in delta)
    if len(h) != 8:
        raise ValueError("eight effective coefficient changes required")
    change = [_dot(row, h) for row in moments.correlation_jacobian]
    for i in range(4):
        change[4+i] += sum((h[a]*h[4+b]*moments.front_mixed_moments[i][a][b]
                           for a in range(4) for b in range(4)), F(0))
    return tuple(change)


def instrument_span_ranks(moments: CoupledMoments) -> tuple[int, int]:
    """Finite-law ranks of V and [V,J] on positive evaluation support.

    Equality is the universal residual-orthogonality implication for this
    fixed digital law, not physical identifiability or a necessary condition
    for the particular supplied target to have zero gradient.
    """
    pairs = [(v, j) for v, j, p in zip(moments.instruments, moments.output_jacobians,
                                     moments.evaluation_weights) if p]
    return exact_matrix_rank([v for v, _ in pairs]), exact_matrix_rank([v+j for v, j in pairs])
