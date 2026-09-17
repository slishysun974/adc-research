"""Sample-wise candidate with independent stage-1 main and auxiliary outputs.

Both outputs observe the same stage-1 CDAC summing node.  The auxiliary static
target is a linear transfer of that node, independent of any synthetic PWL
nonlinearity selected for the main amplifier.  Each output can retain a
different fraction of its previous-output error.  This is a discriminating
behavioral hypothesis, not a claim about the silicon's reset or timing.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Hashable

from adc_research.platform.backend_sar import convert as convert_sar
from adc_research.platform.finite_settling import _settled_stage
from adc_research.platform.pipeline import (
    PipelineResult,
    StaticPipelineConfig,
    StaticPipelineNonidealities,
)
from adc_research.platform.reconstruct import reconstruct
from adc_research.platform.stage import process as process_stage


@dataclass(frozen=True)
class DualPathSettlingState:
    stage1_main: float = 0.0
    stage1_auxiliary: float = 0.0
    stage2_main: float = 0.0

    def __post_init__(self) -> None:
        if any(not isfinite(value) for value in self.as_tuple()):
            raise ValueError("dual-path settling state must be finite")

    def as_tuple(self) -> tuple[float, float, float]:
        return (self.stage1_main, self.stage1_auxiliary, self.stage2_main)


@dataclass(frozen=True)
class DualPathSettlingConfig:
    """Remaining previous-output error fractions for three analog outputs."""

    stage1_main_factor: float
    stage1_auxiliary_factor: float
    stage2_main_factor: float

    def __post_init__(self) -> None:
        if any(
            not isfinite(value) or value < 0 or value >= 1
            for value in self.as_tuple()
        ):
            raise ValueError("dual-path settling factors must lie in [0,1)")

    def as_tuple(self) -> tuple[float, float, float]:
        return (
            self.stage1_main_factor,
            self.stage1_auxiliary_factor,
            self.stage2_main_factor,
        )


@dataclass(frozen=True)
class DualPathSettlingResult:
    pipeline: PipelineResult
    stage1_main_target: float
    stage1_auxiliary_target: float
    stage1_auxiliary_output: float
    stage2_main_target: float
    prior_state: DualPathSettlingState
    next_state: DualPathSettlingState


def process(
    value: float,
    config: StaticPipelineConfig,
    settling: DualPathSettlingConfig,
    state: DualPathSettlingState,
    *,
    sample_index: int = 0,
    dither_symbols: tuple[Hashable | None, Hashable | None] = (None, None),
    nonidealities: StaticPipelineNonidealities | None = None,
) -> DualPathSettlingResult:
    """Advance one sample through the three-output candidate model."""

    applied = nonidealities or StaticPipelineNonidealities()
    stage1_flash_input = (
        config.auxiliary_gain_ratios[0] * value + config.auxiliary_offsets[0]
    )
    stage1_target = process_stage(
        value,
        stage1_flash_input,
        dither_symbols[0],
        config.stage1,
        nonidealities=applied.stage1,
    )
    stage1_main = _settled_stage(
        stage1_target,
        state.stage1_main,
        settling.stage1_main_factor,
        config.stage1.next_stage_range,
    )

    main_linear_gain = (
        applied.stage1.actual_interstage_gain
        if applied.stage1.actual_interstage_gain is not None
        else config.stage1.nominal_interstage_gain
    )
    auxiliary_target = (
        config.auxiliary_gain_ratios[1]
        * main_linear_gain
        * stage1_target.residue_preamp
        + config.auxiliary_offsets[1]
    )
    auxiliary_output = (
        (1.0 - settling.stage1_auxiliary_factor) * auxiliary_target
        + settling.stage1_auxiliary_factor * state.stage1_auxiliary
    )

    stage2_target = process_stage(
        stage1_main.residue,
        auxiliary_output,
        dither_symbols[1],
        config.stage2,
        nonidealities=applied.stage2,
    )
    stage2_main = _settled_stage(
        stage2_target,
        state.stage2_main,
        settling.stage2_main_factor,
        config.stage2.next_stage_range,
    )
    backend = convert_sar(
        stage2_main.residue,
        config.backend,
        sample_index=sample_index,
    )
    digital = reconstruct(
        (stage1_main, stage2_main), backend, config.reconstruction
    )
    pipeline = PipelineResult(
        sample_index=sample_index,
        input_value=value,
        stage1=stage1_main,
        stage2=stage2_main,
        backend=backend,
        reconstruction=digital,
    )
    return DualPathSettlingResult(
        pipeline=pipeline,
        stage1_main_target=stage1_target.residue,
        stage1_auxiliary_target=auxiliary_target,
        stage1_auxiliary_output=auxiliary_output,
        stage2_main_target=stage2_target.residue,
        prior_state=state,
        next_state=DualPathSettlingState(
            stage1_main.residue,
            auxiliary_output,
            stage2_main.residue,
        ),
    )
