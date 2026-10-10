"""Gu candidate's digital geometry, built without analog gain truth."""

from __future__ import annotations

from typing import Mapping

from adc_research.calibration.pwl import PwlConfig, slice_width_from_unsigned_bits
from adc_research.calibration.two_stage import TwoStagePwlCalibrationConfig
from adc_research.platform.pipeline import StaticPipelineConfig


def build_gu_two_stage_baseline(
    pipeline: StaticPipelineConfig,
    pwl_implications: Mapping[str, object],
) -> TwoStagePwlCalibrationConfig:
    """Use the declared digital bits, not a simulated amplifier's PWL edges.

    This is the *behavioral candidate* geometry, not proof of unpublished
    on-chip bit widths or a claim about the analog transfer's shape.
    """

    count = 4
    width1 = slice_width_from_unsigned_bits(
        int(pwl_implications["stage1_positive_magnitude_bits"]),
        slice_count=count,
    )
    width2 = slice_width_from_unsigned_bits(
        int(pwl_implications["stage2_positive_magnitude_bits"]),
        slice_count=count,
    )
    if width1 != int(pwl_implications["stage1_four_slice_b0"]):
        raise ValueError("stage-1 PWL bit geometry disagrees with declared b0")
    if width2 != int(pwl_implications["stage2_four_slice_b0"]):
        raise ValueError("stage-2 PWL bit geometry disagrees with declared b0")

    reconstruction = pipeline.reconstruction
    if not reconstruction.dither_code_copies:
        raise ValueError("two-stage calibration needs configured dither copies")
    stage1_weight, stage2_weight = reconstruction.front_stage_weights
    backend_raw_full_scale = (
        pipeline.backend.code_count * reconstruction.backend_weight / 2
    )
    if count * width1 != stage1_weight or count * width2 != backend_raw_full_scale:
        raise ValueError("digital PWL domain disagrees with reconstruction weights")

    return TwoStagePwlCalibrationConfig(
        stage1_pwl=PwlConfig(width1, (1.0,) * count),
        stage2_pwl=PwlConfig(width2, (1.0,) * count),
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
