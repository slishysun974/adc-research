"""Two-stage fixed-point PWL correction with gated-LMS coefficient updates."""

from __future__ import annotations

from dataclasses import dataclass, replace

from adc_research.calibration.fixed_gated_lms import (
    FixedGatedLmsConfig,
    FixedGatedLmsState,
    FixedGatedLmsUpdate,
    exported_coefficient_codes,
    update_fixed,
)
from adc_research.calibration.fixed_pwl import (
    FixedTwoStageConfig,
    FixedTwoStageResult,
    correct_two_stage_fixed,
)
from adc_research.platform.pipeline import PipelineResult


@dataclass(frozen=True)
class FixedTwoStageAdaptiveState:
    stage1: FixedGatedLmsState
    stage2: FixedGatedLmsState


@dataclass(frozen=True)
class FixedTwoStageAdaptiveConfig:
    cascade: FixedTwoStageConfig
    stage1_lms: FixedGatedLmsConfig
    stage2_lms: FixedGatedLmsConfig

    def __post_init__(self) -> None:
        for stage_name, pwl, lms in (
            ("stage 1", self.cascade.stage1_pwl, self.stage1_lms),
            ("stage 2", self.cascade.stage2_pwl, self.stage2_lms),
        ):
            if lms.slice_width_scaled != pwl.slice_width_scaled:
                raise ValueError(f"{stage_name} LMS and PWL slice widths must match")
            if lms.coefficient_count != pwl.slice_count:
                raise ValueError(f"{stage_name} LMS and PWL slice counts must match")
            if lms.coefficient_format != pwl.arithmetic.coefficient_format:
                raise ValueError(
                    f"{stage_name} LMS and PWL coefficient formats must match"
                )
            if lms.data_fractional_bits != self.cascade.data_fractional_bits:
                raise ValueError(
                    f"{stage_name} LMS and cascade data formats must match"
                )


@dataclass(frozen=True)
class FixedTwoStageAdaptiveResult:
    calibration: FixedTwoStageResult
    stage1_local_learning_output_scaled: int
    stage2_local_learning_output_scaled: int
    stage1_update: FixedGatedLmsUpdate
    stage2_update: FixedGatedLmsUpdate
    state: FixedTwoStageAdaptiveState


def cascade_from_fixed_state(
    config: FixedTwoStageConfig,
    state: FixedTwoStageAdaptiveState,
    stage1_lms: FixedGatedLmsConfig,
    stage2_lms: FixedGatedLmsConfig,
) -> FixedTwoStageConfig:
    """Replace the Q1.10 coefficient interfaces with the current state."""

    return replace(
        config,
        stage1_pwl=replace(
            config.stage1_pwl,
            coefficient_codes=exported_coefficient_codes(state.stage1, stage1_lms),
            coefficient_saturations=(False,) * stage1_lms.coefficient_count,
        ),
        stage2_pwl=replace(
            config.stage2_pwl,
            coefficient_codes=exported_coefficient_codes(state.stage2, stage2_lms),
            coefficient_saturations=(False,) * stage2_lms.coefficient_count,
        ),
    )


def correct_and_update_fixed(
    raw: PipelineResult,
    state: FixedTwoStageAdaptiveState,
    config: FixedTwoStageAdaptiveConfig,
) -> FixedTwoStageAdaptiveResult:
    """Correct one sample, then update both coefficient accumulators."""

    dynamic = cascade_from_fixed_state(
        config.cascade,
        state,
        config.stage1_lms,
        config.stage2_lms,
    )
    calibration = correct_two_stage_fixed(raw, dynamic)
    dither1 = calibration.stage1_dither_scaled
    dither2 = calibration.stage2_dither_scaled
    if dither1 == 0 or dither2 == 0:
        raise ValueError("two-stage adaptive update requires both nonzero dithers")
    stage1_local = calibration.stage1_pwl.corrected_code_scaled - dither1
    stage2_local = calibration.stage2_pwl.corrected_code_scaled - dither2
    stage1_update = update_fixed(
        state.stage1,
        dither_code_scaled=dither1,
        corrected_output_scaled=stage1_local,
        config=config.stage1_lms,
    )
    stage2_update = update_fixed(
        state.stage2,
        dither_code_scaled=dither2,
        corrected_output_scaled=stage2_local,
        config=config.stage2_lms,
    )
    next_state = FixedTwoStageAdaptiveState(
        stage1=stage1_update.state,
        stage2=stage2_update.state,
    )
    return FixedTwoStageAdaptiveResult(
        calibration=calibration,
        stage1_local_learning_output_scaled=stage1_local,
        stage2_local_learning_output_scaled=stage2_local,
        stage1_update=stage1_update,
        stage2_update=stage2_update,
        state=next_state,
    )
