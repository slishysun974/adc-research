"""Conditional finite propagation for a protected triangular two-stage map.

These are deterministic norm bounds. No platform, IID assumption, fitted
Jacobian or general Gu contraction is supplied by this module.
"""

from dataclasses import dataclass
from fractions import Fraction as F


@dataclass(frozen=True)
class CascadeBound:
    front: tuple[F, ...]
    rear: tuple[F, ...]
    front_limit: F
    rear_limit: F


def cascade_bound(rho_front, rho_rear, coupling, error_front, error_rear,
                  initial_front, initial_rear, steps):
    r1, r2, b, e1, e2, a1, a2 = map(F, (rho_front, rho_rear, coupling,
                                         error_front, error_rear,
                                         initial_front, initial_rear))
    if not 0 <= r1 < 1 or not 0 <= r2 < 1:
        raise ValueError("both diagonal contraction bounds must be in [0,1)")
    if min(b, e1, e2, a1, a2) < 0 or not isinstance(steps, int) or steps < 0:
        raise ValueError("nonnegative radii, perturbations and integer steps required")
    front, rear = [a1], [a2]
    for _ in range(steps):
        # Simultaneous commits: front uses the OLD rear radius.
        front.append(r1*front[-1] + b*rear[-1] + e1)
        rear.append(r2*rear[-1] + e2)
    limit2 = e2/(1-r2)
    limit1 = (e1 + b*limit2)/(1-r1)
    return CascadeBound(tuple(front), tuple(rear), limit1, limit2)


def weighted_contraction(rho_front, rho_rear, coupling, rear_weight):
    """Factor for max(front radius, rear_weight * rear radius)."""
    r1, r2, b, w = map(F, (rho_front, rho_rear, coupling, rear_weight))
    if not 0 <= r1 < 1 or not 0 <= r2 < 1 or b < 0 or w <= 0:
        raise ValueError("valid contraction, coupling and positive weight required")
    return max(r1 + b/w, r2)


@dataclass(frozen=True)
class PeriodicCascadeTube:
    """Least periodic radii of an explicitly supplied positive comparison map.

    The last radius repeats phase zero. Derivative bounds, update defects,
    closed protected neighborhoods and periodicity are caller obligations;
    these radii alone do not certify an ADC trajectory.
    """

    front: tuple[F, ...]
    rear: tuple[F, ...]
    period_front: F
    period_rear: F
    period_coupling: F
    period_error_front: F
    period_error_rear: F


def periodic_cascade_tube(phase_bounds):
    """Solve the ordered periodic comparison recurrence exactly.

    Each row is (front factor, rear factor, coupling, front error, rear
    error). All entries must be nonnegative. Individual factors may exceed
    one; both full-period diagonal products must be strictly below one.
    Front updates use the OLD rear radius, as in simultaneous bank commits.
    This function computes candidate radii, not gate or domain certificates.
    """
    rows = tuple(tuple(map(F, row)) for row in phase_bounds)
    if not rows or any(len(row) != 5 or min(row) < 0 for row in rows):
        raise ValueError("a nonempty sequence of five nonnegative bounds is required")
    a1, a2, coupling, e1, e2 = F(1), F(1), F(0), F(0), F(0)
    for f1, f2, b, d1, d2 in rows:
        # Compose on the left and retain old rear terms in both sums.
        a1, a2, coupling, e1, e2 = (
            f1*a1, f2*a2, f1*coupling + b*a2,
            f1*e1 + b*e2 + d1, f2*e2 + d2,
        )
    if a1 >= 1 or a2 >= 1:
        raise ValueError("both full-period diagonal products must be below one")
    radius2 = e2/(1-a2)
    radius1 = (e1 + coupling*radius2)/(1-a1)
    front, rear = [radius1], [radius2]
    for f1, f2, b, d1, d2 in rows:
        front.append(f1*front[-1] + b*rear[-1] + d1)
        rear.append(f2*rear[-1] + d2)
    return PeriodicCascadeTube(tuple(front), tuple(rear), a1, a2, coupling, e1, e2)


def tube_fits_caps(tube, phase_caps):
    """Check radii against independently certified CLOSED phase rectangles.

    Strict gate margins must already hold throughout each closed rectangle.
    This arithmetic check supplies neither those margins nor an initial-state
    containment check. Caps are given for phases 0..P-1, without the repeated
    terminal phase.
    """
    caps = tuple(tuple(map(F, row)) for row in phase_caps)
    if len(caps) != len(tube.front)-1 or any(
            len(row) != 2 or min(row) < 0 for row in caps):
        raise ValueError("one pair of nonnegative caps per phase is required")
    return all(r1 <= cap1 and r2 <= cap2 for r1, r2, (cap1, cap2) in
               zip(tube.front[:-1], tube.rear[:-1], caps, strict=True))
