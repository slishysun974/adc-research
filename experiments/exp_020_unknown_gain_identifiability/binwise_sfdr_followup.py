"""Compare two conditional SFDR enclosures on EXP-020's synthetic family.

This reuses the frozen experiment configuration but does not claim a physical
transfer envelope. The original EXP-020 run and its source hashes stay intact.
"""

from __future__ import annotations

import json
from dataclasses import asdict

import yaml

from adc_research.calibration.gu_baseline import build_gu_two_stage_baseline
from adc_research.evaluation.backend_code_envelope import bound_backend_voltage_to_gu_code
from adc_research.evaluation.observations import digital_sample
from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.platform.amplifier import StaticPwlTruthConfig
from adc_research.platform.pipeline import StaticPipelineNonidealities, process
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stage import StaticStageNonidealities
from adc_research.platform.stimulus import CoherentSineConfig, coherent_sine
from adc_research.theory.finite_record_bounds import (
    bound_finite_coherent_sfdr_binwise,
    bound_finite_coherent_tone,
)

from bound_family import CONFIG, ROOT


def run() -> dict:
    experiment = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    architecture = yaml.safe_load(
        (ROOT / experiment["architecture_config"]).read_text(encoding="utf-8")
    )
    pipeline = build_gu_static_hypothesis_a(architecture)
    unity_gu = build_gu_two_stage_baseline(pipeline, architecture["pwl_implications"])
    left, middle, right = experiment["counterexample"]["support_edges"]
    bump = experiment["counterexample"]["peak_output_perturbation"]
    alternative = StaticPipelineNonidealities(stage2=StaticStageNonidealities(
        pwl_truth=StaticPwlTruthConfig(
            (0.0, left, middle, right, 1.0),
            (0.0, left, middle + bump, right, 1.0),
        ),
    ))
    tone = experiment["heldout_tone"]
    inputs = coherent_sine(CoherentSineConfig(
        sample_rate_hz=float(tone["sample_rate_hz"]),
        sample_count=int(tone["sample_count"]),
        tone_bin=int(tone["tone_bin"]),
        amplitude_peak=float(tone["amplitude_peak"]),
        phase_radians=float(tone["phase_radians"]),
    ))
    pairs = [tuple(pair) for pair in experiment["training"]["dither_symbol_pairs"]]
    nominal_codes: list[int] = []
    changed_codes: list[int] = []
    lower_codes: list[int] = []
    upper_codes: list[int] = []
    for index, value in enumerate(inputs):
        pair = pairs[index % len(pairs)]
        nominal = process(float(value), pipeline, sample_index=index, dither_symbols=pair)
        changed = process(
            float(value), pipeline, sample_index=index, dither_symbols=pair,
            nonidealities=alternative,
        )
        observation = digital_sample(nominal)
        changed_observation = digital_sample(changed)
        if (
            observation.stage1_symbol != changed_observation.stage1_symbol
            or observation.stage2_symbol != changed_observation.stage2_symbol
            or observation.stage1_dither_symbol != changed_observation.stage1_dither_symbol
            or observation.stage2_dither_symbol != changed_observation.stage2_dither_symbol
        ):
            raise AssertionError(f"front-stage digital field changed at {index}")
        envelope = bound_backend_voltage_to_gu_code(
            observation, pipeline.backend, unity_gu,
            min(nominal.stage2.residue, changed.stage2.residue),
            max(nominal.stage2.residue, changed.stage2.residue),
        )
        if envelope.backend_overload_possible:
            raise AssertionError(f"backend overload possible at {index}")
        if not (
            envelope.lower_output_code <= nominal.reconstruction.output_code
            <= envelope.upper_output_code
            and envelope.lower_output_code <= changed.reconstruction.output_code
            <= envelope.upper_output_code
        ):
            raise AssertionError(f"endpoint code escaped interval at {index}")
        nominal_codes.append(nominal.reconstruction.output_code)
        changed_codes.append(changed.reconstruction.output_code)
        lower_codes.append(envelope.lower_output_code)
        upper_codes.append(envelope.upper_output_code)

    tone_bin = int(tone["tone_bin"])
    old = bound_finite_coherent_tone(
        nominal_codes, lower_codes, upper_codes, fundamental_bin=tone_bin,
    )
    binwise = bound_finite_coherent_sfdr_binwise(
        lower_codes, upper_codes, fundamental_bin=tone_bin,
    )
    actual = [analyze_coherent_tone(
        codes, sample_rate_hz=float(tone["sample_rate_hz"]),
        fundamental_bin=tone_bin,
    ).metrics.sfdr_dbc for codes in (nominal_codes, changed_codes)]
    return {
        "scope": "EXP-020 synthetic one-parameter stage-2 transfer family, frozen unity calibration",
        "uncertain_samples": sum(lo < hi for lo, hi in zip(lower_codes, upper_codes, strict=True)),
        "parseval_sfdr_dbc": asdict(old.sfdr_dbc),
        "binwise_sfdr_dbc": asdict(binwise.sfdr_dbc),
        "binwise_sum_code_halfwidths": binwise.sum_code_halfwidths,
        "endpoint_sfdr_dbc": actual,
        "endpoint_covered": all(binwise.sfdr_dbc.lower <= x <= binwise.sfdr_dbc.upper for x in actual),
    }


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
