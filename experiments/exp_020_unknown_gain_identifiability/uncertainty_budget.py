"""Reproduce the spectral proof budget for EXP-020's synthetic reference.

This does not derive a physical code envelope. The frozen experiment's nominal
pipeline supplies only a reference record for planning resolution.
"""

from __future__ import annotations

import json
from math import floor
from pathlib import Path

import yaml

from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.platform.pipeline import process
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stimulus import CoherentSineConfig, coherent_sine
from adc_research.theory.finite_record_bounds import code_uncertainty_budget_for_floors


ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(__file__).with_name("config.yaml")
TARGETS = ((70.0, 90.0), (72.0, 90.0), (70.0, 95.0))


def run() -> dict:
    experiment = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    architecture = yaml.safe_load(
        (ROOT / experiment["architecture_config"]).read_text(encoding="utf-8")
    )
    pipeline = build_gu_static_hypothesis_a(architecture)
    tone = experiment["heldout_tone"]
    inputs = coherent_sine(CoherentSineConfig(
        sample_rate_hz=float(tone["sample_rate_hz"]),
        sample_count=int(tone["sample_count"]),
        tone_bin=int(tone["tone_bin"]),
        amplitude_peak=float(tone["amplitude_peak"]),
        phase_radians=float(tone["phase_radians"]),
    ))
    pairs = [tuple(pair) for pair in experiment["training"]["dither_symbol_pairs"]]
    codes = tuple(
        process(float(value), pipeline, sample_index=index,
                dither_symbols=pairs[index % len(pairs)]).reconstruction.output_code
        for index, value in enumerate(inputs)
    )
    metrics = analyze_coherent_tone(
        codes, sample_rate_hz=float(tone["sample_rate_hz"]),
        fundamental_bin=int(tone["tone_bin"]),
    ).metrics
    budgets = []
    for sndr_floor, sfdr_floor in TARGETS:
        result = code_uncertainty_budget_for_floors(
            codes, fundamental_bin=int(tone["tone_bin"]),
            minimum_sndr_db=sndr_floor, minimum_sfdr_dbc=sfdr_floor,
        )
        budgets.append({
            "minimum_sndr_db": sndr_floor,
            "minimum_sfdr_dbc": sfdr_floor,
            "sndr_rms_budget_codes": result.sndr_rms_budget,
            "sfdr_rms_budget_codes": result.sfdr_rms_budget,
            "joint_rms_budget_codes": result.joint_rms_budget,
            "max_one_code_ambiguous_samples": floor(
                len(codes) * result.joint_rms_budget**2
            ),
        })
    return {
        "scope": "EXP-020 nominal synthetic reference; proof-method budget only",
        "sample_count": len(codes),
        "fundamental_bin": int(tone["tone_bin"]),
        "reference_fundamental_rms_codes": metrics.fundamental_rms,
        "reference_sndr_db": metrics.sndr_db,
        "reference_sfdr_dbc": metrics.sfdr_dbc,
        "budgets": budgets,
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
