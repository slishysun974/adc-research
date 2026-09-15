"""Fixed-point PWL correction and two-stage cascade.

The coefficient and data fractional resolutions follow Gu et al. The paper
does not disclose multiplier rounding, intermediate word lengths, or overflow
placement, so those behaviors remain explicit configuration choices.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose
from typing import Hashable, Literal, Mapping

from adc_research.calibration.fixed_point import (
    OverflowMode,
    RoundingMode,
    UnsignedFixedFormat,
    fixed_to_float,
    round_shift,
    signed_bits_required,
)
from adc_research.calibration.known_truth import TwoStagePwlCalibrationConfig
from adc_research.calibration.pwl import NegativeFullScalePolicy, PwlConfig
from adc_research.platform.pipeline import PipelineResult


OffsetRounding = Literal["after_coefficient_sum", "per_coefficient"]


@dataclass(frozen=True)
class FixedPwlArithmetic:
    coefficient_format: UnsignedFixedFormat = UnsignedFixedFormat(11, 10)
    data_fractional_bits: int = 3
    coefficient_rounding: RoundingMode = "nearest_even"
    multiplication_rounding: RoundingMode = "nearest_even"
    coefficient_overflow: OverflowMode = "saturate"
    offset_rounding: OffsetRounding = "after_coefficient_sum"

    def __post_init__(self) -> None:
        if self.data_fractional_bits < 0:
            raise ValueError("data_fractional_bits must be nonnegative")
        if self.offset_rounding not in (
            "after_coefficient_sum",
            "per_coefficient",
        ):
            raise ValueError("unsupported offset rounding rule")

    @property
    def data_scale(self) -> int:
        return 1 << self.data_fractional_bits


@dataclass(frozen=True)
class FixedPwlConfig:
    slice_width_scaled: int
    coefficient_codes: tuple[int, ...]
    source_slopes: tuple[float, ...]
    arithmetic: FixedPwlArithmetic
    coefficient_saturations: tuple[bool, ...]
    negative_full_scale_policy: NegativeFullScalePolicy = "extend_last_slice"

    def __post_init__(self) -> None:
        if self.slice_width_scaled <= 0:
            raise ValueError("slice_width_scaled must be positive")
        if not self.coefficient_codes:
            raise ValueError("at least one coefficient is required")
        if len(self.coefficient_codes) != len(self.source_slopes):
            raise ValueError("coefficient codes and source slopes must match")
        if len(self.coefficient_saturations) != len(self.coefficient_codes):
            raise ValueError("coefficient saturation flags must match")
        maximum = self.arithmetic.coefficient_format.maximum_code
        if any(code < 0 or code > maximum for code in self.coefficient_codes):
            raise ValueError("coefficient code lies outside configured format")

    @property
    def slice_count(self) -> int:
        return len(self.coefficient_codes)

    @property
    def full_scale_scaled(self) -> int:
        return self.slice_width_scaled * self.slice_count

    @property
    def quantized_slopes(self) -> tuple[float, ...]:
        fractional_bits = self.arithmetic.coefficient_format.fractional_bits
        return tuple(
            fixed_to_float(code, fractional_bits)
            for code in self.coefficient_codes
        )

    @property
    def coefficient_errors(self) -> tuple[float, ...]:
        return tuple(
            quantized - source
            for quantized, source in zip(
                self.quantized_slopes,
                self.source_slopes,
                strict=True,
            )
        )


def quantize_pwl_config(
    floating: PwlConfig,
    arithmetic: FixedPwlArithmetic,
) -> FixedPwlConfig:
    scaled_width = floating.slice_width * arithmetic.data_scale
    if not isclose(scaled_width, round(scaled_width), abs_tol=1e-12):
        raise ValueError("slice width is not representable in the data format")
    codes = []
    saturations = []
    for slope in floating.slopes:
        code, saturated = arithmetic.coefficient_format.quantize(
            slope,
            rounding=arithmetic.coefficient_rounding,
            overflow=arithmetic.coefficient_overflow,
        )
        codes.append(code)
        saturations.append(saturated)
    return FixedPwlConfig(
        slice_width_scaled=round(scaled_width),
        coefficient_codes=tuple(codes),
        source_slopes=floating.slopes,
        arithmetic=arithmetic,
        coefficient_saturations=tuple(saturations),
        negative_full_scale_policy=floating.negative_full_scale_policy,
    )


@dataclass(frozen=True)
class FixedPwlResult:
    raw_code_scaled: int
    sign: int
    magnitude_scaled: int
    slice_index: int
    local_code_scaled: int
    coefficient_code: int
    product_wide: int
    product_scaled: int
    offset_wide: int
    offset_scaled: int
    corrected_magnitude_scaled: int
    corrected_code_scaled: int
    product_bits_required: int
    offset_bits_required: int
    corrected_bits_required: int
    negative_full_scale_extension: bool

    def corrected_code(self, fractional_bits: int) -> float:
        return fixed_to_float(self.corrected_code_scaled, fractional_bits)


def _offset_terms(config: FixedPwlConfig, slice_index: int) -> tuple[int, int]:
    coefficient_bits = config.arithmetic.coefficient_format.fractional_bits
    rounding = config.arithmetic.multiplication_rounding
    selected = config.coefficient_codes[:slice_index]
    if config.arithmetic.offset_rounding == "after_coefficient_sum":
        wide = config.slice_width_scaled * sum(selected)
        scaled = round_shift(wide, coefficient_bits, rounding)
        return wide, scaled
    wide_terms = tuple(config.slice_width_scaled * code for code in selected)
    scaled = sum(round_shift(term, coefficient_bits, rounding) for term in wide_terms)
    return sum(wide_terms), scaled


def correct_fixed(raw_code_scaled: int, config: FixedPwlConfig) -> FixedPwlResult:
    """Correct one signed code represented with the configured data fraction."""

    full_scale = config.full_scale_scaled
    if raw_code_scaled < -full_scale or raw_code_scaled >= full_scale:
        raise ValueError("raw code lies outside the signed PWL domain")
    negative_endpoint = raw_code_scaled == -full_scale
    if negative_endpoint and config.negative_full_scale_policy == "reject":
        raise ValueError("negative full-scale code is unresolved by this policy")

    sign = -1 if raw_code_scaled < 0 else (1 if raw_code_scaled > 0 else 0)
    magnitude = abs(raw_code_scaled)
    if negative_endpoint:
        slice_index = config.slice_count - 1
        local = config.slice_width_scaled
    else:
        slice_index = min(
            magnitude // config.slice_width_scaled,
            config.slice_count - 1,
        )
        local = magnitude - slice_index * config.slice_width_scaled

    coefficient = config.coefficient_codes[slice_index]
    product_wide = local * coefficient
    product_scaled = round_shift(
        product_wide,
        config.arithmetic.coefficient_format.fractional_bits,
        config.arithmetic.multiplication_rounding,
    )
    offset_wide, offset_scaled = _offset_terms(config, slice_index)
    corrected_magnitude = offset_scaled + product_scaled
    corrected = sign * corrected_magnitude
    return FixedPwlResult(
        raw_code_scaled=raw_code_scaled,
        sign=sign,
        magnitude_scaled=magnitude,
        slice_index=slice_index,
        local_code_scaled=local,
        coefficient_code=coefficient,
        product_wide=product_wide,
        product_scaled=product_scaled,
        offset_wide=offset_wide,
        offset_scaled=offset_scaled,
        corrected_magnitude_scaled=corrected_magnitude,
        corrected_code_scaled=corrected,
        product_bits_required=max(product_wide.bit_length(), 1),
        offset_bits_required=max(offset_wide.bit_length(), 1),
        corrected_bits_required=signed_bits_required(corrected),
        negative_full_scale_extension=negative_endpoint,
    )


@dataclass(frozen=True)
class FixedTwoStageConfig:
    stage1_pwl: FixedPwlConfig
    stage2_pwl: FixedPwlConfig
    stage1_symbol_weight_scaled: int
    stage2_symbol_weight_scaled: int
    backend_weight_scaled: int
    output_offset_scaled: int
    output_range_scaled: tuple[int, int]
    dither_code_copies_scaled: (
        tuple[Mapping[Hashable, int], Mapping[Hashable, int]]
    )
    data_fractional_bits: int


def _scale_exact(value: float, scale: int, name: str) -> int:
    scaled = value * scale
    if not isclose(scaled, round(scaled), abs_tol=1e-12):
        raise ValueError(f"{name} is not representable in the data format")
    return round(scaled)


def quantize_two_stage_config(
    floating: TwoStagePwlCalibrationConfig,
    arithmetic: FixedPwlArithmetic,
) -> FixedTwoStageConfig:
    scale = arithmetic.data_scale
    mappings = tuple(
        {
            symbol: _scale_exact(value, scale, "dither code copy")
            for symbol, value in mapping.items()
        }
        for mapping in floating.dither_code_copies
    )
    return FixedTwoStageConfig(
        stage1_pwl=quantize_pwl_config(floating.stage1_pwl, arithmetic),
        stage2_pwl=quantize_pwl_config(floating.stage2_pwl, arithmetic),
        stage1_symbol_weight_scaled=_scale_exact(
            floating.stage1_symbol_weight,
            scale,
            "stage1 symbol weight",
        ),
        stage2_symbol_weight_scaled=_scale_exact(
            floating.stage2_symbol_weight,
            scale,
            "stage2 symbol weight",
        ),
        backend_weight_scaled=_scale_exact(
            floating.backend_weight,
            scale,
            "backend weight",
        ),
        output_offset_scaled=_scale_exact(
            floating.output_offset,
            scale,
            "output offset",
        ),
        output_range_scaled=(
            _scale_exact(floating.output_range[0], scale, "output range"),
            _scale_exact(floating.output_range[1], scale, "output range"),
        ),
        dither_code_copies_scaled=mappings,
        data_fractional_bits=arithmetic.data_fractional_bits,
    )


def _dither_scaled(
    symbol: Hashable | None,
    mapping: Mapping[Hashable, int],
    stage_number: int,
) -> int:
    if symbol is None:
        return 0
    if symbol not in mapping:
        raise KeyError(f"stage {stage_number} dither symbol is not configured")
    return mapping[symbol]


@dataclass(frozen=True)
class FixedTwoStageResult:
    stage2_raw_scaled: int
    stage2_pwl: FixedPwlResult
    stage2_dither_scaled: int
    stage1_raw_before_dither_scaled: int
    stage1_raw_scaled: int
    stage1_pwl: FixedPwlResult
    stage1_dither_scaled: int
    corrected_centered_scaled: int
    unclipped_output_scaled: int
    output_scaled: int
    saturated_low: bool
    saturated_high: bool
    correctable: bool
    maximum_signed_data_bits_required: int

    def unclipped_output_code(self, fractional_bits: int) -> float:
        return fixed_to_float(self.unclipped_output_scaled, fractional_bits)


def correct_two_stage_fixed(
    raw: PipelineResult,
    config: FixedTwoStageConfig,
) -> FixedTwoStageResult:
    """Apply the stage-2 then stage-1 PWL cascade with integer arithmetic."""

    scale = 1 << config.data_fractional_bits
    if config.backend_weight_scaled % scale:
        raise ValueError("fractional backend weight is not supported by this reference")
    stage2_raw = (
        config.backend_weight_scaled * raw.backend.centered_code
    )
    stage2 = correct_fixed(stage2_raw, config.stage2_pwl)
    dither2 = _dither_scaled(
        raw.stage2.cdac.dither_symbol,
        config.dither_code_copies_scaled[1],
        2,
    )
    stage1_before = (
        config.stage2_symbol_weight_scaled * raw.stage2.quantizer.symbol
        + stage2.corrected_code_scaled
    )
    stage1_raw = stage1_before - dither2
    stage1 = correct_fixed(stage1_raw, config.stage1_pwl)
    dither1 = _dither_scaled(
        raw.stage1.cdac.dither_symbol,
        config.dither_code_copies_scaled[0],
        1,
    )
    centered = (
        config.stage1_symbol_weight_scaled * raw.stage1.quantizer.symbol
        + stage1.corrected_code_scaled
        - dither1
    )
    unclipped = centered + config.output_offset_scaled
    low, high = config.output_range_scaled
    saturated_low = unclipped < low
    saturated_high = unclipped > high
    output = min(max(unclipped, low), high)
    path_overload = any(
        not stage.correctable
        or stage.main_input_overload_low
        or stage.main_input_overload_high
        for stage in (raw.stage1, raw.stage2)
    ) or raw.backend.overload_low or raw.backend.overload_high
    signed_values = (
        stage2_raw,
        stage2.corrected_code_scaled,
        stage1_before,
        stage1_raw,
        stage1.corrected_code_scaled,
        centered,
        unclipped,
        output,
    )
    return FixedTwoStageResult(
        stage2_raw_scaled=stage2_raw,
        stage2_pwl=stage2,
        stage2_dither_scaled=dither2,
        stage1_raw_before_dither_scaled=stage1_before,
        stage1_raw_scaled=stage1_raw,
        stage1_pwl=stage1,
        stage1_dither_scaled=dither1,
        corrected_centered_scaled=centered,
        unclipped_output_scaled=unclipped,
        output_scaled=output,
        saturated_low=saturated_low,
        saturated_high=saturated_high,
        correctable=not (path_overload or saturated_low or saturated_high),
        maximum_signed_data_bits_required=max(
            signed_bits_required(value) for value in signed_values
        ),
    )

