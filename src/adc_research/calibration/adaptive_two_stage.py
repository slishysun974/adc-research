"""Two-stage adaptive PWL correction with explicit local LMS observations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from adc_research.calibration.gated_lms import (
    GatedLmsBlockUpdate,
    GatedLmsConfig,
    GatedLmsState,
    GatedLmsUpdate,
    update,
    update_block_mean,
)
from adc_research.calibration.known_truth import (
    TwoStagePwlCalibrationConfig,
    TwoStagePwlCalibrationResult,
    correct_two_stage,
)
from adc_research.calibration.pwl import PwlConfig
from adc_research.platform.pipeline import PipelineResult


@dataclass(frozen=True)
class TwoStageAdaptiveState:
    stage1: GatedLmsState
    stage2: GatedLmsState


@dataclass(frozen=True)
class TwoStageAdaptiveConfig:
    cascade: TwoStagePwlCalibrationConfig
    stage1_lms: GatedLmsConfig
    stage2_lms: GatedLmsConfig

    def __post_init__(self) -> None:
        if self.stage1_lms.slice_width != self.cascade.stage1_pwl.slice_width:
            raise ValueError("stage-1 LMS and PWL slice widths must match")
        if self.stage2_lms.slice_width != self.cascade.stage2_pwl.slice_width:
            raise ValueError("stage-2 LMS and PWL slice widths must match")
        if (
            self.stage1_lms.coefficient_count
            != self.cascade.stage1_pwl.slice_count
        ):
            raise ValueError("stage-1 LMS and PWL slice counts must match")
        if (
            self.stage2_lms.coefficient_count
            != self.cascade.stage2_pwl.slice_count
        ):
            raise ValueError("stage-2 LMS and PWL slice counts must match")


@dataclass(frozen=True)
class TwoStageAdaptiveResult:
    calibration: TwoStagePwlCalibrationResult
    stage1_local_learning_output: float
    stage2_local_learning_output: float
    stage1_update: GatedLmsUpdate
    stage2_update: GatedLmsUpdate
    state: TwoStageAdaptiveState


@dataclass(frozen=True)
class TwoStageAdaptiveObservation:
    """Two local learning observations formed without changing coefficients."""

    calibration: TwoStagePwlCalibrationResult
    stage1_local_learning_output: float
    stage2_local_learning_output: float


@dataclass(frozen=True)
class TwoStageAdaptiveBlockUpdate:
    """One simultaneous block-mean update of the two coefficient banks."""

    stage1_update: GatedLmsBlockUpdate
    stage2_update: GatedLmsBlockUpdate
    state: TwoStageAdaptiveState


def cascade_from_state(
    config: TwoStagePwlCalibrationConfig,
    state: TwoStageAdaptiveState,
) -> TwoStagePwlCalibrationConfig:
    return TwoStagePwlCalibrationConfig(
        stage1_pwl=PwlConfig(
            config.stage1_pwl.slice_width,
            state.stage1.coefficients,
            config.stage1_pwl.negative_full_scale_policy,
        ),
        stage2_pwl=PwlConfig(
            config.stage2_pwl.slice_width,
            state.stage2.coefficients,
            config.stage2_pwl.negative_full_scale_policy,
        ),
        stage1_symbol_weight=config.stage1_symbol_weight,
        stage2_symbol_weight=config.stage2_symbol_weight,
        backend_weight=config.backend_weight,
        output_offset=config.output_offset,
        output_range=config.output_range,
        dither_code_copies=config.dither_code_copies,
    )


def correct_and_update(
    raw: PipelineResult,
    state: TwoStageAdaptiveState,
    config: TwoStageAdaptiveConfig,
) -> TwoStageAdaptiveResult:
    """Correct stage 2 then stage 1 and update both local coefficient banks.

    The learning observation for each bank excludes its coarse-stage symbol.
    This keeps the adaptive thresholds in the same local residue-code domain as
    that bank's PWL selector.  Both banks use the coefficients that corrected
    the current sample; their updates become visible on the next sample.
    """

    observation = observe(raw, state, config)
    calibration = observation.calibration
    dither1 = calibration.stage1_dither_copy
    dither2 = calibration.stage2_dither_copy
    stage1_local = observation.stage1_local_learning_output
    stage2_local = observation.stage2_local_learning_output
    update2 = update(
        state.stage2,
        dither_code=dither2,
        corrected_output=stage2_local,
        config=config.stage2_lms,
    )
    update1 = update(
        state.stage1,
        dither_code=dither1,
        corrected_output=stage1_local,
        config=config.stage1_lms,
    )
    next_state = TwoStageAdaptiveState(
        stage1=update1.state,
        stage2=update2.state,
    )
    return TwoStageAdaptiveResult(
        calibration=calibration,
        stage1_local_learning_output=stage1_local,
        stage2_local_learning_output=stage2_local,
        stage1_update=update1,
        stage2_update=update2,
        state=next_state,
    )


def observe(
    raw: PipelineResult,
    state: TwoStageAdaptiveState,
    config: TwoStageAdaptiveConfig,
) -> TwoStageAdaptiveObservation:
    """Form both local LMS observations without updating either bank."""

    dynamic = cascade_from_state(config.cascade, state)
    calibration = correct_two_stage(raw, dynamic)
    dither1 = calibration.stage1_dither_copy
    dither2 = calibration.stage2_dither_copy
    if dither1 == 0 or dither2 == 0:
        raise ValueError("two-stage adaptive observation requires both nonzero dithers")
    return TwoStageAdaptiveObservation(
        calibration=calibration,
        stage1_local_learning_output=(
            calibration.stage1_pwl.corrected_code - dither1
        ),
        stage2_local_learning_output=(
            calibration.stage2_pwl.corrected_code - dither2
        ),
    )


def update_block_mean_observations(
    state: TwoStageAdaptiveState,
    observations: Sequence[TwoStageAdaptiveObservation],
    config: TwoStageAdaptiveConfig,
) -> TwoStageAdaptiveBlockUpdate:
    """Update both banks from a block formed at one fixed coefficient state."""

    values = tuple(observations)
    if not values:
        raise ValueError("two-stage block update requires observations")
    stage1 = update_block_mean(
        state.stage1,
        observations=tuple(
            (
                value.calibration.stage1_dither_copy,
                value.stage1_local_learning_output,
            )
            for value in values
        ),
        config=config.stage1_lms,
    )
    stage2 = update_block_mean(
        state.stage2,
        observations=tuple(
            (
                value.calibration.stage2_dither_copy,
                value.stage2_local_learning_output,
            )
            for value in values
        ),
        config=config.stage2_lms,
    )
    next_state = TwoStageAdaptiveState(stage1=stage1.state, stage2=stage2.state)
    return TwoStageAdaptiveBlockUpdate(
        stage1_update=stage1,
        stage2_update=stage2,
        state=next_state,
    )
