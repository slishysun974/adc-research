from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import sys
from pathlib import Path

import yaml

from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.platform.dual_path_settling import (
    DualPathSettlingConfig,
    DualPathSettlingState,
    process as process_dual_path,
)
from adc_research.platform.finite_settling import (
    FiniteSettlingConfig,
    SettlingState,
    process as process_reduced,
)
from adc_research.platform.presets import (
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
)
from adc_research.platform.stimulus import CoherentSineConfig, coherent_sine
from adc_research.theory.finite_settling import (
    DualPathPeriodicSettlingConfig,
    PeriodicSettlingConfig,
    first_order_residual_factor,
    predict_periodic_dual_path_settling,
    predict_periodic_settling,
)
from adc_research.theory.static_transfer import (
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


def threshold_probe(architecture: dict, main_factor: float, aux_factor: float) -> dict:
    platform_config = build_gu_static_hypothesis_a(architecture)
    dual = process_dual_path(
        0.03175,
        platform_config,
        DualPathSettlingConfig(main_factor, aux_factor, main_factor),
        DualPathSettlingState(),
    )
    reduced = process_reduced(
        0.03175,
        platform_config,
        FiniteSettlingConfig((main_factor, main_factor)),
        SettlingState(),
    )
    return {
        "input_value": 0.03175,
        "flash_threshold": 0.125,
        "main_output": dual.pipeline.stage1.residue,
        "auxiliary_output": dual.stage1_auxiliary_output,
        "dual_path_stage2_symbol": dual.pipeline.stage2.quantizer.symbol,
        "reduced_stage2_symbol": reduced.pipeline.stage2.quantizer.symbol,
        "distinguishes_decisions": (
            dual.pipeline.stage2.quantizer.symbol
            != reduced.pipeline.stage2.quantizer.symbol
        ),
    }


def static_grid_gate(experiment: dict, architecture: dict, profile: dict) -> dict:
    gate = experiment["static_grid"]
    ratio = float(gate["auxiliary_gain_ratio"])
    enabled = tuple(gate["enabled_effects"])
    theory_config = build_gu_theory_config(
        architecture,
        nonidealities=profile,
        enabled_effects=enabled,
        stage2_flash_auxiliary_gain_ratio=ratio,
    )
    independent = predict_static_transfer(
        theory_config, independent_stage1_auxiliary=True
    )
    reduced = predict_static_transfer(theory_config)
    platform_config = build_gu_static_hypothesis_a(
        architecture, stage2_flash_auxiliary_gain_ratio=ratio
    )
    applied = build_gu_gate_d_nonidealities(profile, enabled_effects=enabled)
    count = int(gate["sample_count"])
    phase = (math.sqrt(5) - 1) / 2
    q2_mismatch = code_mismatch = correctable_mismatch = reduced_q2_difference = 0
    for index in range(count):
        value = -1 + 2 * (index + phase) / count
        predicted = independent.segment_at(value)
        observed = process_dual_path(
            value,
            platform_config,
            DualPathSettlingConfig(0.0, 0.0, 0.0),
            DualPathSettlingState(),
            sample_index=index,
            nonidealities=applied,
        ).pipeline
        q2_mismatch += predicted.stage2_symbol != observed.stage2.quantizer.symbol
        code_mismatch += predicted.output_code != observed.reconstruction.output_code
        correctable_mismatch += (
            predicted.correctable != observed.reconstruction.correctable
        )
        reduced_q2_difference += (
            predicted.stage2_symbol != reduced.segment_at(value).stage2_symbol
        )
    return {
        "sample_count": count,
        "auxiliary_gain_ratio": ratio,
        "synthetic_main_pwl": True,
        "theory_platform_q2_disagreements": q2_mismatch,
        "theory_platform_code_disagreements": code_mismatch,
        "theory_platform_correctable_disagreements": correctable_mismatch,
        "independent_vs_reduced_q2_differences": reduced_q2_difference,
        "independent_segment_count": len(independent.segments),
        "reduced_segment_count": len(reduced.segments),
    }


def dynamic_gate(experiment: dict, architecture: dict, main_factor: float) -> list[dict]:
    tone = experiment["tone"]
    sample_rate = float(tone["sample_rate_hz"])
    sample_count = int(tone["sample_count"])
    initial = tuple(float(value) for value in experiment["platform_validation"]["initial_outputs"])
    warmup_periods = int(experiment["platform_validation"]["warmup_periods"])
    rows = []
    for ratio in (float(value) for value in experiment["auxiliary_gain_ratios"]):
        theory_config = build_gu_theory_config(
            architecture, stage2_flash_auxiliary_gain_ratio=ratio
        )
        platform_config = build_gu_static_hypothesis_a(
            architecture, stage2_flash_auxiliary_gain_ratio=ratio
        )
        for case_name, case in experiment["cases"].items():
            auxiliary_factor = first_order_residual_factor(
                float(case["auxiliary_bandwidth_hz"]),
                float(case["auxiliary_phase_duration_s"]),
            )
            theory_settling = DualPathPeriodicSettlingConfig(
                main_factor, auxiliary_factor, main_factor
            )
            platform_settling = DualPathSettlingConfig(
                main_factor, auxiliary_factor, main_factor
            )
            reduced_settling = PeriodicSettlingConfig((main_factor, main_factor))
            for amplitude in (float(value) for value in tone["amplitude_peaks_normalized"]):
                for tone_bin in (int(value) for value in tone["coherent_tone_bins"]):
                    values = tuple(
                        float(value)
                        for value in coherent_sine(
                            CoherentSineConfig(
                                sample_rate_hz=sample_rate,
                                sample_count=sample_count,
                                tone_bin=tone_bin,
                                amplitude_peak=amplitude,
                                phase_radians=float(tone["phase_radians"]),
                            )
                        )
                    )
                    predicted = predict_periodic_dual_path_settling(
                        values, theory_config, theory_settling
                    )
                    reduced = predict_periodic_settling(
                        values, theory_config, reduced_settling
                    )
                    state = DualPathSettlingState(*initial)
                    for _ in range(warmup_periods):
                        for index, value in enumerate(values):
                            state = process_dual_path(
                                value,
                                platform_config,
                                platform_settling,
                                state,
                                sample_index=index,
                            ).next_state

                    q2_mismatch = code_mismatch = correctable_mismatch = 0
                    max_main_error = max_aux_error = max_stage2_error = 0.0
                    for index, value in enumerate(values):
                        observed = process_dual_path(
                            value,
                            platform_config,
                            platform_settling,
                            state,
                            sample_index=index,
                        )
                        state = observed.next_state
                        q2_mismatch += (
                            predicted.stage2_symbols[index]
                            != observed.pipeline.stage2.quantizer.symbol
                        )
                        code_mismatch += (
                            predicted.output_codes[index]
                            != observed.pipeline.reconstruction.output_code
                        )
                        correctable_mismatch += (
                            predicted.correctable[index]
                            != observed.pipeline.reconstruction.correctable
                        )
                        max_main_error = max(
                            max_main_error,
                            abs(predicted.stage1_main_outputs[index] - observed.pipeline.stage1.residue),
                        )
                        max_aux_error = max(
                            max_aux_error,
                            abs(predicted.stage1_auxiliary_outputs[index] - observed.stage1_auxiliary_output),
                        )
                        max_stage2_error = max(
                            max_stage2_error,
                            abs(predicted.stage2_main_outputs[index] - observed.pipeline.stage2.residue),
                        )

                    dual_spectrum = analyze_coherent_tone(
                        predicted.output_codes,
                        sample_rate_hz=sample_rate,
                        fundamental_bin=tone_bin,
                        harmonic_orders=tuple(int(value) for value in tone["harmonic_orders"]),
                        full_scale_peak=float(tone["full_scale_peak_codes"]),
                    )
                    reduced_spectrum = analyze_coherent_tone(
                        reduced.output_codes,
                        sample_rate_hz=sample_rate,
                        fundamental_bin=tone_bin,
                        harmonic_orders=tuple(int(value) for value in tone["harmonic_orders"]),
                        full_scale_peak=float(tone["full_scale_peak_codes"]),
                    )
                    row = {
                        "case": case_name,
                        "provenance": case["provenance"],
                        "auxiliary_gain_ratio": ratio,
                        "amplitude_peak": amplitude,
                        "fundamental_bin": tone_bin,
                        "fundamental_frequency_hz": sample_rate * tone_bin / sample_count,
                        "main_factor": main_factor,
                        "auxiliary_factor": auxiliary_factor,
                        "q2_disagreements": q2_mismatch,
                        "code_disagreements": code_mismatch,
                        "correctable_disagreements": correctable_mismatch,
                        "max_main_absolute_error": max_main_error,
                        "max_auxiliary_absolute_error": max_aux_error,
                        "max_stage2_absolute_error": max_stage2_error,
                        "dual_vs_reduced_q2_differences": sum(
                            left != right
                            for left, right in zip(predicted.stage2_symbols, reduced.stage2_symbols, strict=True)
                        ),
                        "dual_vs_reduced_code_differences": sum(
                            left != right
                            for left, right in zip(predicted.output_codes, reduced.output_codes, strict=True)
                        ),
                        "dual_sndr_db": dual_spectrum.metrics.sndr_db,
                        "reduced_sndr_db": reduced_spectrum.metrics.sndr_db,
                        "dual_sfdr_dbc": dual_spectrum.metrics.sfdr_dbc,
                        "reduced_sfdr_dbc": reduced_spectrum.metrics.sfdr_dbc,
                        "uncorrectable_samples": sum(not item for item in predicted.correctable),
                    }
                    rows.append(row)
                    print(
                        f"{case_name}, ratio={ratio}, A={amplitude}, bin={tone_bin}: "
                        f"q2 Δ={row['dual_vs_reduced_q2_differences']}, "
                        f"code Δ={row['dual_vs_reduced_code_differences']}",
                        flush=True,
                    )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    experiment = read_yaml(EXPERIMENT_CONFIG)
    architecture_path = ROOT / experiment["architecture_config"]
    nonideality_path = ROOT / experiment["nonideality_config"]
    architecture = read_yaml(architecture_path)
    profile = read_yaml(nonideality_path)
    output_dir = ROOT / "artifacts" / "runs" / "EXP_019" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")

    main_factor = first_order_residual_factor(
        float(experiment["main_bandwidth_hz"]),
        float(experiment["main_phase_duration_s"]),
    )
    split_case = experiment["cases"]["split_paper_endpoints"]
    paper_aux_factor = first_order_residual_factor(
        float(split_case["auxiliary_bandwidth_hz"]),
        float(split_case["auxiliary_phase_duration_s"]),
    )
    probe = threshold_probe(architecture, main_factor, paper_aux_factor)
    static = static_grid_gate(experiment, architecture, profile)
    rows = dynamic_gate(experiment, architecture, main_factor)

    limits = experiment["acceptance"]
    max_analog_error = max(
        row[key]
        for row in rows
        for key in (
            "max_main_absolute_error",
            "max_auxiliary_absolute_error",
            "max_stage2_absolute_error",
        )
    )
    split_decision_differences = sum(
        row["dual_vs_reduced_q2_differences"]
        for row in rows
        if row["case"] == "split_paper_endpoints"
    )
    matched_code_disagreements = max(
        row["dual_vs_reduced_code_differences"]
        for row in rows
        if row["case"] == "matched_paths"
    )
    summary = {
        "experiment_id": experiment["experiment_id"],
        "scope": "conditional one-pole cross-sample-hold candidate with independent stage-1 auxiliary output",
        "paper_endpoints_do_not_identify_state_semantics": True,
        "record_count": len(rows),
        "dynamic_validation_samples": len(rows) * int(experiment["tone"]["sample_count"]),
        "main_residual_factor": main_factor,
        "paper_auxiliary_residual_factor_under_assumption": paper_aux_factor,
        "threshold_probe": probe,
        "static_grid": static,
        "maximum_dynamic_code_disagreements": max(row["code_disagreements"] for row in rows),
        "maximum_dynamic_q2_disagreements": max(row["q2_disagreements"] for row in rows),
        "maximum_dynamic_correctable_disagreements": max(row["correctable_disagreements"] for row in rows),
        "maximum_analog_absolute_error": max_analog_error,
        "matched_code_disagreements": matched_code_disagreements,
        "split_decision_differences": split_decision_differences,
        "records": rows,
    }
    summary["pass"] = all(
        (
            probe["distinguishes_decisions"],
            summary["maximum_dynamic_code_disagreements"] <= int(limits["maximum_theory_platform_code_disagreements"]),
            summary["maximum_dynamic_q2_disagreements"] <= int(limits["maximum_theory_platform_decision_disagreements"]),
            summary["maximum_dynamic_correctable_disagreements"] <= int(limits["maximum_theory_platform_correctable_disagreements"]),
            max_analog_error <= float(limits["maximum_analog_absolute_error"]),
            matched_code_disagreements <= int(limits["maximum_matched_reduced_code_disagreements"]),
            split_decision_differences >= int(limits["minimum_split_decision_disagreements"]),
            static["theory_platform_q2_disagreements"] <= int(limits["maximum_static_grid_disagreements"]),
            static["theory_platform_code_disagreements"] <= int(limits["maximum_static_grid_disagreements"]),
            static["theory_platform_correctable_disagreements"] <= int(limits["maximum_static_grid_disagreements"]),
            static["independent_vs_reduced_q2_differences"] >= int(limits["minimum_static_pwl_decision_disagreements"]),
        )
    )

    output_dir.mkdir(parents=True)
    (output_dir / "metrics.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    with (output_dir / "spectral_summary.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(
            {"experiment": experiment, "architecture": architecture, "nonidealities": profile},
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    tracked = [
        EXPERIMENT_CONFIG,
        Path(__file__).resolve(),
        architecture_path,
        nonideality_path,
        ROOT / "src/adc_research/platform/dual_path_settling.py",
        ROOT / "src/adc_research/platform/finite_settling.py",
        ROOT / "src/adc_research/theory/finite_settling.py",
        ROOT / "src/adc_research/theory/static_transfer.py",
    ]
    (output_dir / "environment.json").write_text(
        json.dumps(
            {
                "python": sys.version,
                "platform": platform.platform(),
                "argv": sys.argv,
                "source_sha256": source_hash(tracked),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps({key: value for key, value in summary.items() if key != "records"}, indent=2))
    print(output_dir)
    if not summary["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
