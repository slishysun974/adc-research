"""Four-point Gu candidate with fixed alpha=1/4 statistic smoothing.

Only digital observations enter. Raw gates and products use the old bank.
Two product fractional guard bits are retained; coefficient commits still
occur once per 120 conversions. No offline target or analog truth is read.
"""

from dataclasses import dataclass

from adc_research.calibration.fixed_adaptive_two_stage import FixedTwoStageAdaptiveState
from adc_research.calibration.fixed_four_lane_window import (
    FixedFourLaneWindowConfig, FixedFourLaneWindowResult, correct_fixed_four_lane_window,
)
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState, exported_coefficient_codes
from adc_research.calibration.fixed_point import round_fraction

FILTER_LIMITS = (4*4*512*8700, 4*4*128*2175)


def smooth_product(previous: int, product: int, limit: int) -> int:
    """H represents 4 times the smoothed integer gate-product sum."""
    if any(isinstance(x,bool) or not isinstance(x,int) for x in (previous,product,limit)):
        raise ValueError("integer filter state, product and bound required")
    if limit <= 0 or abs(previous) > limit or abs(4*product) > limit:
        raise ValueError("filter data outside declared bounds")
    result = round_fraction(3*previous+4*product,4,"nearest_even")
    assert abs(result) <= limit
    return result


@dataclass(frozen=True)
class FilteredWindowState:
    calibration: FixedTwoStageAdaptiveState
    stage1_filter_codes: tuple[int,...] = (0,)*4
    stage2_filter_codes: tuple[int,...] = (0,)*4

    def __post_init__(self):
        if not isinstance(self.calibration,FixedTwoStageAdaptiveState):
            raise ValueError("explicit fixed calibration state required")
        for values,limit in zip((self.stage1_filter_codes,self.stage2_filter_codes),FILTER_LIMITS):
            if not isinstance(values,tuple) or len(values) != 4 or any(isinstance(v,bool) or not isinstance(v,int) or abs(v) > limit for v in values):
                raise ValueError("four bounded signed integer filter states required per bank")


@dataclass(frozen=True)
class FilteredWindowResult:
    raw: FixedFourLaneWindowResult
    state: FilteredWindowState
    requested_deltas: tuple[tuple[int,...],tuple[int,...]]
    applied_deltas: tuple[tuple[int,...],tuple[int,...]]


def _commit(old,raw_update,filtered,cfg):
    requested = tuple(round_fraction(-step.numerator*30*value*(1 << 22),
        step.denominator*64*4,"nearest_even") for step,value in zip(cfg.step_sizes,filtered,strict=True))
    after = tuple(min(max(a+d,0),cfg.maximum_accumulator_code)
                  for a,d in zip(old.accumulator_codes,requested,strict=True))
    applied = tuple(a-b for a,b in zip(after,old.accumulator_codes,strict=True))
    provisional = FixedGatedLmsState(after,old.gate_counts,old.nonzero_update_counts,
        old.coefficient_change_counts,old.sample_count)
    before_codes = exported_coefficient_codes(old,cfg)
    after_codes = exported_coefficient_codes(provisional,cfg)
    updated = FixedGatedLmsState(after,
        tuple(a+b for a,b in zip(old.gate_counts,raw_update.selected_gate_counts,strict=True)),
        tuple(n+int(d != 0) for n,d in zip(old.nonzero_update_counts,applied,strict=True)),
        tuple(n+int(a != b) for n,a,b in zip(old.coefficient_change_counts,before_codes,after_codes,strict=True)),
        old.sample_count+120)
    return updated,requested,applied


def correct_filtered_window(conversions,state: FilteredWindowState,config: FixedFourLaneWindowConfig):
    if not isinstance(state,FilteredWindowState):
        raise TypeError("FilteredWindowState required")
    adaptive = config.adaptive
    if config.selection != "point_products" or config.lane_period != 30:
        raise ValueError("120-conversion four-point contract required")
    for cfg,width in ((adaptive.stage1_lms,1024),(adaptive.stage2_lms,256)):
        if (cfg.slice_width_scaled != width or cfg.data_fractional_bits != 3
                or cfg.accumulator_fractional_bits != 22 or cfg.coefficient_format.fractional_bits != 10
                or cfg.coefficient_format.total_bits != 11 or cfg.update_rounding != "nearest_even"):
            raise ValueError("declared Q1.10/Q3/Q22 bank and rounding required")
    if (set(adaptive.cascade.dither_code_copies_scaled[0].values()) != {-512,512}
            or set(adaptive.cascade.dither_code_copies_scaled[1].values()) != {-128,128}):
        raise ValueError("declared dither copies required for filter range proof")
    raw = correct_fixed_four_lane_window(conversions,state.calibration,config)
    filters = tuple(tuple(smooth_product(previous,product,limit)
        for previous,product in zip(old,update.selected_product_sums,strict=True))
        for old,update,limit in zip((state.stage1_filter_codes,state.stage2_filter_codes),
                                  (raw.stage1_update,raw.stage2_update),FILTER_LIMITS,strict=True))
    commits = tuple(_commit(old,update,filtered,cfg) for old,update,filtered,cfg in zip(
        (state.calibration.stage1,state.calibration.stage2),(raw.stage1_update,raw.stage2_update),filters,
        (adaptive.stage1_lms,adaptive.stage2_lms),strict=True))
    next_state = FilteredWindowState(FixedTwoStageAdaptiveState(commits[0][0],commits[1][0]),*filters)
    return FilteredWindowResult(raw,next_state,tuple(c[1] for c in commits),tuple(c[2] for c in commits))
