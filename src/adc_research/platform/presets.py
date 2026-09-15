"""Reviewed adapters from named research assumptions to platform configs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Sequence

from adc_research.platform.amplifier import StaticPwlTruthConfig
from adc_research.platform.backend_sar import SarConfig
from adc_research.platform.cdac import CdacConfig, CdacMismatch
from adc_research.platform.pipeline import (
    StaticPipelineConfig,
    StaticPipelineNonidealities,
)
from adc_research.platform.quantizer import QuantizerConfig
from adc_research.platform.reconstruct import ReconstructionConfig
from adc_research.platform.stage import StaticStageConfig, StaticStageNonidealities


GU_GATE_D_EFFECTS = frozenset(
    {
        "flash_threshold_offsets",
        "cdac_code_level_mismatch",
        "linear_interstage_gain",
        "static_pwl_truth",
    }
)


def build_gu_static_hypothesis_a(
    assumption: Mapping[str, Any],
    *,
    dither_profile: str | None = None,
    stage2_flash_auxiliary_gain_ratio: float = 1.0,
    stage2_flash_auxiliary_offset: float = 0.0,
) -> StaticPipelineConfig:
    """Resolve the named Gu hypothesis-A YAML into executable components.

    This adapter is intentionally specific: it refuses a different assumption
    set rather than silently treating any vaguely similar mapping as candidate A.
    """

    supported = (
        assumption.get("assumption_set_id") == "gu_static_hypothesis_a_v0_1"
        or assumption.get("config_id") == "gu_behavioral_v1"
    )
    if not supported:
        raise ValueError("unsupported Gu static assumption set")

    domain = assumption["normalized_domain"]
    input_range = tuple(domain["input_range"])
    template = assumption["front_stage_template"]
    symbols = tuple(template["output_symbols"])
    levels = tuple(template["dac_levels"])
    if len(symbols) != len(levels):
        raise ValueError("each front-stage symbol must have one DAC level")

    dither = assumption["dither_hypothesis"]
    selected_profile = dither_profile or dither["default_profile"]
    try:
        profile = dither["profiles"][selected_profile]
    except KeyError as error:
        raise ValueError(f"unknown dither profile: {selected_profile}") from error
    amplitude = profile["residue_preamp_normalized_half_amplitude"]
    symbol_values = tuple(dither["symbol_values"])
    dither_levels = {symbol: symbol * amplitude for symbol in symbol_values}

    quantizer = QuantizerConfig(
        tuple(template["thresholds"]),
        symbols,
        input_range=input_range,
    )
    stage = StaticStageConfig(
        quantizer=quantizer,
        cdac=CdacConfig(
            nominal_levels=dict(zip(symbols, levels, strict=True)),
            dither_levels=dither_levels,
        ),
        nominal_interstage_gain=template["nominal_interstage_gain"],
        next_stage_range=input_range,
    )

    backend = assumption["backend"]
    digital = assumption["digital_reconstruction"]
    weights = digital["centered_weights"]
    copy1, copy2 = profile["digital_copy_centered_codes"]
    reconstruction = ReconstructionConfig(
        front_stage_weights=(
            weights["stage1_symbol"],
            weights["stage2_symbol"],
        ),
        backend_weight=weights["backend_centered_code"],
        output_offset=digital["output_offset"],
        output_range=tuple(digital["output_range"]),
        dither_code_copies=(
            {symbol: symbol * copy1 for symbol in symbol_values},
            {symbol: symbol * copy2 for symbol in symbol_values},
        ),
    )
    return StaticPipelineConfig(
        stage1=stage,
        stage2=stage,
        backend=SarConfig(
            bits=backend["bits"],
            input_range=input_range,
            channels=backend["channels"],
        ),
        reconstruction=reconstruction,
        # In Fig. 13 the first inter-stage main path drives the stage-2 CDAC,
        # while its auxiliary path drives the stage-2 flash.  The stage-1
        # decision itself is therefore not assigned this inter-stage mismatch.
        auxiliary_gain_ratios=(1.0, stage2_flash_auxiliary_gain_ratio),
        auxiliary_offsets=(0.0, stage2_flash_auxiliary_offset),
    )


def build_gu_gate_d_nonidealities(
    profile: Mapping[str, Any],
    *,
    enabled_effects: Sequence[str] = (),
) -> StaticPipelineNonidealities:
    """Resolve named Gate-D effects into independent per-stage switches."""

    if profile.get("config_id") != "gu_gate_d_static_v0_1":
        raise ValueError("unsupported Gate-D nonideality profile")
    enabled = frozenset(enabled_effects)
    unknown = enabled - GU_GATE_D_EFFECTS
    if unknown:
        raise ValueError(f"unknown Gate-D effects: {sorted(unknown)}")
    effects = profile["effects"]

    def build_stage(stage_name: str) -> StaticStageNonidealities:
        threshold_offsets = (
            tuple(effects["flash_threshold_offsets"][stage_name])
            if "flash_threshold_offsets" in enabled
            else ()
        )
        cdac_mismatch = (
            CdacMismatch(
                code_level_errors=dict(
                    effects["cdac_code_level_mismatch"][stage_name]
                )
            )
            if "cdac_code_level_mismatch" in enabled
            else None
        )
        actual_gain = (
            effects["linear_interstage_gain"][stage_name]
            if "linear_interstage_gain" in enabled
            else None
        )
        if "static_pwl_truth" in enabled:
            truth_profile = effects["static_pwl_truth"][stage_name]
            truth = StaticPwlTruthConfig(
                tuple(truth_profile["ideal_output_edges"]),
                tuple(truth_profile["distorted_output_edges"]),
            )
        else:
            truth = None
        return StaticStageNonidealities(
            threshold_offsets=threshold_offsets,
            cdac_mismatch=cdac_mismatch,
            actual_interstage_gain=actual_gain,
            pwl_truth=truth,
        )

    return StaticPipelineNonidealities(
        stage1=build_stage("stage1"),
        stage2=build_stage("stage2"),
    )
