"""Composition of quantizer, CDAC, and residue amplifier for one sample."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Hashable

from adc_research.platform.amplifier import (
    AmplifierResult,
    PwlAmplifierResult,
    StaticPwlTruthConfig,
    amplify_ideal_static,
    amplify_static_pwl_truth,
)
from adc_research.platform.cdac import (
    CdacConfig,
    CdacMismatch,
    DacResult,
    reconstruct as reconstruct_cdac,
)
from adc_research.platform.quantizer import (
    QuantizerConfig,
    QuantizerResult,
    convert,
)


@dataclass(frozen=True)
class StaticStageConfig:
    quantizer: QuantizerConfig
    cdac: CdacConfig
    nominal_interstage_gain: float
    next_stage_range: tuple[float, float] = (-1.0, 1.0)


STATIC_NONIDEALITY_ORDER = (
    "flash_threshold_offsets",
    "cdac_code_level_mismatch",
    "analog_dither_injection",
    "linear_interstage_gain",
    "static_pwl_truth",
)


@dataclass(frozen=True)
class StaticStageNonidealities:
    """Independent static nonideality switches for one front stage."""

    threshold_offsets: tuple[float, ...] = ()
    cdac_mismatch: CdacMismatch | None = None
    actual_interstage_gain: float | None = None
    pwl_truth: StaticPwlTruthConfig | None = None

    def __post_init__(self) -> None:
        if any(not isfinite(offset) for offset in self.threshold_offsets):
            raise ValueError("threshold offsets must be finite")
        if self.actual_interstage_gain is not None and (
            not isfinite(self.actual_interstage_gain)
            or self.actual_interstage_gain <= 0
        ):
            raise ValueError("actual interstage gain must be finite and positive")


@dataclass(frozen=True)
class StageResult:
    main_input: float
    auxiliary_input: float
    main_input_overload_low: bool
    main_input_overload_high: bool
    quantizer: QuantizerResult
    cdac: DacResult
    residue_preamp: float
    amplifier: AmplifierResult | PwlAmplifierResult
    residue: float
    correctable: bool
    overload_low: bool
    overload_high: bool
    applied_nonideality_order: tuple[str, ...]


def process(
    main_input: float,
    auxiliary_input: float,
    dither_symbol: Hashable | None,
    config: StaticStageConfig,
    *,
    nonidealities: StaticStageNonidealities | None = None,
) -> StageResult:
    """Process one sample while preserving the main/auxiliary path split."""

    applied = nonidealities or StaticStageNonidealities()
    decision = convert(
        auxiliary_input,
        config.quantizer,
        threshold_offsets=applied.threshold_offsets or None,
    )
    dac = reconstruct_cdac(
        decision.symbol,
        dither_symbol,
        config.cdac,
        applied.cdac_mismatch,
    )
    residue_preamp = (
        main_input - dac.actual_dac_value + dac.dither_contribution
    )
    if applied.pwl_truth is None:
        amplifier = amplify_ideal_static(
            residue_preamp,
            nominal_gain=config.nominal_interstage_gain,
            actual_gain=applied.actual_interstage_gain,
        )
    else:
        amplifier = amplify_static_pwl_truth(
            residue_preamp,
            nominal_gain=config.nominal_interstage_gain,
            truth=applied.pwl_truth,
            actual_gain=applied.actual_interstage_gain,
        )
    low, high = config.next_stage_range
    overload_low = amplifier.output_value < low
    overload_high = amplifier.output_value >= high
    input_low, input_high = config.quantizer.input_range
    return StageResult(
        main_input=main_input,
        auxiliary_input=auxiliary_input,
        main_input_overload_low=main_input < input_low,
        main_input_overload_high=main_input >= input_high,
        quantizer=decision,
        cdac=dac,
        residue_preamp=residue_preamp,
        amplifier=amplifier,
        residue=amplifier.output_value,
        correctable=not (overload_low or overload_high),
        overload_low=overload_low,
        overload_high=overload_high,
        applied_nonideality_order=STATIC_NONIDEALITY_ORDER,
    )
