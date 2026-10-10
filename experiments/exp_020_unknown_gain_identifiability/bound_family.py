"""Bound a synthetic stage-2 transfer family on EXP-020's held-out tone.

For 0 <= alpha <= 1, g_alpha = (1-alpha) * nominal + alpha * alternative.
Only the stage-2 main transfer varies.  Front decisions and frozen unity Gu
coefficients are identical across the family.  This is a mathematical example,
not a physically measured transfer envelope.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from pathlib import Path

import yaml

from adc_research.calibration.gu_baseline import build_gu_two_stage_baseline
from adc_research.calibration.two_stage import correct_two_stage_observed
from adc_research.evaluation.backend_code_envelope import (
    bound_backend_voltage_to_gu_code,
)
from adc_research.evaluation.observations import digital_sample
from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.platform.amplifier import StaticPwlTruthConfig
from adc_research.platform.pipeline import StaticPipelineNonidealities, process
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stage import StaticStageNonidealities
from adc_research.platform.stimulus import CoherentSineConfig, coherent_sine
from adc_research.theory.finite_record_bounds import bound_finite_coherent_tone


ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(__file__).with_name("config.yaml")


def _integer_code(value: float) -> int:
    return min(max(round(value), 0), 4095)


def run() -> dict:
    experiment = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    architecture_path = ROOT / experiment["architecture_config"]
    architecture = yaml.safe_load(architecture_path.read_text(encoding="utf-8"))
    pipeline = build_gu_static_hypothesis_a(architecture)
    unity_gu = build_gu_two_stage_baseline(
        pipeline, architecture["pwl_implications"]
    )
    left, middle, right = experiment["counterexample"]["support_edges"]
    bump = experiment["counterexample"]["peak_output_perturbation"]
    truth = StaticPwlTruthConfig(
        (0.0, left, middle, right, 1.0),
        (0.0, left, middle + bump, right, 1.0),
    )
    alternative = StaticPipelineNonidealities(
        stage2=StaticStageNonidealities(pwl_truth=truth)
    )
    tone = experiment["heldout_tone"]
    samples = coherent_sine(CoherentSineConfig(
        sample_rate_hz=float(tone["sample_rate_hz"]),
        sample_count=int(tone["sample_count"]),
        tone_bin=int(tone["tone_bin"]),
        amplitude_peak=float(tone["amplitude_peak"]),
        phase_radians=float(tone["phase_radians"]),
    ))
    pairs = [tuple(pair) for pair in experiment["training"]["dither_symbol_pairs"]]
    reference_codes: list[int] = []
    alternative_codes: list[int] = []
    lower_codes: list[int] = []
    upper_codes: list[int] = []
    possible_backend_overloads = 0
    for index, value in enumerate(samples):
        pair = pairs[index % len(pairs)]
        reference = process(
            float(value), pipeline, sample_index=index, dither_symbols=pair
        )
        changed = process(
            float(value), pipeline, sample_index=index, dither_symbols=pair,
            nonidealities=alternative,
        )
        observed = digital_sample(reference)
        changed_observed = digital_sample(changed)
        if (
            observed.stage1_symbol != changed_observed.stage1_symbol
            or observed.stage2_symbol != changed_observed.stage2_symbol
            or observed.stage1_dither_symbol != changed_observed.stage1_dither_symbol
            or observed.stage2_dither_symbol != changed_observed.stage2_dither_symbol
        ):
            raise AssertionError("a front-stage field changed in the stage-2-only family")
        envelope = bound_backend_voltage_to_gu_code(
            observed, pipeline.backend, unity_gu,
            min(reference.stage2.residue, changed.stage2.residue),
            max(reference.stage2.residue, changed.stage2.residue),
        )
        reference_code = _integer_code(
            correct_two_stage_observed(observed, unity_gu).unclipped_output_code
        )
        changed_code = _integer_code(
            correct_two_stage_observed(changed_observed, unity_gu).unclipped_output_code
        )
        if reference_code != reference.reconstruction.output_code:
            raise AssertionError("unity Gu correction disagrees with nominal reconstruction")
        if changed_code != changed.reconstruction.output_code:
            raise AssertionError("unity Gu correction disagrees with changed reconstruction")
        if not (
            envelope.lower_output_code <= reference_code <= envelope.upper_output_code
            and envelope.lower_output_code <= changed_code <= envelope.upper_output_code
        ):
            raise AssertionError("an endpoint record escaped the conditional envelope")
        reference_codes.append(reference_code)
        alternative_codes.append(changed_code)
        lower_codes.append(envelope.lower_output_code)
        upper_codes.append(envelope.upper_output_code)
        possible_backend_overloads += envelope.backend_overload_possible

    metric_kwargs = {
        "sample_rate_hz": float(tone["sample_rate_hz"]),
        "fundamental_bin": int(tone["tone_bin"]),
    }
    reference_metrics = analyze_coherent_tone(reference_codes, **metric_kwargs).metrics
    changed_metrics = analyze_coherent_tone(alternative_codes, **metric_kwargs).metrics
    bounds = bound_finite_coherent_tone(
        reference_codes, lower_codes, upper_codes,
        fundamental_bin=int(tone["tone_bin"]),
    )
    paths = (
        CONFIG, architecture_path, Path(__file__),
        ROOT / "src/adc_research/evaluation/backend_code_envelope.py",
        ROOT / "src/adc_research/theory/finite_record_bounds.py",
    )
    result = {
        "assumed_family": "g_alpha=(1-alpha)*nominal+alpha*alternative, 0<=alpha<=1; stage-2 main path only",
        "source_sha256": {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths
        },
        "sample_count": len(samples),
        "uncertain_output_samples": sum(
            lower < upper for lower, upper in zip(lower_codes, upper_codes, strict=True)
        ),
        "largest_output_span_codes": max(
            upper - lower for lower, upper in zip(lower_codes, upper_codes, strict=True)
        ),
        "possible_backend_overload_samples": possible_backend_overloads,
        "reference": {
            "sndr_db": reference_metrics.sndr_db,
            "sfdr_dbc": reference_metrics.sfdr_dbc,
        },
        "alternative": {
            "sndr_db": changed_metrics.sndr_db,
            "sfdr_dbc": changed_metrics.sfdr_dbc,
        },
        "bounds": asdict(bounds),
    }
    result["passed"] = (
        possible_backend_overloads == 0
        and bounds.sndr_db.lower <= changed_metrics.sndr_db <= bounds.sndr_db.upper
        and bounds.sfdr_dbc.lower <= changed_metrics.sfdr_dbc <= bounds.sfdr_dbc.upper
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    output_dir = ROOT / "artifacts/runs/EXP_020" / args.run_id
    result = run()
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({key: result[key] for key in (
        "passed", "uncertain_output_samples", "largest_output_span_codes",
        "possible_backend_overload_samples", "reference", "alternative", "bounds"
    )}, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
