"""Redundancy-aware digital reconstruction for the reference platform."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Mapping, Sequence

from adc_research.platform.backend_sar import SarResult
from adc_research.platform.stage import StageResult


@dataclass(frozen=True)
class ReconstructionConfig:
    """Integer weights and output semantics for a pipeline reconstruction."""

    front_stage_weights: tuple[int, ...]
    backend_weight: int
    output_offset: int
    output_range: tuple[int, int]
    dither_code_copies: tuple[Mapping[Hashable, int], ...] = ()

    def __post_init__(self) -> None:
        if not self.front_stage_weights:
            raise ValueError("at least one front-stage weight is required")
        if self.backend_weight <= 0:
            raise ValueError("backend_weight must be positive")
        low, high = self.output_range
        if high < low:
            raise ValueError("output_range must be increasing")
        if self.dither_code_copies and len(self.dither_code_copies) != len(
            self.front_stage_weights
        ):
            raise ValueError(
                "dither_code_copies must match the number of front stages"
            )


@dataclass(frozen=True)
class ReconstructionResult:
    stage_symbols: tuple[Hashable, ...]
    stage_weight_terms: tuple[int, ...]
    backend_centered_code: int
    backend_weight_term: int
    uncorrected_centered_code: int
    digital_dither_copy: int
    corrected_centered_code: int
    unclipped_output_code: int
    output_code: int
    saturated_low: bool
    saturated_high: bool
    correctable: bool


def reconstruct(
    stage_results: Sequence[StageResult],
    backend_result: SarResult,
    config: ReconstructionConfig,
) -> ReconstructionResult:
    """Combine stage symbols and a backend code, then subtract dither copies."""

    if len(stage_results) != len(config.front_stage_weights):
        raise ValueError("stage_results must match configured front-stage weights")

    stage_symbols = tuple(stage.quantizer.symbol for stage in stage_results)
    try:
        stage_terms = tuple(
            weight * symbol
            for weight, symbol in zip(
                config.front_stage_weights, stage_symbols, strict=True
            )
        )
    except TypeError as error:
        raise TypeError("stage symbols must support integer weighting") from error

    backend_term = config.backend_weight * backend_result.centered_code
    uncorrected_centered = sum(stage_terms) + backend_term

    dither_copy = 0
    for index, stage in enumerate(stage_results):
        symbol = stage.cdac.dither_symbol
        if symbol is None:
            continue
        if not config.dither_code_copies:
            raise ValueError("active dither has no configured digital code copy")
        mapping = config.dither_code_copies[index]
        if symbol not in mapping:
            raise KeyError(
                f"stage {index + 1} dither symbol has no digital copy: {symbol!r}"
            )
        dither_copy += mapping[symbol]

    corrected_centered = uncorrected_centered - dither_copy
    unclipped = corrected_centered + config.output_offset
    low, high = config.output_range
    saturated_low = unclipped < low
    saturated_high = unclipped > high
    output_code = min(max(unclipped, low), high)

    # A gain-scaled auxiliary comparator path may legitimately extend beyond
    # its nominal coordinate range near full scale.  Information is lost only
    # when a *main* signal path or the following residue/backend overloads.
    path_overload = any(
        not stage.correctable
        or stage.main_input_overload_low
        or stage.main_input_overload_high
        for stage in stage_results
    ) or backend_result.overload_low or backend_result.overload_high

    return ReconstructionResult(
        stage_symbols=stage_symbols,
        stage_weight_terms=stage_terms,
        backend_centered_code=backend_result.centered_code,
        backend_weight_term=backend_term,
        uncorrected_centered_code=uncorrected_centered,
        digital_dither_copy=dither_copy,
        corrected_centered_code=corrected_centered,
        unclipped_output_code=unclipped,
        output_code=output_code,
        saturated_low=saturated_low,
        saturated_high=saturated_high,
        correctable=not (path_overload or saturated_low or saturated_high),
    )
