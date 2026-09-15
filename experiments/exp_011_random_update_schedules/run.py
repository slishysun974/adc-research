from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import random
import statistics
import sys
from dataclasses import dataclass
from math import sqrt
from pathlib import Path

import yaml

from adc_research.calibration.adaptive_two_stage import (
    TwoStageAdaptiveConfig,
    TwoStageAdaptiveObservation,
    TwoStageAdaptiveState,
    cascade_from_state,
    correct_and_update,
    observe,
    update_block_mean_observations,
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


def scaled_steps(
    normalized_steps: tuple[float, ...],
    full_scale: float,
    step_scale: float,
) -> tuple[float, ...]:
    return tuple(
        step_scale * step / (full_scale * full_scale)
        for step in normalized_steps
    )


@dataclass
class PairedMoments:
    count: int = 0
    sum_x: float = 0.0
    sum_y: float = 0.0
    sum_x2: float = 0.0
    sum_y2: float = 0.0
    sum_xy: float = 0.0

    def add(self, x: float, y: float) -> None:
        self.count += 1
        self.sum_x += x
        self.sum_y += y
        self.sum_x2 += x * x
        self.sum_y2 += y * y
        self.sum_xy += x * y

    def summary(self) -> dict:
        if self.count == 0:
            raise ValueError("cannot summarize empty moments")
        mean_x = self.sum_x / self.count
        mean_y = self.sum_y / self.count
        mean_xy = self.sum_xy / self.count
        variance_x = max(self.sum_x2 / self.count - mean_x * mean_x, 0.0)
        variance_y = max(self.sum_y2 / self.count - mean_y * mean_y, 0.0)
        denominator = sqrt(variance_x * variance_y)
        correlation = (
            (mean_xy - mean_x * mean_y) / denominator
            if denominator > 0
            else 0.0
        )
        return {
            "count": self.count,
            "mean_x": mean_x,
            "mean_y": mean_y,
            "mean_product": mean_xy,
            "correlation": correlation,
        }


def evaluate(
    samples: list[tuple[int, tuple[int, int], PipelineResult]],
    cascade: TwoStagePwlCalibrationConfig,
) -> dict:
    absolute_error_sum = 0.0
    maximum_error = 0.0
    saturations = 0
    physical_overloads = 0
    stage1_product = 0.0
    stage2_product = 0.0
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
        stage1_product += result.stage1_dither_copy * stage1_local
        stage2_product += result.stage2_dither_copy * stage2_local
    count = len(samples)
    return {
        "checks": count,
        "mae_codes": absolute_error_sum / count,
        "maximum_absolute_error_codes": maximum_error,
        "saturations": saturations,
        "physical_overloads": physical_overloads,
        "mean_stage1_dither_output_product": stage1_product / count,
        "mean_stage2_dither_output_product": stage2_product / count,
    }


def build_adaptive_config(
    oracle: TwoStagePwlCalibrationConfig,
    normalized_steps: tuple[float, ...],
    bounds: tuple[float, float],
    step_scale: float,
) -> TwoStageAdaptiveConfig:
    return TwoStageAdaptiveConfig(
        cascade=oracle,
        stage1_lms=GatedLmsConfig(
            oracle.stage1_pwl.slice_width,
            scaled_steps(
                normalized_steps,
                oracle.stage1_pwl.full_scale_magnitude,
                step_scale,
            ),
            bounds,
        ),
        stage2_lms=GatedLmsConfig(
            oracle.stage2_pwl.slice_width,
            scaled_steps(
                normalized_steps,
                oracle.stage2_pwl.full_scale_magnitude,
                step_scale,
            ),
            bounds,
        ),
    )


def initial_state(
    oracle: TwoStagePwlCalibrationConfig,
    coefficients: dict | None = None,
) -> TwoStageAdaptiveState:
    if coefficients is None:
        return TwoStageAdaptiveState(
            stage1=GatedLmsState.unity(oracle.stage1_pwl.slice_count),
            stage2=GatedLmsState.unity(oracle.stage2_pwl.slice_count),
        )
    return TwoStageAdaptiveState(
        stage1=GatedLmsState(
            coefficients=tuple(coefficients["stage1"]),
            gate_counts=(0,) * oracle.stage1_pwl.slice_count,
        ),
        stage2=GatedLmsState(
            coefficients=tuple(coefficients["stage2"]),
            gate_counts=(0,) * oracle.stage2_pwl.slice_count,
        ),
    )


def maximum_low_slice_error(
    state: TwoStageAdaptiveState,
    oracle: TwoStagePwlCalibrationConfig,
) -> float:
    return max(
        abs(actual - expected)
        for actual, expected in (
            *zip(state.stage1.coefficients[:2], oracle.stage1_pwl.slopes[:2]),
            *zip(state.stage2.coefficients[:2], oracle.stage2_pwl.slopes[:2]),
        )
    )


def coefficient_variances(
    snapshots: list[tuple[tuple[float, ...], tuple[float, ...]]],
) -> dict:
    if len(snapshots) < 2:
        raise ValueError("steady-state variance requires at least two snapshots")
    return {
        "stage1": tuple(
            statistics.pvariance(snapshot[0][index] for snapshot in snapshots)
            for index in range(4)
        ),
        "stage2": tuple(
            statistics.pvariance(snapshot[1][index] for snapshot in snapshots)
            for index in range(4)
        ),
    }


def train_case(
    *,
    schedule: dict,
    replication: int,
    training: dict,
    oracle: TwoStagePwlCalibrationConfig,
    sample_lookup: dict[tuple[int, int, int], PipelineResult],
    evaluation_samples: list[tuple[int, tuple[int, int], PipelineResult]],
) -> tuple[dict, list[dict]]:
    period = int(schedule["period"])
    kind = schedule["kind"]
    if period <= 0:
        raise ValueError("schedule period must be positive")
    if kind not in {"instantaneous", "subsampled_instantaneous", "block_mean"}:
        raise ValueError(f"unsupported schedule kind: {kind}")
    sample_count = int(training["samples_per_replication"])
    if kind == "block_mean" and sample_count % period:
        raise ValueError("block-mean sample count must be divisible by period")

    normalized_steps = tuple(training["normalized_step_sizes"])
    bounds = tuple(training["coefficient_bounds"])
    config = build_adaptive_config(
        oracle,
        normalized_steps,
        bounds,
        float(schedule["step_scale"]),
    )
    state = initial_state(oracle, training.get("initial_coefficients"))
    seed_base = int(training["base_seed"]) + 1009 * replication
    rng_signal = random.Random(seed_base ^ 0x13579BDF)
    rng_dither1 = random.Random(seed_base ^ 0x2468ACE1)
    rng_dither2 = random.Random(seed_base ^ 0x6A09E667)

    all_moments = {
        "prng_cross": PairedMoments(),
        "stage1_own": PairedMoments(),
        "stage2_own": PairedMoments(),
        "stage1_to_stage2": PairedMoments(),
        "stage2_to_stage1": PairedMoments(),
    }
    steady_moments = {name: PairedMoments() for name in all_moments}
    steady_start = int(training["steady_state_start_sample"])
    snapshot_period = int(training["steady_state_snapshot_period"])
    steady_snapshots: list[tuple[tuple[float, ...], tuple[float, ...]]] = []
    convergence: list[dict] = []
    checkpoints = set(training["checkpoint_samples"])
    update_events = 0
    physical_overloads = 0
    block: list[TwoStageAdaptiveObservation] = []

    def append_checkpoint(adc_samples: int) -> None:
        convergence.append(
            {
                "schedule": schedule["name"],
                "replication": replication,
                "adc_samples": adc_samples,
                "update_events": update_events,
                "stage1_observations_used": state.stage1.sample_count,
                "stage2_observations_used": state.stage2.sample_count,
                "maximum_low_slice_coefficient_error": maximum_low_slice_error(
                    state,
                    oracle,
                ),
                **{
                    f"stage1_k{index + 1}": value
                    for index, value in enumerate(state.stage1.coefficients)
                },
                **{
                    f"stage2_k{index + 1}": value
                    for index, value in enumerate(state.stage2.coefficients)
                },
            }
        )

    if 0 in checkpoints:
        append_checkpoint(0)

    for adc_sample in range(1, sample_count + 1):
        expected = rng_signal.randrange(4096)
        dither1 = -1 if rng_dither1.getrandbits(1) == 0 else 1
        dither2 = -1 if rng_dither2.getrandbits(1) == 0 else 1
        raw = sample_lookup[(expected, dither1, dither2)]

        if kind == "instantaneous":
            result = correct_and_update(raw, state, config)
            observation = TwoStageAdaptiveObservation(
                calibration=result.calibration,
                stage1_local_learning_output=result.stage1_local_learning_output,
                stage2_local_learning_output=result.stage2_local_learning_output,
            )
            state = result.state
            update_events += 1
        else:
            observation = observe(raw, state, config)
            if kind == "subsampled_instantaneous" and adc_sample % period == 0:
                state = update_block_mean_observations(
                    state,
                    (observation,),
                    config,
                ).state
                update_events += 1
            elif kind == "block_mean":
                block.append(observation)
                if len(block) == period:
                    state = update_block_mean_observations(
                        state,
                        block,
                        config,
                    ).state
                    block.clear()
                    update_events += 1

        calibration = observation.calibration
        dither1_code = calibration.stage1_dither_copy
        dither2_code = calibration.stage2_dither_copy
        local1 = observation.stage1_local_learning_output
        local2 = observation.stage2_local_learning_output
        pairs = {
            "prng_cross": (float(dither1), float(dither2)),
            "stage1_own": (dither1_code, local1),
            "stage2_own": (dither2_code, local2),
            "stage1_to_stage2": (dither1_code, local2),
            "stage2_to_stage1": (dither2_code, local1),
        }
        for name, (x, y) in pairs.items():
            all_moments[name].add(x, y)
            if adc_sample > steady_start:
                steady_moments[name].add(x, y)
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

        if adc_sample >= steady_start and adc_sample % snapshot_period == 0:
            steady_snapshots.append(
                (state.stage1.coefficients, state.stage2.coefficients)
            )
        if adc_sample in checkpoints:
            append_checkpoint(adc_sample)

    if block:
        raise AssertionError("block-mean schedule ended with a partial block")

    final_cascade = cascade_from_state(oracle, state)
    evaluation = evaluate(evaluation_samples, final_cascade)
    threshold = float(training["low_slice_error_threshold"])
    time_to_threshold = next(
        (
            row["adc_samples"]
            for row in convergence
            if row["maximum_low_slice_coefficient_error"] <= threshold
        ),
        None,
    )
    prng_summary = all_moments["prng_cross"].summary()
    row = {
        "schedule": schedule["name"],
        "kind": kind,
        "period": period,
        "step_scale": float(schedule["step_scale"]),
        "replication": replication,
        "adc_samples": sample_count,
        "update_events": update_events,
        "stage1_observations_used": state.stage1.sample_count,
        "stage2_observations_used": state.stage2.sample_count,
        "stage1_coefficients": state.stage1.coefficients,
        "stage2_coefficients": state.stage2.coefficients,
        "stage1_gate_counts": state.stage1.gate_counts,
        "stage2_gate_counts": state.stage2.gate_counts,
        "maximum_low_slice_coefficient_error": maximum_low_slice_error(state, oracle),
        "time_to_low_slice_error_threshold_samples": time_to_threshold,
        "steady_coefficient_variances": coefficient_variances(steady_snapshots),
        "all_sample_moments": {
            name: value.summary() for name, value in all_moments.items()
        },
        "steady_sample_moments": {
            name: value.summary() for name, value in steady_moments.items()
        },
        "absolute_prng_cross_correlation_z": abs(prng_summary["correlation"])
        * sqrt(prng_summary["count"]),
        "physical_overloads": physical_overloads,
        "evaluation": evaluation,
    }
    return row, convergence


def mean_and_std(values: list[float]) -> dict:
    return {
        "mean": statistics.fmean(values),
        "population_std": statistics.pstdev(values),
        "minimum": min(values),
        "maximum": max(values),
    }


def aggregate_schedule(name: str, rows: list[dict]) -> dict:
    selected = [row for row in rows if row["schedule"] == name]
    if not selected:
        raise ValueError(f"no rows for schedule {name}")
    reached_threshold = [
        row["time_to_low_slice_error_threshold_samples"]
        for row in selected
        if row["time_to_low_slice_error_threshold_samples"] is not None
    ]
    return {
        "replications": len(selected),
        "final_mae_codes": mean_and_std(
            [row["evaluation"]["mae_codes"] for row in selected]
        ),
        "final_maximum_absolute_error_codes": mean_and_std(
            [row["evaluation"]["maximum_absolute_error_codes"] for row in selected]
        ),
        "maximum_low_slice_coefficient_error": mean_and_std(
            [row["maximum_low_slice_coefficient_error"] for row in selected]
        ),
        "time_to_low_slice_error_threshold_samples": {
            "values": [
                row["time_to_low_slice_error_threshold_samples"] for row in selected
            ],
            "reached_count": len(reached_threshold),
            "median_of_reached": (
                statistics.median(reached_threshold) if reached_threshold else None
            ),
        },
        "mean_within_replication_steady_low_slice_variance": statistics.fmean(
            statistics.fmean(
                (*row["steady_coefficient_variances"]["stage1"][:2],
                 *row["steady_coefficient_variances"]["stage2"][:2])
            )
            for row in selected
        ),
        "maximum_absolute_prng_cross_correlation_z": max(
            row["absolute_prng_cross_correlation_z"] for row in selected
        ),
        "mean_steady_cross_stage_correlations": {
            "stage1_dither_to_stage2_output": statistics.fmean(
                row["steady_sample_moments"]["stage1_to_stage2"]["correlation"]
                for row in selected
            ),
            "stage2_dither_to_stage1_output": statistics.fmean(
                row["steady_sample_moments"]["stage2_to_stage1"]["correlation"]
                for row in selected
            ),
        },
        "total_physical_overloads": sum(row["physical_overloads"] for row in selected),
        "maximum_fourth_gate_count": max(
            max(row["stage1_gate_counts"][3], row["stage2_gate_counts"][3])
            for row in selected
        ),
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
    output_dir = ROOT / "artifacts" / "runs" / "EXP_011" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    output_dir.mkdir(parents=True)

    pipeline = build_gu_static_hypothesis_a(architecture)
    nonidealities = build_gu_gate_d_nonidealities(
        truth_profile,
        enabled_effects=("static_pwl_truth",),
    )
    oracle = build_two_stage_oracle(pipeline, nonidealities)
    evaluation_samples: list[tuple[int, tuple[int, int], PipelineResult]] = []
    sample_lookup: dict[tuple[int, int, int], PipelineResult] = {}
    for dither1 in (-1, 1):
        for dither2 in (-1, 1):
            pair = (dither1, dither2)
            for expected in range(4096):
                value = -1.0 + (expected + 0.5) / 2048.0
                raw = process(
                    value,
                    pipeline,
                    sample_index=len(evaluation_samples),
                    dither_symbols=pair,
                    nonidealities=nonidealities,
                )
                evaluation_samples.append((expected, pair, raw))
                sample_lookup[(expected, dither1, dither2)] = raw

    unity = initial_state(oracle)
    reference_evaluations = {
        "unity": evaluate(
            evaluation_samples,
            cascade_from_state(oracle, unity),
        ),
        "oracle": evaluate(evaluation_samples, oracle),
    }
    rows: list[dict] = []
    convergence: list[dict] = []
    for schedule in experiment["schedules"]:
        for replication in range(int(experiment["training"]["replications"])):
            row, trace = train_case(
                schedule=schedule,
                replication=replication,
                training=experiment["training"],
                oracle=oracle,
                sample_lookup=sample_lookup,
                evaluation_samples=evaluation_samples,
            )
            rows.append(row)
            convergence.extend(trace)

    aggregates = {
        schedule["name"]: aggregate_schedule(schedule["name"], rows)
        for schedule in experiment["schedules"]
    }
    block_variance = aggregates["block_mean_30"][
        "mean_within_replication_steady_low_slice_variance"
    ]
    every_variance = aggregates["every_sample"][
        "mean_within_replication_steady_low_slice_variance"
    ]
    subsampled_variance = aggregates["one_sample_per_30"][
        "mean_within_replication_steady_low_slice_variance"
    ]
    variance_ratio = block_variance / subsampled_variance
    block_to_every_variance_relative_difference = abs(
        block_variance - every_variance
    ) / every_variance
    block_mae = aggregates["block_mean_30"]["final_mae_codes"]["mean"]
    every_mae = aggregates["every_sample"]["final_mae_codes"]["mean"]
    block_to_every_mae_relative_difference = abs(block_mae - every_mae) / every_mae
    unity_mae = reference_evaluations["unity"]["mae_codes"]
    acceptance = experiment["acceptance"]
    pass_status = all(
        (
            max(
                aggregate["maximum_absolute_prng_cross_correlation_z"]
                for aggregate in aggregates.values()
            )
            <= acceptance["maximum_absolute_prng_cross_correlation_z"],
            sum(
                aggregate["total_physical_overloads"]
                for aggregate in aggregates.values()
            )
            <= acceptance["maximum_physical_overloads"],
            max(
                aggregate["maximum_fourth_gate_count"]
                for aggregate in aggregates.values()
            )
            <= acceptance["maximum_fourth_gate_count"],
            max(block_mae, every_mae) / unity_mae
            <= acceptance["maximum_low_variance_schedule_mae_ratio_to_unity"],
            variance_ratio
            <= acceptance["maximum_block_to_subsampled_steady_variance_ratio"],
            block_to_every_variance_relative_difference
            <= acceptance[
                "maximum_block_to_every_steady_variance_relative_difference"
            ],
            block_to_every_mae_relative_difference
            <= acceptance["maximum_block_to_every_final_mae_relative_difference"],
        )
    )
    metrics = {
        "experiment_id": experiment["experiment_id"],
        "architecture_config": architecture["config_id"],
        "truth_config": truth_profile["config_id"],
        "mode": "two_stage_floating_random_schedule_comparison",
        "claim_exclusion": (
            "software_prng_not_hardware_prng_not_bit_true_decimator_or_coefficient_extractor"
        ),
        "paper_reported_rates": {
            "adc_sample_rate_hz": 3.0e9,
            "parallel_lanes": 4,
            "per_lane_rate_hz": 750.0e6,
            "per_lane_rate_after_decimate_by_30_hz": 25.0e6,
            "merged_observation_rate_after_decimate_by_30_hz": 100.0e6,
            "single_selected_output_rate_after_4_to_1_mux_hz": 25.0e6,
        },
        "comparison_normalization": (
            "periodic schedules use period-times step size so first-order mean "
            "coefficient drift is normalized per ADC input sample"
        ),
        "oracle_coefficients": {
            "stage1": oracle.stage1_pwl.slopes,
            "stage2": oracle.stage2_pwl.slopes,
        },
        "reference_evaluations": reference_evaluations,
        "schedule_aggregates": aggregates,
        "block_to_subsampled_steady_low_slice_variance_ratio": variance_ratio,
        "block_to_every_steady_low_slice_variance_relative_difference": (
            block_to_every_variance_relative_difference
        ),
        "block_to_every_final_mae_relative_difference": (
            block_to_every_mae_relative_difference
        ),
        "replication_results": rows,
        "pass": pass_status,
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )
    with (output_dir / "convergence.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=convergence[0].keys())
        writer.writeheader()
        writer.writerows(convergence)
    with (output_dir / "replications.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        flat_rows = [
            {
                "schedule": row["schedule"],
                "replication": row["replication"],
                "update_events": row["update_events"],
                "maximum_low_slice_coefficient_error": row[
                    "maximum_low_slice_coefficient_error"
                ],
                "time_to_threshold_samples": row[
                    "time_to_low_slice_error_threshold_samples"
                ],
                "steady_low_slice_variance": statistics.fmean(
                    (
                        *row["steady_coefficient_variances"]["stage1"][:2],
                        *row["steady_coefficient_variances"]["stage2"][:2],
                    )
                ),
                "prng_cross_correlation_z": row[
                    "absolute_prng_cross_correlation_z"
                ],
                "stage1_to_stage2_steady_correlation": row[
                    "steady_sample_moments"
                ]["stage1_to_stage2"]["correlation"],
                "stage2_to_stage1_steady_correlation": row[
                    "steady_sample_moments"
                ]["stage2_to_stage1"]["correlation"],
                "mae_codes": row["evaluation"]["mae_codes"],
                "maximum_absolute_error_codes": row["evaluation"][
                    "maximum_absolute_error_codes"
                ],
            }
            for row in rows
        ]
        writer = csv.DictWriter(handle, fieldnames=flat_rows[0].keys())
        writer.writeheader()
        writer.writerows(flat_rows)
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
    print(json.dumps({key: value for key, value in metrics.items() if key != "replication_results"}, indent=2))
    print(output_dir)
    if not pass_status:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
