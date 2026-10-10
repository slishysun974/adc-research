"""Digital paired contrasts and excitation; pairing validity is external.

These are offline conditional equations, not a streaming calibration update.
Two decoded raw values do not prove equal analog input, history, or target.
"""

from dataclasses import dataclass
from fractions import Fraction as F

from adc_research.theory.gated_correlation_roots import stage_basis
from adc_research.theory.window_mean_map import exact_matrix_rank


@dataclass(frozen=True)
class PairedDitherObservation:
    raw_plus: F
    raw_minus: F
    dither_magnitude: F
    count: int = 1

    def __post_init__(self):
        if (any(not isinstance(x, F) for x in (self.raw_plus, self.raw_minus, self.dither_magnitude))
                or self.dither_magnitude <= 0):
            raise ValueError("exact raw values and positive exact dither magnitude required")
        if not isinstance(self.count, int) or isinstance(self.count, bool) or self.count <= 0:
            raise ValueError("positive integer pair count required")


def pair_basis_difference(pair, width=F(128)):
    if not isinstance(pair, PairedDitherObservation) or not isinstance(width, F) or width <= 0:
        raise ValueError("decoded pair and positive exact width required")
    plus = stage_basis(pair.raw_plus, width)
    minus = stage_basis(pair.raw_minus, width)
    return tuple(a-b for a, b in zip(plus, minus))


def _solve(matrix, rhs):
    """Exact elimination; only a full-rank square system is solved."""
    size = len(rhs)
    a = [list(row)+[b] for row, b in zip(matrix, rhs)]
    for column in range(size):
        pivot = next((r for r in range(column, size) if a[r][column] != 0), None)
        if pivot is None:
            return None
        a[column], a[pivot] = a[pivot], a[column]
        scale = a[column][column]
        a[column] = [v/scale for v in a[column]]
        for r in range(size):
            if r != column:
                scale = a[r][column]
                a[r] = [v-scale*p for v, p in zip(a[r], a[column])]
    return tuple(row[-1] for row in a)


def analyze_pair_equations(pairs, coefficients=(F(1),)*4, width=F(128), common_gates=None):
    """Return unrounded contrast loss, one shared-gate moment and pair Gram.

    Features are psi(raw_plus)-psi(raw_minus), desired contrasts 2*dither.
    Least squares uses only these digital observations, never ideal targets.
    A full-rank Gram identifies this contrast objective, not a physical inverse.
    """
    pairs, coefficients = tuple(pairs), tuple(coefficients)
    if (not pairs or len(coefficients) != 4
            or any(not isinstance(k, F) for k in coefficients)):
        raise ValueError("nonempty pairs and four exact coefficients required")
    if common_gates is None:
        common_gates = (True,)*len(pairs)
    common_gates = tuple(common_gates)
    if len(common_gates) != len(pairs) or any(not isinstance(g, bool) for g in common_gates):
        raise ValueError("one Boolean shared gate per pair required")
    features = tuple(pair_basis_difference(pair, width) for pair in pairs)
    total = sum(pair.count for pair in pairs)
    gram, rhs = [[F(0)]*4 for _ in range(4)], [F(0)]*4
    residuals = []
    moment = loss = F(0)
    for pair, feature, gate in zip(pairs, features, common_gates):
        residual = sum((k*v for k, v in zip(coefficients, feature)), F(0))-2*pair.dither_magnitude
        residuals.append(residual)
        weight = F(pair.count, total)*gate
        moment += weight*pair.dither_magnitude*residual/2
        loss += weight*residual**2
        for i in range(4):
            rhs[i] += weight*feature[i]*2*pair.dither_magnitude
            for j in range(4):
                gram[i][j] += weight*feature[i]*feature[j]
    rank = exact_matrix_rank(gram)
    solution = _solve(gram, rhs) if rank == 4 else None
    fitted_loss = None if solution is None else sum((F(pair.count, total)*gate*
        (sum((k*v for k, v in zip(solution, feature)), F(0))-2*pair.dither_magnitude)**2
        for pair, feature, gate in zip(pairs, features, common_gates)), F(0))
    return {'total_pairs': total, 'accepted_pairs': sum(pair.count for pair, g in zip(pairs, common_gates) if g),
            'features': features, 'contrast_residuals': tuple(residuals),
            'shared_gate_correlation': moment, 'contrast_mse': loss,
            'basis_difference_gram': tuple(map(tuple, gram)), 'basis_difference_rank': rank,
            'unobserved_coefficient_dimensions': 4-rank, 'contrast_least_squares_coefficients': solution,
            'minimum_contrast_mse': fitted_loss, 'same_signal_and_history_verified': False,
            'physical_inverse_identified': False}


def pair_constraint_components(nodes, shifts):
    """Components of finite integer target nodes joined by available 2D steps.

    If an error h is equal across every edge, it is constant per component.
    This is an exact finite support model, not a graph of actual chip inputs.
    """
    nodes, shifts = tuple(sorted(set(nodes))), tuple(sorted(set(shifts)))
    if not nodes or any(not isinstance(n, int) or isinstance(n, bool) for n in nodes):
        raise ValueError("nonempty integer support required")
    if not shifts or any(not isinstance(s, int) or isinstance(s, bool) or s <= 0 for s in shifts):
        raise ValueError("positive integer pair steps required")
    parents = {n: n for n in nodes}

    def find(n):
        while parents[n] != n:
            parents[n] = parents[parents[n]]
            n = parents[n]
        return n

    edges = 0
    for n in nodes:
        for shift in shifts:
            if n+shift in parents:
                a, b = find(n), find(n+shift)
                parents[b] = a
                edges += 1
    groups = {}
    for n in nodes:
        groups.setdefault(find(n), []).append(n)
    components = tuple(tuple(group) for group in sorted(groups.values(), key=lambda group: group[0]))
    return {'nodes': len(nodes), 'edge_count': edges, 'steps': shifts, 'components': components,
            'component_count': len(components), 'edge_constraint_rank': len(nodes)-len(components),
            'unanchored_error_dimensions': len(components)}
