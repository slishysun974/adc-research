"""Compare three update schedules on the same independent-auxiliary ADC records."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from dataclasses import asdict
from pathlib import Path

import yaml

from adc_research.calibration.adaptive_two_stage import (
    TwoStageAdaptiveConfig,
    TwoStageAdaptiveState,
    cascade_from_state,
    correct_and_update,
    observe,
    update_block_mean_observations,
)
from adc_research.calibration.gated_lms import GatedLmsConfig, GatedLmsState
from adc_research.calibration.gu_baseline import build_gu_two_stage_baseline
from adc_research.calibration.two_stage import correct_two_stage_observed
from adc_research.evaluation.observations import digital_sample
from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.platform.amplifier import StaticCubicTruthConfig
from adc_research.platform.dual_path_settling import (
    DualPathSettlingConfig,
    DualPathSettlingState,
    process as process_dual_path,
)
from adc_research.platform.pipeline import StaticPipelineNonidealities
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stage import StaticStageNonidealities
from adc_research.platform.stimulus import CoherentSineConfig, coherent_sine


ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(__file__).with_name("config.yaml")
SETTLING = DualPathSettlingConfig(0.0, 0.0, 0.0)


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _truth(case: dict) -> StaticPipelineNonidealities:
    if case["kind"] != "cubic":
        raise ValueError("EXP-025 accepts only the frozen cubic test curves")
    return StaticPipelineNonidealities(
        stage1=StaticStageNonidealities(
            cubic_truth=StaticCubicTruthConfig(**case["stage1"])
        ),
        stage2=StaticStageNonidealities(
            cubic_truth=StaticCubicTruthConfig(**case["stage2"])
        ),
    )


def _random_stream(spec: dict, pairs: list[tuple[int, int]], seed: int):
    rng = random.Random(seed)
    low, high = map(float, spec["input_range"])
    for _ in range(spec["sample_count"]):
        yield rng.uniform(low, high), pairs[rng.randrange(len(pairs))]


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


def _raw(value, symbols, index, pipeline, truth):
    return process_dual_path(
        value, pipeline, SETTLING, DualPathSettlingState(),
        sample_index=index, dither_symbols=symbols, nonidealities=truth,
    ).pipeline


def _record(stream, pipeline, truth):
    records = []
    overloads = 0
    for index, (value, symbols) in enumerate(stream):
        raw = _raw(float(value), symbols, index, pipeline, truth)
        overloads += _physical_overload(raw)
        expected = min(max(math.floor((float(value) + 1.0) * 2048), 0), 4095)
        records.append((
            expected,
            raw.reconstruction.output_code,
            digital_sample(raw),
            raw.reconstruction.saturated_low or raw.reconstruction.saturated_high,
        ))
    return records, overloads


def _score(records, cascade=None, *, tone=None):
    codes = []
    total_error = 0
    maximum_error = 0
    saturations = 0
    for expected, nominal, observed, nominal_saturated in records:
        if cascade is None:
            code = nominal
            saturations += nominal_saturated
        else:
            corrected = correct_two_stage_observed(observed, cascade)
            code = min(max(round(corrected.unclipped_output_code), 0), 4095)
            saturations += corrected.saturated_low or corrected.saturated_high
        error = abs(code - expected)
        total_error += error
        maximum_error = max(maximum_error, error)
        codes.append(code)
    result = {
        "sample_count": len(records),
        "mae_codes": total_error / len(records),
        "maximum_absolute_error_codes": maximum_error,
        "digital_saturations": saturations,
    }
    if tone is not None:
        result["spectrum"] = asdict(analyze_coherent_tone(
            codes, sample_rate_hz=float(tone["sample_rate_hz"]),
            fundamental_bin=tone["tone_bin"], full_scale_peak=2048.0,
        ).metrics)
    return result


def _adaptive_config(baseline, training, scale=1.0):
    normalized = tuple(map(float, training["normalized_step_sizes"]))
    bounds = tuple(map(float, training["coefficient_bounds"]))
    return TwoStageAdaptiveConfig(
        cascade=baseline,
        stage1_lms=GatedLmsConfig(
            baseline.stage1_pwl.slice_width,
            tuple(scale * step / baseline.stage1_pwl.full_scale_magnitude**2
                  for step in normalized), bounds,
        ),
        stage2_lms=GatedLmsConfig(
            baseline.stage2_pwl.slice_width,
            tuple(scale * step / baseline.stage2_pwl.full_scale_magnitude**2
                  for step in normalized), bounds,
        ),
    )


def _initial_state(baseline):
    return TwoStageAdaptiveState(
        stage1=GatedLmsState.unity(baseline.stage1_pwl.slice_count),
        stage2=GatedLmsState.unity(baseline.stage2_pwl.slice_count),
    )


def _train(seed, schedules, period, scale, training, pairs, pipeline, truth,
           baseline, validation):
    if set(schedules) != {"every_sample", "one_sample_per_30", "block_mean_30"}:
        raise ValueError("EXP-025 requires all three declared schedules")
    states = {name: _initial_state(baseline) for name in schedules}
    normal_config = _adaptive_config(baseline, training)
    periodic_config = _adaptive_config(baseline, training, scale)
    checkpoints = set(training["checkpoint_samples"])
    trajectories = {name: [] for name in schedules}
    events = {name: 0 for name in schedules}
    block = []
    overloads = 0

    def checkpoint(sample_count):
        for name in schedules:
            cascade = cascade_from_state(baseline, states[name])
            trajectories[name].append({
                "training_samples": sample_count,
                "validation_mae_codes": _score(validation, cascade)["mae_codes"],
            })

    checkpoint(0)
    for sample_count, (value, symbols) in enumerate(
        _random_stream(training, pairs, seed), 1
    ):
        raw = _raw(value, symbols, sample_count - 1, pipeline, truth)
        overloads += _physical_overload(raw)
        observed = digital_sample(raw)
        name = "every_sample"
        states[name] = correct_and_update(
            observed, states[name], normal_config
        ).state
        events[name] += 1
        if sample_count % period == 0:
            name = "one_sample_per_30"
            instantaneous = observe(observed, states[name], periodic_config)
            states[name] = update_block_mean_observations(
                states[name], (instantaneous,), periodic_config
            ).state
            events[name] += 1
        name = "block_mean_30"
        block.append(observe(observed, states[name], periodic_config))
        if len(block) == period:
            states[name] = update_block_mean_observations(
                states[name], block, periodic_config
            ).state
            block.clear()
            events[name] += 1
        if sample_count in checkpoints:
            checkpoint(sample_count)
    return states, trajectories, events, overloads, len(block)


def _stats(values):
    return {
        "mean": statistics.fmean(values),
        "population_std": statistics.pstdev(values),
        "minimum": min(values),
        "maximum": max(values),
    }


def _source_hash(paths):
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run() -> dict:
    config = _yaml(CONFIG)
    reference_path = ROOT / config["reference_protocol"]
    reference = _yaml(reference_path)
    architecture_path = ROOT / reference["architecture_config"]
    architecture = _yaml(architecture_path)
    pipeline = build_gu_static_hypothesis_a(architecture)
    baseline = build_gu_two_stage_baseline(pipeline, architecture["pwl_implications"])
    training = reference["training"]
    period = int(config["decimation_period"])
    scale = float(config["periodic_step_scale"])
    schedules = config["schedules"]
    seeds = config["training_seeds"]
    if period != 30 or scale != 30.0 or len(seeds) != len(set(seeds)):
        raise ValueError("EXP-025 expects the declared period, scale and unique seeds")
    if training["checkpoint_samples"][-1] != training["sample_count"]:
        raise ValueError("last checkpoint must be final sample")
    pairs = [tuple(pair) for pair in training["dither_symbol_pairs"]]
    tone = reference["heldout_tone"]
    sine = coherent_sine(CoherentSineConfig(
        sample_rate_hz=float(tone["sample_rate_hz"]),
        sample_count=tone["sample_count"], tone_bin=tone["tone_bin"],
        amplitude_peak=tone["amplitude_peak"],
        phase_radians=tone["phase_radians"],
    ))
    tone_rng = random.Random(tone["dither_seed"])
    tone_stream = list(zip(
        sine, (pairs[tone_rng.randrange(len(pairs))] for _ in sine), strict=True
    ))
    paths = [
        CONFIG, Path(__file__), reference_path, architecture_path,
        ROOT / "src/adc_research/platform/amplifier.py",
        ROOT / "src/adc_research/platform/stage.py",
        ROOT / "src/adc_research/platform/pipeline.py",
        ROOT / "src/adc_research/platform/dual_path_settling.py",
        ROOT / "src/adc_research/platform/finite_settling.py",
        ROOT / "src/adc_research/platform/presets.py",
        ROOT / "src/adc_research/platform/quantizer.py",
        ROOT / "src/adc_research/platform/cdac.py",
        ROOT / "src/adc_research/platform/backend_sar.py",
        ROOT / "src/adc_research/platform/reconstruct.py",
        ROOT / "src/adc_research/platform/stimulus.py",
        ROOT / "src/adc_research/calibration/gu_baseline.py",
        ROOT / "src/adc_research/calibration/adaptive_two_stage.py",
        ROOT / "src/adc_research/calibration/gated_lms.py",
        ROOT / "src/adc_research/calibration/two_stage.py",
        ROOT / "src/adc_research/evaluation/observations.py",
        ROOT / "src/adc_research/metrics/spectral.py",
    ]
    result = {
        "experiment_id": config["experiment_id"],
        "source_sha256": _source_hash(paths),
        "reference_protocol": config["reference_protocol"],
        "auxiliary_model": config["auxiliary_model"],
        "training_protocol": training,
        "validation_protocol": reference["validation"],
        "heldout_random_protocol": reference["heldout_random"],
        "heldout_tone_protocol": tone,
        "training_seeds": seeds,
        "decimation_period": period,
        "periodic_step_scale": scale,
        "schedules": schedules,
        "cases": {},
    }
    valid = True
    for case_name in config["cases"]:
        truth = _truth(reference["cases"][case_name])
        validation, validation_overloads = _record(
            _random_stream(reference["validation"], pairs,
                           reference["validation"]["seed"]), pipeline, truth,
        )
        heldout, random_overloads = _record(
            _random_stream(reference["heldout_random"], pairs,
                           reference["heldout_random"]["seed"]), pipeline, truth,
        )
        tone_record, tone_overloads = _record(tone_stream, pipeline, truth)
        nominal_random = _score(heldout)
        nominal_tone = _score(tone_record, tone=tone)
        case_rows = []
        for seed in seeds:
            states, trajectories, events, train_overloads, pending = _train(
                seed, schedules, period, scale, training, pairs, pipeline, truth,
                baseline, validation,
            )
            valid &= train_overloads <= config["acceptance"]["maximum_physical_overloads"]
            for name in schedules:
                state = states[name]
                cascade = cascade_from_state(baseline, state)
                random_score = _score(heldout, cascade)
                tone_score = _score(tone_record, cascade, tone=tone)
                validation_maes = [point["validation_mae_codes"]
                                   for point in trajectories[name]]
                threshold = validation_maes[0] * float(
                    reference["convergence"]["validation_mae_fraction_of_unity"]
                )
                first_sustained = next((
                    point["training_samples"]
                    for index, point in enumerate(trajectories[name])
                    if all(value <= threshold for value in validation_maes[index:])
                ), None)
                row = {
                    "training_seed": seed,
                    "schedule": name,
                    "training_physical_overloads": train_overloads,
                    "update_events": events[name],
                    "stage1_observations_used": state.stage1.sample_count,
                    "stage2_observations_used": state.stage2.sample_count,
                    "pending_block_observations": pending if name == "block_mean_30" else 0,
                    "validation_trajectory": trajectories[name],
                    "first_sustained_half_unity_validation_mae_sample": first_sustained,
                    "stage1_coefficients": state.stage1.coefficients,
                    "stage2_coefficients": state.stage2.coefficients,
                    "stage1_gate_counts": state.stage1.gate_counts,
                    "stage2_gate_counts": state.stage2.gate_counts,
                    "heldout_random": random_score,
                    "heldout_tone": tone_score,
                }
                case_rows.append(row)
                valid &= all(math.isfinite(value) for value in (
                    random_score["mae_codes"], tone_score["mae_codes"],
                    tone_score["spectrum"]["sndr_db"],
                    tone_score["spectrum"]["sfdr_dbc"],
                ))
            print(f"{case_name} seed {seed}: completed", flush=True)
        aggregates = {}
        for name in schedules:
            rows = [row for row in case_rows if row["schedule"] == name]
            aggregates[name] = {
                "heldout_random_mae_codes": _stats(
                    [row["heldout_random"]["mae_codes"] for row in rows]
                ),
                "heldout_tone_sndr_db": _stats(
                    [row["heldout_tone"]["spectrum"]["sndr_db"] for row in rows]
                ),
                "heldout_tone_sfdr_dbc": _stats(
                    [row["heldout_tone"]["spectrum"]["sfdr_dbc"] for row in rows]
                ),
                "sustained_half_unity_count": sum(
                    row["first_sustained_half_unity_validation_mae_sample"] is not None
                    for row in rows
                ),
                "total_heldout_digital_saturations": sum(
                    row["heldout_random"]["digital_saturations"]
                    + row["heldout_tone"]["digital_saturations"] for row in rows
                ),
            }
        result["cases"][case_name] = {
            "analog_case": reference["cases"][case_name],
            "validation_physical_overloads": validation_overloads,
            "heldout_random_physical_overloads": random_overloads,
            "heldout_tone_physical_overloads": tone_overloads,
            "heldout_random_nominal": nominal_random,
            "heldout_tone_nominal": nominal_tone,
            "runs": case_rows,
            "schedule_aggregates": aggregates,
        }
        valid &= (validation_overloads + random_overloads + tone_overloads
                  <= config["acceptance"]["maximum_physical_overloads"])
    result["protocol_passed"] = bool(valid)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    output_dir = ROOT / "artifacts/runs/EXP_025" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    result = run()
    output_dir.mkdir(parents=True)
    output_file = output_dir / "summary.json"
    output_file.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({"protocol_passed": result["protocol_passed"],
                      "output": str(output_file)}, indent=2))
    if not result["protocol_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
