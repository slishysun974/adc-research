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


def _box(bounds, dimension=None, maximum=None):
    bounds = tuple(tuple(pair) for pair in bounds)
    if not bounds or (dimension is not None and len(bounds) != dimension):
        raise ValueError("nonempty rectangle of the declared dimension required")
    for pair in bounds:
        if len(pair) != 2:
            raise ValueError("each interval needs two endpoints")
        for value in pair: _integer(value, "rectangle endpoint")
        if pair[0] > pair[1] or (maximum is not None and not 0 <= pair[0] <= pair[1] <= maximum):
            raise ValueError("ordered legal integer intervals required")
    return bounds


def subtract_integer_box(source, cover):
    """Disjoint exact rectangles for source minus cover, including tie points."""
    source = _box(source)
    cover = _box(cover, len(source))
    intersection = tuple((max(a,c), min(b,d)) for (a,b),(c,d) in zip(source,cover))
    if any(lo > hi for lo,hi in intersection): return (source,)
    middle = list(source)
    pieces = []
    for axis, (lo,hi) in enumerate(intersection):
        start, end = middle[axis]
        if start < lo:
            piece = middle.copy(); piece[axis] = (start,lo-1)
            pieces.append(tuple(piece))
        if hi < end:
            piece = middle.copy(); piece[axis] = (hi+1,end)
            pieces.append(tuple(piece))
        middle[axis] = (lo,hi)
    return tuple(pieces)


def integer_box_uncovered(source, covers, *, max_fragments=4096):
    """Exact uncovered pieces; corners or a bounding hull do not prove coverage."""
    source = _box(source)
    covers = tuple(_box(box,len(source)) for box in covers)
    _integer(max_fragments,"fragment budget")
    if max_fragments <= 0: raise ValueError("positive fragment budget required")
    pieces = (source,)
    for cover in covers:
        remaining = []
        for piece in pieces:
            remaining.extend(subtract_integer_box(piece,cover))
            if len(remaining) > max_fragments:
                raise ValueError("integer coverage fragment budget exceeded")
        pieces = tuple(remaining)
        if not pieces: break
    return pieces


def certify_phase_unions(phase_boxes, request_vectors, *, guard_bits=12,
                         maximum=2047*4096, max_cells=256,
                         max_requests=512, max_fragments=4096):
    """Exact phase-to-phase inclusion for export-cell-constant integer updates.

    request_vectors(phase,codes) returns EVERY allowed full request vector for
    that phase/export cell. Future coverage and independence from hidden bits
    beyond the exported codes are caller obligations. All coordinates are
    retained. Finite unions are tested by exact subtraction, not by corners.
    The last phase maps back to phase zero. No cycle of a varying input or
    PRNG is inferred from this inclusion certificate.
    """
    for value,name in ((guard_bits,"guard bits"),(maximum,"state maximum"),
                       (max_cells,"cell budget"),(max_requests,"request budget")):
        _integer(value,name)
    if guard_bits < 0 or min(maximum,max_cells,max_requests) <= 0:
        raise ValueError("legal export precision and positive budgets required")
    phases = tuple(tuple(_box(box,maximum=maximum) for box in phase) for phase in phase_boxes)
    if not phases or any(not phase for phase in phases):
        raise ValueError("nonempty unions for every phase required")
    dimension = len(phases[0][0])
    if any(len(box) != dimension for phase in phases for box in phase):
        raise ValueError("all phase rectangles must have the same dimension")
    # Fail before any request computation when the declared local cover is too large.
    potential_cells = 0
    for phase in phases:
        for box in phase:
            count = 1
            for lo,hi in box:
                count *= export_code(hi,guard_bits)-export_code(lo,guard_bits)+1
            potential_cells += count
    if potential_cells > max_cells:
        raise ValueError("export-cell budget exceeded before evaluating requests")
    cells, violating, request_count = [], [], 0
    for phase_index, phase in enumerate(phases):
        targets = phases[(phase_index+1) % len(phases)]
        for box_index, box in enumerate(phase):
            ranges = tuple(range(export_code(lo,guard_bits),export_code(hi,guard_bits)+1)
                           for lo,hi in box)
            for codes in product(*ranges):
                intersection = tuple((max(lo,export_cell(code,guard_bits)[0]),
                                      min(hi,export_cell(code,guard_bits)[1]))
                                     for (lo,hi),code in zip(box,codes))
                if any(lo > hi for lo,hi in intersection): continue
                vectors = iter(request_vectors(phase_index,codes))
                entries = []
                for vector in vectors:
                    request_count += 1
                    if request_count > max_requests:
                        raise ValueError("full-request vector budget exceeded")
                    vector = tuple(vector)
                    if len(vector) != dimension:
                        raise ValueError("full request vector must retain all coordinates")
                    for value in vector: _integer(value,"request coordinate")
                    image = tuple((min(max(lo+d,0),maximum),min(max(hi+d,0),maximum))
                                  for (lo,hi),d in zip(intersection,vector))
                    uncovered = integer_box_uncovered(image,targets,max_fragments=max_fragments)
                    witness = tuple(lo for lo,_ in uncovered[0]) if uncovered else None
                    entries.append({"request":vector,"image":image,
                                    "inside":not uncovered,"uncovered_witness":witness})
                    if uncovered:
                        violating.append((phase_index,box_index,codes,vector,witness))
                if not entries: raise ValueError("at least one allowed full request is required")
                cells.append({"phase":phase_index,"box":box_index,"codes":codes,
                              "intersection":intersection,"requests":entries})
    return {"phase_unions":phases,"dimension":dimension,"cell_count":len(cells),
            "request_count":request_count,"cells":cells,"invariant":not violating,
            "violations":violating,
            "future_request_coverage_provided_by_caller":True,
            "actual_input_or_prng_period_certified":False}


def propagate_export_itineraries(initial_box, windows, request_vector, *,
                                  guard_bits=12, maximum=2047*4096,
                                  max_cells_per_window=128, max_branches=128,
                                  max_total_requests=64):
    """Exact initial-state partition for a FIXED finite window sequence.

    Each branch stores an initial rectangle and its cumulative translation.
    Export-code boundaries split the initial rectangle, without filling gaps
    or merging different itineraries. Saturation is deliberately a stop: the
    translation theorem applies only before any possible saturated state.
    Budget stops preserve only complete earlier window certificates.
    No periodic extension, source/PRNG closure or contraction is supplied.
    """
    for value,name in ((windows,"window count"),(guard_bits,"guard bits"),
                       (maximum,"state maximum"),(max_cells_per_window,"cell budget"),
                       (max_branches,"branch budget"),(max_total_requests,"request budget")):
        _integer(value,name)
    if windows < 0 or guard_bits < 0 or min(maximum,max_cells_per_window,max_branches,max_total_requests) <= 0:
        raise ValueError("nonnegative time/precision and positive budgets required")
    initial_box=_box(initial_box,maximum=maximum)
    dimension=len(initial_box)
    def volume(box):
        count=1
        for lo,hi in box: count*=hi-lo+1
        return count
    cardinality=volume(initial_box)
    branches=[{'initial':initial_box,'current':initial_box,
               'offset':(0,)*dimension,'itinerary':()}]
    history=[];requests={};status='complete';stop=None
    for window in range(windows):
        potential=0
        for branch in branches:
            count=1
            for lo,hi in branch['current']:
                count*=export_code(hi,guard_bits)-export_code(lo,guard_bits)+1
            potential+=count
        if potential>max_cells_per_window or potential>max_branches:
            status='cell_budget' if potential>max_cells_per_window else 'branch_budget'
            stop={'window':window,'required_cells':potential,'required_branches':potential}
            break
        intersections=[]
        for parent,branch in enumerate(branches):
            ranges=tuple(range(export_code(lo,guard_bits),export_code(hi,guard_bits)+1)
                         for lo,hi in branch['current'])
            for codes in product(*ranges):
                cell=tuple((max(lo,export_cell(code,guard_bits)[0]),
                            min(hi,export_cell(code,guard_bits)[1]))
                           for (lo,hi),code in zip(branch['current'],codes))
                if all(lo<=hi for lo,hi in cell): intersections.append((parent,codes,cell))
        needed=sorted({codes for _,codes,_ in intersections})
        if len(requests)+len(needed)>max_total_requests:
            status='request_budget'
            stop={'window':window,'required_new_requests':len(needed),
                  'prior_requests':len(requests)}
            break
        for codes in needed:
            vector=tuple(request_vector(window,codes))
            if len(vector)!=dimension:
                raise ValueError("full request must retain every initial coordinate")
            for value in vector: _integer(value,'request coordinate')
            requests[window,codes]=vector
        following=[];actions=[];unsafe=[]
        for parent,codes,cell in intersections:
            branch=branches[parent];vector=requests[window,codes]
            after=tuple((lo+d,hi+d) for (lo,hi),d in zip(cell,vector))
            if any(lo<0 or hi>maximum for lo,hi in after):
                unsafe.append({'codes':codes,'cell':cell,'request':vector,'unclipped_image':after})
            origin=tuple((lo-d,hi-d) for (lo,hi),d in zip(cell,branch['offset']))
            offset=tuple(a+b for a,b in zip(branch['offset'],vector))
            following.append({'initial':origin,'current':after,'offset':offset,
                              'itinerary':branch['itinerary']+(codes,)})
            actions.append({'parent':parent,'codes':codes,'before':cell,'request':vector,
                            'after':after,'initial':origin})
        if unsafe:
            status='saturation_possible';stop={'window':window,'unsafe_images':unsafe}
            break
        assert sum(volume(branch['initial']) for branch in following)==cardinality
        history.append({'window':window,'source_branches':len(branches),
                        'cells':len(intersections),'unique_requests':len(needed),
                        'initial_state_count':cardinality,'actions':actions,
                        'after_branches':following})
        branches=following
    return {'status':status,'certified_windows':len(history),'requested_windows':windows,
            'initial_state_count':cardinality,'initial':initial_box,'branches':branches,
            'history':history,'stop':stop,'unique_requests_evaluated':len(requests),
            'future_windows_certified':False,'periodic_extension_certified':False}
