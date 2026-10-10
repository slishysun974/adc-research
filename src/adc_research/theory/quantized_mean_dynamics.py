"""Exact export cells and finite-state diagnostics for a frozen stage record.

The pooled 120-conversion mean map is a declared diagnostic, not the actual
phase-varying four-lane updater. Only digital raw codes and dither enter here.
Third and fourth coefficients are clamped; their requests are still reported.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction as F
from itertools import product

from adc_research.calibration.fixed_point import round_fraction


def _integer(value, name):
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{name} must be an integer")
    return value


def export_code(accumulator: int, guard_bits: int = 12) -> int:
    _integer(accumulator, "accumulator")
    _integer(guard_bits, "guard bits")
    if accumulator < 0 or guard_bits < 0:
        raise ValueError("nonnegative accumulator and guard bits required")
    return round_fraction(accumulator, 1 << guard_bits, "nearest_even")


def export_cell(code: int, guard_bits: int = 12) -> tuple[int, int]:
    """Integer preimage of an interior nearest-even coefficient code.

    Saturation is not included. At a half LSB the even code owns the tie.
    Code zero's lower endpoint is truncated to the nonnegative state domain.
    """
    _integer(code, "code")
    _integer(guard_bits, "guard bits")
    if code < 0 or guard_bits < 0:
        raise ValueError("nonnegative code and guard bits required")
    if guard_bits == 0:
        return code, code
    scale = 1 << guard_bits
    parity = code % 2
    return max(0, code*scale-scale//2+parity), code*scale+scale//2-parity


@dataclass(frozen=True)
class FixedStageRow:
    raw_scaled: int
    dither_scaled: int
    count: int = 1

    def __post_init__(self):
        for name, value in self.__dict__.items():
            _integer(value, name)
        if not self.dither_scaled or self.count <= 0:
            raise ValueError("nonzero aligned dither and positive count required")


@dataclass(frozen=True)
class StageRequest:
    products: tuple[int, ...]
    gates: tuple[int, ...]
    deltas: tuple[int, ...]
    total: int


class FrozenStageMean:
    """Fixed Q3/PWL rounding with once-rounded, pooled mean requests.

    Window size multiplies the empirical mean. For exactly window_size rows,
    this is the actual frozen-window sum; otherwise it is a virtual mean map.
    """

    def __init__(self, rows, *, width_scaled: int, steps,
                 window_size: int = 120, coefficient_bits: int = 10,
                 data_bits: int = 3, accumulator_bits: int = 22,
                 fixed_high=(1024, 1024)):
        self.rows = tuple(rows)
        self.width = _integer(width_scaled, "width")
        self.steps = tuple(steps)
        self.window = _integer(window_size, "window")
        self.coefficient_bits = _integer(coefficient_bits, "coefficient bits")
        self.data_bits = _integer(data_bits, "data bits")
        self.accumulator_bits = _integer(accumulator_bits, "accumulator bits")
        self.fixed_high = tuple(fixed_high)
        if not self.rows or any(not isinstance(row, FixedStageRow) for row in self.rows):
            raise TypeError("nonempty fixed digital stage rows required")
        if self.width <= 0 or self.window <= 0 or self.coefficient_bits < 0 or self.data_bits < 0:
            raise ValueError("positive width/window and nonnegative fractional bits required")
        if self.accumulator_bits < self.coefficient_bits:
            raise ValueError("accumulator must be at least as fine as coefficients")
        if len(self.steps) != 4 or any(not isinstance(s, F) or s <= 0 for s in self.steps):
            raise ValueError("four positive exact steps required")
        if len(self.fixed_high) != 2 or any(not isinstance(c, int) or isinstance(c, bool) or
                not 0 <= c < (2 << self.coefficient_bits) for c in self.fixed_high):
            raise ValueError("two legal fixed coefficient codes required")
        if any(not -4*self.width <= row.raw_scaled < 4*self.width for row in self.rows):
            raise ValueError("a digital row is outside the signed PWL domain")
        self.total = sum(row.count for row in self.rows)
        self.guard = self.accumulator_bits-self.coefficient_bits
        self.maximum = ((2 << self.coefficient_bits)-1) << self.guard
        self.cache = {}

    def request(self, codes) -> StageRequest:
        codes = tuple(codes)
        if len(codes) != 2 or any(not isinstance(c, int) or isinstance(c, bool) or
                not 0 <= c < (2 << self.coefficient_bits) for c in codes):
            raise ValueError("two legal low coefficient codes required")
        if codes in self.cache:
            return self.cache[codes]
        coefficients = codes+self.fixed_high
        divisor = 1 << self.coefficient_bits
        thresholds = tuple(round_fraction(self.width*sum(coefficients[:i]), divisor,
                                          "nearest_even") for i in range(4))
        sums, counts = [0]*4, [0]*4
        for row in self.rows:
            magnitude = abs(row.raw_scaled)
            segment = min(magnitude//self.width, 3)
            local = magnitude-segment*self.width
            offset = round_fraction(self.width*sum(coefficients[:segment]), divisor, "nearest_even")
            value = round_fraction(local*coefficients[segment], divisor, "nearest_even")+offset
            value *= (row.raw_scaled > 0)-(row.raw_scaled < 0)
            value -= row.dither_scaled
            for i, threshold in enumerate(thresholds):
                if i == 0 or abs(value) >= threshold:
                    sums[i] += row.count*row.dither_scaled*value
                    counts[i] += row.count
        deltas = []
        for step, correlation in zip(self.steps, sums):
            numerator = -step.numerator*self.window*correlation*(1 << self.accumulator_bits)
            denominator = step.denominator*self.total*(1 << (2*self.data_bits))
            deltas.append(round_fraction(numerator, denominator, "nearest_even"))
        result = StageRequest(tuple(sums), tuple(counts), tuple(deltas), self.total)
        self.cache[codes] = result
        return result

    def transition(self, state):
        state = tuple(state)
        if len(state) != 2 or any(not isinstance(z, int) or isinstance(z, bool) or
                not 0 <= z <= self.maximum for z in state):
            raise ValueError("two legal integer accumulators required")
        request = self.request(tuple(export_code(z, self.guard) for z in state))
        return tuple(min(max(z+d, 0), self.maximum) for z, d in zip(state, request.deltas))


def certify_rectangle(model: FrozenStageMean, bounds):
    """Exact images of every export-cell intersection in an integer rectangle.

    No trajectory sampling is used. Constant requests give the image extrema
    directly, including saturation. A fixed state must satisfy each coordinate
    separately (zero request, or an outward request at a saturation endpoint).
    """
    bounds = tuple(tuple(pair) for pair in bounds)
    if len(bounds) != 2 or any(len(pair) != 2 or any(not isinstance(z, int) or isinstance(z, bool)
            for z in pair) or not 0 <= pair[0] <= pair[1] <= model.maximum for pair in bounds):
        raise ValueError("two legal ordered integer bounds required")
    code_ranges = [range(export_code(lo, model.guard), export_code(hi, model.guard)+1)
                   for lo, hi in bounds]
    cells, violations, fixed_cells = [], [], []
    for codes in product(*code_ranges):
        intersections = tuple((max(pair[0], export_cell(code, model.guard)[0]),
                               min(pair[1], export_cell(code, model.guard)[1]))
                              for pair, code in zip(bounds, codes))
        if any(lo > hi for lo, hi in intersections):
            continue
        request = model.request(codes)
        images = tuple((min(max(lo+d, 0), model.maximum), min(max(hi+d, 0), model.maximum))
                       for (lo, hi), d in zip(intersections, request.deltas))
        inside = all(bound[0] <= image[0] <= image[1] <= bound[1]
                     for bound, image in zip(bounds, images))
        fixed = all(d == 0 or (d < 0 and lo == 0) or (d > 0 and hi == model.maximum)
                    for (lo, hi), d in zip(intersections, request.deltas))
        cell = {"codes": codes, "intersection": intersections, "images": images,
                "request": request, "inside": inside, "contains_fixed_state": fixed}
        cells.append(cell)
        if not inside:
            violations.append(codes)
        if fixed:
            fixed_cells.append(codes)
    invariant = not violations
    cardinality = (bounds[0][1]-bounds[0][0]+1)*(bounds[1][1]-bounds[1][0]+1)
    return {"bounds": bounds, "integer_state_count": cardinality, "cells": cells,
            "invariant": invariant, "violating_codes": violations,
            "fixed_state_cells": fixed_cells,
            "all_clamped_requests_zero": all(not any(c["request"].deltas[2:]) for c in cells),
            "all_clamped_gates_closed": all(not any(c["request"].gates[2:]) for c in cells),
            "every_state_eventually_nontrivially_periodic": invariant and not fixed_cells}


def accelerated_orbit(model: FrozenStageMean, initial, bounds, max_events=20000):
    """Skip only steps that provably keep exactly the same exported codes.

    Interior rectangle required, so no saturation occurs. A repeated full
    accumulator state certifies the cycle; repeated coefficient codes alone
    do not. A limit without repetition does not certify a period.
    """
    _integer(max_events, "event limit")
    initial, bounds = tuple(initial), tuple(tuple(pair) for pair in bounds)
    if len(initial) != 2 or any(not isinstance(z, int) or isinstance(z, bool) for z in initial):
        raise ValueError("two integer initial accumulators required")
    if len(bounds) != 2 or any(len(pair) != 2 or any(not isinstance(z, int) or isinstance(z, bool)
            for z in pair) for pair in bounds):
        raise ValueError("two integer rectangle bounds required")
    if max_events <= 0 or any(not 0 < lo <= hi < model.maximum for lo, hi in bounds):
        raise ValueError("positive event limit and an interior rectangle required")
    state, seen, events, clock = initial, {}, [], 0
    for _ in range(max_events):
        if any(not lo <= z <= hi for z, (lo, hi) in zip(state, bounds)):
            return {"status": "left_rectangle", "events": events, "last_state": state}
        if state in seen:
            index, start = seen[state]
            return {"status": "cycle", "cycle_start": start, "period": clock-start,
                    "cycle_event_start": index, "events": events, "last_state": state}
        seen[state] = (len(events), clock)
        codes = tuple(export_code(z, model.guard) for z in state)
        deltas = model.request(codes).deltas[:2]
        if not any(deltas):
            return {"status": "fixed", "events": events, "last_state": state, "steps": clock}
        last = min((hi-z)//d if d > 0 else (z-lo)//(-d)
                   for z, d, (lo, hi) in zip(state, deltas,
                       (export_cell(c, model.guard) for c in codes)) if d)
        steps = last+1
        events.append({"step": clock, "state": state, "codes": codes,
                       "deltas": deltas, "constant_request_steps": steps})
        state = tuple(z+steps*d for z, d in zip(state, deltas))
        clock += steps
    return {"status": "event_limit", "events": events, "last_state": state, "steps": clock}
