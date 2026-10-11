"""Offline temporal moments and exact finite partitions; no learner imports.

The affine covariance formula requires iid random multipliers, a deterministic
additive term and independence from the old state. Finite partitions require
only the supplied integer sums, square sums and counts.
"""

from fractions import Fraction as F


def affine_temporal_covariance(mean_factor, variances):
    """Cov(k_i,k_j) = r**abs(j-i) Var(k_min(i,j)), including transients."""
    r = F(mean_factor)
    vv = tuple(map(F, variances))
    if not vv or any(v < 0 for v in vv):
        raise ValueError("nonempty nonnegative variances required")
    return tuple(tuple(r**abs(j-i)*vv[min(i, j)] for j in range(len(vv)))
                 for i in range(len(vv)))


def stationary_group_factors(mean_factor, count):
    """Variance/adjacent covariance of N-state means, divided by state variance.

Second-order stationary initialization and |r| < 1 are CONDITIONS, not a
stationarity test. A negative r is allowed and can improve averaging.
"""
    r = F(mean_factor)
    if abs(r) >= 1 or count < 1 or int(count) != count:
        raise ValueError("|r| < 1 and positive integer count required")
    n = int(count)
    w = (n + 2*sum((n-h)*r**h for h in range(1, n)))/F(n*n)
    cross = r*(1-r**n)**2/(F(n*n)*(1-r)**2)
    return {"mean_variance_factor": w, "adjacent_covariance_factor": cross,
            "adjacent_difference_variance_factor": 2*(w-cross),
            "iid_variance_understatement_factor": n*w}


def partition_moments(sums, square_sums, counts):
    """Exact weighted within/between variance from disjoint integer groups."""
    ss, qq, nn = tuple(map(int, sums)), tuple(map(int, square_sums)), tuple(map(int, counts))
    if not ss or len(ss) != len(qq) or len(ss) != len(nn) or any(n <= 0 for n in nn):
        raise ValueError("equally sized nonempty lists and positive counts required")
    if any(q*n < s*s for s, q, n in zip(ss, qq, nn)):
        raise ValueError("invalid square sum")
    total = sum(nn)
    mean = F(sum(ss), total)
    means = tuple(F(s, n) for s, n in zip(ss, nn))
    within = sum(F(q, 1)-F(s*s, n) for s, q, n in zip(ss, qq, nn))/total
    between = sum(n*(m-mean)**2 for n, m in zip(nn, means))/total
    variance = F(sum(qq), total)-mean**2
    return {"mean": mean, "variance": variance, "within_variance": within,
            "between_variance": between, "group_means": means}
