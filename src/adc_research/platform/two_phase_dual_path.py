"""Offline two-phase main/auxiliary candidate with independent static truth.

Tracking and amplification maps are explicit hypotheses. They do not infer
the chip's reset state from its reported bandwidth or settling accuracy.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import Hashable

from adc_research.platform.amplifier import StaticCubicTruthConfig, amplify_static_cubic_truth
from adc_research.platform.backend_sar import convert as convert_sar
from adc_research.platform.dual_path_settling import DualPathSettlingState
from adc_research.platform.pipeline import PipelineResult, StaticPipelineConfig, StaticPipelineNonidealities
from adc_research.platform.reconstruct import reconstruct
from adc_research.platform.stage import process as process_stage


@dataclass(frozen=True)
class TwoPhasePath:
    amplification_factor: float
    tracking_factor: float
    tracking_target: float = 0.0

    def __post_init__(self) -> None:
        if (not isfinite(self.amplification_factor) or not 0 <= self.amplification_factor < 1 or
            not isfinite(self.tracking_factor) or not 0 <= self.tracking_factor <= 1 or
            not isfinite(self.tracking_target)):
            raise ValueError("two-phase factors and tracking target are invalid")

    @property
    def memory_factor(self) -> float:
        return self.amplification_factor*self.tracking_factor

    def advance(self, previous: float, target: float) -> tuple[float, float]:
        if not isfinite(previous) or not isfinite(target):
            raise ValueError("two-phase state and target must be finite")
        start = self.tracking_target+self.tracking_factor*(previous-self.tracking_target)
        return start, target+self.amplification_factor*(start-target)


@dataclass(frozen=True)
class TwoPhaseDualPathConfig:
    stage1_main: TwoPhasePath
    stage1_auxiliary: TwoPhasePath
    stage2_main: TwoPhasePath
    auxiliary_gain: float = 4.0
    auxiliary_truth: StaticCubicTruthConfig = StaticCubicTruthConfig(1.0, 0.0)

    def __post_init__(self) -> None:
        if not isfinite(self.auxiliary_gain) or self.auxiliary_gain <= 0:
            raise ValueError("auxiliary gain must be positive and finite")


@dataclass(frozen=True)
class TwoPhaseDualPathResult:
    pipeline: PipelineResult
    tracking_starts: tuple[float, float, float]
    static_targets: tuple[float, float, float]
    auxiliary_output: float
    next_state: DualPathSettlingState


def _replace_residue(target, value, domain):
    low, high = domain
    return replace(target, residue=value, overload_low=value < low, overload_high=value >= high,
                   correctable=(not target.main_input_overload_low and
                                not target.main_input_overload_high and low <= value < high),
                   applied_nonideality_order=(*target.applied_nonideality_order, "two_phase_settling"))


def process(value: float, config: StaticPipelineConfig, phases: TwoPhaseDualPathConfig,
            state: DualPathSettlingState, *, sample_index: int = 0,
            dither_symbols: tuple[Hashable | None, Hashable | None] = (None, None),
            nonidealities: StaticPipelineNonidealities | None = None) -> TwoPhaseDualPathResult:
    applied = nonidealities or StaticPipelineNonidealities()
    stage1 = process_stage(value, config.auxiliary_gain_ratios[0]*value+config.auxiliary_offsets[0],
                           dither_symbols[0], config.stage1, nonidealities=applied.stage1)
    start1, main1 = phases.stage1_main.advance(state.stage1_main, stage1.residue)
    stage1_actual = _replace_residue(stage1, main1, config.stage1.next_stage_range)
    auxiliary_target = amplify_static_cubic_truth(
        stage1.residue_preamp, nominal_gain=config.stage1.nominal_interstage_gain,
        actual_gain=phases.auxiliary_gain, truth=phases.auxiliary_truth,
    ).output_value
    start_aux, auxiliary = phases.stage1_auxiliary.advance(state.stage1_auxiliary, auxiliary_target)
    stage2 = process_stage(main1, auxiliary, dither_symbols[1], config.stage2,
                           nonidealities=applied.stage2)
    start2, main2 = phases.stage2_main.advance(state.stage2_main, stage2.residue)
    stage2_actual = _replace_residue(stage2, main2, config.stage2.next_stage_range)
    backend = convert_sar(main2, config.backend, sample_index=sample_index)
    digital = reconstruct((stage1_actual, stage2_actual), backend, config.reconstruction)
    return TwoPhaseDualPathResult(
        PipelineResult(sample_index, value, stage1_actual, stage2_actual, backend, digital),
        (start1, start_aux, start2), (stage1.residue, auxiliary_target, stage2.residue),
        auxiliary, DualPathSettlingState(main1, auxiliary, main2),
    )
