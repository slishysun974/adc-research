from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from pathlib import Path

import yaml

from adc_research.platform.pipeline import process
from adc_research.platform.presets import (
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
)
from adc_research.theory.static_transfer import (
    StaticTransferPrediction,
    build_gu_theory_config,
    predict_static_transfer,
)


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_CONFIG = Path(__file__).resolve().with_name("config.yaml")


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def source_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def prediction_summary(prediction: StaticTransferPrediction) -> dict:
    return {
        "segment_count": len(prediction.segments),
        "missing_code_count": len(prediction.missing_codes),
        "missing_codes": prediction.missing_codes,
        "minimum_dnl_lsb": min(prediction.dnl_lsb),
        "maximum_dnl_lsb": max(prediction.dnl_lsb),
        "maximum_absolute_dnl_lsb": max(map(abs, prediction.dnl_lsb)),
        "minimum_transition_inl_lsb": min(prediction.transition_inl_lsb),
        "maximum_transition_inl_lsb": max(prediction.transition_inl_lsb),
        "maximum_absolute_transition_inl_lsb": max(
            map(abs, prediction.transition_inl_lsb)
        ),
        "negative_step_count": prediction.negative_step_count,
        "uncorrectable_input_width": prediction.uncorrectable_input_width,
        "uncorrectable_input_fraction": (
            prediction.uncorrectable_input_width
            / (prediction.input_range[1] - prediction.input_range[0])
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    experiment = read_yaml(EXPERIMENT_CONFIG)
    architecture_path = ROOT / experiment["architecture_config"]
    nonidealities_path = ROOT / experiment["nonidealities_config"]
    architecture = read_yaml(architecture_path)
    nonideality_profile = read_yaml(nonidealities_path)
    output_dir = ROOT / "artifacts" / "runs" / "EXP_015" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    output_dir.mkdir(parents=True)

    holdout = experiment["holdout"]
    sample_count = int(holdout["sample_count"])
    phase = float(holdout["fractional_phase"])
    if sample_count <= 0 or not 0 < phase < 1:
        raise ValueError("holdout grid requires positive count and phase in (0,1)")

    case_results = []
    segment_rows = []
    for case_name, case in experiment["cases"].items():
        enabled = tuple(case["enabled_effects"])
        dither_symbols = tuple(case["dither_symbols"])
        ratio = float(case["stage2_flash_auxiliary_gain_ratio"])
        offset = float(case["stage2_flash_auxiliary_offset"])

        theory_config = build_gu_theory_config(
            architecture,
            nonidealities=nonideality_profile,
            enabled_effects=enabled,
            dither_symbols=dither_symbols,
            stage2_flash_auxiliary_gain_ratio=ratio,
            stage2_flash_auxiliary_offset=offset,
        )
        prediction = predict_static_transfer(theory_config)

        reference_config = build_gu_static_hypothesis_a(
            architecture,
            stage2_flash_auxiliary_gain_ratio=ratio,
            stage2_flash_auxiliary_offset=offset,
        )
        applied = build_gu_gate_d_nonidealities(
            nonideality_profile,
            enabled_effects=enabled,
        )

        code_disagreements = 0
        correctable_disagreements = 0
        maximum_code_error = 0
        platform_uncorrectable_count = 0
        first_disagreement = None
        for sample_index in range(sample_count):
            value = -1 + 2 * (sample_index + phase) / sample_count
            predicted = prediction.segment_at(value)
            observed = process(
                value,
                reference_config,
                sample_index=sample_index,
                dither_symbols=dither_symbols,
                nonidealities=applied,
            )
            observed_code = observed.reconstruction.output_code
            observed_correctable = observed.reconstruction.correctable
            code_error = abs(predicted.output_code - observed_code)
            code_disagreements += code_error != 0
            correctable_disagreements += (
                predicted.correctable != observed_correctable
            )
            maximum_code_error = max(maximum_code_error, code_error)
            platform_uncorrectable_count += not observed_correctable
            if (
                first_disagreement is None
                and (
                    code_error != 0
                    or predicted.correctable != observed_correctable
                )
            ):
                first_disagreement = {
                    "sample_index": sample_index,
                    "input_value": value,
                    "predicted_code": predicted.output_code,
                    "observed_code": observed_code,
                    "predicted_correctable": predicted.correctable,
                    "observed_correctable": observed_correctable,
                }

        domain_width = prediction.input_range[1] - prediction.input_range[0]
        platform_uncorrectable_width = (
            domain_width * platform_uncorrectable_count / sample_count
        )
        summary = prediction_summary(prediction)
        summary.update(
            {
                "case": case_name,
                "enabled_effects": enabled,
                "dither_symbols": dither_symbols,
                "stage2_flash_auxiliary_gain_ratio": ratio,
                "stage2_flash_auxiliary_offset": offset,
                "holdout_sample_count": sample_count,
                "holdout_fractional_phase": phase,
                "holdout_code_disagreements": code_disagreements,
                "holdout_correctable_disagreements": correctable_disagreements,
                "holdout_maximum_code_error": maximum_code_error,
                "platform_uncorrectable_count": platform_uncorrectable_count,
                "platform_uncorrectable_width_estimate": (
                    platform_uncorrectable_width
                ),
                "uncorrectable_width_estimation_error": abs(
                    prediction.uncorrectable_input_width
                    - platform_uncorrectable_width
                ),
                "first_disagreement": first_disagreement,
            }
        )
        case_results.append(summary)

        for index, segment in enumerate(prediction.segments):
            segment_rows.append(
                {
                    "case": case_name,
                    "segment_index": index,
                    "input_lower": segment.input_lower,
                    "input_upper": segment.input_upper,
                    "width": segment.width,
                    "stage1_symbol": segment.stage1_symbol,
                    "stage2_symbol": segment.stage2_symbol,
                    "backend_centered_code": segment.backend_centered_code,
                    "unclipped_output_code": segment.unclipped_output_code,
                    "output_code": segment.output_code,
                    "correctable": segment.correctable,
                    "stage1_pwl_slice": segment.stage1_pwl_slice,
                    "stage2_pwl_slice": segment.stage2_pwl_slice,
                }
            )
        print(
            f"completed {case_name}: {len(prediction.segments)} segments, "
            f"{code_disagreements} code disagreements",
            flush=True,
        )

    by_name = {row["case"]: row for row in case_results}
    ideal = by_name["ideal"]
    boundary = by_name["redundancy_boundary_failure"]
    acceptance = experiment["acceptance"]
    pass_status = all(
        (
            ideal["maximum_absolute_dnl_lsb"]
            <= float(acceptance["maximum_ideal_absolute_dnl_lsb"]),
            ideal["maximum_absolute_transition_inl_lsb"]
            <= float(acceptance["maximum_ideal_absolute_inl_lsb"]),
            ideal["missing_code_count"]
            <= int(acceptance["maximum_ideal_missing_codes"]),
            ideal["negative_step_count"]
            <= int(acceptance["maximum_ideal_negative_steps"]),
            ideal["uncorrectable_input_width"]
            <= float(acceptance["maximum_ideal_uncorrectable_input_width"]),
            max(row["holdout_code_disagreements"] for row in case_results)
            <= int(acceptance["maximum_holdout_code_disagreements"]),
            max(
                row["holdout_correctable_disagreements"]
                for row in case_results
            )
            <= int(acceptance["maximum_holdout_correctable_disagreements"]),
            boundary["uncorrectable_input_width"]
            >= float(acceptance["minimum_boundary_failure_theory_width"]),
            boundary["platform_uncorrectable_count"]
            >= int(acceptance["minimum_boundary_failure_platform_count"]),
            boundary["uncorrectable_width_estimation_error"]
            <= float(acceptance["maximum_boundary_failure_width_error"]),
        )
    )

    metrics = {
        "experiment_id": experiment["experiment_id"],
        "architecture_config": architecture["config_id"],
        "nonidealities_config": nonideality_profile["config_id"],
        "prediction_scope": (
            "memoryless static transfer with fixed physical parameters and "
            "no digital calibration"
        ),
        "method": (
            "independent recursive interval partition and piecewise-affine "
            "composition"
        ),
        "holdout_use": (
            "platform samples validate predictions and are not used to locate "
            "boundaries or fit parameters"
        ),
        "cases": case_results,
        "pass": pass_status,
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    with (output_dir / "case_metrics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        flattened = [
            {key: value for key, value in row.items() if key != "first_disagreement"}
            for row in case_results
        ]
        writer = csv.DictWriter(handle, fieldnames=flattened[0].keys())
        writer.writeheader()
        writer.writerows(flattened)
    with (output_dir / "transfer_segments.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=segment_rows[0].keys())
        writer.writeheader()
        writer.writerows(segment_rows)
    (output_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(
            {
                "experiment": experiment,
                "architecture": architecture,
                "nonidealities": nonideality_profile,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    tracked_sources = [
        EXPERIMENT_CONFIG,
        architecture_path,
        nonidealities_path,
        ROOT / "src" / "adc_research" / "theory" / "static_transfer.py",
        ROOT / "src" / "adc_research" / "platform" / "pipeline.py",
        ROOT / "src" / "adc_research" / "platform" / "presets.py",
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
