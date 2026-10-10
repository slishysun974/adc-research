"""Sound frozen-window Gu state and output intervals for actual window order.

All rows use the same pre-commit coefficient box. Correlation products are
summed before the single boundary rounding. This is an offline enclosure of
the declared all-products four-lane candidate, not an online learner.
"""

from dataclasses import dataclass

from adc_research.calibration.fixed_four_lane_window import FixedFourLaneWindowConfig
from adc_research.calibration.fixed_gated_lms import adaptive_lower_thresholds_scaled
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.evaluation.fixed_online_state_bounds import (
    FixedStateBox, IntegerInterval, _coefficient_bounds, _corrected_interval,
    _dither, _magnitude_bounds, _validate_bank,
)


@dataclass(frozen=True)
class FrozenWindowBounds:
    codes: tuple[IntegerInterval, ...]
    next_state_box: FixedStateBox
    products_stage1: tuple[IntegerInterval, ...]
    products_stage2: tuple[IntegerInterval, ...]
    requested_stage1: tuple[IntegerInterval, ...]
    requested_stage2: tuple[IntegerInterval, ...]
    uncertain_gates_stage1: tuple[int, ...]
    uncertain_gates_stage2: tuple[int, ...]
    all_exported_coefficients_singleton: bool


def _products(output, dither, coefficients, cfg):
    lower=adaptive_lower_thresholds_scaled(coefficients[0],cfg)
    upper=adaptive_lower_thresholds_scaled(coefficients[1],cfg)
    amin,amax=_magnitude_bounds(output)
    intervals,uncertain=[],[]
    for i in range(cfg.coefficient_count):
        if i and amax<lower[i]:
            interval=IntegerInterval(0,0)
            ambiguity=False
        else:
            values=(dither*output.lower,dither*output.upper)
            lo,hi=min(values),max(values)
            ambiguity=bool(i and amin<upper[i])
            if ambiguity:
                lo,hi=min(lo,0),max(hi,0)
            interval=IntegerInterval(lo,hi)
        intervals.append(interval)
        uncertain.append(int(ambiguity))
    return tuple(intervals),tuple(uncertain)


def _commit(accumulators, products, cfg):
    requested=[]
    next_intervals=[]
    for state,value,step in zip(accumulators,products,cfg.step_sizes,strict=True):
        def delta(product):
            return round_fraction(-step.numerator*product*(1 << cfg.accumulator_fractional_bits),
                                  step.denominator*(1 << (2*cfg.data_fractional_bits)),cfg.update_rounding)
        ends=(delta(value.lower),delta(value.upper))
        change=IntegerInterval(min(ends),max(ends))
        requested.append(change)
        next_intervals.append(IntegerInterval(
            min(max(state.lower+change.lower,0),cfg.maximum_accumulator_code),
            min(max(state.upper+change.upper,0),cfg.maximum_accumulator_code)))
    return tuple(requested),tuple(next_intervals)


def bound_frozen_window(samples, state: FixedStateBox, config: FixedFourLaneWindowConfig):
    """Enclose one complete all-products window without interior commits.

    Window grouping, lane alignment and chronology are caller declarations;
    this function accepts decoded digital observations only. Undefined PWL
    branches fail explicitly, even when introduced by conservative merging.
    """
    samples=tuple(samples)
    if config.selection!='all_products':
        raise ValueError('this enclosure requires full correlation aggregation')
    if len(samples)!=config.window_size:
        raise ValueError('one complete frozen window required')
    if any(not isinstance(s,DigitalCalibrationSample) for s in samples):
        raise TypeError('decoded digital calibration samples required')
    cfg=config.adaptive
    _validate_bank(state.stage1_accumulators,cfg.stage1_lms)
    _validate_bank(state.stage2_accumulators,cfg.stage2_lms)
    coefficients1=_coefficient_bounds(state.stage1_accumulators,cfg.stage1_lms)
    coefficients2=_coefficient_bounds(state.stage2_accumulators,cfg.stage2_lms)
    cascade=cfg.cascade
    scale=1 << cascade.data_fractional_bits
    if cascade.backend_weight_scaled%scale:
        raise ValueError('fractional backend weight is unsupported')
    low,high=cascade.output_range_scaled
    if low%scale or high%scale:
        raise ValueError('integer final code range required')
    sums1=[IntegerInterval(0,0) for _ in cfg.stage1_lms.step_sizes]
    sums2=[IntegerInterval(0,0) for _ in cfg.stage2_lms.step_sizes]
    gates1,gates2=[0]*len(sums1),[0]*len(sums2)
    codes=[]
    cache={}
    for sample in samples:
        if sample not in cache:
            d1=_dither(sample.stage1_dither_symbol,cascade.dither_code_copies_scaled[0],1)
            d2=_dither(sample.stage2_dither_symbol,cascade.dither_code_copies_scaled[1],2)
            raw2=cascade.backend_weight_scaled*sample.backend_centered_code
            out2=_corrected_interval(IntegerInterval(raw2,raw2),cascade.stage2_pwl,coefficients2)
            raw1=out2.shifted(cascade.stage2_symbol_weight_scaled*sample.stage2_symbol-d2)
            out1=_corrected_interval(raw1,cascade.stage1_pwl,coefficients1)
            output=out1.shifted(cascade.stage1_symbol_weight_scaled*sample.stage1_symbol-d1+cascade.output_offset_scaled)
            code=IntegerInterval(
                min(max(round_fraction(output.lower,scale,'nearest_even'),low//scale),high//scale),
                min(max(round_fraction(output.upper,scale,'nearest_even'),low//scale),high//scale))
            p1,g1=_products(out1.shifted(-d1),d1,coefficients1,cfg.stage1_lms)
            p2,g2=_products(out2.shifted(-d2),d2,coefficients2,cfg.stage2_lms)
            cache[sample]=(code,p1,p2,g1,g2)
        code,p1,p2,g1,g2=cache[sample]
        codes.append(code)
        for i,(a,b) in enumerate(zip(p1,p2,strict=True)):
            sums1[i]=IntegerInterval(sums1[i].lower+a.lower,sums1[i].upper+a.upper)
            sums2[i]=IntegerInterval(sums2[i].lower+b.lower,sums2[i].upper+b.upper)
            gates1[i]+=g1[i]
            gates2[i]+=g2[i]
    request1,after1=_commit(state.stage1_accumulators,sums1,cfg.stage1_lms)
    request2,after2=_commit(state.stage2_accumulators,sums2,cfg.stage2_lms)
    return FrozenWindowBounds(tuple(codes),FixedStateBox(after1,after2),tuple(sums1),tuple(sums2),
                              request1,request2,tuple(gates1),tuple(gates2),
                              coefficients1[0]==coefficients1[1] and coefficients2[0]==coefficients2[1])
