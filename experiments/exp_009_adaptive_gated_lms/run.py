from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import random
import sys
from dataclasses import asdict
from math import sqrt
from pathlib import Path

import yaml

from adc_research.calibration.gated_lms import (
    GatedLmsConfig,
    GatedLmsState,
    adaptive_lower_thresholds,
    update,
)
from adc_research.calibration.known_truth import oracle_pwl_config
from adc_research.calibration.pwl import PwlConfig, correct
from adc_research.platform.amplifier import (
    StaticPwlTruthConfig,
    amplify_static_pwl_truth,
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


def build_truth(profile: dict) -> StaticPwlTruthConfig:
    return StaticPwlTruthConfig(
        tuple(profile["ideal_output_edges"]),
        tuple(profile["distorted_output_edges"]),
    )


def plant_output(value: float, truth: StaticPwlTruthConfig) -> float:
    return amplify_static_pwl_truth(
        value / 4.0,
        nominal_gain=4.0,
        truth=truth,
    ).output_value


def evaluate(
    truth: StaticPwlTruthConfig,
    coefficients: tuple[float, ...],
    *,
    half_range: float,
    points: int,
) -> dict:
    if points < 2:
        raise ValueError("evaluation grid requires at least two points")
    config = PwlConfig(0.25, coefficients)
    squared_error = 0.0
    maximum_error = 0.0
    for index in range(points):
        value = -half_range + 2.0 * half_range * index / (points - 1)
        raw = plant_output(value, truth)
        calibrated = correct(raw, config).corrected_code
        error = calibrated - value
        squared_error += error * error
        maximum_error = max(maximum_error, abs(error))
    return {
        "points": points,
        "rms_error": sqrt(squared_error / points),
        "maximum_absolute_error": maximum_error,
    }


def train_case(
    *,
    stage_name: str,
    truth: StaticPwlTruthConfig,
    profile_name: str,
    profile: dict,
    training: dict,
    evaluation_points: int,
    seed: int,
) -> tuple[dict, list[dict]]:
    slice_width = training["normalized_slice_width"]
    dither_magnitude = training["normalized_dither_half_amplitude"]
    coefficient_bounds = tuple(training["coefficient_bounds"])
    config = GatedLmsConfig(
        slice_width=slice_width,
        step_sizes=tuple(training["step_sizes"]),
        coefficient_bounds=coefficient_bounds,
    )
    state = GatedLmsState(
        coefficients=tuple(training["initial_coefficients"]),
        gate_counts=(0,) * config.coefficient_count,
    )
    oracle = oracle_pwl_config(truth, raw_code_full_scale=1.0)
    rng_signal = random.Random(seed)
    rng_dither = random.Random(seed ^ 0x5A17)
    half_range = profile["half_range"]
    checkpoints = set(training["checkpoints"])
    trace: list[dict] = []
    truth_slice_counts = [0] * truth.slice_count
    maximum_threshold_identity_error = 0.0
    paired_dither = training["paired_dither_probe"]
    if paired_dither and training["samples"] % 2:
        raise ValueError("paired dither probe requires an even sample count")
    pair_base = 0.0
    pair_first_symbol = 1

    def append_checkpoint(sample_count: int) -> None:
        thresholds = adaptive_lower_thresholds(
            state.coefficients,
            slice_width,
        )
        trace.append(
            {
                "stage": stage_name,
                "profile": profile_name,
                "sample_count": sample_count,
                "k1": state.coefficients[0],
                "k2": state.coefficients[1],
                "k3": state.coefficients[2],
                "k4": state.coefficients[3],
                "b1": thresholds[1],
                "b2": thresholds[2],
                "b3": thresholds[3],
                "gate1": state.gate_counts[0],
                "gate2": state.gate_counts[1],
                "gate3": state.gate_counts[2],
                "gate4": state.gate_counts[3],
            }
        )

    if 0 in checkpoints:
        append_checkpoint(0)

    for sample_index in range(1, training["samples"] + 1):
        if paired_dither:
            if sample_index % 2:
                pair_base = rng_signal.uniform(-half_range, half_range)
                pair_first_symbol = -1 if rng_dither.getrandbits(1) == 0 else 1
                dither_symbol = pair_first_symbol
            else:
                dither_symbol = -pair_first_symbol
            base_value = pair_base
        else:
            base_value = rng_signal.uniform(-half_range, half_range)
            dither_symbol = -1 if rng_dither.getrandbits(1) == 0 else 1
        dither = dither_symbol * dither_magnitude
        plant_input = base_value + dither
        if not -1.0 <= plant_input <= 1.0:
            raise AssertionError("training stimulus left PWL truth domain")
        amplified = amplify_static_pwl_truth(
            plant_input / 4.0,
            nominal_gain=4.0,
            truth=truth,
        )
        truth_slice_counts[amplified.slice_index] += 1
        estimate = PwlConfig(slice_width, state.coefficients)
        corrected_before_subtraction = correct(
            amplified.output_value,
            estimate,
        ).corrected_code
        corrected_output = corrected_before_subtraction - dither
        result = update(
            state,
            dither_code=dither,
            corrected_output=corrected_output,
            config=config,
        )
        expected_thresholds = adaptive_lower_thresholds(
            result.coefficients_before,
            slice_width,
        )
        maximum_threshold_identity_error = max(
            maximum_threshold_identity_error,
            max(
                abs(actual - expected)
                for actual, expected in zip(
                    result.adaptive_lower_thresholds,
                    expected_thresholds,
                    strict=True,
                )
            ),
        )
        state = result.state
        if sample_index in checkpoints:
            append_checkpoint(sample_index)

    initial_evaluation = evaluate(
        truth,
        tuple(training["initial_coefficients"]),
        half_range=half_range,
        points=evaluation_points,
    )
    final_evaluation = evaluate(
        truth,
        state.coefficients,
        half_range=half_range,
        points=evaluation_points,
    )
    coefficient_errors = tuple(
        actual - expected
        for actual, expected in zip(
            state.coefficients,
            oracle.slopes,
            strict=True,
        )
    )
    row = {
        "stage": stage_name,
        "profile": profile_name,
        "profile_interpretation": profile["interpretation"],
        "samples": state.sample_count,
        "half_range_after_dither_subtraction": half_range,
        "dither_half_amplitude": dither_magnitude,
        "paired_dither_probe": paired_dither,
        "oracle_coefficients": oracle.slopes,
        "final_coefficients": state.coefficients,
        "coefficient_errors": coefficient_errors,
        "maximum_coefficient_absolute_error": max(map(abs, coefficient_errors)),
        "gate_counts": state.gate_counts,
        "gate_fractions": tuple(
            count / state.sample_count for count in state.gate_counts
        ),
        "truth_slice_counts_before_dither_subtraction": tuple(truth_slice_counts),
        "final_adaptive_lower_thresholds": adaptive_lower_thresholds(
            state.coefficients,
            slice_width,
        ),
        "maximum_threshold_identity_error": maximum_threshold_identity_error,
        "initial_evaluation": initial_evaluation,
        "final_evaluation": final_evaluation,
        "rms_improvement_ratio": (
            initial_evaluation["rms_error"] / final_evaluation["rms_error"]
            if final_evaluation["rms_error"] > 0
            else float("inf")
        ),
    }
    return row, trace


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    experiment = read_yaml(EXPERIMENT_CONFIG)
    architecture_path = ROOT / experiment["architecture_config"]
    truth_path = ROOT / experiment["truth_config"]
    architecture = read_yaml(architecture_path)
    truth_profile = read_yaml(truth_path)
    output_dir = ROOT / "artifacts" / "runs" / "EXP_009" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    output_dir.mkdir(parents=True)

    truths = {
        stage: build_truth(
            truth_profile["effects"]["static_pwl_truth"][stage]
        )
        for stage in ("stage1", "stage2")
    }
    rows = []
    traces = []
    for stage_index, (stage_name, truth) in enumerate(truths.items()):
        for profile_index, (profile_name, profile) in enumerate(
            experiment["stimulus_profiles"].items()
        ):
            row, trace = train_case(
                stage_name=stage_name,
                truth=truth,
                profile_name=profile_name,
                profile=profile,
                training=experiment["training"],
                evaluation_points=experiment["evaluation_grid_points"],
                seed=(
                    experiment["training"]["seed"]
                    + 1000 * stage_index
                    + profile_index
                ),
            )
            rows.append(row)
            traces.extend(trace)

    acceptance = experiment["acceptance"]
    nominal_rows = [row for row in rows if row["profile"] == "nominal_residue"]
    expanded_rows = [row for row in rows if row["profile"] == "expanded_residue"]
    pass_status = all(
        (
            all(
                row["gate_counts"][3]
                == acceptance["nominal_fourth_gate_count"]
                for row in nominal_rows
            ),
            all(
                abs(row["final_coefficients"][3] - 1.0)
                <= acceptance["nominal_fourth_coefficient_change"]
                for row in nominal_rows
            ),
            all(
                row["gate_counts"][3]
                >= acceptance["minimum_expanded_fourth_gate_count"]
                for row in expanded_rows
            ),
            all(
                row["maximum_coefficient_absolute_error"]
                <= acceptance["maximum_expanded_coefficient_absolute_error"]
                for row in expanded_rows
            ),
            all(
                row["rms_improvement_ratio"]
                >= acceptance["minimum_expanded_rms_improvement_ratio"]
                for row in expanded_rows
            ),
            all(
                row["maximum_threshold_identity_error"]
                <= acceptance["maximum_adaptive_threshold_identity_error"]
                for row in rows
            ),
        )
    )

    # Counterexample from the paper's monotonicity warning.  An upper-bound
    # gate maps the larger member to zero while retaining the smaller member.
    band_gate_boundary = 0.5
    lower_output = 0.49
    upper_output = 0.51
    band_gated_lower = lower_output if lower_output < band_gate_boundary else 0.0
    band_gated_upper = upper_output if upper_output < band_gate_boundary else 0.0
    band_gate_order_reversal = band_gated_upper < band_gated_lower

    metrics = {
        "experiment_id": experiment["experiment_id"],
        "architecture_config": architecture["config_id"],
        "truth_config": truth_profile["config_id"],
        "mode": "floating_gated_lms_primitive",
        "claim_exclusion": (
            "not_two_stage_joint_convergence_not_bit_true_not_silicon_statistics"
        ),
        "paper_equation_contract": {
            "k1_uses_all_samples": True,
            "higher_coefficients_use_adaptive_lower_threshold_only": True,
            "simultaneous_preupdate_threshold_evaluation": True,
            "band_gate_order_reversal_counterexample": band_gate_order_reversal,
        },
        "cases": rows,
        "pass": pass_status and band_gate_order_reversal,
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    with (output_dir / "convergence.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=traces[0].keys())
        writer.writeheader()
        writer.writerows(traces)
    (output_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(
            {
                "experiment": experiment,
                "architecture": architecture,
                "truth_profile": truth_profile,
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
        ROOT / "src" / "adc_research" / "platform" / "amplifier.py",
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
    if not metrics["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
