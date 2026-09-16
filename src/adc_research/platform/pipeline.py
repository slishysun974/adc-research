"""Static three-stage ADC with an affine proxy for the auxiliary amplifier.

The stage-2 flash observes a scaled/offset copy of the stage-1 main
residue.  This preserves the paper's decision/CDAC topology but does not model
an independently nonlinear or dynamically settling stage-1 auxiliary output.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Hashable

from adc_research.platform.backend_sar import (
    SarConfig,
    SarResult,
    convert as convert_sar,
)
from adc_research.platform.reconstruct import (
    ReconstructionConfig,
    ReconstructionResult,
    reconstruct,
)
from adc_research.platform.stage import (
    StaticStageConfig,
    StaticStageNonidealities,
    StageResult,
    process as process_stage,
)


@dataclass(frozen=True)
class StaticPipelineConfig:
    stage1: StaticStageConfig
    stage2: StaticStageConfig
    backend: SarConfig
    reconstruction: ReconstructionConfig
    auxiliary_gain_ratios: tuple[float, float] = (1.0, 1.0)
    auxiliary_offsets: tuple[float, float] = (0.0, 0.0)

    def __post_init__(self) -> None:
        if len(self.reconstruction.front_stage_weights) != 2:
            raise ValueError("a three-stage pipeline requires two front-stage weights")
        if any(ratio <= 0 or not isfinite(ratio) for ratio in self.auxiliary_gain_ratios):
            raise ValueError("auxiliary gain ratios must be finite and positive")
        if any(not isfinite(offset) for offset in self.auxiliary_offsets):
            raise ValueError("auxiliary offsets must be finite")


@dataclass(frozen=True)
class StaticPipelineNonidealities:
    """Per-stage static effects, disabled by default and independent of config."""

    stage1: StaticStageNonidealities = field(default_factory=StaticStageNonidealities)
    stage2: StaticStageNonidealities = field(default_factory=StaticStageNonidealities)


@dataclass(frozen=True)
class PipelineResult:
    sample_index: int
    input_value: float
    stage1: StageResult
    stage2: StageResult
    backend: SarResult
    reconstruction: ReconstructionResult


def process(
    value: float,
    config: StaticPipelineConfig,
    *,
    sample_index: int = 0,
    dither_symbols: tuple[Hashable | None, Hashable | None] = (None, None),
    nonidealities: StaticPipelineNonidealities | None = None,
) -> PipelineResult:
    """Process one sample and retain every Gate-C intermediate quantity."""

    applied = nonidealities or StaticPipelineNonidealities()
    stage1_auxiliary = (
        config.auxiliary_gain_ratios[0] * value + config.auxiliary_offsets[0]
    )
    stage1 = process_stage(
        value,
        stage1_auxiliary,
        dither_symbols[0],
        config.stage1,
        nonidealities=applied.stage1,
    )

    stage2_auxiliary = (
        config.auxiliary_gain_ratios[1] * stage1.residue
        + config.auxiliary_offsets[1]
    )
    stage2 = process_stage(
        stage1.residue,
        stage2_auxiliary,
        dither_symbols[1],
        config.stage2,
        nonidealities=applied.stage2,
    )
    backend = convert_sar(
        stage2.residue,
        config.backend,
        sample_index=sample_index,
    )
    digital = reconstruct((stage1, stage2), backend, config.reconstruction)
    return PipelineResult(
        sample_index=sample_index,
        input_value=value,
        stage1=stage1,
        stage2=stage2,
        backend=backend,
        reconstruction=digital,
    )
