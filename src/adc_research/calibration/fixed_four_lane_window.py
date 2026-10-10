"""Declared shared-bank four-lane Gu window candidate, not chip timing.

All scoring, local learning outputs and gates use the window's old state.
Only digital observations enter here. Products remain unrounded until one
boundary commit; updated coefficients first affect the following window.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Sequence

from adc_research.calibration.fixed_adaptive_two_stage import (
    FixedTwoStageAdaptiveConfig, FixedTwoStageAdaptiveState, cascade_from_fixed_state,
)
from adc_research.calibration.fixed_gated_lms import (
    FixedGatedLmsConfig, FixedGatedLmsState,
    adaptive_lower_thresholds_scaled, exported_coefficient_codes,
)
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.fixed_pwl import FixedTwoStageResult, correct_two_stage_fixed_observed
from adc_research.calibration.observation import DigitalCalibrationSample


def _int(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    return value


@dataclass(frozen=True)
class FourLaneConversion:
    conversion_id: int
    lane: int
    sample: DigitalCalibrationSample

    def __post_init__(self) -> None:
        if _int(self.conversion_id, "conversion ID") < 0:
            raise ValueError("conversion ID must be nonnegative")
        if not 0 <= _int(self.lane, "lane") < 4:
            raise ValueError("lane must be in 0..3")
        if not isinstance(self.sample, DigitalCalibrationSample):
            raise TypeError("online window accepts DigitalCalibrationSample only")


@dataclass(frozen=True)
class FixedFourLaneWindowConfig:
    adaptive: FixedTwoStageAdaptiveConfig
    lane_period: int = 30
    selection: Literal["all_products", "point_products"] = "all_products"
    point_phase: int = 0
    lane_order: tuple[int, int, int, int] = (0, 1, 2, 3)

    def __post_init__(self) -> None:
        if _int(self.lane_period, "lane period") <= 0:
            raise ValueError("lane period must be positive")
        if not 0 <= _int(self.point_phase, "point phase") < self.lane_period:
            raise ValueError("point phase must lie inside the lane window")
        if self.selection not in ("all_products", "point_products"):
            raise ValueError("unsupported window selection")
        if len(self.lane_order) != 4 or set(self.lane_order) != {0, 1, 2, 3}:
            raise ValueError("lane order must be a permutation of 0..3")
        for value in self.lane_order:
            _int(value, "lane order entry")

    @property
    def window_size(self) -> int:
        return 4*self.lane_period


@dataclass(frozen=True)
class FixedWindowBankUpdate:
    coefficient_codes_before: tuple[int, ...]
    thresholds_scaled: tuple[int, ...]
    lane_product_sums: tuple[tuple[int, ...], ...]
    lane_gate_counts: tuple[tuple[int, ...], ...]
    selected_product_sums: tuple[int, ...]
    selected_gate_counts: tuple[int, ...]
    product_multiplier: int
    requested_deltas: tuple[int, ...]
    applied_deltas: tuple[int, ...]
    coefficient_codes_after: tuple[int, ...]
    state: FixedGatedLmsState


@dataclass(frozen=True)
class FixedFourLaneWindowResult:
    first_conversion_id: int
    last_conversion_id: int
    selected_conversion_ids: tuple[int, ...]
    calibrations: tuple[FixedTwoStageResult, ...]
    stage1_learning_outputs_scaled: tuple[int, ...]
    stage2_learning_outputs_scaled: tuple[int, ...]
    stage1_update: FixedWindowBankUpdate
    stage2_update: FixedWindowBankUpdate
    state: FixedTwoStageAdaptiveState


def _bank(state: FixedGatedLmsState, cfg: FixedGatedLmsConfig,
          rows: Sequence[FourLaneConversion], values: Sequence[tuple[int, int]],
          selected: tuple[bool, ...], multiplier: int) -> FixedWindowBankUpdate:
    coefficients = exported_coefficient_codes(state, cfg)
    thresholds = adaptive_lower_thresholds_scaled(coefficients, cfg)
    count = cfg.coefficient_count
    lane_sums = [[0]*count for _ in range(4)]
    lane_counts = [[0]*count for _ in range(4)]
    sums, counts = [0]*count, [0]*count
    for row, (dither, output), take in zip(rows, values, selected, strict=True):
        for i, threshold in enumerate(thresholds):
            if i == 0 or abs(output) >= threshold:
                product = dither*output
                lane_sums[row.lane][i] += product
                lane_counts[row.lane][i] += 1
                if take:
                    sums[i] += product
                    counts[i] += 1
    requested = tuple(round_fraction(
        -step.numerator*multiplier*product*(1 << cfg.accumulator_fractional_bits),
        step.denominator*(1 << (2*cfg.data_fractional_bits)), cfg.update_rounding,
    ) for step, product in zip(cfg.step_sizes, sums, strict=True))
    after = tuple(min(max(value+delta, 0), cfg.maximum_accumulator_code)
                  for value, delta in zip(state.accumulator_codes, requested, strict=True))
    applied = tuple(a-b for a, b in zip(after, state.accumulator_codes, strict=True))
    provisional = FixedGatedLmsState(after, state.gate_counts,
                                    state.nonzero_update_counts, state.coefficient_change_counts,
                                    state.sample_count)
    exported_after = exported_coefficient_codes(provisional, cfg)
    next_state = FixedGatedLmsState(
        after, tuple(a+b for a, b in zip(state.gate_counts, counts, strict=True)),
        tuple(n+int(d != 0) for n, d in zip(state.nonzero_update_counts, applied, strict=True)),
        tuple(n+int(a != b) for n, a, b in zip(state.coefficient_change_counts,
                                             coefficients, exported_after, strict=True)),
        state.sample_count+len(rows),
    )
    return FixedWindowBankUpdate(
        coefficients, thresholds, tuple(map(tuple, lane_sums)), tuple(map(tuple, lane_counts)),
        tuple(sums), tuple(counts), multiplier, requested, applied, exported_after, next_state,
    )


def correct_fixed_four_lane_window(
    conversions: Sequence[FourLaneConversion], state: FixedTwoStageAdaptiveState,
    config: FixedFourLaneWindowConfig,
) -> FixedFourLaneWindowResult:
    """Score 4*P conversions, then update two shared banks once.

    Full selection sums all 4*P products with base per-conversion step mu.
    Point selection multiplies its four products by P, so both estimate the
    same elapsed-window update scale. Division by active gate counts is never
    performed. sample_count counts all scored conversions; gate_counts counts
    selected active products, and change counters count boundary commits.
    """
    rows = tuple(conversions)
    if len(rows) != config.window_size:
        raise ValueError("complete four-lane window required; partial windows are not committed")
    if any(not isinstance(row, FourLaneConversion) for row in rows):
        raise TypeError("window rows must be FourLaneConversion values")
    first = state.stage1.sample_count
    if state.stage2.sample_count != first or first % config.window_size:
        raise ValueError("both banks must start at the same aligned window boundary")
    for bank, cfg in ((state.stage1, config.adaptive.stage1_lms),
                      (state.stage2, config.adaptive.stage2_lms)):
        if len(bank.accumulator_codes) != cfg.coefficient_count or any(
            value > cfg.maximum_accumulator_code for value in bank.accumulator_codes
        ):
            raise ValueError("state lies outside the declared coefficient bank")
    for offset, row in enumerate(rows):
        expected = first+offset
        if row.conversion_id != expected or row.lane != config.lane_order[expected % 4]:
            raise ValueError("conversion ID or four-way lane alignment mismatch")
    dynamic = cascade_from_fixed_state(config.adaptive.cascade, state,
                                       config.adaptive.stage1_lms, config.adaptive.stage2_lms)
    calibrations = tuple(correct_two_stage_fixed_observed(row.sample, dynamic) for row in rows)
    values1, values2 = [], []
    for calibration in calibrations:
        d1, d2 = calibration.stage1_dither_scaled, calibration.stage2_dither_scaled
        if d1 == 0 or d2 == 0:
            raise ValueError("both aligned nonzero digital dither copies are required")
        values1.append((d1, calibration.stage1_pwl.corrected_code_scaled-d1))
        values2.append((d2, calibration.stage2_pwl.corrected_code_scaled-d2))
    selected = tuple(config.selection == "all_products" or
                     (offset//4) == config.point_phase for offset in range(len(rows)))
    multiplier = 1 if config.selection == "all_products" else config.lane_period
    update1 = _bank(state.stage1, config.adaptive.stage1_lms, rows, values1, selected, multiplier)
    update2 = _bank(state.stage2, config.adaptive.stage2_lms, rows, values2, selected, multiplier)
    return FixedFourLaneWindowResult(
        first, first+len(rows)-1, tuple(row.conversion_id for row, take in zip(rows, selected) if take),
        calibrations, tuple(y for _, y in values1), tuple(y for _, y in values2),
        update1, update2, FixedTwoStageAdaptiveState(update1.state, update2.state),
    )
