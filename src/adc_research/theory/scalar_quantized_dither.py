"""Analytic population moments for a static single-slope control.

Uniform integrals are piecewise exact Fractions. No simulator or fitted
response is used. These results do not include PWL gates or coupled stages.
"""

from dataclasses import dataclass
from fractions import Fraction
import math


@dataclass(frozen=True)
class ScalarPopulation:
    correlation: Fraction              # E[D R]
    product_second_moment: Fraction    # E[(D R)^2]
    raw_mean: Fraction
    raw_second_moment: Fraction
    raw_target_cross_moment: Fraction  # E[R (X+D)]
    target_second_moment: Fraction     # E[(X+D)^2]
    input_mean: Fraction
    quantization_error_correlation: Fraction  # E[D (R-a(X+D))]

    @property
    def mse_minimizer(self):
        return self.raw_target_cross_moment / self.raw_second_moment

    def mse(self, coefficient: float) -> float:
        return (coefficient**2 * float(self.raw_second_moment)
                - 2*coefficient*float(self.raw_target_cross_moment)
                + float(self.target_second_moment))


def scalar_population(*, gain: Fraction, dither: Fraction,
                      low: Fraction, high: Fraction, quantized: bool) -> ScalarPopulation:
    """Exact uniform (or degenerate DC) moments, unit-step floor quantizer.

    There is no endpoint saturation: the caller must check its quantizer's
    range. Half-open bin membership and negative floor are retained.
    """
    if gain <= 0 or dither <= 0 or low > high:
        raise ValueError("positive gain/dither and ordered support required")
    ex = (low+high)/2
    ex2 = (low*low+low*high+high*high)/3
    target2 = ex2+dither*dither
    if not quantized:
        b = gain*dither*dither
        return ScalarPopulation(b, gain*gain*dither*dither*target2,
            gain*ex, gain*gain*target2, gain*target2, target2, ex, Fraction(0))
    b = c = er = er2 = cross = Fraction(0)
    for sign in (-1, 1):
        dd = sign*dither
        if low == high:
            cells = [(low, high, math.floor(gain*(low+dd)))]
        else:
            qlow, qhigh = math.floor(gain*(low+dd)), math.floor(gain*(high+dd))
            cells = [(max(low, Fraction(q)/gain-dd),
                      min(high, Fraction(q+1)/gain-dd), q)
                     for q in range(qlow, qhigh+1)]
        for left, right, q in cells:
            if low != high and left >= right:
                continue
            weight = Fraction(1, 2) if low == high else (right-left)/(2*(high-low))
            center = (left+right)/2
            b += weight*dd*q
            c += weight*dd*dd*q*q
            er += weight*q
            er2 += weight*q*q
            cross += weight*q*(center+dd)
    return ScalarPopulation(b, c, er, er2, cross, target2, ex,
                            b-gain*dither*dither)


@dataclass(frozen=True)
class ScalarWindowLaw:
    equilibrium: float
    contraction: float
    multiplier_variance: float
    stationary_variance: float
    time_constant_windows: float

    def mean(self, windows: int, initial: float = 1.0):
        return self.equilibrium+self.contraction**windows*(initial-self.equilibrium)

    def mean_variance(self, windows: int, initial: float = 1.0):
        """Finite-time exact first/second recurrence, independent windows."""
        mean, variance = initial, 0.0
        r, v = self.contraction, self.multiplier_variance
        c = self.equilibrium*(1-r)
        for _ in range(windows):
            variance = (r*r+v)*variance+v*mean*mean
            mean = r*mean+c
        return mean, variance

    def stationary_mean_variance(self, samples: int):
        """Variance of n consecutive stationary states, Cov_h=V*r^h."""
        if samples <= 0:
            raise ValueError("positive block length required")
        r = self.contraction
        # Analytic geometric weighted sum. Our experiment has r near .998;
        # this expression is stable there, including short blocks.
        weighted = r*((samples-1)-samples*r+r**samples)/(1-r)**2
        return self.stationary_variance*(samples+2*weighted)/(samples*samples)

    def adjacent_half_drift_variance(self, half_samples: int):
        """Variance of mean(second adjacent half)-mean(first half)."""
        r = self.contraction
        cross = (self.stationary_variance*r*(1-r**half_samples)**2
                 / ((1-r)**2*half_samples**2))
        return 2*(self.stationary_mean_variance(half_samples)-cross)


def scalar_window_law(population: ScalarPopulation, *, dither: float,
                      step: float, selected: int, multiplier: int) -> ScalarWindowLaw:
    if dither <= 0 or step <= 0 or selected <= 0 or multiplier <= 0:
        raise ValueError("positive update parameters required")
    b, c = float(population.correlation), float(population.product_second_moment)
    if b <= 0:
        raise ValueError("positive correlation required for this stable scalar law")
    alpha = step*multiplier
    r = 1-alpha*selected*b
    v = alpha*alpha*selected*(c-b*b)
    denominator = 1-r*r-v
    if not 0 < r < 1 or denominator <= 0 or v < 0:
        raise ValueError("control must have positive contraction and mean-square stability")
    equilibrium = dither*dither/b
    return ScalarWindowLaw(equilibrium, r, v, v*equilibrium**2/denominator,
                           -1/math.log(r))
