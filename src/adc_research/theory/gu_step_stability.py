"""Exact learning-rate bounds for the declared iid single-slope control.

This module is offline theory. It neither imports the platform nor changes
the Gu learner. Window selection and scale factors are explicit inputs.
"""

from dataclasses import dataclass
from fractions import Fraction as F
import math


@dataclass(frozen=True)
class ScalarStepLaw:
    equilibrium: F
    gamma: F
    u: F
    mean_factor: F
    second_factor: F
    multiplier_variance: F
    mean_step_upper: F
    mean_square_step_upper: F

    @property
    def mean_stable(self) -> bool:
        return abs(self.mean_factor) < 1

    @property
    def mean_square_stable(self) -> bool:
        return self.second_factor < 1

    @property
    def stationary_variance(self) -> F:
        if not self.mean_square_stable:
            raise ValueError("strict mean-square stability is required")
        return self.multiplier_variance * self.equilibrium**2 / (1-self.second_factor)

    def exact_moments(self, windows: int, initial: F = F(1)) -> tuple[F, F]:
        if windows < 0:
            raise ValueError("nonnegative window count required")
        mean, variance = F(initial), F(0)
        constant = self.equilibrium * (1-self.mean_factor)
        for _ in range(windows):
            variance = self.second_factor*variance + self.multiplier_variance*mean**2
            mean = self.mean_factor*mean + constant
        return mean, variance

    def float_moments(self, windows: int, initial: float = 1.0) -> tuple[float, float]:
        """Closed finite-time moments; floating evaluation, not an enclosure."""
        if windows < 0:
            raise ValueError("nonnegative window count required")
        if windows == 0:
            return initial, 0.0
        r, q, v = map(float, (self.mean_factor, self.second_factor,
                             self.multiplier_variance))
        star, error = float(self.equilibrium), initial-float(self.equilibrium)

        def mixed_power(t: float) -> float:
            if q == t:
                return windows*q**(windows-1)
            return (q**windows-t**windows)/(q-t)

        variance = v*(star**2*mixed_power(1.0) + 2*star*error*mixed_power(r)
                      + error**2*mixed_power(r*r))
        return star+r**windows*error, variance

    def mean_error_windows(self, relative_error: float) -> int:
        """Windows until |E[k]-k*| / |k0-k*| is at most the given ratio."""
        if not self.mean_stable or not 0 < relative_error < 1:
            raise ValueError("stable mean and relative error in (0,1) required")
        factor = abs(float(self.mean_factor))
        if factor == 0:
            return 1
        windows = math.ceil(math.log(relative_error)/math.log(factor))
        # Correct possible floating ceil errors at an integer boundary.
        while factor**windows > relative_error:
            windows += 1
        while windows > 0 and factor**(windows-1) <= relative_error:
            windows -= 1
        return windows


def scalar_step_law(*, correlation: F, product_second_moment: F, dither: F,
                    step: F, selected: int, multiplier: F) -> ScalarStepLaw:
    """B=E[DR], C=E[(DR)^2]; iid windows independent of their old state."""
    if (correlation <= 0 or dither <= 0 or step <= 0 or multiplier <= 0
            or selected <= 0 or int(selected) != selected):
        raise ValueError("positive moments/scales and integer sample count required")
    if product_second_moment < correlation**2:
        raise ValueError("second moment must be at least the squared mean")
    gamma = (product_second_moment-correlation**2)/(selected*correlation**2)
    u = step*multiplier*selected*correlation
    r, v = 1-u, gamma*u*u
    mean_upper = F(2)/(multiplier*selected*correlation)
    return ScalarStepLaw(dither*dither/correlation, gamma, u, r, r*r+v, v,
                         mean_upper, mean_upper/(1+gamma))


def continuous_net_mse_u_upper(*, gain: F, gamma: F) -> F:
    """Strict stationary MSE benefit over unity, continuous fresh scoring.

    Returns the open upper endpoint for u. Zero means no positive u has a
    strict benefit. No quantization, gates, or output integer rounding.
    """
    if gain <= 0 or gamma < 0:
        raise ValueError("positive gain and nonnegative gamma required")
    error2 = (gain-1)**2
    if error2 == 0:
        return F(0)
    return 2*error2/(gamma+(1+gamma)*error2)


def request_dead_zone_step(*, product_sum: F, multiplier: F,
                           fractional_bits: int = 22) -> F | None:
    """Largest positive step rounding a fixed Q-state request to zero.

    Boundary is included under nearest-even rounding. None denotes an
    identically zero product; saturation/export are separate questions.
    """
    if multiplier <= 0 or fractional_bits < 0 or int(fractional_bits) != fractional_bits:
        raise ValueError("positive multiplier and nonnegative integer width required")
    if product_sum == 0:
        return None
    return F(1, 2**(fractional_bits+1))/(multiplier*abs(product_sum))
