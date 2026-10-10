"""Offline ideal-code projection and root bias. Never an online input."""

from fractions import Fraction as F

from adc_research.evaluation.gated_target_diagnostics import decompose_target_correlation
from adc_research.theory.front_gate_attribution import stage_gate_frames
from adc_research.theory.gated_correlation_roots import WeightedStageRow, stage_basis


def _record(record):
    record = tuple(record)
    if not record or any(not isinstance(row, WeightedStageRow) or not isinstance(target, F)
                         for row, target in record):
        raise ValueError("nonempty weighted digital rows and explicit offline Fraction targets required")
    return record


def project_low_front_targets(record, width=F(128), fixed_high=(F(1), F(1))):
    """Exact unconstrained two-coefficient least-squares reference, offline only."""
    record = _record(record)
    if (not isinstance(width, F) or width <= 0 or len(fixed_high) != 2
            or any(not isinstance(k, F) for k in fixed_high)):
        raise ValueError("exact positive width and two exact fixed high slopes required")
    total = sum(row.count for row, _ in record)
    gram, rhs = [[F(0)]*2 for _ in range(2)], [F(0)]*2
    prepared = []
    for row, target in record:
        basis = stage_basis(row.raw, width)
        response = target+row.dither-sum((k*p for k, p in zip(fixed_high, basis[2:])), F(0))
        prepared.append((row, target, basis))
        for i in range(2):
            rhs[i] += row.count*basis[i]*response/total
            for j in range(2):
                gram[i][j] += row.count*basis[i]*basis[j]/total
    a, b = gram[0]
    c, d = gram[1]
    det = a*d-b*c
    if det <= 0:
        raise ValueError("the two digital basis columns must have positive Gram determinant")
    low = ((d*rhs[0]-b*rhs[1])/det, (a*rhs[1]-c*rhs[0])/det)
    coefficients = (*low, *fixed_high)
    residuals = tuple(sum((k*p for k, p in zip(coefficients, basis)), F(0))-row.dither-target
                      for row, target, basis in prepared)
    orthogonality = tuple(sum((row.count*basis[i]*error for (row, _, basis), error
                              in zip(prepared, residuals)), F(0))/total for i in range(2))
    assert orthogonality == (F(0), F(0))
    return {"coefficients": coefficients, "basis_gram": tuple(map(tuple, gram)),
            "basis_gram_determinant": det, "basis_error_orthogonality": orthogonality,
            "minimum_continuous_mse": sum((row.count*error**2 for (row, _, _), error
                                           in zip(prepared, residuals)), F(0))/total,
            "oracle_reference_only": True, "constrained_to_online_domain": False}


def decompose_front_target_bias(record, coefficients, projection, width=F(128)):
    """Verify target leakage, representation residual, coefficient bias and MSE."""
    record = _record(record)
    rows = tuple(row for row, target in record)
    frames = stage_gate_frames(rows, coefficients, width)
    total = sum(row.count for row in rows)
    least_squares = tuple(projection["coefficients"])
    if tuple(coefficients[2:]) != least_squares[2:]:
        raise ValueError("reference and branch must have identical fixed high coefficients")
    residuals = tuple(sum((k*p for k, p in zip(least_squares, frame.basis)), F(0))
                      -frame.observation.dither-target for frame, (_, target) in zip(frames, record))
    delta = tuple(k-ref for k, ref in zip(coefficients[:2], least_squares[:2]))
    decomposition = []
    for i in range(4):
        selection = decompose_target_correlation(tuple((target, row.dither, frame.gates[i], row.count)
                                                      for (row, target), frame in zip(record, frames)))
        root_error = sum((row.count*row.dither*(frame.local-target)
                          for (row, target), frame in zip(record, frames) if frame.gates[i]), F(0))/total
        representation = sum((row.count*row.dither*error
                              for row, frame, error in zip(rows, frames, residuals) if frame.gates[i]), F(0))/total
        sensitivity = tuple(sum((row.count*row.dither*frame.basis[j]
                                 for row, frame in zip(rows, frames) if frame.gates[i]), F(0))/total
                            for j in range(2))
        coefficient_part = sum((a*b for a, b in zip(sensitivity, delta)), F(0))
        correlation = sum((row.count*row.dither*frame.local
                           for row, frame in zip(rows, frames) if frame.gates[i]), F(0))/total
        assert selection["gated_target_correlation"]+root_error == correlation
        assert root_error == representation+coefficient_part
        selection.update(continuous_root_error_correlation=root_error,
                         projection_residual_correlation=representation,
                         coefficient_bias_correlation=coefficient_part,
                         learning_correlation=correlation,
                         identity_verified=True)
        decomposition.append(selection)
    mse = sum((row.count*(frame.local-target)**2
               for (row, target), frame in zip(record, frames)), F(0))/total
    gram = projection["basis_gram"]
    quadratic = sum((delta[i]*gram[i][j]*delta[j] for i in range(2) for j in range(2)), F(0))
    # The projection is fitted to this record; the identity is a fit-only claim.
    assert mse == projection["minimum_continuous_mse"]+quadratic
    return {"gates": decomposition, "continuous_mse": mse,
            "low_coefficient_bias_from_projection": delta, "excess_mse": quadratic,
            "mse_projection_identity_verified": True}
