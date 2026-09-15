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
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.theory.dual_path import joint_auxiliary_offset_interval


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_CONFIG = Path(__file__).with_name("config.yaml")


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def code_center(raw_code: int) -> float:
    return -1 + (raw_code + 0.5) / 2048


def normalized_offset(volts: float, full_scale_vpp: float) -> float:
    return 2 * volts / full_scale_vpp


def source_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def scoped_tables(architecture: dict, indices: list[int]) -> tuple[tuple, tuple]:
    template = architecture["front_stage_template"]
    thresholds = tuple(template["thresholds"][index] for index in indices)
    first = indices[0]
    expected = list(range(first, first + len(indices)))
    if indices != expected:
        raise ValueError("boundary scope must be a contiguous index range")
    levels = tuple(template["dac_levels"][first : first + len(indices) + 1])
    return thresholds, levels


def platform_corner_audit(
    architecture: dict,
    experiment: dict,
    corners: list[dict],
) -> dict:
    checks = 0
    failures = 0
    failures_by_corner: list[dict] = []
    pairs = experiment["platform_validation"]["dither_symbol_pairs"]
    for corner in corners:
        config = build_gu_static_hypothesis_a(
            architecture,
            dither_profile=experiment["dither_profile"],
            stage2_flash_auxiliary_gain_ratio=corner["gain_ratio"],
            stage2_flash_auxiliary_offset=corner["offset_normalized"],
        )
        corner_failures = 0
        first_failure = None
        for expected in range(4096):
            value = code_center(expected)
            for pair in pairs:
                result = process(
                    value,
                    config,
                    sample_index=expected,
                    dither_symbols=tuple(pair),
                )
                checks += 1
                failed = (
                    result.reconstruction.output_code != expected
                    or not result.reconstruction.correctable
                )
                if failed:
                    failures += 1
                    corner_failures += 1
                    if first_failure is None:
                        first_failure = {
                            "expected_code": expected,
                            "dither_symbols": pair,
                            "stage1_residue": result.stage1.residue,
                            "stage2_symbol": result.stage2.quantizer.symbol,
                            "stage2_residue": result.stage2.residue,
                            "actual_code": result.reconstruction.output_code,
                            "correctable": result.reconstruction.correctable,
                        }
        failures_by_corner.append(
            {**corner, "failure_count": corner_failures, "first_failure": first_failure}
        )
    return {
        "checks": checks,
        "failures": failures,
        "corners": failures_by_corner,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    experiment = read_yaml(EXPERIMENT_CONFIG)
    architecture_path = ROOT / experiment["architecture_config"]
    architecture = read_yaml(architecture_path)
    output_dir = ROOT / "artifacts" / "runs" / "EXP_004" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    output_dir.mkdir(parents=True)

    full_scale = experiment["physical_mapping"]["differential_full_scale_vpp"]
    dither_amplitude = architecture["dither_hypothesis"]["profiles"][
        experiment["dither_profile"]
    ]["residue_preamp_normalized_half_amplitude"]

    scopes = {}
    interval_rows = []
    for scope_name, indices in experiment["theory_boundary_scopes"].items():
        thresholds, levels = scoped_tables(architecture, indices)
        scopes[scope_name] = (thresholds, levels)
        for ratio in (0.97, 1.03):
            interval = joint_auxiliary_offset_interval(
                thresholds,
                levels,
                auxiliary_gain_ratio=ratio,
                interstage_gain=4,
                dither_half_amplitude=dither_amplitude,
            )
            interval_rows.append(
                {
                    "scope": scope_name,
                    "gain_ratio": ratio,
                    "offset_lower_normalized": interval.lower,
                    "offset_upper_normalized": interval.upper,
                    "offset_half_width_mv": interval.half_width * full_scale * 500,
                }
            )

    pretrim = experiment["pretrim"]
    pretrim_audits = {}
    pretrim_platform = {}
    for sigma in pretrim["deterministic_sigma_envelopes"]:
        corners = []
        for systematic in (-pretrim["systematic_gain_mismatch_magnitude"], pretrim["systematic_gain_mismatch_magnitude"]):
            for random_gain in (-sigma * pretrim["random_gain_mismatch_sigma"], sigma * pretrim["random_gain_mismatch_sigma"]):
                for offset_v in (-sigma * pretrim["random_offset_sigma_v"], sigma * pretrim["random_offset_sigma_v"]):
                    corners.append(
                        {
                            "systematic_gain": systematic,
                            "random_gain": random_gain,
                            "gain_ratio": 1 + systematic + random_gain,
                            "offset_v": offset_v,
                            "offset_normalized": normalized_offset(offset_v, full_scale),
                        }
                    )
        scope_results = {}
        for scope_name, (thresholds, levels) in scopes.items():
            safe = 0
            minimum_margin = float("inf")
            for corner in corners:
                interval = joint_auxiliary_offset_interval(
                    thresholds,
                    levels,
                    auxiliary_gain_ratio=corner["gain_ratio"],
                    interstage_gain=4,
                    dither_half_amplitude=dither_amplitude,
                )
                safe += interval.contains(corner["offset_normalized"])
                minimum_margin = min(
                    minimum_margin,
                    corner["offset_normalized"] - interval.lower,
                    interval.upper - corner["offset_normalized"],
                )
            scope_results[scope_name] = {
                "corner_count": len(corners),
                "safe_corner_count": safe,
                "minimum_signed_margin_normalized": minimum_margin,
            }
        pretrim_audits[str(sigma)] = scope_results
        pretrim_platform[str(sigma)] = platform_corner_audit(
            architecture, experiment, corners
        )

    posttrim = experiment["posttrim_temperature_drift"]
    sigma = posttrim["deterministic_sigma_envelope"]
    posttrim_corners = []
    for gain_drift in (-sigma * posttrim["gain_sigma_upper_bound"], sigma * posttrim["gain_sigma_upper_bound"]):
        for offset_v in (-sigma * posttrim["offset_sigma_upper_bound_v"], sigma * posttrim["offset_sigma_upper_bound_v"]):
            posttrim_corners.append(
                {
                    "gain_ratio": 1 + gain_drift,
                    "gain_drift": gain_drift,
                    "offset_v": offset_v,
                    "offset_normalized": normalized_offset(offset_v, full_scale),
                }
            )
    posttrim_platform = platform_corner_audit(
        architecture, experiment, posttrim_corners
    )

    metrics = {
        "experiment_id": experiment["experiment_id"],
        "architecture_config": architecture["config_id"],
        "dither_profile": experiment["dither_profile"],
        "systematic_only_offset_intervals": interval_rows,
        "pretrim_deterministic_envelopes": pretrim_audits,
        "pretrim_platform": pretrim_platform,
        "posttrim_three_sigma_platform": posttrim_platform,
        "interpretation": "deterministic_sigma_corners_not_statistical_yield",
    }

    with (output_dir / "systematic_offset_intervals.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=interval_rows[0].keys())
        writer.writeheader()
        writer.writerows(interval_rows)
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    (output_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(
            {"experiment": experiment, "architecture": architecture},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    tracked_sources = [
        EXPERIMENT_CONFIG,
        architecture_path,
        ROOT / "src" / "adc_research" / "theory" / "dual_path.py",
        ROOT / "src" / "adc_research" / "theory" / "redundancy.py",
        ROOT / "src" / "adc_research" / "platform" / "pipeline.py",
        ROOT / "src" / "adc_research" / "platform" / "presets.py",
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


if __name__ == "__main__":
    main()
