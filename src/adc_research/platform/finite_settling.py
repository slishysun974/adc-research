"""Stateful first-order settling extension for the reference platform.

This module is deliberately platform-side: it advances one sample at a time
from an explicit prior residue state.  The independent theory implementation
uses the closed-form periodic boundary condition instead of calling this code.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import Hashable

from adc_research.platform.backend_sar import convert as convert_sar
from adc_research.platform.pipeline import (
    PipelineResult,
    StaticPipelineConfig,
    StaticPipelineNonidealities,
)
from adc_research.platform.reconstruct import reconstruct
from adc_research.platform.stage import StageResult, process as process_stage


@dataclass(frozen=True)
class SettlingState:
    """Previous settled outputs of the two front stages."""

    stage1_residue: float = 0.0
    stage2_residue: float = 0.0

    def __post_init__(self) -> None:
        if not all(isfinite(value) for value in self.as_tuple()):
            raise ValueError("settling state must be finite")

    def as_tuple(self) -> tuple[float, float]:
        return (self.stage1_residue, self.stage2_residue)


@dataclass(frozen=True)
class FiniteSettlingConfig:
    """Per-stage fraction of the previous-output error left after one phase."""

    residual_factors: tuple[float, float]

    def __post_init__(self) -> None:
        if len(self.residual_factors) != 2:
            raise ValueError("three-stage pipeline requires two settling factors")
        if any(
            not isfinite(value) or value < 0 or value >= 1
            for value in self.residual_factors
        ):
            raise ValueError("settling residual factors must lie in [0,1)")


@dataclass(frozen=True)
class FiniteSettlingResult:
    """One platform sample plus static targets and the next dynamic state."""

    pipeline: PipelineResult
    stage1_target_residue: float
    stage2_target_residue: float
    prior_state: SettlingState
    next_state: SettlingState


def _settled_stage(
    target: StageResult,
    previous_residue: float,
    residual_factor: float,
    next_stage_range: tuple[float, float],
) -> StageResult:
    actual = (
        (1.0 - residual_factor) * target.residue
        + residual_factor * previous_residue
    )
    low, high = next_stage_range
    overload_low = actual < low
    overload_high = actual >= high
    return replace(
        target,
        residue=actual,
        correctable=(
            not target.main_input_overload_low
            and not target.main_input_overload_high
            and not overload_low
            and not overload_high
        ),
        overload_low=overload_low,
        overload_high=overload_high,
        applied_nonideality_order=(
            *target.applied_nonideality_order,
            "finite_settling",
        ),
    )


def process(
    value: float,
    config: StaticPipelineConfig,
    settling: FiniteSettlingConfig,
    state: SettlingState,
    *,
    sample_index: int = 0,
    dither_symbols: tuple[Hashable | None, Hashable | None] = (None, None),
    nonidealities: StaticPipelineNonidealities | None = None,
) -> FiniteSettlingResult:
    """Advance the dynamic reference platform by exactly one input sample."""

    applied = nonidealities or StaticPipelineNonidealities()
    stage1_auxiliary = (
        config.auxiliary_gain_ratios[0] * value + config.auxiliary_offsets[0]
    )
    stage1_target = process_stage(
        value,
        stage1_auxiliary,
        dither_symbols[0],
        config.stage1,
        nonidealities=applied.stage1,
    )
    stage1 = _settled_stage(
        stage1_target,
        state.stage1_residue,
        settling.residual_factors[0],
        config.stage1.next_stage_range,
    )

    stage2_auxiliary = (
        config.auxiliary_gain_ratios[1] * stage1.residue
        + config.auxiliary_offsets[1]
    )
    stage2_target = process_stage(
        stage1.residue,
        stage2_auxiliary,
        dither_symbols[1],
        config.stage2,
        nonidealities=applied.stage2,
    )
    stage2 = _settled_stage(
        stage2_target,
        state.stage2_residue,
        settling.residual_factors[1],
        config.stage2.next_stage_range,
    )
    backend = convert_sar(
        stage2.residue,
        config.backend,
        sample_index=sample_index,
    )
    digital = reconstruct((stage1, stage2), backend, config.reconstruction)
    pipeline = PipelineResult(
        sample_index=sample_index,
        input_value=value,
        stage1=stage1,
        stage2=stage2,
        backend=backend,
        reconstruction=digital,
    )
    return FiniteSettlingResult(
        pipeline=pipeline,
        stage1_target_residue=stage1_target.residue,
        stage2_target_residue=stage2_target.residue,
        prior_state=state,
        next_state=SettlingState(stage1.residue, stage2.residue),
    )
