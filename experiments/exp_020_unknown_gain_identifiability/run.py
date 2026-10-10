"""Finite digital observations cannot identify an unrestricted analog curve."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import yaml

from adc_research.evaluation.observations import digital_sample
from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.platform.amplifier import StaticPwlTruthConfig
from adc_research.platform.pipeline import StaticPipelineNonidealities, process
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stage import StaticStageNonidealities
from adc_research.platform.stimulus import CoherentSineConfig, coherent_sine


ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(__file__).with_name("config.yaml")


def run() -> dict:
    experiment = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    architecture_path = ROOT / experiment["architecture_config"]
    architecture = yaml.safe_load(architecture_path.read_text(encoding="utf-8"))
    pipeline = build_gu_static_hypothesis_a(architecture)
    left, middle, right = experiment["counterexample"]["support_edges"]
    bump = experiment["counterexample"]["peak_output_perturbation"]
    if not (0 < left < middle < right < 1 and 0 < bump < right - middle):
        raise ValueError("counterexample must be a positive, monotone interior bump")
    truth = StaticPwlTruthConfig(
        (0.0, left, middle, right, 1.0),
        (0.0, left, middle + bump, right, 1.0),
    )
    alternative = StaticPipelineNonidealities(
        stage2=StaticStageNonidealities(pwl_truth=truth)
    )
    pairs = [tuple(pair) for pair in experiment["training"]["dither_symbol_pairs"]]
    code_count = experiment["training"]["input_code_centers"]
    training_digital_mismatches = training_output_mismatches = 0
    training_support_hits = 0
    training_count = 0
    for code in range(code_count):
        value = -1.0 + (code + 0.5) * 2.0 / code_count
        for pair in pairs:
            reference = process(value, pipeline, sample_index=training_count, dither_symbols=pair)
            changed = process(
                value,
                pipeline,
                sample_index=training_count,
                dither_symbols=pair,
                nonidealities=alternative,
            )
            training_support_hits += left < abs(reference.stage2.residue) < right
            training_digital_mismatches += digital_sample(reference) != digital_sample(changed)
            training_output_mismatches += (
                reference.reconstruction.output_code != changed.reconstruction.output_code
            )
            training_count += 1

    tone = experiment["heldout_tone"]
    samples = coherent_sine(
        CoherentSineConfig(
            sample_rate_hz=float(tone["sample_rate_hz"]),
            sample_count=tone["sample_count"],
            tone_bin=tone["tone_bin"],
            amplitude_peak=tone["amplitude_peak"],
            phase_radians=tone["phase_radians"],
        )
    )
    reference_codes = []
    alternative_codes = []
    first_difference = None
    heldout_digital_mismatches = heldout_output_mismatches = 0
    heldout_overloads = 0
    for index, sample in enumerate(samples):
        pair = pairs[index % len(pairs)]
        reference = process(float(sample), pipeline, sample_index=index, dither_symbols=pair)
        changed = process(
            float(sample),
            pipeline,
            sample_index=index,
            dither_symbols=pair,
            nonidealities=alternative,
        )
        reference_codes.append(reference.reconstruction.output_code)
        alternative_codes.append(changed.reconstruction.output_code)
        heldout_digital_mismatches += digital_sample(reference) != digital_sample(changed)
        mismatch = reference.reconstruction.output_code != changed.reconstruction.output_code
        heldout_output_mismatches += mismatch
        heldout_overloads += (
            not reference.stage1.correctable
            or not reference.stage2.correctable
            or not changed.stage1.correctable
            or not changed.stage2.correctable
        )
        if mismatch and first_difference is None:
            first_difference = {
                "sample_index": index,
                "input_value": float(sample),
                "dither_symbols": pair,
                "stage2_nominal_output": reference.stage2.residue,
                "reference_backend_code": reference.backend.centered_code,
                "alternative_backend_code": changed.backend.centered_code,
                "reference_output_code": reference.reconstruction.output_code,
                "alternative_output_code": changed.reconstruction.output_code,
            }
    spectral_args = {
        "sample_rate_hz": float(tone["sample_rate_hz"]),
        "fundamental_bin": tone["tone_bin"],
        "full_scale_peak": 2048.0,
    }
    reference_metrics = analyze_coherent_tone(reference_codes, **spectral_args).metrics
    alternative_metrics = analyze_coherent_tone(alternative_codes, **spectral_args).metrics
    result = {
        "experiment_id": experiment["experiment_id"],
        "architecture_config": experiment["architecture_config"],
        "source_sha256": hashlib.sha256(
            CONFIG.read_bytes() + architecture_path.read_bytes() + Path(__file__).read_bytes()
        ).hexdigest(),
        "analog_curves": {
            "reference": "nominal linear stage-2 gain",
            "alternative_stage2_ideal_output_edges": truth.ideal_output_edges,
            "alternative_stage2_distorted_output_edges": truth.distorted_output_edges,
            "alternative_stage2_forward_slopes": truth.forward_slopes,
        },
        "training": {
            "sample_count": training_count,
            "support_hits": training_support_hits,
            "digital_mismatches": training_digital_mismatches,
            "output_mismatches": training_output_mismatches,
        },
        "heldout_tone": {
            "sample_count": len(samples),
            "digital_mismatches": heldout_digital_mismatches,
            "output_mismatches": heldout_output_mismatches,
            "physical_overloads": heldout_overloads,
            "first_output_difference": first_difference,
            "reference_metrics": asdict(reference_metrics),
            "alternative_metrics": asdict(alternative_metrics),
            "sndr_difference_db": alternative_metrics.sndr_db - reference_metrics.sndr_db,
            "sfdr_difference_db": alternative_metrics.sfdr_dbc - reference_metrics.sfdr_dbc,
        },
    }
    acceptance = experiment["acceptance"]
    result["passed"] = (
        training_support_hits == 0
        and training_digital_mismatches <= acceptance["maximum_training_digital_mismatches"]
        and training_output_mismatches <= acceptance["maximum_training_output_mismatches"]
        and heldout_output_mismatches >= acceptance["minimum_heldout_output_mismatches"]
        and abs(result["heldout_tone"]["sndr_difference_db"])
        > acceptance["minimum_heldout_sndr_difference_db"]
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    output_dir = ROOT / "artifacts" / "runs" / "EXP_020" / args.run_id
    result = run()
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"passed": result["passed"], "training": result["training"],
                      "heldout_tone": {key: value for key, value in result["heldout_tone"].items()
                                       if key in ("output_mismatches", "sndr_difference_db", "sfdr_difference_db")}},
                     indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
