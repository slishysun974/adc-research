"""Exact offline four-grid losses and finite output moments.

Inputs are complete, same-word output records. No derivative, segment
protection, online selector, target acquisition or platform is defined here.
"""
from dataclasses import dataclass
from fractions import Fraction as F

from adc_research.theory.lane_phase_statistics import _exact


@dataclass(frozen=True)
class FourGridLoss:
    output_interaction: tuple[F, ...]
    front_loss: F
    rear_loss: F
    front_rear_cross: F
    interaction_error_cross: F
    interaction_front_cross: F
    interaction_rear_cross: F
    interaction_square: F
    loss_interaction: F
    joint_loss: F


def four_grid_loss(old, front, rear, joint, targets):
    """L11-L00 = front_loss + rear_loss + loss_interaction.

    All four grids use the same fixed words and targets. Output interaction
    c=Z11-Z10-Z01+Z00 includes actual arithmetic and segment changes. Even
    c=0 does not eliminate the square-loss cross term 2*x*y.
    """
    z, f, r, j, t = [tuple(_exact(x) for x in row)
                      for row in (old, front, rear, joint, targets)]
    n = len(z)
    if not n or any(len(row) != n for row in (f, r, j, t)):
        raise ValueError('matching nonempty same-word outputs and targets required')
    interaction = tuple(d-b-c+a for a, b, c, d in zip(z, f, r, j))
    terms = [F(0)]*7
    for a, b, c, d, target, h in zip(z, f, r, j, t, interaction):
        e, x, y = a-target, b-a, c-a
        values = (2*e*x+x*x, 2*e*y+y*y, 2*x*y,
                  2*e*h, 2*x*h, 2*y*h, h*h)
        terms = [total+value for total, value in zip(terms, values)]
    terms = [value/n for value in terms]
    cross = sum(terms[2:], F(0))
    return FourGridLoss(interaction, *terms, cross, sum(terms, F(0)))


@dataclass(frozen=True)
class OutputMoments:
    mean: tuple[F, ...]
    second: tuple[F, ...]


def output_moments(atoms):
    """Uniform finite law AFTER all actual output operations."""
    rows = tuple(tuple(_exact(x) for x in row) for row in atoms)
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError('nonempty equal-length output atoms required')
    return OutputMoments(
        tuple(sum((row[i] for row in rows), F(0))/len(rows)
              for i in range(len(rows[0]))),
        tuple(sum((row[i]**2 for row in rows), F(0))/len(rows)
              for i in range(len(rows[0]))))


def mix_output_moments(laws, weights):
    """Mix full output moments, without linearizing the digital processing."""
    rows, p = tuple(laws), tuple(_exact(x) for x in weights)
    if (not rows or len(rows) != len(p) or any(x < 0 for x in p)
            or sum(p) != 1 or not rows[0].mean
            or any(len(row.mean) != len(rows[0].mean)
                   or len(row.second) != len(row.mean) for row in rows)):
        raise ValueError('matching moments and nonnegative unit-sum weights required')
    return OutputMoments(*(
        tuple(sum((weight*getattr(row, name)[i] for row, weight in zip(rows, p)), F(0))
              for i in range(len(rows[0].mean))) for name in ('mean', 'second')))


@dataclass(frozen=True)
class OutputLossComparison:
    mean_output_difference: tuple[F, ...]
    target_cross: F
    mean_square: F
    variance: F
    center: F
    radius: F
    lower: F
    upper: F


def moments_loss_comparison(moments, reference, targets, radii=None):
    """Exact E[L]-Lref, with independent algebraic target boxes.

    Mean, square and variance are OUTPUT statistics; they do not close a
    coefficient-moment model or certify the physical target box.
    """
    ref, t = [tuple(_exact(x) for x in row) for row in (reference, targets)]
    r = (F(0),)*len(ref) if radii is None else tuple(_exact(x) for x in radii)
    if (not ref or any(len(row) != len(ref) for row in
            (t, r, moments.mean, moments.second)) or any(x < 0 for x in r)):
        raise ValueError('matching moments, reference, targets and nonnegative radii required')
    b = tuple(m-z for m, z in zip(moments.mean, ref))
    v = tuple(s-m*m for m, s in zip(moments.mean, moments.second))
    if any(x < 0 for x in v):
        raise ValueError('output second moments must dominate mean squares')
    n = len(ref)
    cross = 2*sum(((z-target)*h for z, target, h in zip(ref, t, b)), F(0))/n
    square, variance = sum((x*x for x in b), F(0))/n, sum(v, F(0))/n
    center = cross+square+variance
    radius = 2*sum((a*abs(h) for a, h in zip(r, b)), F(0))/n
    return OutputLossComparison(b, cross, square, variance, center, radius,
                                center-radius, center+radius)
