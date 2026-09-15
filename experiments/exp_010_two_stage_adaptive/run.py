from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import random
import sys
from pathlib import Path

import yaml

from adc_research.calibration.adaptive_two_stage import (
    TwoStageAdaptiveConfig,
    TwoStageAdaptiveState,
    cascade_from_state,
    correct_and_update,
)
from adc_research.calibration.gated_lms import GatedLmsConfig, GatedLmsState
from adc_research.calibration.known_truth import (
    TwoStagePwlCalibrationConfig,
    build_two_stage_oracle,
    correct_two_stage,
)
from adc_research.platform.pipeline import PipelineResult, process
from adc_research.platform.presets import (
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
)


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_CONFIG = Path(__file__).with_name("config.yaml")


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def source_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def scaled_steps(normalized_steps: tuple[float, ...], full_scale: float) -> tuple[float, ...]:
    return tuple(step / (full_scale * full_scale) for step in normalized_steps)


def evaluate(
    samples: list[tuple[int, tuple[int, int], PipelineResult]],
    cascade: TwoStagePwlCalibrationConfig,
) -> dict:
    absolute_error_sum = 0.0
    maximum_error = 0.0
    saturations = 0
    physical_overloads = 0
    stage1_correlation = 0.0
    stage2_correlation = 0.0
    for expected, _, raw in samples:
        result = correct_two_stage(raw, cascade)
        error = result.unclipped_output_code - expected
        absolute_error_sum += abs(error)
        maximum_error = max(maximum_error, abs(error))
        saturations += int(result.saturated_low or result.saturated_high)
        physical_overloads += int(
            any(
                not stage.correctable
                or stage.main_input_overload_low
                or stage.main_input_overload_high
                for stage in (raw.stage1, raw.stage2)
            )
            or raw.backend.overload_low
            or raw.backend.overload_high
        )
        stage1_local = result.stage1_pwl.corrected_code - result.stage1_dither_copy
        stage2_local = result.stage2_pwl.corrected_code - result.stage2_dither_copy
        stage1_correlation += result.stage1_dither_copy * stage1_local
        stage2_correlation += result.stage2_dither_copy * stage2_local
    count = len(samples)
    return {
        "checks": count,
        "mae_codes": absolute_error_sum / count,
        "maximum_absolute_error_codes": maximum_error,
        "saturations": saturations,
        "physical_overloads": physical_overloads,
        "mean_stage1_dither_output_product": stage1_correlation / count,
        "mean_stage2_dither_output_product": stage2_correlation / count,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    experiment = read_yaml(EXPERIMENT_CONFIG)
    architecture_path = ROOT / experiment["architecture_config"]
    truth_path = ROOT / experiment["truth_config"]
    architecture = read_yaml(architecture_path)
    truth_profile = read_yaml(truth_path)
    output_dir = ROOT / "artifacts" / "runs" / "EXP_010" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    output_dir.mkdir(parents=True)

    pipeline = build_gu_static_hypothesis_a(architecture)
    nonidealities = build_gu_gate_d_nonidealities(
        truth_profile,
        enabled_effects=("static_pwl_truth",),
    )
    oracle = build_two_stage_oracle(pipeline, nonidealities)
    normalized_steps = tuple(experiment["training"]["normalized_step_sizes"])
    bounds = tuple(experiment["training"]["coefficient_bounds"])
    adaptive_config = TwoStageAdaptiveConfig(
        cascade=oracle,
        stage1_lms=GatedLmsConfig(
            oracle.stage1_pwl.slice_width,
            scaled_steps(normalized_steps, oracle.stage1_pwl.full_scale_magnitude),
            bounds,
        ),
        stage2_lms=GatedLmsConfig(
            oracle.stage2_pwl.slice_width,
            scaled_steps(normalized_steps, oracle.stage2_pwl.full_scale_magnitude),
            bounds,
        ),
    )
    state = TwoStageAdaptiveState(
        stage1=GatedLmsState.unity(oracle.stage1_pwl.slice_count),
        stage2=GatedLmsState.unity(oracle.stage2_pwl.slice_count),
    )

    samples: list[tuple[int, tuple[int, int], PipelineResult]] = []
    for pair_list in experiment["dither_symbol_pairs"]:
        pair = tuple(pair_list)
        for expected in range(4096):
            value = -1.0 + (expected + 0.5) / 2048.0
            raw = process(
                value,
                pipeline,
                sample_index=len(samples),
                dither_symbols=pair,
                nonidealities=nonidealities,
            )
            samples.append((expected, pair, raw))

    unity_cascade = cascade_from_state(oracle, state)
    convergence = []

    def append_checkpoint(epoch: int) -> None:
        convergence.append(
            {
                "epoch": epoch,
                "samples": state.stage1.sample_count,
                "stage1_k1": state.stage1.coefficients[0],
                "stage1_k2": state.stage1.coefficients[1],
                "stage1_k3": state.stage1.coefficients[2],
                "stage1_k4": state.stage1.coefficients[3],
                "stage1_gate1": state.stage1.gate_counts[0],
                "stage1_gate2": state.stage1.gate_counts[1],
                "stage1_gate3": state.stage1.gate_counts[2],
                "stage1_gate4": state.stage1.gate_counts[3],
                "stage2_k1": state.stage2.coefficients[0],
                "stage2_k2": state.stage2.coefficients[1],
                "stage2_k3": state.stage2.coefficients[2],
                "stage2_k4": state.stage2.coefficients[3],
                "stage2_gate1": state.stage2.gate_counts[0],
                "stage2_gate2": state.stage2.gate_counts[1],
                "stage2_gate3": state.stage2.gate_counts[2],
                "stage2_gate4": state.stage2.gate_counts[3],
            }
        )

    checkpoint_epochs = set(experiment["training"]["checkpoint_epochs"])
    if 0 in checkpoint_epochs:
        append_checkpoint(0)
    rng = random.Random(experiment["training"]["seed"])
    training_order = list(range(len(samples)))
    for epoch in range(1, experiment["training"]["epochs"] + 1):
        rng.shuffle(training_order)
        for sample_index in training_order:
            raw = samples[sample_index][2]
            state = correct_and_update(raw, state, adaptive_config).state
        if epoch in checkpoint_epochs:
            append_checkpoint(epoch)

    final_cascade = cascade_from_state(oracle, state)
    evaluations = {
        "unity": evaluate(samples, unity_cascade),
        "adaptive": evaluate(samples, final_cascade),
        "oracle": evaluate(samples, oracle),
    }
    stage1_errors = tuple(
        actual - expected
        for actual, expected in zip(
            state.stage1.coefficients,
            oracle.stage1_pwl.slopes,
            strict=True,
        )
    )
    stage2_errors = tuple(
        actual - expected
        for actual, expected in zip(
            state.stage2.coefficients,
            oracle.stage2_pwl.slopes,
            strict=True,
        )
    )
    improvement = evaluations["unity"]["mae_codes"] / evaluations["adaptive"]["mae_codes"]
    acceptance = experiment["acceptance"]
    pass_status = all(
        (
            state.stage1.gate_counts[3]
            <= acceptance["maximum_fourth_gate_count"],
            state.stage2.gate_counts[3]
            <= acceptance["maximum_fourth_gate_count"],
            max(map(abs, stage1_errors[:2]))
            <= acceptance["maximum_stage1_k1_k2_absolute_error"],
            max(map(abs, stage2_errors[:2]))
            <= acceptance["maximum_stage2_k1_k2_absolute_error"],
            improvement
            >= acceptance["minimum_mae_improvement_ratio_over_unity"],
            evaluations["adaptive"]["mae_codes"]
            <= acceptance["maximum_adaptive_mae_codes"],
            evaluations["adaptive"]["physical_overloads"]
            <= acceptance["maximum_physical_overloads"],
        )
    )
    metrics = {
        "experiment_id": experiment["experiment_id"],
        "architecture_config": architecture["config_id"],
        "truth_config": truth_profile["config_id"],
        "mode": "two_stage_floating_adaptive_block_balanced",
        "claim_exclusion": (
            "not_hardware_prng_decimation_not_bit_true_not_outer_slice_convergence"
        ),
        "schedule": {
            "kind": experiment["training"]["schedule"],
            "epochs": experiment["training"]["epochs"],
            "samples_per_epoch": len(samples),
            "total_updates_per_stage": state.stage1.sample_count,
        },
        "oracle_coefficients": {
            "stage1": oracle.stage1_pwl.slopes,
            "stage2": oracle.stage2_pwl.slopes,
        },
        "adaptive_coefficients": {
            "stage1": state.stage1.coefficients,
            "stage2": state.stage2.coefficients,
        },
        "coefficient_errors": {
            "stage1": stage1_errors,
            "stage2": stage2_errors,
        },
        "gate_counts": {
            "stage1": state.stage1.gate_counts,
            "stage2": state.stage2.gate_counts,
        },
        "evaluations": evaluations,
        "mae_improvement_ratio_over_unity": improvement,
        "pass": pass_status,
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    with (output_dir / "convergence.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=convergence[0].keys())
        writer.writeheader()
        writer.writerows(convergence)
    (output_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(
            {
                "experiment": experiment,
                "architecture": architecture,
                "truth_profile": truth_profile,
                "resolved_step_sizes": {
                    "stage1": adaptive_config.stage1_lms.step_sizes,
                    "stage2": adaptive_config.stage2_lms.step_sizes,
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    tracked_sources = [
        EXPERIMENT_CONFIG,
        architecture_path,
        truth_path,
        ROOT / "src" / "adc_research" / "calibration" / "pwl.py",
        ROOT / "src" / "adc_research" / "calibration" / "gated_lms.py",
        ROOT / "src" / "adc_research" / "calibration" / "adaptive_two_stage.py",
        ROOT / "src" / "adc_research" / "calibration" / "known_truth.py",
    ]
    (output_dir / "environment.json").write_text(
        json.dumps(
            {
                "python": sys.version,
                "platform": platform.platform(),
                "argv": sys.argv,
                "source_sha256": source_hash(tracked_sources),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(metrics, indent=2))
    print(output_dir)
    if not pass_status:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
