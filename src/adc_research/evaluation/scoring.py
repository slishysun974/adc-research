"""Offline correction wrappers with physical-overload scoring."""

from dataclasses import replace

from adc_research.calibration.fixed_pwl import (
    FixedTwoStageConfig,
    FixedTwoStageResult,
    correct_two_stage_fixed_observed,
)
from adc_research.calibration.two_stage import (
    TwoStagePwlCalibrationConfig,
    TwoStagePwlCalibrationResult,
    correct_two_stage_observed,
)
from adc_research.evaluation.observations import digital_sample
from adc_research.platform.pipeline import PipelineResult


def _physical_overload(raw: PipelineResult) -> bool:
    return any(
        not stage.correctable
        or stage.main_input_overload_low
        or stage.main_input_overload_high
        for stage in (raw.stage1, raw.stage2)
    ) or raw.backend.overload_low or raw.backend.overload_high


def correct_two_stage(
    raw: PipelineResult,
    config: TwoStagePwlCalibrationConfig,
) -> TwoStagePwlCalibrationResult:
    """Score floating correction with hidden platform overload information."""

    result = correct_two_stage_observed(digital_sample(raw), config)
    return replace(result, correctable=result.correctable and not _physical_overload(raw))


def correct_two_stage_fixed(
    raw: PipelineResult,
    config: FixedTwoStageConfig,
) -> FixedTwoStageResult:
    """Score fixed-point correction with hidden platform overload information."""

    result = correct_two_stage_fixed_observed(digital_sample(raw), config)
    return replace(result, correctable=result.correctable and not _physical_overload(raw))
