"""Offline finite laws for phase mapping, conditional bias and deadlines.

No random bits are generated and no online schedule is implemented. Binary
word uniformity and independence, when used, are explicit caller assumptions.
"""
from dataclasses import dataclass
from fractions import Fraction as F


def _integer(value, name, minimum=1):
    if type(value) is not int or value < minimum:
        raise ValueError(name+' must be an integer >= '+str(minimum))
    return value


def _exact(value):
    if isinstance(value,F): return value
    if type(value) is int: return F(value)
    raise TypeError('integers or explicit Fractions required')


def residue_counts(stop, phases=30, start=0):
    """Exact residue counts for every integer in [start,stop)."""
    _integer(stop,'stop'); _integer(start,'start',0); _integer(phases,'phases')
    if start>=stop: raise ValueError('nonempty nonnegative integer interval required')
    def prefix(n):
        q,r=divmod(n,phases)
        return tuple(q+int(i<r) for i in range(phases))
    return tuple(a-b for a,b in zip(prefix(stop),prefix(start)))


def modulo_law(bits, phases=30, *, exclude_zero=False):
    """Uniform B-bit word (or uniform NONZERO word), then modulo phases."""
    _integer(bits,'bits'); _integer(phases,'phases')
    if type(exclude_zero) is not bool: raise ValueError('exclude_zero must be Boolean')
    start=int(exclude_zero); size=(1<<bits)-start
    return tuple(F(c,size) for c in residue_counts(1<<bits,phases,start))


@dataclass(frozen=True)
class BoundedRejectionLaw:
    probabilities: tuple[F,...]
    rejected_probability_per_draw: F
    deadline_failure_probability: F
    expected_draws: F
    maximum_draws: int
    bits_per_draw: int


def bounded_rejection_law(bits=5, phases=30, attempts=4, fallback=0):
    """Accept below floor(2**bits/P)*P; first acceptance modulo P.

    After K rejected independent uniform words use the fixed fallback.
    These are derived probabilities and resource counts, not sampler code.
    """
    _integer(bits,'bits'); _integer(phases,'phases'); _integer(attempts,'attempts')
    _integer(fallback,'fallback',0)
    size=1<<bits
    if phases>size or fallback>=phases: raise ValueError('phase range exceeds word or fallback domain')
    rho=F(size-(size//phases)*phases,size)
    failure=rho**attempts
    probs=tuple((1-failure)/phases+failure*int(i==fallback) for i in range(phases))
    expected=sum((rho**j for j in range(attempts)),F(0))
    return BoundedRejectionLaw(probs,rho,failure,expected,attempts,bits)


def probabilities(values):
    p=tuple(_exact(x) for x in values)
    if not p or any(x<0 for x in p) or sum(p)!=1:
        raise ValueError('exact nonnegative probabilities summing to one required')
    return p


def total_variation(first, second):
    p,q=probabilities(first),probabilities(second)
    if len(p)!=len(q): raise ValueError('same probability domains required')
    return sum((abs(a-b) for a,b in zip(p,q)),F(0))/2


def weighted_moments(values, law):
    rows=tuple(tuple(_exact(x) for x in row) for row in values)
    p=probabilities(law)
    if not rows or len(rows)!=len(p) or not rows[0] or any(len(r)!=len(rows[0]) for r in rows):
        raise ValueError('matching exact vector atoms and probability law required')
    d=len(rows[0])
    mean=tuple(sum((w*r[i] for w,r in zip(p,rows)),F(0)) for i in range(d))
    cov=tuple(tuple(sum((w*(r[i]-mean[i])*(r[j]-mean[j]) for w,r in zip(p,rows)),F(0))
                    for j in range(d)) for i in range(d))
    return mean,cov


def expectation_shift_bound(values, first, second):
    """Signed E_first[f]-E_second[f], and TV*(max(f)-min(f))."""
    f=tuple(_exact(x) for x in values)
    p,q=probabilities(first),probabilities(second)
    if len(f)!=len(p) or len(p)!=len(q): raise ValueError('matching finite scalar law required')
    actual=sum(((a-b)*v for a,b,v in zip(p,q,f)),F(0))
    bound=total_variation(p,q)*(max(f)-min(f))
    return actual,bound


def conditional_lane_mean(products, lane_probabilities, lanes=4):
    """Mean given the COMPLETE frozen window and its conditional marginals.

    Rows are phase-major. Marginal laws must actually hold conditional on
    this window/history, not merely in a long global count of selections.
    """
    _integer(lanes,'lanes')
    rows=tuple(tuple(_exact(x) for x in r) for r in products)
    ps=tuple(probabilities(p) for p in lane_probabilities)
    if (not rows or not rows[0] or len(rows)%lanes or len(ps)!=lanes
            or any(len(p)!=len(rows)//lanes for p in ps)
            or any(len(r)!=len(rows[0]) for r in rows)):
        raise ValueError('complete equal lanes and matching conditional marginals required')
    return tuple(sum((ps[l][r]*rows[lanes*r+l][i]
                      for l in range(lanes) for r in range(len(ps[l]))),F(0))/lanes
                 for i in range(len(rows[0])))
