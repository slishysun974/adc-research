"""Offline Gu integer-code bounds from a static digital observation set."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable

from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.calibration.two_stage import (
    TwoStagePwlCalibrationConfig,
    correct_two_stage_observed,
)
from adc_research.theory.static_observation_reachability import StaticObservationEnvelope


@dataclass(frozen=True)
class FullChainCodeEnvelope:
    lower_output_code: int
    upper_output_code: int
    observation_count: int
    digital_clipping_possible: bool
    physical_overload_possible: bool


def bound_static_gu_codes(
    observations: StaticObservationEnvelope,
    calibration: TwoStagePwlCalibrationConfig,
    *,
    stage1_dither_symbol: Hashable | None,
    stage2_dither_symbol: Hashable | None,
) -> FullChainCodeEnvelope:
    """Score every possible candidate observation with frozen Gu coefficients."""
    output_low, output_high = calibration.output_range
    if not (float(output_low).is_integer() and float(output_high).is_integer()):
        raise ValueError("integer output-code rule requires integer bounds")
    if not observations.outcomes:
        raise ValueError("observation envelope must not be empty")
    codes: list[int] = []
    digital_clipping = False
    for outcome in observations.outcomes:
        observed = DigitalCalibrationSample(
            outcome.stage1_symbol,
            outcome.stage2_symbol,
            outcome.backend_centered_code,
            stage1_dither_symbol,
            stage2_dither_symbol,
        )
        try:
            result = correct_two_stage_observed(observed, calibration)
        except ValueError as error:
            raise ValueError(
                f"possible observation lies outside candidate Gu correction domain: {outcome}"
            ) from error
        digital_clipping |= result.saturated_low or result.saturated_high
        codes.append(min(max(round(result.unclipped_output_code), int(output_low)),
                         int(output_high)))
    return FullChainCodeEnvelope(
        lower_output_code=min(codes),
        upper_output_code=max(codes),
        observation_count=len(observations.outcomes),
        digital_clipping_possible=digital_clipping,
        physical_overload_possible=(
            observations.stage1_input_overload_possible
            or observations.stage1_main_overload_possible
            or observations.backend_overload_possible
        ),
    )
