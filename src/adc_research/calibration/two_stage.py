"""Two-stage digital correction; no analog truth is needed by this block."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Hashable, Mapping

from adc_research.calibration.pwl import PwlConfig, PwlResult, correct
from adc_research.calibration.observation import DigitalCalibrationSample


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


def correct_two_stage_observed(
    observed: DigitalCalibrationSample,
    config: TwoStagePwlCalibrationConfig,
) -> TwoStagePwlCalibrationResult:
    """Correct codes using only stage symbols, backend code, and dither tags.

    Here ``correctable`` reports *digital output clipping only*. Physical
    path overload is hidden and is scored by ``evaluation.scoring`` offline.
    """

    if not isinstance(observed, DigitalCalibrationSample):
        raise TypeError("online correction requires a digital calibration sample")

    stage2_raw = config.backend_weight * observed.backend_centered_code
    stage2_pwl = correct(stage2_raw, config.stage2_pwl)
    dither2 = _dither_copy(
        observed.stage2_dither_symbol,
        config.dither_code_copies[1],
        stage_number=2,
    )
    stage1_before_dither = (
        config.stage2_symbol_weight * observed.stage2_symbol
        + stage2_pwl.corrected_code
    )
    stage1_raw = stage1_before_dither - dither2
    stage1_pwl = correct(stage1_raw, config.stage1_pwl)

    dither1 = _dither_copy(
        observed.stage1_dither_symbol,
        config.dither_code_copies[0],
        stage_number=1,
    )
    centered = (
        config.stage1_symbol_weight * observed.stage1_symbol
        + stage1_pwl.corrected_code
        - dither1
    )
    unclipped = centered + config.output_offset
    low, high = config.output_range
    saturated_low = unclipped < low
    saturated_high = unclipped > high
    output = min(max(unclipped, low), high)

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
        correctable=not (saturated_low or saturated_high),
    )
