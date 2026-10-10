"""Exact digital readout excitation and constrained mean-update propagation.

These are conditional diagnostics of decoded observations, not physical
identification or a proof of convergence of the Q22 algorithm.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from fractions import Fraction as F
from typing import Sequence

from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.theory.window_mean_map import WindowMeanMap, exact_matrix_rank


def _matrix(values):
    rows = tuple(tuple(F(x) if isinstance(x, int) and not isinstance(x, bool) else x
                       for x in row) for row in values)
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError("a nonempty rectangular matrix is required")
    if any(not isinstance(x, F) for row in rows for x in row):
        raise TypeError("matrix entries must be integers or explicit Fractions")
    return rows


def identity(size):
    return tuple(tuple(F(i == j) for j in range(size)) for i in range(size))


def matmul(left, right):
    left, right = _matrix(left), _matrix(right)
    if len(left[0]) != len(right):
        raise ValueError("incompatible matrix dimensions")
    return tuple(tuple(sum((a*b for a, b in zip(row, column)), F(0))
                       for column in zip(*right)) for row in left)


def infinity_norm(matrix):
    return max(sum(abs(x) for x in row) for row in _matrix(matrix))


def exact_nullspace(matrix):
    """Rational RREF basis, with no numerical rank tolerance."""
    rows = [list(row) for row in _matrix(matrix)]
    width, pivots, rank = len(rows[0]), [], 0
    for j in range(width):
        pivot = next((i for i in range(rank, len(rows)) if rows[i][j]), None)
        if pivot is None:
            continue
        rows[rank], rows[pivot] = rows[pivot], rows[rank]
        scale = rows[rank][j]
        rows[rank] = [x/scale for x in rows[rank]]
        for i in range(len(rows)):
            if i != rank and rows[i][j]:
                scale = rows[i][j]
                rows[i] = [x-scale*y for x, y in zip(rows[i], rows[rank])]
        pivots.append(j)
        rank += 1
        if rank == len(rows):
            break
    basis = []
    for j in range(width):
        if j in pivots:
            continue
        vector = [F(0)]*width
        vector[j] = F(1)
        for i, pivot in enumerate(pivots):
            vector[pivot] = -rows[i][j]
        basis.append(tuple(vector))
    return tuple(basis)


def positive_definite(matrix):
    """Exact LDL^T test for a symmetric rational matrix."""
    matrix = _matrix(matrix)
    size = len(matrix)
    if len(matrix[0]) != size or any(matrix[i][j] != matrix[j][i]
                                   for i in range(size) for j in range(size)):
        raise ValueError("a square symmetric matrix is required")
    lower = [[F(0)]*size for _ in range(size)]
    diagonal = []
    for j in range(size):
        value = matrix[j][j]-sum((lower[j][k]**2*diagonal[k] for k in range(j)), F(0))
        if value <= 0:
            return False
        diagonal.append(value)
        lower[j][j] = F(1)
        for i in range(j+1, size):
            lower[i][j] = (matrix[i][j]-sum(
                (lower[i][k]*lower[j][k]*diagonal[k] for k in range(j)), F(0)))/value
    return True


def gram_lower_bound(matrix):
    """For a Gram matrix, certify G >= alpha I by exact positive definiteness.

    Alpha is a conservative dyadic candidate, not a fitted eigenvalue.
    Singular Gram matrices have alpha=0. Non-Gram indefinite inputs are
    rejected. The input's Gram provenance is the caller's responsibility.
    """
    matrix = _matrix(matrix)
    size = len(matrix)
    if len(matrix[0]) != size or any(matrix[i][j] != matrix[j][i]
                                   for i in range(size) for j in range(size)):
        raise ValueError("a square symmetric Gram matrix is required")
    schur = [list(row) for row in matrix]
    rank = 0
    for j in range(size):
        pivot = schur[j][j]
        if pivot < 0 or (pivot == 0 and any(schur[j][i] != 0 for i in range(j+1, size))):
            raise ValueError("the matrix is not positive semidefinite")
        if pivot == 0:
            continue
        rank += 1
        for i in range(j+1, size):
            for k in range(j+1, size):
                schur[i][k] -= schur[i][j]*schur[j][k]/pivot
    if rank < size:
        return F(0)
    alpha = min(matrix[i][i] for i in range(size))/2
    while not positive_definite(tuple(tuple(x-alpha*int(i == j) for j, x in enumerate(row))
                                       for i, row in enumerate(matrix))):
        alpha /= 2
    return alpha


def readout_gram(result: WindowMeanMap):
    """Average H_n^T H_n for the two continuous local learning outputs.

    H2=(psi2,0), H1=(k1[selector]*psi2,psi1). Stage-1 selectors
    must remain fixed for H1 to be a local derivative. The result does not
    contain an analog input, target output, or simulator sensitivity.
    """
    gram = [[F(0)]*8 for _ in range(8)]
    for row in result.rows:
        h2 = (*row.basis2, F(0), F(0), F(0), F(0))
        h1 = (*(result.coefficients[4+row.selector1]*x for x in row.basis2), *row.basis1)
        for h in (h2, h1):
            nonzero = [(i, x) for i, x in enumerate(h) if x]
            for i, a in nonzero:
                for j, b in nonzero:
                    gram[i][j] += a*b
    return tuple(tuple(x/len(result.rows) for x in row) for row in gram)


@dataclass(frozen=True)
class RestrictedPropagation:
    coordinates: tuple[int, ...]
    invariant: bool
    leakage: tuple[tuple[F, ...], ...]
    transition: tuple[tuple[F, ...], ...]
    norm_bound: F


def restricted_transition(jacobian, steps: Sequence[F], coordinates: Sequence[int]):
    """Restrict I-diag(steps)J only if the declared coordinate subspace closes.

    Rows outside the subspace must have zero columns inside it. Selecting
    a principal minor alone is not sufficient to establish closure.
    """
    jacobian = _matrix(jacobian)
    size = len(jacobian)
    steps, coordinates = tuple(steps), tuple(coordinates)
    if len(jacobian[0]) != size or len(steps) != size or any(
            not isinstance(x, F) or x <= 0 for x in steps):
        raise ValueError("a square Jacobian and positive explicit Fraction steps are required")
    if not coordinates or len(set(coordinates)) != len(coordinates) or any(
            not isinstance(i, int) or isinstance(i, bool) or not 0 <= i < size for i in coordinates):
        raise ValueError("distinct in-range coordinates are required")
    outside = [i for i in range(size) if i not in coordinates]
    leakage = tuple(tuple(-steps[i]*jacobian[i][j] for j in coordinates) for i in outside)
    transition = tuple(tuple(F(i == j)-steps[i]*jacobian[i][j] for j in coordinates)
                       for i in coordinates)
    return RestrictedPropagation(coordinates, all(x == 0 for row in leakage for x in row),
                                 leakage, transition, infinity_norm(transition))


def chronological_product(transitions):
    """Return M_last ... M_first, in the declared chronological order."""
    matrices = tuple(_matrix(x) for x in transitions)
    if not matrices:
        raise ValueError("at least one transition is required")
    size = len(matrices[0])
    product = identity(size)
    for matrix in matrices:
        if len(matrix) != size or len(matrix[0]) != size:
            raise ValueError("equally sized square transitions are required")
        product = matmul(matrix, product)
    return product


def empirical_total_variation(left: Sequence[DigitalCalibrationSample],
                              right: Sequence[DigitalCalibrationSample]):
    left, right = tuple(left), tuple(right)
    if not left or len(left) != len(right) or any(
            not isinstance(x, DigitalCalibrationSample) for x in (*left, *right)):
        raise ValueError("equal nonempty decoded observation records are required")
    a, b = Counter(left), Counter(right)
    return sum((F(abs(a[x]-b[x]), 2*len(left)) for x in a.keys() | b.keys()), F(0))


def product_magnitude_bounds(coefficients, geometry):
    """Global |d*y*gate| bounds on the declared continuous digital domain."""
    slopes = tuple(coefficients)
    if len(slopes) != 8 or any(not isinstance(x, F) or not 0 < x < 2 for x in slopes):
        raise ValueError("eight explicit Fraction slopes inside (0,2) are required")
    b2 = geometry.stage2_dither_magnitude*(geometry.stage2_width*sum(slopes[:4])
                                          +geometry.stage2_dither_magnitude)
    b1 = geometry.stage1_dither_magnitude*(geometry.stage1_width*sum(slopes[4:])
                                          +geometry.stage1_dither_magnitude)
    return (b2,)*4+(b1,)*4
