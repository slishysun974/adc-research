"""Offline reference coefficients derived from a known synthetic PWL truth."""

from __future__ import annotations

from math import isclose, isfinite

from adc_research.calibration.pwl import PwlConfig
from adc_research.calibration.two_stage import TwoStagePwlCalibrationConfig
from adc_research.platform.amplifier import StaticPwlTruthConfig
from adc_research.platform.pipeline import StaticPipelineConfig, StaticPipelineNonidealities


def oracle_pwl_config(
    truth: StaticPwlTruthConfig,
    *,
    raw_code_full_scale: float,
    corrected_code_full_scale: float | None = None,
) -> PwlConfig:
    """Derive a digital inverse for a uniformly output-sliced *test* truth."""

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
        raise ValueError("Gu oracle requires uniformly spaced distorted-output slices")

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


def build_two_stage_oracle(
    pipeline_config: StaticPipelineConfig,
    nonidealities: StaticPipelineNonidealities,
) -> TwoStagePwlCalibrationConfig:
    """Build an offline reference from both configured analog test truths."""

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
