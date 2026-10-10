"""Cold-start Gu candidate on frozen hyperparameters and unseen analog curves."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from dataclasses import asdict
from pathlib import Path

import yaml

from adc_research.calibration.adaptive_two_stage import (
    TwoStageAdaptiveConfig,
    TwoStageAdaptiveState,
    cascade_from_state,
    correct_and_update,
)
from adc_research.calibration.gated_lms import GatedLmsConfig, GatedLmsState
from adc_research.calibration.gu_baseline import build_gu_two_stage_baseline
from adc_research.calibration.two_stage import correct_two_stage_observed
from adc_research.evaluation.observations import digital_sample
from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.platform.amplifier import StaticCubicTruthConfig
from adc_research.platform.pipeline import StaticPipelineNonidealities, process
from adc_research.platform.presets import (
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
)
from adc_research.platform.stage import StaticStageNonidealities
from adc_research.platform.stimulus import CoherentSineConfig, coherent_sine


ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(__file__).with_name("config.yaml")


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _physical_overload(raw) -> bool:
    return (
        any(
            not stage.correctable
            or stage.main_input_overload_low
            or stage.main_input_overload_high
            for stage in (raw.stage1, raw.stage2)
        )
        or raw.backend.overload_low
        or raw.backend.overload_high
    )


def _truth(case: dict, historical_profile: dict) -> StaticPipelineNonidealities:
    if case["kind"] == "historical_pwl":
        return build_gu_gate_d_nonidealities(
            historical_profile, enabled_effects=("static_pwl_truth",)
        )
    if case["kind"] != "cubic":
        raise ValueError(f"unsupported analog test curve: {case['kind']}")
    return StaticPipelineNonidealities(
        stage1=StaticStageNonidealities(
            cubic_truth=StaticCubicTruthConfig(**case["stage1"])
        ),
        stage2=StaticStageNonidealities(
            cubic_truth=StaticCubicTruthConfig(**case["stage2"])
        ),
    )


def _adaptive_config(baseline, training: dict) -> TwoStageAdaptiveConfig:
    normalized = tuple(float(value) for value in training["normalized_step_sizes"])
    bounds = tuple(float(value) for value in training["coefficient_bounds"])
    return TwoStageAdaptiveConfig(
        cascade=baseline,
        stage1_lms=GatedLmsConfig(
            baseline.stage1_pwl.slice_width,
            tuple(value / baseline.stage1_pwl.full_scale_magnitude**2
                  for value in normalized),
            bounds,
        ),
        stage2_lms=GatedLmsConfig(
            baseline.stage2_pwl.slice_width,
            tuple(value / baseline.stage2_pwl.full_scale_magnitude**2
                  for value in normalized),
            bounds,
        ),
    )


def _record(pipeline, nonidealities, values, pairs):
    record = []
    overloads = 0
    for index, (value, pair) in enumerate(zip(values, pairs, strict=True)):
        raw = process(
            float(value), pipeline, sample_index=index,
            dither_symbols=pair, nonidealities=nonidealities,
        )
        overload = _physical_overload(raw)
        overloads += overload
        expected = min(max(math.floor((float(value) + 1.0) * 2048), 0), 4095)
        record.append((expected, digital_sample(raw), overload))
    return record, overloads


def _random_record(pipeline, nonidealities, config: dict, pairs):
    rng = random.Random(config["seed"])
    low, high = map(float, config["input_range"])
    values = [rng.uniform(low, high) for _ in range(config["sample_count"])]
    symbols = [pairs[rng.randrange(len(pairs))] for _ in values]
    return _record(pipeline, nonidealities, values, symbols)


def _score(record, cascade, *, tone: dict | None = None) -> dict:
    errors = []
    codes = []
    saturations = 0
    for expected, observed, _ in record:
        corrected = correct_two_stage_observed(observed, cascade)
        errors.append(abs(corrected.unclipped_output_code - expected))
        codes.append(corrected.output_code)
        saturations += corrected.saturated_low or corrected.saturated_high
    result = {
        "sample_count": len(record),
        "mae_codes": sum(errors) / len(errors),
        "maximum_absolute_error_codes": max(errors),
        "digital_saturations": saturations,
    }
    if tone is not None:
        metrics = analyze_coherent_tone(
            codes,
            sample_rate_hz=float(tone["sample_rate_hz"]),
            fundamental_bin=tone["tone_bin"],
            full_scale_peak=2048.0,
        ).metrics
        result["spectrum"] = asdict(metrics)
    return result


def run() -> dict:
    config = _load_yaml(CONFIG)
    architecture_path = ROOT / config["architecture_config"]
    historical_path = ROOT / config["historical_truth_config"]
    architecture = _load_yaml(architecture_path)
    historical_profile = _load_yaml(historical_path)
    pipeline = build_gu_static_hypothesis_a(architecture)
    baseline = build_gu_two_stage_baseline(pipeline, architecture["pwl_implications"])
    training = config["training"]
    adaptive_config = _adaptive_config(baseline, training)
    pairs = [tuple(pair) for pair in training["dither_symbol_pairs"]]
    if training["code_centers"] != 4096 or len(pairs) != 4:
        raise ValueError("EXP-021 freezes all 4096 code centers and four dither pairs")
    tone = config["heldout_tone"]
    sine = coherent_sine(
        CoherentSineConfig(
            sample_rate_hz=float(tone["sample_rate_hz"]),
            sample_count=tone["sample_count"],
            tone_bin=tone["tone_bin"],
            amplitude_peak=tone["amplitude_peak"],
            phase_radians=tone["phase_radians"],
        )
    )
    dither_rng = random.Random(tone["dither_seed"])
    sine_pairs = [pairs[dither_rng.randrange(len(pairs))] for _ in sine]
    source_files = [
        CONFIG, architecture_path, historical_path, Path(__file__),
        ROOT / "src/adc_research/platform/amplifier.py",
        ROOT / "src/adc_research/platform/stage.py",
        ROOT / "src/adc_research/calibration/adaptive_two_stage.py",
        ROOT / "src/adc_research/calibration/gated_lms.py",
        ROOT / "src/adc_research/calibration/two_stage.py",
        ROOT / "src/adc_research/metrics/spectral.py",
    ]
    digest = hashlib.sha256()
    for path in source_files:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    result = {
        "experiment_id": config["experiment_id"],
        "source_sha256": digest.hexdigest(),
        "training_protocol": training,
        "validation_protocol": config["validation"],
        "heldout_random_protocol": config["heldout_random"],
        "heldout_tone_protocol": tone,
        "online_geometry_source": "architecture_pwl_implications",
        "online_observation": "five_field_digital_sample_only",
        "cases": {},
    }
    for name, case in config["cases"].items():
        nonidealities = _truth(case, historical_profile)
        training_record = []
        training_overloads = 0
        for pair in pairs:
            for code in range(training["code_centers"]):
                value = -1.0 + (code + 0.5) / 2048.0
                raw = process(
                    value, pipeline, sample_index=len(training_record),
                    dither_symbols=pair, nonidealities=nonidealities,
                )
                training_record.append(digital_sample(raw))
                training_overloads += _physical_overload(raw)
        validation_record, validation_overloads = _random_record(
            pipeline, nonidealities, config["validation"], pairs
        )
        heldout_record, heldout_overloads = _random_record(
            pipeline, nonidealities, config["heldout_random"], pairs
        )
        tone_record, tone_overloads = _record(
            pipeline, nonidealities, sine, sine_pairs
        )
        state = TwoStageAdaptiveState(
            stage1=GatedLmsState.unity(baseline.stage1_pwl.slice_count),
            stage2=GatedLmsState.unity(baseline.stage2_pwl.slice_count),
        )
        validation = []
        checkpoints = set(training["checkpoint_epochs"])
        unity = cascade_from_state(baseline, state)
        for epoch in range(training["epochs"] + 1):
            if epoch in checkpoints:
                validation.append({
                    "epoch": epoch,
                    "updates_per_stage": state.stage1.sample_count,
                    "mae_codes": _score(
                        validation_record, cascade_from_state(baseline, state)
                    )["mae_codes"],
                    "stage1_coefficients": state.stage1.coefficients,
                    "stage2_coefficients": state.stage2.coefficients,
                    "stage1_gate_counts": state.stage1.gate_counts,
                    "stage2_gate_counts": state.stage2.gate_counts,
                })
            if epoch == training["epochs"]:
                break
            if epoch == 0:
                order = list(range(len(training_record)))
                rng = random.Random(training["seed"])
            rng.shuffle(order)
            for index in order:
                state = correct_and_update(
                    training_record[index], state, adaptive_config
                ).state
        adapted = cascade_from_state(baseline, state)
        random_unity = _score(heldout_record, unity)
        random_adapted = _score(heldout_record, adapted)
        tone_unity = _score(tone_record, unity, tone=tone)
        tone_adapted = _score(tone_record, adapted, tone=tone)
        result["cases"][name] = {
            "analog_case": case,
            "training_samples_per_epoch": len(training_record),
            "training_physical_overloads": training_overloads,
            "validation_physical_overloads": validation_overloads,
            "heldout_random_physical_overloads": heldout_overloads,
            "heldout_tone_physical_overloads": tone_overloads,
            "validation_trajectory": validation,
            "final_stage1_coefficients": state.stage1.coefficients,
            "final_stage2_coefficients": state.stage2.coefficients,
            "final_stage1_gate_counts": state.stage1.gate_counts,
            "final_stage2_gate_counts": state.stage2.gate_counts,
            "heldout_random": {
                "unity": random_unity,
                "adaptive": random_adapted,
                "mae_improvement_ratio": (
                    random_unity["mae_codes"] / random_adapted["mae_codes"]
                ),
            },
            "heldout_tone": {
                "unity": tone_unity,
                "adaptive": tone_adapted,
                "sndr_change_db": (
                    tone_adapted["spectrum"]["sndr_db"]
                    - tone_unity["spectrum"]["sndr_db"]
                ),
                "sfdr_change_db": (
                    tone_adapted["spectrum"]["sfdr_dbc"]
                    - tone_unity["spectrum"]["sfdr_dbc"]
                ),
            },
        }
        print(
            f"{name}: random MAE {random_unity['mae_codes']:.4f} -> "
            f"{random_adapted['mae_codes']:.4f}; tone SNDR "
            f"{tone_unity['spectrum']['sndr_db']:.3f} -> "
            f"{tone_adapted['spectrum']['sndr_db']:.3f} dB",
            flush=True,
        )
    acceptance = config["acceptance"]
    result["protocol_passed"] = all(
        case["training_physical_overloads"]
        <= acceptance["maximum_training_physical_overloads"]
        and case["heldout_random_physical_overloads"]
        + case["heldout_tone_physical_overloads"]
        <= acceptance["maximum_heldout_physical_overloads"]
        and case["heldout_random"]["adaptive"]["digital_saturations"]
        + case["heldout_tone"]["adaptive"]["digital_saturations"]
        <= acceptance["maximum_heldout_digital_saturations"]
        and math.isfinite(case["heldout_tone"]["adaptive"]["spectrum"]["sndr_db"])
        for case in result["cases"].values()
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    output_dir = ROOT / "artifacts/runs/EXP_021" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    result = run()
    output_dir.mkdir(parents=True)
    (output_dir / "summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"protocol_passed": result["protocol_passed"],
                      "output": str(output_dir / "summary.json")}, indent=2))
    if not result["protocol_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
