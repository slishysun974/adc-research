"""Oracle PWL coefficients and the two-stage Gu correction cascade.

This module is for representation tests only.  It derives exact floating-point
inverse coefficients from a platform truth and therefore does not model LMS
coefficient extraction, convergence, fixed-point rounding, or silicon logic.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite
from typing import Hashable, Mapping

from adc_research.calibration.pwl import PwlConfig, PwlResult, correct
from adc_research.platform.amplifier import StaticPwlTruthConfig
from adc_research.platform.pipeline import (
    PipelineResult,
    StaticPipelineConfig,
    StaticPipelineNonidealities,
)


def oracle_pwl_config(
    truth: StaticPwlTruthConfig,
    *,
    raw_code_full_scale: float,
    corrected_code_full_scale: float | None = None,
) -> PwlConfig:
    """Derive the digital inverse of a uniformly output-sliced PWL truth.

    Gu's correction selects slices with the most-significant bits of the *raw*
    code, so the distorted-output edges must be equally spaced.  The ideal
    edges may be nonuniform; their widths determine the oracle slopes.
    """

    if raw_code_full_scale <= 0 or not isfinite(raw_code_full_scale):
        raise ValueError("raw_code_full_scale must be finite and positive")
    corrected_full_scale = (
        raw_code_full_scale
        if corrected_code_full_scale is None
        else corrected_code_full_scale
    )
    if corrected_full_scale <= 0 or not isfinite(corrected_full_scale):
        raise ValueError("corrected_code_full_scale must be finite and positive")

    distorted_edges = truth.distorted_output_edges
    ideal_edges = truth.ideal_output_edges
    distorted_widths = tuple(
        right - left for left, right in zip(distorted_edges, distorted_edges[1:])
    )
    reference_width = distorted_widths[0]
    if any(
        not isclose(width, reference_width, rel_tol=1e-12, abs_tol=1e-15)
        for width in distorted_widths[1:]
    ):
        raise ValueError(
            "Gu oracle requires uniformly spaced distorted-output slices"
        )

    raw_scale = raw_code_full_scale / distorted_edges[-1]
    corrected_scale = corrected_full_scale / ideal_edges[-1]
    slice_width = reference_width * raw_scale
    slopes = tuple(
        ((ideal_right - ideal_left) * corrected_scale)
        / ((distorted_right - distorted_left) * raw_scale)
        for ideal_left, ideal_right, distorted_left, distorted_right in zip(
            ideal_edges[:-1],
            ideal_edges[1:],
            distorted_edges[:-1],
            distorted_edges[1:],
            strict=True,
        )
    )
    return PwlConfig(slice_width=slice_width, slopes=slopes)


@dataclass(frozen=True)
class TwoStagePwlCalibrationConfig:
    stage1_pwl: PwlConfig
    stage2_pwl: PwlConfig
    stage1_symbol_weight: float
    stage2_symbol_weight: float
    backend_weight: float
    output_offset: float
    output_range: tuple[float, float]
    dither_code_copies: tuple[Mapping[Hashable, float], Mapping[Hashable, float]]

    def __post_init__(self) -> None:
        if any(
            not isfinite(value) or value <= 0
            for value in (
                self.stage1_symbol_weight,
                self.stage2_symbol_weight,
                self.backend_weight,
            )
        ):
            raise ValueError("cascade weights must be finite and positive")
        low, high = self.output_range
        if not (isfinite(low) and isfinite(high)) or high < low:
            raise ValueError("output_range must be finite and increasing")


@dataclass(frozen=True)
class TwoStagePwlCalibrationResult:
    stage2_raw_backend_code: float
    stage2_pwl: PwlResult
    stage2_dither_copy: float
    stage1_raw_code_before_dither_subtraction: float
    stage1_raw_code: float
    stage1_pwl: PwlResult
    stage1_dither_copy: float
    corrected_centered_code: float
    unclipped_output_code: float
    output_code: float
    saturated_low: bool
    saturated_high: bool
    correctable: bool


def build_two_stage_oracle(
    pipeline_config: StaticPipelineConfig,
    nonidealities: StaticPipelineNonidealities,
) -> TwoStagePwlCalibrationConfig:
    """Build oracle inverse coefficients from both configured stage truths."""

    truth1 = nonidealities.stage1.pwl_truth
    truth2 = nonidealities.stage2.pwl_truth
    if truth1 is None or truth2 is None:
        raise ValueError("both pipeline stages must provide PWL truth")

    reconstruction = pipeline_config.reconstruction
    if not reconstruction.dither_code_copies:
        raise ValueError("two-stage oracle requires configured dither code copies")
    stage1_weight, stage2_weight = reconstruction.front_stage_weights
    backend_raw_full_scale = (
        pipeline_config.backend.code_count
        * reconstruction.backend_weight
        / 2
    )
    return TwoStagePwlCalibrationConfig(
        stage1_pwl=oracle_pwl_config(
            truth1,
            raw_code_full_scale=stage1_weight,
        ),
        stage2_pwl=oracle_pwl_config(
            truth2,
            raw_code_full_scale=backend_raw_full_scale,
        ),
        stage1_symbol_weight=stage1_weight,
        stage2_symbol_weight=stage2_weight,
        backend_weight=reconstruction.backend_weight,
        output_offset=reconstruction.output_offset,
        output_range=reconstruction.output_range,
        dither_code_copies=(
            reconstruction.dither_code_copies[0],
            reconstruction.dither_code_copies[1],
        ),
    )


def _dither_copy(
    symbol: Hashable | None,
    mapping: Mapping[Hashable, float],
    *,
    stage_number: int,
) -> float:
    if symbol is None:
        return 0.0
    if symbol not in mapping:
        raise KeyError(
            f"stage {stage_number} dither symbol has no digital copy: {symbol!r}"
        )
    return mapping[symbol]


def correct_two_stage(
    raw: PipelineResult,
    config: TwoStagePwlCalibrationConfig,
) -> TwoStagePwlCalibrationResult:
    """Correct stage 2 first, then stage 1, with local dither subtraction.

    The stage-2 dither copy is removed before the reconstructed first-stage
    residue code enters the stage-1 PWL block.  The stage-1 dither copy is
    removed only after stage-1 PWL correction.
    """

    stage2_raw = config.backend_weight * raw.backend.centered_code
    stage2_pwl = correct(stage2_raw, config.stage2_pwl)
    dither2 = _dither_copy(
        raw.stage2.cdac.dither_symbol,
        config.dither_code_copies[1],
        stage_number=2,
    )
    stage1_before_dither = (
        config.stage2_symbol_weight * raw.stage2.quantizer.symbol
        + stage2_pwl.corrected_code
    )
    stage1_raw = stage1_before_dither - dither2
    stage1_pwl = correct(stage1_raw, config.stage1_pwl)

    dither1 = _dither_copy(
        raw.stage1.cdac.dither_symbol,
        config.dither_code_copies[0],
        stage_number=1,
    )
    centered = (
        config.stage1_symbol_weight * raw.stage1.quantizer.symbol
        + stage1_pwl.corrected_code
        - dither1
    )
    unclipped = centered + config.output_offset
    low, high = config.output_range
    saturated_low = unclipped < low
    saturated_high = unclipped > high
    output = min(max(unclipped, low), high)

    path_overload = any(
        not stage.correctable
        or stage.main_input_overload_low
        or stage.main_input_overload_high
        for stage in (raw.stage1, raw.stage2)
    ) or raw.backend.overload_low or raw.backend.overload_high
    return TwoStagePwlCalibrationResult(
        stage2_raw_backend_code=stage2_raw,
        stage2_pwl=stage2_pwl,
        stage2_dither_copy=dither2,
        stage1_raw_code_before_dither_subtraction=stage1_before_dither,
        stage1_raw_code=stage1_raw,
        stage1_pwl=stage1_pwl,
        stage1_dither_copy=dither1,
        corrected_centered_code=centered,
        unclipped_output_code=unclipped,
        output_code=output,
        saturated_low=saturated_low,
        saturated_high=saturated_high,
        correctable=not (path_overload or saturated_low or saturated_high),
    )
