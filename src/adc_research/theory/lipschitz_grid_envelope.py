"""Conditional continuous transfer bounds from samples and a supplied slope limit.

The caller must establish that each measured interval contains the true
output at its grid point and that the Lipschitz constant applies throughout
the declared input domain and across every condition being claimed.  The
largest slope observed *on this grid* is not such a certificate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite

from adc_research.theory.static_observation_reachability import ClosedInterval


@dataclass(frozen=True)
class LipschitzGridEnvelope:
    grid_inputs: tuple[float, ...]
    measured_outputs: tuple[ClosedInterval, ...]
    slope_bound: float
    feasible_outputs: tuple[ClosedInterval, ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        xs = self.grid_inputs
        ys = self.measured_outputs
        if len(xs) < 2 or len(xs) != len(ys):
            raise ValueError("at least two matched grid points are required")
        if any(not isfinite(x) for x in xs) or any(
            right <= left for left, right in zip(xs, xs[1:])
        ):
            raise ValueError("grid inputs must be finite and strictly increasing")
        if not isfinite(self.slope_bound) or self.slope_bound < 0:
            raise ValueError("slope_bound must be finite and nonnegative")
        if any(not isinstance(item, ClosedInterval) for item in ys):
            raise TypeError("measured outputs must be ClosedInterval values")

        # Forward/backward feasibility trims each measured interval to values
        # compatible with *all* grid points. An empty intersection means the
        # supplied samples and slope bound describe no possible transfer.
        forward = [ys[0]]
        for index in range(1, len(xs)):
            reach = self.slope_bound * (xs[index] - xs[index - 1])
            prior = forward[-1]
            low = max(ys[index].lower, prior.lower - reach)
            high = min(ys[index].upper, prior.upper + reach)
            if low > high:
                raise ValueError("grid outputs contradict the supplied slope bound")
            forward.append(ClosedInterval(low, high))

        backward: list[ClosedInterval] = list(ys)
        for index in range(len(xs) - 2, -1, -1):
            reach = self.slope_bound * (xs[index + 1] - xs[index])
            following = backward[index + 1]
            low = max(ys[index].lower, following.lower - reach)
            high = min(ys[index].upper, following.upper + reach)
            if low > high:
                raise ValueError("grid outputs contradict the supplied slope bound")
            backward[index] = ClosedInterval(low, high)

        feasible = []
        for earlier, later in zip(forward, backward, strict=True):
            low = max(earlier.lower, later.lower)
            high = min(earlier.upper, later.upper)
            if low > high:
                raise ValueError("grid outputs contradict the supplied slope bound")
            feasible.append(ClosedInterval(low, high))
        object.__setattr__(self, "feasible_outputs", tuple(feasible))

    def __call__(self, query: ClosedInterval) -> ClosedInterval:
        """Enclose every admissible transfer output over a closed input interval."""
        if not isinstance(query, ClosedInterval):
            raise TypeError("query must be a ClosedInterval")
        xs = self.grid_inputs
        if query.lower < xs[0] or query.upper > xs[-1]:
            raise ValueError("query lies outside the measured input domain")
        slope = self.slope_bound
        lower_candidates: list[float] = []
        upper_candidates: list[float] = []
        for index, (left_x, right_x) in enumerate(zip(xs, xs[1:])):
            start = max(query.lower, left_x)
            stop = min(query.upper, right_x)
            if start > stop:
                continue
            left_y = self.feasible_outputs[index]
            right_y = self.feasible_outputs[index + 1]
            if slope == 0:
                segment_lower = max(left_y.lower, right_y.lower)
                segment_upper = min(left_y.upper, right_y.upper)
            else:
                # The lower cone is the maximum of a falling and rising
                # line. Its minimum is at their intersection, clamped to
                # this portion of the grid cell. The upper cone is dual.
                lower_crossing = (
                    left_y.lower - right_y.lower + slope * (left_x + right_x)
                ) / (2 * slope)
                at_lower = min(max(lower_crossing, start), stop)
                segment_lower = max(
                    left_y.lower - slope * (at_lower - left_x),
                    right_y.lower - slope * (right_x - at_lower),
                )
                upper_crossing = (
                    right_y.upper - left_y.upper + slope * (left_x + right_x)
                ) / (2 * slope)
                at_upper = min(max(upper_crossing, start), stop)
                segment_upper = min(
                    left_y.upper + slope * (at_upper - left_x),
                    right_y.upper + slope * (right_x - at_upper),
                )
            if segment_lower > segment_upper:
                raise ValueError("numerical or grid inconsistency in transfer envelope")
            lower_candidates.append(segment_lower)
            upper_candidates.append(segment_upper)
        return ClosedInterval(min(lower_candidates), max(upper_candidates))
