from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from pathlib import Path

import yaml

from adc_research.calibration.pwl import (
    PwlConfig,
    correct,
    slice_width_from_unsigned_bits,
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    experiment = read_yaml(EXPERIMENT_CONFIG)
    architecture_path = ROOT / experiment["architecture_config"]
    architecture = read_yaml(architecture_path)
    output_dir = ROOT / "artifacts" / "runs" / "EXP_005" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    output_dir.mkdir(parents=True)

    slopes = tuple(experiment["validation_slopes"])
    profiles = {}
    continuity_rows = []
    total_unity_checks = 0
    total_unity_failures = 0
    total_symmetry_checks = 0
    total_symmetry_failures = 0
    total_inverse_checks = 0
    total_inverse_failures = 0

    for profile_name, profile in experiment["pwl_profiles"].items():
        width = slice_width_from_unsigned_bits(
            profile["unsigned_magnitude_bits"],
            slice_count=4,
        )
        if width != profile["expected_slice_width"]:
            raise AssertionError(f"unexpected slice width for {profile_name}")
        full_scale = 4 * width
        unity = PwlConfig(width, (1.0, 1.0, 1.0, 1.0))
        unity_failures = 0
        for raw_code in range(-full_scale, full_scale):
            total_unity_checks += 1
            if correct(raw_code, unity).corrected_code != raw_code:
                unity_failures += 1
                total_unity_failures += 1

        config = PwlConfig(width, slopes)
        max_continuity_gap = 0.0
        epsilon = 1e-9
        for index in range(1, 4):
            boundary = index * width
            at_positive = correct(boundary, config).corrected_code
            below_positive = correct(boundary - epsilon, config).corrected_code
            at_negative = correct(-boundary, config).corrected_code
            above_negative = correct(-boundary + epsilon, config).corrected_code
            positive_gap = abs(at_positive - below_positive)
            negative_gap = abs(at_negative - above_negative)
            max_continuity_gap = max(
                max_continuity_gap, positive_gap, negative_gap
            )
            continuity_rows.append(
                {
                    "profile": profile_name,
                    "boundary_magnitude": boundary,
                    "positive_gap": positive_gap,
                    "negative_gap": negative_gap,
                }
            )

        symmetry_failures = 0
        for raw_code in range(1, full_scale):
            total_symmetry_checks += 1
            if correct(-raw_code, config).corrected_code != -correct(
                raw_code, config
            ).corrected_code:
                symmetry_failures += 1
                total_symmetry_failures += 1

        offsets = config.slice_offsets
        upper_edges = tuple(
            offset + slope * width
            for offset, slope in zip(offsets, slopes, strict=True)
        )
        corrected_full_scale = upper_edges[-1]
        inverse_failures = 0
        sample_count = experiment["inverse_truth_samples_per_polarity"]
        for sample_index in range(1, sample_count + 1):
            target = corrected_full_scale * sample_index / (sample_count + 1)
            segment = next(
                index
                for index, upper in enumerate(upper_edges)
                if target <= upper
            )
            raw_magnitude = (
                segment * width
                + (target - offsets[segment]) / slopes[segment]
            )
            for sign in (-1, 1):
                total_inverse_checks += 1
                actual = correct(sign * raw_magnitude, config).corrected_code
                if abs(actual - sign * target) > 1e-10:
                    inverse_failures += 1
                    total_inverse_failures += 1

        negative_endpoint = correct(-full_scale, config)
        reject_config = PwlConfig(
            width,
            slopes,
            negative_full_scale_policy=experiment[
                "negative_full_scale_policies"
            ]["bit_true_audit"],
        )
        reject_raised = False
        try:
            correct(-full_scale, reject_config)
        except ValueError:
            reject_raised = True

        profiles[profile_name] = {
            "signed_code_bits": profile["signed_code_bits"],
            "unsigned_magnitude_bits": profile["unsigned_magnitude_bits"],
            "slice_width": width,
            "provenance": profile["provenance"],
            "unity_checks": 2 * full_scale,
            "unity_failures": unity_failures,
            "symmetry_checks": full_scale - 1,
            "symmetry_failures": symmetry_failures,
            "max_continuity_gap": max_continuity_gap,
            "inverse_truth_checks": 2 * sample_count,
            "inverse_truth_failures": inverse_failures,
            "negative_full_scale_extension": {
                "input_code": -full_scale,
                "slice_index": negative_endpoint.slice_index,
                "local_code": negative_endpoint.local_code,
                "corrected_code": negative_endpoint.corrected_code,
            },
            "reject_policy_raised": reject_raised,
        }

    pass_status = (
        total_unity_failures == 0
        and total_symmetry_failures == 0
        and total_inverse_failures == 0
        and all(row["positive_gap"] < 2e-9 and row["negative_gap"] < 2e-9 for row in continuity_rows)
        and all(item["reject_policy_raised"] for item in profiles.values())
    )
    metrics = {
        "experiment_id": experiment["experiment_id"],
        "architecture_config": architecture["config_id"],
        "profiles": profiles,
        "totals": {
            "unity_checks": total_unity_checks,
            "unity_failures": total_unity_failures,
            "symmetry_checks": total_symmetry_checks,
            "symmetry_failures": total_symmetry_failures,
            "inverse_truth_checks": total_inverse_checks,
            "inverse_truth_failures": total_inverse_failures,
        },
        "negative_full_scale_policy": "explicit_behavioral_extension_not_silicon_claim",
        "q008_behavioral_pass": pass_status,
    }

    with (output_dir / "continuity.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=continuity_rows[0].keys())
        writer.writeheader()
        writer.writerows(continuity_rows)
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
        ROOT / "src" / "adc_research" / "calibration" / "pwl.py",
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
