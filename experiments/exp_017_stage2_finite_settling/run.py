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

from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.platform.finite_settling import (
    FiniteSettlingConfig,
    SettlingState,
    process,
)
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stimulus import CoherentSineConfig, coherent_sine
from adc_research.theory.finite_settling import (
    PeriodicSettlingConfig,
    equivalent_settling_bits,
    first_order_residual_factor,
    predict_periodic_settling,
)
from adc_research.theory.static_spectrum import predict_finite_coherent_tone
from adc_research.theory.static_transfer import (
    build_gu_theory_config,
    predict_static_transfer,
)


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_CONFIG = Path(__file__).resolve().with_name("config.yaml")
DB_METRIC_NAMES = ("sndr_db", "snr_db", "thd_db", "sfdr_dbc")


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def source_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def resolved_residual_factors(case: dict) -> tuple[float, float]:
    if "residual_factors" in case:
        return tuple(float(value) for value in case["residual_factors"])
    bandwidths = tuple(float(value) for value in case["bandwidth_hz"])
    durations = tuple(float(value) for value in case["phase_duration_s"])
    return tuple(
        first_order_residual_factor(bandwidth, duration)
        for bandwidth, duration in zip(bandwidths, durations, strict=True)
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    experiment = read_yaml(EXPERIMENT_CONFIG)
    architecture_path = ROOT / experiment["architecture_config"]
    architecture = read_yaml(architecture_path)
    theory_config = build_gu_theory_config(architecture)
    platform_config = build_gu_static_hypothesis_a(architecture)
    static_transfer = predict_static_transfer(theory_config)
    output_dir = ROOT / "artifacts" / "runs" / "EXP_017" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    output_dir.mkdir(parents=True)

    tone = experiment["tone"]
    sample_rate_hz = float(tone["sample_rate_hz"])
    sample_count = int(tone["sample_count"])
    tone_bins = tuple(int(value) for value in tone["coherent_tone_bins"])
    amplitudes = tuple(float(value) for value in tone["amplitude_peaks_normalized"])
    phase_radians = float(tone["phase_radians"])
    harmonic_orders = tuple(int(value) for value in tone["harmonic_orders"])
    full_scale_peak = float(tone["full_scale_peak_codes"])
    validation = experiment["platform_validation"]
    initial_state_values = tuple(
        float(value) for value in validation["initial_stage_residues"]
    )
    warmup_periods = int(validation["warmup_periods"])

    rows = []
    for case_name, case in experiment["cases"].items():
        residual_factors = resolved_residual_factors(case)
        theory_settling = PeriodicSettlingConfig(residual_factors)
        platform_settling = FiniteSettlingConfig(residual_factors)
        equivalent_bits = tuple(
            equivalent_settling_bits(value) for value in residual_factors
        )
        for amplitude in amplitudes:
            for tone_bin in tone_bins:
                stimulus = coherent_sine(
                    CoherentSineConfig(
                        sample_rate_hz=sample_rate_hz,
                        sample_count=sample_count,
                        tone_bin=tone_bin,
                        amplitude_peak=amplitude,
                        phase_radians=phase_radians,
                    )
                )
                values = tuple(float(value) for value in stimulus)
                predicted = predict_periodic_settling(
                    values,
                    theory_config,
                    theory_settling,
                )

                state = SettlingState(*initial_state_values)
                for _ in range(warmup_periods):
                    for sample_index, value in enumerate(values):
                        state = process(
                            value,
                            platform_config,
                            platform_settling,
                            state,
                            sample_index=sample_index,
                        ).next_state

                observed_codes = []
                observed_correctable = []
                maximum_stage1_error = 0.0
                maximum_stage2_error = 0.0
                for sample_index, value in enumerate(values):
                    result = process(
                        value,
                        platform_config,
                        platform_settling,
                        state,
                        sample_index=sample_index,
                    )
                    state = result.next_state
                    pipeline = result.pipeline
                    observed_codes.append(pipeline.reconstruction.output_code)
                    observed_correctable.append(
                        pipeline.reconstruction.correctable
                    )
                    maximum_stage1_error = max(
                        maximum_stage1_error,
                        abs(
                            predicted.stage1_residues[sample_index]
                            - pipeline.stage1.residue
                        ),
                    )
                    maximum_stage2_error = max(
                        maximum_stage2_error,
                        abs(
                            predicted.stage2_residues[sample_index]
                            - pipeline.stage2.residue
                        ),
                    )

                code_disagreements = sum(
                    left != right
                    for left, right in zip(
                        predicted.output_codes,
                        observed_codes,
                        strict=True,
                    )
                )
                correctable_disagreements = sum(
                    left != right
                    for left, right in zip(
                        predicted.correctable,
                        observed_correctable,
                        strict=True,
                    )
                )
                theory_spectrum = analyze_coherent_tone(
                    predicted.output_codes,
                    sample_rate_hz=sample_rate_hz,
                    fundamental_bin=tone_bin,
                    harmonic_orders=harmonic_orders,
                    full_scale_peak=full_scale_peak,
                )
                platform_spectrum = analyze_coherent_tone(
                    observed_codes,
                    sample_rate_hz=sample_rate_hz,
                    fundamental_bin=tone_bin,
                    harmonic_orders=harmonic_orders,
                    full_scale_peak=full_scale_peak,
                )
                metric_errors = {
                    name: abs(
                        getattr(theory_spectrum.metrics, name)
                        - getattr(platform_spectrum.metrics, name)
                    )
                    for name in DB_METRIC_NAMES
                }

                static_limit_disagreements = None
                if case_name == "static_limit":
                    static = predict_finite_coherent_tone(
                        static_transfer,
                        sample_rate_hz=sample_rate_hz,
                        sample_count=sample_count,
                        fundamental_bin=tone_bin,
                        amplitude_peak=amplitude,
                        phase_radians=phase_radians,
                        harmonic_orders=harmonic_orders,
                        full_scale_peak=full_scale_peak,
                    )
                    static_limit_disagreements = sum(
                        left != right
                        for left, right in zip(
                            predicted.output_codes,
                            static.output_codes,
                            strict=True,
                        )
                    )

                row = {
                    "case": case_name,
                    "provenance": case["provenance"],
                    "amplitude_peak": amplitude,
                    "fundamental_bin": tone_bin,
                    "fundamental_frequency_hz": (
                        sample_rate_hz * tone_bin / sample_count
                    ),
                    "stage1_residual_factor": residual_factors[0],
                    "stage2_residual_factor": residual_factors[1],
                    "stage1_equivalent_bits": equivalent_bits[0],
                    "stage2_equivalent_bits": equivalent_bits[1],
                    "code_disagreements": code_disagreements,
                    "correctable_disagreements": correctable_disagreements,
                    "maximum_stage1_residue_absolute_error": maximum_stage1_error,
                    "maximum_stage2_residue_absolute_error": maximum_stage2_error,
                    "uncorrectable_samples": sum(
                        not value for value in predicted.correctable
                    ),
                    "static_limit_code_disagreements": static_limit_disagreements,
                }
                for name, value in asdict(theory_spectrum.metrics).items():
                    row[f"theory_{name}"] = value
                for name, value in asdict(platform_spectrum.metrics).items():
                    row[f"platform_{name}"] = value
                for name, value in metric_errors.items():
                    row[f"{name}_absolute_error_db"] = value
                rows.append(row)
                print(
                    f"completed {case_name}, A={amplitude}, bin={tone_bin}: "
                    f"{code_disagreements} code disagreements",
                    flush=True,
                )

    frequency_spreads = []
    for case_name in experiment["cases"]:
        for amplitude in amplitudes:
            group = [
                row
                for row in rows
                if row["case"] == case_name
                and row["amplitude_peak"] == amplitude
            ]
            frequency_spreads.append(
                {
                    "case": case_name,
                    "amplitude_peak": amplitude,
                    "sndr_spread_db": max(row["theory_sndr_db"] for row in group)
                    - min(row["theory_sndr_db"] for row in group),
                    "sfdr_spread_db": max(row["theory_sfdr_dbc"] for row in group)
                    - min(row["theory_sfdr_dbc"] for row in group),
                }
            )

    finite_stage_errors = [
        row[key]
        for row in rows
        for key in (
            "maximum_stage1_residue_absolute_error",
            "maximum_stage2_residue_absolute_error",
        )
    ]
    static_limit_errors = [
        row["static_limit_code_disagreements"]
        for row in rows
        if row["static_limit_code_disagreements"] is not None
    ]
    maxima = {
        "code_disagreements": max(row["code_disagreements"] for row in rows),
        "correctable_disagreements": max(
            row["correctable_disagreements"] for row in rows
        ),
        "stage_residue_absolute_error": max(finite_stage_errors),
        "metric_absolute_error_db": max(
            row[f"{name}_absolute_error_db"]
            for row in rows
            for name in DB_METRIC_NAMES
        ),
        "static_limit_code_disagreements": max(static_limit_errors),
        "uncorrectable_samples": max(row["uncorrectable_samples"] for row in rows),
    }
    anchor_row = next(
        row for row in rows if row["case"] == "paper_main_path_anchor"
    )
    anchor_bits = anchor_row["stage1_equivalent_bits"]
    acceptance = experiment["acceptance"]
    pass_status = all(
        (
            maxima["code_disagreements"]
            <= int(acceptance["maximum_code_disagreements"]),
            maxima["correctable_disagreements"]
            <= int(acceptance["maximum_correctable_disagreements"]),
            maxima["stage_residue_absolute_error"]
            <= float(acceptance["maximum_stage_residue_absolute_error"]),
            maxima["metric_absolute_error_db"]
            <= float(acceptance["maximum_metric_absolute_error_db"]),
            maxima["static_limit_code_disagreements"]
            <= int(acceptance["maximum_static_limit_code_disagreements"]),
            maxima["uncorrectable_samples"]
            <= int(acceptance["maximum_uncorrectable_samples"]),
            anchor_bits >= float(acceptance["minimum_anchor_equivalent_bits"]),
            anchor_bits <= float(acceptance["maximum_anchor_equivalent_bits"]),
        )
    )

    metrics = {
        "experiment_id": experiment["experiment_id"],
        "model_scope": (
            "stateful one-pole main-path settling with periodic steady-state "
            "input and no digital calibration"
        ),
        "paper_anchor_interpretation": (
            "11 GHz and 100 ps jointly imply approximately 10-bit one-pole "
            "small-signal settling; they do not identify reset, slew, or "
            "large-signal memory semantics"
        ),
        "theory_method": (
            "closed-form periodic boundary condition followed by one cyclic pass"
        ),
        "platform_method": (
            "sample-wise state recurrence from a held-out initial state and "
            "one full warmup period"
        ),
        "record_count": len(rows),
        "total_validation_samples": len(rows) * sample_count,
        "anchor_equivalent_bits": anchor_bits,
        "maxima": maxima,
        "frequency_spreads": frequency_spreads,
        "records": rows,
        "pass": pass_status,
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    with (output_dir / "spectral_summary.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
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
        ROOT / "src" / "adc_research" / "theory" / "finite_settling.py",
        ROOT / "src" / "adc_research" / "theory" / "static_transfer.py",
        ROOT / "src" / "adc_research" / "platform" / "finite_settling.py",
        ROOT / "src" / "adc_research" / "platform" / "stage.py",
        ROOT / "src" / "adc_research" / "metrics" / "spectral.py",
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
    print(
        json.dumps(
            {
                "anchor_equivalent_bits": anchor_bits,
                "maxima": maxima,
                "frequency_spreads": frequency_spreads,
                "pass": pass_status,
            },
            indent=2,
        )
    )
    print(output_dir)
    if not pass_status:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
