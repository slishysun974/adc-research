"""Four explicit shared-bank timing hypotheses; digital observations only."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Sequence

from adc_research.calibration.fixed_adaptive_two_stage import (
    FixedTwoStageAdaptiveState, correct_and_update_fixed, cascade_from_fixed_state,
)
from adc_research.calibration.fixed_four_lane_window import (
    FourLaneConversion, FixedFourLaneWindowConfig, correct_fixed_four_lane_window,
)
from adc_research.calibration.fixed_gated_lms import (
    FixedGatedLmsState, exported_coefficient_codes,
)
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed

TimingMethod = Literal["merged_boundary", "lane_rounded_boundary", "serial_immediate", "delayed_broadcast"]
METHODS = ("merged_boundary", "lane_rounded_boundary", "serial_immediate", "delayed_broadcast")


@dataclass(frozen=True)
class CommitBroadcastState:
    master: FixedTwoStageAdaptiveState
    visible: FixedTwoStageAdaptiveState


@dataclass(frozen=True)
class TimingCommit:
    after_conversion_id: int
    learning_state: FixedTwoStageAdaptiveState
    master_before: FixedTwoStageAdaptiveState
    master_after: FixedTwoStageAdaptiveState
    selected_conversion_ids: tuple[int, ...]
    products: tuple[tuple[int, ...], tuple[int, ...]]
    gate_counts: tuple[tuple[int, ...], tuple[int, ...]]
    requested: tuple[tuple[int, ...], tuple[int, ...]]
    applied: tuple[tuple[int, ...], tuple[int, ...]]


@dataclass(frozen=True)
class CommitBroadcastResult:
    state: CommitBroadcastState
    calibrations: tuple
    commits: tuple[TimingCommit, ...]


def _epoch(state, sample_count):
    return replace(state, stage1=replace(state.stage1, sample_count=sample_count),
                   stage2=replace(state.stage2, sample_count=sample_count))


def _apply_bank(bank, cfg, requested, gates, samples):
    before = exported_coefficient_codes(bank, cfg)
    after = tuple(min(max(a+d, 0), cfg.maximum_accumulator_code)
                  for a, d in zip(bank.accumulator_codes, requested, strict=True))
    applied = tuple(a-b for a, b in zip(after, bank.accumulator_codes, strict=True))
    exported = exported_coefficient_codes(replace(bank, accumulator_codes=after), cfg)
    result = FixedGatedLmsState(
        after, tuple(a+b for a, b in zip(bank.gate_counts, gates, strict=True)),
        tuple(a+int(b != 0) for a, b in zip(bank.nonzero_update_counts, applied, strict=True)),
        tuple(a+int(b != c) for a, b, c in zip(bank.coefficient_change_counts, before, exported, strict=True)),
        bank.sample_count+samples,
    )
    return result, applied


def _apply(master, cfg, requested, gates, samples):
    first, d1 = _apply_bank(master.stage1, cfg.stage1_lms, requested[0], gates[0], samples)
    second, d2 = _apply_bank(master.stage2, cfg.stage2_lms, requested[1], gates[1], samples)
    return FixedTwoStageAdaptiveState(first, second), (d1, d2)


def _round_product(product, cfg, index, multiplier):
    step = cfg.step_sizes[index]
    return round_fraction(-step.numerator*multiplier*product*(1 << cfg.accumulator_fractional_bits),
                          step.denominator*(1 << (2*cfg.data_fractional_bits)), cfg.update_rounding)


def correct_commit_broadcast_window(
    conversions: Sequence[FourLaneConversion], state: CommitBroadcastState,
    config: FixedFourLaneWindowConfig, method: TimingMethod,
) -> CommitBroadcastResult:
    """Process a complete window with explicit merge/commit/visibility semantics.

    No targets or analog states are accepted. Counters are diagnostic metadata;
    delayed visibility stores an old coefficient version at the current epoch.
    """
    if method not in METHODS:
        raise ValueError("unsupported commit/broadcast contract")
    if config.selection != "point_products":
        raise ValueError("timing comparison requires one selected point per lane")
    if method != "delayed_broadcast" and state.master != state.visible:
        raise ValueError("zero-latency method requires identical master and visible states")
    if state.master.stage1.sample_count != state.visible.stage1.sample_count:
        raise ValueError("master and visible epochs must match")
    rows = tuple(conversions)
    # Also validates IDs, lanes, both bank epochs, state bounds and sample types.
    frozen = correct_fixed_four_lane_window(rows, state.visible, config)
    cfg = config.adaptive
    for bank, bank_cfg in ((state.master.stage1, cfg.stage1_lms), (state.master.stage2, cfg.stage2_lms)):
        if bank.sample_count != state.visible.stage1.sample_count or any(
            a > bank_cfg.maximum_accumulator_code for a in bank.accumulator_codes
        ):
            raise ValueError("master bank bounds or epochs disagree")
    if method == "serial_immediate":
        scaled = replace(cfg,
            stage1_lms=replace(cfg.stage1_lms, step_sizes=tuple(s*config.lane_period for s in cfg.stage1_lms.step_sizes)),
            stage2_lms=replace(cfg.stage2_lms, step_sizes=tuple(s*config.lane_period for s in cfg.stage2_lms.step_sizes)))
        current, calibrations, commits = state.master, [], []
        selected = set(frozen.selected_conversion_ids)
        dynamic = cascade_from_fixed_state(cfg.cascade, current, cfg.stage1_lms, cfg.stage2_lms)
        for row in rows:
            if row.conversion_id in selected:
                before = current
                result = correct_and_update_fixed(row.sample, before, scaled)
                current = result.state
                updates = (result.stage1_update, result.stage2_update)
                products = tuple(tuple(u.dither_code_scaled*u.corrected_output_scaled if take else 0
                                       for take in u.gate_mask) for u in updates)
                commits.append(TimingCommit(row.conversion_id, before, before, current,
                    (row.conversion_id,), products, tuple(tuple(map(int, u.gate_mask)) for u in updates),
                    tuple(u.requested_accumulator_deltas for u in updates),
                    tuple(u.applied_accumulator_deltas for u in updates)))
                calibrations.append(result.calibration)
                dynamic = cascade_from_fixed_state(cfg.cascade, current, cfg.stage1_lms, cfg.stage2_lms)
            else:
                calibrations.append(correct_two_stage_fixed_observed(row.sample, dynamic))
                current = _epoch(current, current.stage1.sample_count+1)
        return CommitBroadcastResult(CommitBroadcastState(current, current), tuple(calibrations), tuple(commits))

    updates = (frozen.stage1_update, frozen.stage2_update)
    requested = tuple(u.requested_deltas for u in updates)
    if method == "lane_rounded_boundary":
        selected = set(frozen.selected_conversion_ids)
        requests = [[0]*cfg.stage1_lms.coefficient_count, [0]*cfg.stage2_lms.coefficient_count]
        for row, cal in zip(rows, frozen.calibrations, strict=True):
            if row.conversion_id not in selected:
                continue
            for stage, (u, bank_cfg, dither, local) in enumerate((
                (updates[0], cfg.stage1_lms, cal.stage1_dither_scaled, cal.stage1_pwl.corrected_code_scaled-cal.stage1_dither_scaled),
                (updates[1], cfg.stage2_lms, cal.stage2_dither_scaled, cal.stage2_pwl.corrected_code_scaled-cal.stage2_dither_scaled))):
                for i, threshold in enumerate(u.thresholds_scaled):
                    product = dither*local if i == 0 or abs(local) >= threshold else 0
                    requests[stage][i] += _round_product(product, bank_cfg, i, config.lane_period)
        requested = tuple(map(tuple, requests))
    gates = tuple(u.selected_gate_counts for u in updates)
    master, applied = _apply(state.master, cfg, requested, gates, len(rows))
    visible = _epoch(state.master, master.stage1.sample_count) if method == "delayed_broadcast" else master
    event = TimingCommit(rows[-1].conversion_id, state.visible, state.master, master,
        frozen.selected_conversion_ids, tuple(u.selected_product_sums for u in updates),
        gates, requested, applied)
    return CommitBroadcastResult(CommitBroadcastState(master, visible), frozen.calibrations, (event,))
