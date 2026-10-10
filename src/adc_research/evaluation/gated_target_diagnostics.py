"""Offline target/dither/gate decomposition; never an online learner input."""

from collections import defaultdict
from fractions import Fraction as F


def decompose_target_correlation(record):
    """Split E[D T G] into conditional imbalance and gate covariance.

    Rows are (exact target, exact dither, Boolean gate, positive count).
    Strata use the target value. No independence is inferred from the names
    of a generator or from a small empirical correlation.
    """
    strata = defaultdict(lambda: [0, F(0), 0, F(0)])
    for target, dither, gate, count in record:
        if not isinstance(target, F) or not isinstance(dither, F) or not isinstance(gate, bool):
            raise TypeError("explicit Fraction targets/dithers and Boolean gates required")
        if not isinstance(count, int) or isinstance(count, bool) or count <= 0:
            raise ValueError("positive integer counts required")
        values = strata[target]
        values[0] += count
        values[1] += count*dither
        values[2] += count*gate
        values[3] += count*dither*gate
    total = sum(value[0] for value in strata.values())
    if not total:
        raise ValueError("nonempty offline record required")
    unconditional = sum((t*v[1] for t,v in strata.items()), F(0))/total
    gated = sum((t*v[3] for t,v in strata.items()), F(0))/total
    imbalance = sum((t*v[1]*v[2]/v[0] for t,v in strata.items()), F(0))/total
    selection = gated-imbalance
    return {"total": total, "target_strata": len(strata),
            "conditionally_balanced_strata": sum(v[1] == 0 for v in strata.values()),
            "unconditional_target_correlation": unconditional,
            "gated_target_correlation": gated,
            "conditional_imbalance_part": imbalance, "gate_covariance_part": selection}
