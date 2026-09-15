from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from dataclasses import replace
from pathlib import Path

import yaml

from adc_research.calibration.known_truth import (
    build_two_stage_oracle,
    correct_two_stage,
)
from adc_research.calibration.pwl import PwlConfig, correct
from adc_research.platform.pipeline import process
from adc_research.platform.presets import (
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
)
from adc_research.theory.pwl_reachability import pwl_slice_reachability


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


def pipeline_with_dither(base, profile: dict):
    amplitude = profile["preamp_half_amplitude"]
    dither_levels = {-1: -amplitude, 1: amplitude}
    stage1 = replace(
        base.stage1,
        cdac=replace(base.stage1.cdac, dither_levels=dither_levels),
    )
    stage2 = replace(
        base.stage2,
        cdac=replace(base.stage2.cdac, dither_levels=dither_levels),
    )
    copy1 = profile["stage1_digital_copy"]
    copy2 = profile["stage2_digital_copy"]
    reconstruction = replace(
        base.reconstruction,
        dither_code_copies=(
            {-1: -copy1, 1: copy1},
            {-1: -copy2, 1: copy2},
        ),
    )
    return replace(
        base,
        stage1=stage1,
        stage2=stage2,
        reconstruction=reconstruction,
    )


def uniform_scaling_audit(oracle, scale_factors: list[int]) -> dict:
    failures = 0
    checks = 0
    profiles = (
        ("stage1", oracle.stage1_pwl, range(-512, 512)),
        ("stage2", oracle.stage2_pwl, range(-128, 128)),
    )
    rows = []
    for stage_name, base, raw_codes in profiles:
        for scale in scale_factors:
            scaled = PwlConfig(
                slice_width=base.slice_width * scale,
                slopes=base.slopes,
            )
            case_failures = 0
            case_checks = 0
            for raw_code in raw_codes:
                reference = correct(raw_code, base)
                actual = correct(raw_code * scale, scaled)
                failed = (
                    actual.slice_index != reference.slice_index
                    or abs(
                        actual.corrected_code / scale
                        - reference.corrected_code
                    )
                    > 1e-12
                )
                failures += failed
                case_failures += failed
                checks += 1
                case_checks += 1
            rows.append(
                {
                    "stage": stage_name,
                    "scale_factor": scale,
                    "checks": case_checks,
                    "failures": case_failures,
                    "scaled_b0": scaled.slice_width,
                }
            )
    return {"checks": checks, "failures": failures, "cases": rows}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    experiment = read_yaml(EXPERIMENT_CONFIG)
    architecture_path = ROOT / experiment["architecture_config"]
    nonidealities_path = ROOT / experiment["nonidealities_config"]
    architecture = read_yaml(architecture_path)
    nonidealities_profile = read_yaml(nonidealities_path)
    output_dir = ROOT / "artifacts" / "runs" / "EXP_008" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    output_dir.mkdir(parents=True)

    base = build_gu_static_hypothesis_a(architecture)
    truth_nonidealities = build_gu_gate_d_nonidealities(
        nonidealities_profile,
        enabled_effects=("static_pwl_truth",),
    )
    truth1 = truth_nonidealities.stage1.pwl_truth
    truth2 = truth_nonidealities.stage2.pwl_truth
    reachability_config = experiment["reachability_model"]
    theoretical = {
        "stage1": pwl_slice_reachability(
            truth1.ideal_output_edges[3],
            nominal_residue_output_half_range=reachability_config[
                "nominal_residue_output_half_range"
            ],
            interstage_gain=reachability_config["interstage_gain"],
            next_stage_half_range=reachability_config["next_stage_half_range"],
        ),
        "stage2": pwl_slice_reachability(
            truth2.ideal_output_edges[3],
            nominal_residue_output_half_range=reachability_config[
                "nominal_residue_output_half_range"
            ],
            interstage_gain=reachability_config["interstage_gain"],
            next_stage_half_range=reachability_config["next_stage_half_range"],
        ),
    }

    profile_rows = []
    representative_hits = []
    oracles = {}
    for profile_name, profile in experiment["dither_profiles"].items():
        pipeline = pipeline_with_dither(base, profile)
        oracle = build_two_stage_oracle(pipeline, truth_nonidealities)
        oracles[profile_name] = oracle
        truth_coverage1 = [0] * truth1.slice_count
        truth_coverage2 = [0] * truth2.slice_count
        correction_coverage1 = [0] * oracle.stage1_pwl.slice_count
        correction_coverage2 = [0] * oracle.stage2_pwl.slice_count
        physical_overloads = 0
        final_saturations = 0
        corrected_absolute_error = 0.0
        maximum_corrected_error = 0.0
        checks = 0

        for pair_list in experiment["dither_symbol_pairs"]:
            pair = tuple(pair_list)
            for expected in range(4096):
                value = -1 + (expected + 0.5) / 2048
                raw = process(
                    value,
                    pipeline,
                    sample_index=expected,
                    dither_symbols=pair,
                    nonidealities=truth_nonidealities,
                )
                calibrated = correct_two_stage(raw, oracle)
                truth_coverage1[raw.stage1.amplifier.slice_index] += 1
                truth_coverage2[raw.stage2.amplifier.slice_index] += 1
                correction_coverage1[calibrated.stage1_pwl.slice_index] += 1
                correction_coverage2[calibrated.stage2_pwl.slice_index] += 1
                physical_overloads += any(
                    not stage.correctable
                    or stage.main_input_overload_low
                    or stage.main_input_overload_high
                    for stage in (raw.stage1, raw.stage2)
                ) or raw.backend.overload_low or raw.backend.overload_high
                final_saturations += calibrated.saturated_low or calibrated.saturated_high
                error = calibrated.unclipped_output_code - expected
                corrected_absolute_error += abs(error)
                maximum_corrected_error = max(
                    maximum_corrected_error, abs(error)
                )
                checks += 1

                if (
                    (raw.stage1.amplifier.slice_index == 3
                    or raw.stage2.amplifier.slice_index == 3)
                    and len(representative_hits) < 20
                ):
                    representative_hits.append(
                        {
                            "profile": profile_name,
                            "expected_code": expected,
                            "dither_symbols": pair,
                            "stage1_ideal_output": raw.stage1.amplifier.ideal_output_value,
                            "stage1_truth_slice": raw.stage1.amplifier.slice_index,
                            "stage2_ideal_output": raw.stage2.amplifier.ideal_output_value,
                            "stage2_truth_slice": raw.stage2.amplifier.slice_index,
                            "stage1_correction_slice": calibrated.stage1_pwl.slice_index,
                            "stage2_correction_slice": calibrated.stage2_pwl.slice_index,
                            "corrected_error_codes": error,
                        }
                    )

        amplitude = profile["preamp_half_amplitude"]
        profile_rows.append(
            {
                "profile": profile_name,
                "status": profile["status"],
                "preamp_half_amplitude": amplitude,
                "nominal_reachable_output_supremum": reachability_config[
                    "nominal_residue_output_half_range"
                ]
                + reachability_config["interstage_gain"] * amplitude,
                "stage1_predicted_fourth_slice_reachable": theoretical[
                    "stage1"
                ].reached_by(amplitude),
                "stage2_predicted_fourth_slice_reachable": theoretical[
                    "stage2"
                ].reached_by(amplitude),
                "stage1_truth_slice4_hits": truth_coverage1[3],
                "stage2_truth_slice4_hits": truth_coverage2[3],
                "stage1_correction_slice4_hits": correction_coverage1[3],
                "stage2_correction_slice4_hits": correction_coverage2[3],
                "physical_overloads": physical_overloads,
                "final_saturations": final_saturations,
                "corrected_mae_codes": corrected_absolute_error / checks,
                "corrected_max_abs_error_codes": maximum_corrected_error,
            }
        )

    scaling = uniform_scaling_audit(
        oracles["behavioral_default"],
        experiment["uniform_internal_code_scale_factors"],
    )
    default = next(row for row in profile_rows if row["profile"] == "behavioral_default")
    probe = next(row for row in profile_rows if row["profile"] == "controlled_slice4_probe")
    acceptance = experiment["acceptance"]
    default_fourth_hits = (
        default["stage1_truth_slice4_hits"] + default["stage2_truth_slice4_hits"]
    )
    pass_status = all(
        (
            default_fourth_hits
            <= acceptance["maximum_default_fourth_slice_hits"],
            probe["stage1_truth_slice4_hits"]
            >= acceptance["minimum_probe_fourth_slice_hits_per_stage"],
            probe["stage2_truth_slice4_hits"]
            >= acceptance["minimum_probe_fourth_slice_hits_per_stage"],
            probe["physical_overloads"]
            <= acceptance["maximum_probe_physical_overloads"],
            scaling["failures"]
            <= acceptance["maximum_uniform_scaling_invariance_failures"],
            probe["corrected_max_abs_error_codes"]
            <= acceptance["maximum_probe_corrected_absolute_error_codes"],
        )
    )

    metrics = {
        "experiment_id": experiment["experiment_id"],
        "architecture_config": architecture["config_id"],
        "nonidealities_config": nonidealities_profile["config_id"],
        "theoretical_reachability": {
            stage: {
                "slice_lower_edge": result.slice_lower_edge,
                "minimum_preamp_dither_infimum": result.minimum_preamp_dither_infimum,
                "maximum_preamp_dither_without_nominal_overload": result.maximum_preamp_dither_without_nominal_overload,
                "feasible_below_nominal_overload": result.feasible_below_nominal_overload,
            }
            for stage, result in theoretical.items()
        },
        "profiles": profile_rows,
        "uniform_internal_code_scaling": scaling,
        "interpretation": {
            "amplitude_path": "controlled_1bit_probe_proves_reachability_not_silicon_linearization_dither_mapping",
            "code_scaling_path": "uniform_raw_code_and_b0_scaling_is_slice_occupancy_invariant",
        },
        "pass": pass_status,
    }

    with (output_dir / "profile_metrics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=profile_rows[0].keys())
        writer.writeheader()
        writer.writerows(profile_rows)
    with (output_dir / "scaling_invariance.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=scaling["cases"][0].keys())
        writer.writeheader()
        writer.writerows(scaling["cases"])
    (output_dir / "representative_slice4_hits.json").write_text(
        json.dumps(representative_hits, indent=2), encoding="utf-8"
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    (output_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(
            {
                "experiment": experiment,
                "architecture": architecture,
                "nonidealities": nonidealities_profile,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    tracked_sources = [
        EXPERIMENT_CONFIG,
        architecture_path,
        nonidealities_path,
        ROOT / "src" / "adc_research" / "theory" / "pwl_reachability.py",
        ROOT / "src" / "adc_research" / "platform" / "pipeline.py",
        ROOT / "src" / "adc_research" / "platform" / "stage.py",
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
