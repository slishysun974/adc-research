"""Exact offline selector moments and fixed-rear output comparisons.

The caller supplies a fixed digital evaluation law. Targets are offline
arguments only. No scheduler, random generator, or online update is defined.
"""
from dataclasses import dataclass
from fractions import Fraction as F

from adc_research.theory.lane_phase_statistics import _exact


def vector_moments(values):
    rows = tuple(tuple(_exact(x) for x in row) for row in values)
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError('nonempty equal-length exact vectors required')
    n, d = len(rows), len(rows[0])
    mean = tuple(sum((row[i] for row in rows), F(0))/n for i in range(d))
    covariance = tuple(tuple(sum(((row[i]-mean[i])*(row[j]-mean[j])
                                  for row in rows), F(0))/n
                             for j in range(d)) for i in range(d))
    return mean, covariance


def output_gram(features):
    rows = tuple(tuple(_exact(x) for x in row) for row in features)
    if not rows or not rows[0] or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError('nonempty equal-length exact output bases required')
    return tuple(tuple(sum((row[i]*row[j] for row in rows), F(0))/len(rows)
                       for j in range(len(rows[0]))) for i in range(len(rows[0])))


def weighted_covariance_difference(gram, first, second, scales):
    """E[L_first-L_second] when affine updates have the SAME mean.

    scales includes the window length and step, in the same coordinate
    order as the covariance matrices. This does not round or export states.
    """
    h, a, b = [tuple(tuple(_exact(x) for x in row) for row in m)
               for m in (gram, first, second)]
    s = tuple(_exact(x) for x in scales)
    d = len(s)
    if not d or any(len(m) != d or any(len(row) != d for row in m) for m in (h,a,b)):
        raise ValueError('matching square matrices and scales required')
    return sum((h[i][j]*s[i]*s[j]*(a[i][j]-b[i][j])
                for i in range(d) for j in range(d)), F(0))


@dataclass(frozen=True)
class AffineLossComparison:
    mean_bias: tuple[F, ...]
    mean_output_difference: tuple[F, ...]
    variance_cost: F
    bias_square: F
    target_cross: F
    mse_difference_at_centers: F
    target_box_radius: F
    lower: F
    upper: F


def affine_loss_comparison(features, reference_outputs, reference_update,
                           selected_updates, targets, radii=None):
    """Random effective front update versus a deterministic reference.

    reference_outputs are the continuous outputs AFTER reference_update.
    The rear raw values, digital words, evaluation weights and targets must
    stay fixed; equal-weight selector atoms are supplied explicitly. Target
    boxes are independent per row, so the interval endpoints are tight for
    those algebraic boxes, not automatically for a physical signal family.
    """
    psi = tuple(tuple(_exact(x) for x in row) for row in features)
    z, ref, t = [tuple(_exact(x) for x in row)
                 for row in (reference_outputs, reference_update, targets)]
    r = (F(0),)*len(z) if radii is None else tuple(_exact(x) for x in radii)
    mean, cov = vector_moments(selected_updates)
    d = len(mean)
    if (not psi or len(z) != len(psi) or len(t) != len(z) or len(r) != len(z)
            or len(ref) != d or any(len(row) != d for row in psi) or any(x < 0 for x in r)):
        raise ValueError('matching bases, updates, targets and nonnegative radii required')
    bias = tuple(a-b for a,b in zip(mean, ref))
    shift = tuple(sum((x*y for x,y in zip(row,bias)), F(0)) for row in psi)
    h = output_gram(psi)
    variance = sum((h[i][j]*cov[i][j] for i in range(d) for j in range(d)), F(0))
    square = sum((x*x for x in shift), F(0))/len(z)
    cross = 2*sum(((a-b)*c for a,b,c in zip(z,t,shift)), F(0))/len(z)
    radius = 2*sum((a*abs(b) for a,b in zip(r,shift)), F(0))/len(z)
    center = variance+square+cross
    return AffineLossComparison(bias, shift, variance, square, cross, center,
                                radius, center-radius, center+radius)


def finite_output_loss_comparison(selected_outputs, reference_outputs, targets, radii=None):
    """Exact expected loss interval for arbitrary finite output atoms.

    Works with actual Q3/integer outputs and needs no derivatives, segment
    protection or equal effective update means. Atoms are equally probable.
    """
    rows = tuple(tuple(_exact(x) for x in row) for row in selected_outputs)
    ref, target = [tuple(_exact(x) for x in v) for v in (reference_outputs, targets)]
    r = (F(0),)*len(ref) if radii is None else tuple(_exact(x) for x in radii)
    if (not rows or not ref or len(target) != len(ref) or len(r) != len(ref)
            or any(len(row) != len(ref) for row in rows) or any(x < 0 for x in r)):
        raise ValueError('matching nonempty outputs and target boxes required')
    shift = tuple(sum((row[i] for row in rows), F(0))/len(rows)-ref[i]
                  for i in range(len(ref)))
    center = sum((sum(((row[i]-target[i])**2 for row in rows), F(0))/len(rows)
                  -(ref[i]-target[i])**2 for i in range(len(ref))), F(0))/len(ref)
    radius = 2*sum((a*abs(b) for a,b in zip(r,shift)), F(0))/len(ref)
    return shift, center, center-radius, center+radius


def bilinear_loss_terms(triples, old_error):
    """Per-word continuous change for atoms (a,b,c): delta Z = a+b*c.

    a is the linear response; b is the rear-induced raw change; c is the
    effective front slope change in the ORIGINAL front segment. Segment
    preservation must be established by the caller, not by this algebra.
    """
    rows = tuple(tuple(_exact(x) for x in row) for row in triples)
    e = _exact(old_error)
    if not rows or any(len(row) != 3 for row in rows):
        raise ValueError('nonempty exact (linear, rear, front) atoms required')
    return tuple(sum((value for value in values), F(0))/len(rows) for values in (
        [2*e*a for a,b,c in rows], [a*a for a,b,c in rows],
        [2*e*b*c for a,b,c in rows], [2*a*b*c for a,b,c in rows],
        [(b*c)**2 for a,b,c in rows]))
