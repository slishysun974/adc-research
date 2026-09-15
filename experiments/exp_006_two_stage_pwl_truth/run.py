from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from dataclasses import asdict
from pathlib import Path

import yaml

from adc_research.calibration.known_truth import (
    build_two_stage_oracle,
    correct_two_stage,
)
from adc_research.calibration.pwl import correct
from adc_research.platform.amplifier import (
    StaticPwlTruthConfig,
    amplify_static_pwl_truth,
)
from adc_research.platform.pipeline import StaticPipelineNonidealities, process
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stage import StaticStageNonidealities


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


def continuous_inverse_audit(
    truth: StaticPwlTruthConfig,
    oracle,
    *,
    code_full_scale: float,
    probe_count: int,
) -> dict:
    maximum_error = 0.0
    checks = 0
    for index in range(-probe_count, probe_count):
        ideal_output = index / probe_count * truth.ideal_output_edges[-1]
        amplified = amplify_static_pwl_truth(
            ideal_output / 4,
            nominal_gain=4,
            truth=truth,
        )
        raw_code_coordinate = (
            amplified.output_value
            / truth.distorted_output_edges[-1]
            * code_full_scale
        )
        recovered = correct(raw_code_coordinate, oracle).corrected_code
        expected = (
            ideal_output / truth.ideal_output_edges[-1] * code_full_scale
        )
        maximum_error = max(maximum_error, abs(recovered - expected))
        checks += 1
    return {"checks": checks, "maximum_error_codes": maximum_error}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    experiment = read_yaml(EXPERIMENT_CONFIG)
    architecture_path = ROOT / experiment["architecture_config"]
    architecture = read_yaml(architecture_path)
    output_dir = ROOT / "artifacts" / "runs" / "EXP_006" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    output_dir.mkdir(parents=True)

    base = build_gu_static_hypothesis_a(
        architecture,
        dither_profile=experiment["dither_profile"],
    )
    truth1 = build_truth(experiment["pwl_truths"]["stage1"])
    truth2 = build_truth(experiment["pwl_truths"]["stage2"])
    pipeline = base
    nonidealities = StaticPipelineNonidealities(
        stage1=StaticStageNonidealities(pwl_truth=truth1),
        stage2=StaticStageNonidealities(pwl_truth=truth2),
    )
    oracle = build_two_stage_oracle(pipeline, nonidealities)

    expected_stage1 = experiment["pwl_truths"]["stage1"][
        "expected_oracle_slopes"
    ]
    expected_stage2 = experiment["pwl_truths"]["stage2"][
        "expected_oracle_slopes"
    ]
    coefficient_error = max(
        abs(actual - expected)
        for actual, expected in zip(
            oracle.stage1_pwl.slopes + oracle.stage2_pwl.slopes,
            tuple(expected_stage1) + tuple(expected_stage2),
            strict=True,
        )
    )

    probes = experiment["continuous_inverse_probe_count"]
    continuous = {
        "stage1": continuous_inverse_audit(
            truth1,
            oracle.stage1_pwl,
            code_full_scale=experiment["pwl_truths"]["stage1"][
                "raw_code_full_scale"
            ],
            probe_count=probes,
        ),
        "stage2": continuous_inverse_audit(
            truth2,
            oracle.stage2_pwl,
            code_full_scale=experiment["pwl_truths"]["stage2"][
                "raw_code_full_scale"
            ],
            probe_count=probes,
        ),
    }

    pair_rows = []
    representative_traces = []
    total_checks = 0
    total_corrected_absolute_error = 0.0
    total_uncorrected_absolute_error = 0.0
    total_wrong_order_absolute_error = 0.0
    maximum_corrected_error = 0.0
    maximum_uncorrected_error = 0.0
    maximum_wrong_order_error = 0.0
    total_negative_steps = 0
    total_flat_steps = 0
    physical_overloads = 0
    calibrated_saturation_codes: list[int] = []
    stage1_truth_slices = [0] * truth1.slice_count
    stage2_truth_slices = [0] * truth2.slice_count
    stage1_correction_slices = [0] * oracle.stage1_pwl.slice_count
    stage2_correction_slices = [0] * oracle.stage2_pwl.slice_count

    for pair_list in experiment["dither_symbol_pairs"]:
        pair = tuple(pair_list)
        corrected_errors = []
        uncorrected_errors = []
        wrong_order_errors = []
        corrected_outputs = []
        pair_physical_overloads = 0
        pair_saturations = 0

        for expected in range(4096):
            value = -1 + (expected + 0.5) / 2048
            raw = process(
                value,
                pipeline,
                sample_index=expected,
                dither_symbols=pair,
                nonidealities=nonidealities,
            )
            calibrated = correct_two_stage(raw, oracle)

            corrected_error = calibrated.unclipped_output_code - expected
            uncorrected_error = (
                raw.reconstruction.unclipped_output_code - expected
            )

            # Counterfactual order audit: keep dither2 inside PWL1 and subtract
            # it afterward.  This is intentionally not a supported core path.
            wrong_stage1_input = (
                oracle.stage2_symbol_weight * raw.stage2.quantizer.symbol
                + calibrated.stage2_pwl.corrected_code
            )
            wrong_stage1 = correct(wrong_stage1_input, oracle.stage1_pwl)
            wrong_output = (
                oracle.output_offset
                + oracle.stage1_symbol_weight * raw.stage1.quantizer.symbol
                + wrong_stage1.corrected_code
                - calibrated.stage2_dither_copy
                - calibrated.stage1_dither_copy
            )
            wrong_order_error = wrong_output - expected

            corrected_errors.append(corrected_error)
            uncorrected_errors.append(uncorrected_error)
            wrong_order_errors.append(wrong_order_error)
            corrected_outputs.append(calibrated.unclipped_output_code)
            stage1_truth_slices[raw.stage1.amplifier.slice_index] += 1
            stage2_truth_slices[raw.stage2.amplifier.slice_index] += 1
            stage1_correction_slices[calibrated.stage1_pwl.slice_index] += 1
            stage2_correction_slices[calibrated.stage2_pwl.slice_index] += 1

            physical_overload = any(
                not stage.correctable
                or stage.main_input_overload_low
                or stage.main_input_overload_high
                for stage in (raw.stage1, raw.stage2)
            ) or raw.backend.overload_low or raw.backend.overload_high
            if physical_overload:
                physical_overloads += 1
                pair_physical_overloads += 1
            if calibrated.saturated_low or calibrated.saturated_high:
                calibrated_saturation_codes.append(expected)
                pair_saturations += 1

            if expected in (0, 1024, 2048, 3072, 4095):
                representative_traces.append(
                    {
                        "dither_symbols": pair,
                        "expected_code": expected,
                        "input_value": value,
                        "raw_output_code": raw.reconstruction.output_code,
                        "stage2_raw_backend_code": calibrated.stage2_raw_backend_code,
                        "stage2_corrected_code": calibrated.stage2_pwl.corrected_code,
                        "stage2_dither_copy": calibrated.stage2_dither_copy,
                        "stage1_raw_code_before_dither_subtraction": calibrated.stage1_raw_code_before_dither_subtraction,
                        "stage1_raw_code": calibrated.stage1_raw_code,
                        "stage1_corrected_code": calibrated.stage1_pwl.corrected_code,
                        "stage1_dither_copy": calibrated.stage1_dither_copy,
                        "calibrated_unclipped_output_code": calibrated.unclipped_output_code,
                    }
                )

        negative_steps = sum(
            right < left
            for left, right in zip(corrected_outputs, corrected_outputs[1:])
        )
        flat_steps = sum(
            right == left
            for left, right in zip(corrected_outputs, corrected_outputs[1:])
        )
        pair_rows.append(
            {
                "dither1": pair[0],
                "dither2": pair[1],
                "checks": len(corrected_errors),
                "corrected_mae_codes": sum(map(abs, corrected_errors))
                / len(corrected_errors),
                "corrected_max_abs_error_codes": max(map(abs, corrected_errors)),
                "uncorrected_mae_codes": sum(map(abs, uncorrected_errors))
                / len(uncorrected_errors),
                "uncorrected_max_abs_error_codes": max(
                    map(abs, uncorrected_errors)
                ),
                "wrong_order_mae_codes": sum(map(abs, wrong_order_errors))
                / len(wrong_order_errors),
                "wrong_order_max_abs_error_codes": max(
                    map(abs, wrong_order_errors)
                ),
                "negative_transfer_steps": negative_steps,
                "flat_transfer_steps": flat_steps,
                "physical_overloads": pair_physical_overloads,
                "calibrated_saturations": pair_saturations,
            }
        )
        total_checks += len(corrected_errors)
        total_corrected_absolute_error += sum(map(abs, corrected_errors))
        total_uncorrected_absolute_error += sum(map(abs, uncorrected_errors))
        total_wrong_order_absolute_error += sum(map(abs, wrong_order_errors))
        maximum_corrected_error = max(
            maximum_corrected_error, max(map(abs, corrected_errors))
        )
        maximum_uncorrected_error = max(
            maximum_uncorrected_error, max(map(abs, uncorrected_errors))
        )
        maximum_wrong_order_error = max(
            maximum_wrong_order_error, max(map(abs, wrong_order_errors))
        )
        total_negative_steps += negative_steps
        total_flat_steps += flat_steps

    corrected_mae = total_corrected_absolute_error / total_checks
    uncorrected_mae = total_uncorrected_absolute_error / total_checks
    wrong_order_mae = total_wrong_order_absolute_error / total_checks
    improvement_ratio = uncorrected_mae / corrected_mae
    wrong_order_ratio = wrong_order_mae / corrected_mae
    allowed_saturation_codes = set(
        experiment["acceptance"]["allowed_calibrated_saturation_expected_codes"]
    )
    unexpected_saturation_codes = sorted(
        set(calibrated_saturation_codes) - allowed_saturation_codes
    )
    maximum_continuous_error = max(
        result["maximum_error_codes"] for result in continuous.values()
    )
    acceptance = experiment["acceptance"]
    pass_status = all(
        (
            coefficient_error <= 1e-12,
            maximum_continuous_error
            <= acceptance["maximum_continuous_inverse_error_codes"],
            maximum_corrected_error
            <= acceptance["maximum_quantized_corrected_absolute_error_codes"],
            corrected_mae
            <= acceptance["maximum_quantized_corrected_mae_codes"],
            improvement_ratio >= acceptance["minimum_mae_improvement_ratio"],
            wrong_order_ratio >= acceptance["minimum_wrong_order_mae_ratio"],
            total_negative_steps
            <= acceptance["maximum_negative_transfer_steps"],
            physical_overloads == 0,
            not unexpected_saturation_codes,
        )
    )

    metrics = {
        "experiment_id": experiment["experiment_id"],
        "architecture_config": architecture["config_id"],
        "mode": "known_truth_corrected",
        "claim_exclusion": "not_lms_convergence_or_bit_true_fixed_point",
        "oracle": {
            "stage1_slice_width": oracle.stage1_pwl.slice_width,
            "stage1_slopes": oracle.stage1_pwl.slopes,
            "stage2_slice_width": oracle.stage2_pwl.slice_width,
            "stage2_slopes": oracle.stage2_pwl.slopes,
            "maximum_expected_coefficient_error": coefficient_error,
        },
        "continuous_inverse": continuous,
        "quantized_cascade": {
            "checks": total_checks,
            "corrected_mae_codes": corrected_mae,
            "corrected_max_abs_error_codes": maximum_corrected_error,
            "uncorrected_mae_codes": uncorrected_mae,
            "uncorrected_max_abs_error_codes": maximum_uncorrected_error,
            "mae_improvement_ratio": improvement_ratio,
            "wrong_order_mae_codes": wrong_order_mae,
            "wrong_order_max_abs_error_codes": maximum_wrong_order_error,
            "wrong_order_to_correct_order_mae_ratio": wrong_order_ratio,
            "negative_transfer_steps": total_negative_steps,
            "flat_code_center_steps": total_flat_steps,
            "physical_overloads": physical_overloads,
            "calibrated_saturation_count": len(calibrated_saturation_codes),
            "calibrated_saturation_expected_codes": sorted(
                set(calibrated_saturation_codes)
            ),
            "unexpected_saturation_expected_codes": unexpected_saturation_codes,
        },
        "slice_coverage": {
            "stage1_truth": stage1_truth_slices,
            "stage2_truth": stage2_truth_slices,
            "stage1_correction": stage1_correction_slices,
            "stage2_correction": stage2_correction_slices,
        },
        "pass": pass_status,
    }

    with (output_dir / "dither_pair_metrics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=pair_rows[0].keys())
        writer.writeheader()
        writer.writerows(pair_rows)
    (output_dir / "representative_traces.json").write_text(
        json.dumps(representative_traces, indent=2), encoding="utf-8"
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    (output_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(
            {
                "experiment": experiment,
                "architecture": architecture,
                "derived_oracle": asdict(oracle),
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    tracked_sources = [
        EXPERIMENT_CONFIG,
        architecture_path,
        ROOT / "src" / "adc_research" / "platform" / "amplifier.py",
        ROOT / "src" / "adc_research" / "platform" / "stage.py",
        ROOT / "src" / "adc_research" / "platform" / "pipeline.py",
        ROOT / "src" / "adc_research" / "calibration" / "pwl.py",
        ROOT / "src" / "adc_research" / "calibration" / "known_truth.py",
    ]
    environment = {
        "python": sys.version,
        "platform": platform.platform(),
        "argv": sys.argv,
        "source_sha256": source_hash(tracked_sources),
    }
    (output_dir / "environment.json").write_text(
        json.dumps(environment, indent=2), encoding="utf-8"
    )
    print(json.dumps(metrics, indent=2))
    print(output_dir)
    if not pass_status:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
