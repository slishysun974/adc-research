"""Exact finite-record, offline squared-loss limits for integer readouts.

The observations are declared by the caller. Targets and diagnostic tables
never enter calibration. A trajectory need not be a fixed map of those
observations; its conditional covariance is therefore retained explicitly.
"""

from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction as F

from .static_fixed_contract import nearest_even


@dataclass(frozen=True)
class ObservationLoss:
    count: int
    groups: int
    target_variance: F
    integer_penalty: F
    information_bound: F
    output_variance: F
    target_output_covariance: F
    mean_error_squared: F
    actual_loss: F
    fixed_mapping: bool


def observation_loss(observations, targets, outputs, *, minimum=0, maximum=4095):
    """Group an explicitly supplied finite record, with exact arithmetic.

    information_bound is the optimum of fixed integer maps of observations
    on THIS record. It is not a population or causal-history bound.
    """
    obs, target, output = tuple(observations), tuple(map(F, targets)), tuple(outputs)
    if not obs or len(obs) != len(target) or len(obs) != len(output):
        raise ValueError("nonempty equally sized records required")
    if not isinstance(minimum, int) or not isinstance(maximum, int) or minimum > maximum:
        raise ValueError("ordered integer output range required")
    if any(not isinstance(y, int) or not minimum <= y <= maximum for y in output):
        raise ValueError("outputs must be allowed integers")
    groups = defaultdict(list)
    for o, t, y in zip(obs, target, output, strict=True):
        groups[o].append((t, F(y)))
    vt = penalty = vy = cov = mean_error = actual = F(0)
    for rows in groups.values():
        n = len(rows)
        mt = sum((t for t, _ in rows), F(0)) / n
        my = sum((y for _, y in rows), F(0)) / n
        best = min(maximum, max(minimum, nearest_even(mt)))
        vt += sum((t - mt)**2 for t, _ in rows)
        penalty += n * (mt - best)**2
        vy += sum((y - my)**2 for _, y in rows)
        cov += sum((t - mt)*(y - my) for t, y in rows)
        mean_error += n * (my - mt)**2
        actual += sum((y - t)**2 for t, y in rows)
    n = len(obs)
    result = ObservationLoss(n, len(groups), vt/n, penalty/n, (vt+penalty)/n,
                             vy/n, cov/n, mean_error/n, actual/n, vy == 0)
    assert result.actual_loss == (result.target_variance + result.output_variance
                                 - 2*result.target_output_covariance
                                 + result.mean_error_squared)
    if result.fixed_mapping:
        assert result.actual_loss >= result.information_bound
    return result


def reference_loss(outputs, reference, targets):
    """Actual = reference + displacement power + error/displacement cross."""
    y, z, t = tuple(map(F, outputs)), tuple(map(F, reference)), tuple(map(F, targets))
    if not y or len(y) != len(z) or len(y) != len(t):
        raise ValueError("nonempty equally sized records required")
    n = len(y)
    base = sum((r-a)**2 for r, a in zip(z, t, strict=True))/n
    power = sum((a-r)**2 for a, r in zip(y, z, strict=True))/n
    cross = 2*sum((r-b)*(a-r) for a, r, b in zip(y, z, t, strict=True))/n
    actual = sum((a-b)**2 for a, b in zip(y, t, strict=True))/n
    assert actual == base + power + cross
    return base, power, cross, actual
