"""Exact scalar filtering identities under explicit linear white-noise assumptions.

No ADC transfer, simulator sensitivity or fitted Jacobian is used here.
The scalar gain is an assumed model parameter, not an identified Gu gain.
"""

from fractions import Fraction as F


def scalar_filtered_moments(alpha,beta,step=F(1),noise_variance=F(1)):
    if any(not isinstance(v,F) for v in (alpha,beta,step,noise_variance)):
        raise TypeError("explicit rational model parameters required")
    if not 0 < alpha <= 1 or step <= 0 or noise_variance < 0:
        raise ValueError("invalid scalar filtering assumptions")
    if not 0 < beta < 4/alpha-2:
        raise ValueError("scalar matrix must be strictly Schur stable")
    variance = step**2*noise_variance*(2-alpha)/(beta*(4-2*alpha-alpha*beta))
    trace = 2-alpha-alpha*beta
    matrix = ((1-alpha*beta,-step*(1-alpha)),(alpha*beta/step,1-alpha))
    covariance = ((variance,-alpha*beta*variance/(step*(2-alpha))),
                  (-alpha*beta*variance/(step*(2-alpha)),2*alpha*beta*variance/(step**2*(2-alpha))))
    return {"matrix":matrix,"noise_vector":(-step*alpha,alpha),"covariance":covariance,
        "trace":trace,"determinant":1-alpha,"scalar_state_variance":variance,
        "fixed_state_statistic_variance_ratio":alpha/(2-alpha),
        "baseline_variance":step**2*noise_variance/(beta*(2-beta)) if beta < 2 else None,
        "quarter_step_variance":step**2*noise_variance/(beta*(8-beta)) if beta < 8 else None}
