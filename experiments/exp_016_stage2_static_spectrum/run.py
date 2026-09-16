from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import yaml

from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.platform.pipeline import process
from adc_research.platform.presets import (
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
)
from adc_research.theory.static_spectrum import (
    continuous_tone_metrics,
    predict_continuous_tone,
    predict_finite_coherent_tone,
)
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    experiment = read_yaml(EXPERIMENT_CONFIG)
    architecture_path = ROOT / experiment["architecture_config"]
    nonidealities_path = ROOT / experiment["nonidealities_config"]
    architecture = read_yaml(architecture_path)
    nonidealities = read_yaml(nonidealities_path)
    output_dir = ROOT / "artifacts" / "runs" / "EXP_016" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    output_dir.mkdir(parents=True)

    tone = experiment["tone"]
    sample_rate_hz = float(tone["sample_rate_hz"])
    sample_count = int(tone["sample_count"])
    tone_bins = tuple(int(value) for value in tone["coherent_tone_bins"])
    amplitudes = tuple(float(value) for value in tone["amplitude_peaks_normalized"])
    offset = float(tone["offset_normalized"])
    phase_radians = float(tone["phase_radians"])
    harmonic_orders = tuple(int(value) for value in tone["harmonic_orders"])
    full_scale_peak = float(tone["full_scale_peak_codes"])
    continuous_orders = (0, 1, *harmonic_orders)

    rows: list[dict] = []
    harmonic_rows: list[dict] = []
    for case_name, case in experiment["cases"].items():
        enabled = tuple(case["enabled_effects"])
        transfer = predict_static_transfer(
            build_gu_theory_config(
                architecture,
                nonidealities=nonidealities,
                enabled_effects=enabled,
            )
        )
        reference = build_gu_static_hypothesis_a(architecture)
        applied = build_gu_gate_d_nonidealities(
            nonidealities,
            enabled_effects=enabled,
        )

        for amplitude in amplitudes:
            continuous = predict_continuous_tone(
                transfer,
                amplitude_peak=amplitude,
                offset=offset,
                harmonic_orders=continuous_orders,
            )
            continuous_metrics = continuous_tone_metrics(
                continuous,
                harmonic_orders=harmonic_orders,
                full_scale_peak=full_scale_peak,
            )
            for order in continuous_orders:
                coefficient = continuous.coefficient(order)
                harmonic_rows.append(
                    {
                        "case": case_name,
                        "amplitude_peak": amplitude,
                        "harmonic_order": order,
                        "coefficient_real": coefficient.real,
                        "coefficient_imag": coefficient.imag,
                        "single_sided_power": continuous.single_sided_power(order),
                    }
                )

            for tone_bin in tone_bins:
                predicted = predict_finite_coherent_tone(
                    transfer,
                    sample_rate_hz=sample_rate_hz,
                    sample_count=sample_count,
                    fundamental_bin=tone_bin,
                    amplitude_peak=amplitude,
                    offset=offset,
                    phase_radians=phase_radians,
                    harmonic_orders=harmonic_orders,
                    full_scale_peak=full_scale_peak,
                )
                observed_codes: list[int] = []
                code_disagreements = 0
                correctable_disagreements = 0
                uncorrectable_samples = 0
                maximum_code_error = 0
                for sample_index, input_value in enumerate(predicted.input_values):
                    observed = process(
                        input_value,
                        reference,
                        sample_index=sample_index,
                        nonidealities=applied,
                    )
                    observed_code = observed.reconstruction.output_code
                    observed_codes.append(observed_code)
                    predicted_segment = transfer.segment_at(input_value)
                    code_error = abs(
                        predicted_segment.output_code - observed_code
                    )
                    correctable_error = (
                        predicted_segment.correctable
                        != observed.reconstruction.correctable
                    )
                    code_disagreements += code_error != 0
                    correctable_disagreements += correctable_error
                    uncorrectable_samples += not observed.reconstruction.correctable
                    maximum_code_error = max(maximum_code_error, code_error)

                observed_spectrum = analyze_coherent_tone(
                    observed_codes,
                    sample_rate_hz=sample_rate_hz,
                    fundamental_bin=tone_bin,
                    harmonic_orders=harmonic_orders,
                    full_scale_peak=full_scale_peak,
                )
                predicted_metrics = predicted.spectrum.metrics
                observed_metrics = observed_spectrum.metrics
                metric_errors = {
                    name: abs(
                        getattr(predicted_metrics, name)
                        - getattr(observed_metrics, name)
                    )
                    for name in DB_METRIC_NAMES
                }
                predicted_power = np.asarray(predicted.spectrum.rms_power)
                observed_power = np.asarray(observed_spectrum.rms_power)
                finite_total_ac_power = float(np.sum(predicted_power[1:]))
                continuous_fundamental = (
                    continuous.coefficient(1) * np.exp(1j * phase_radians)
                )

                row = {
                    "case": case_name,
                    "enabled_effects": enabled,
                    "amplitude_peak": amplitude,
                    "fundamental_bin": tone_bin,
                    "fundamental_frequency_hz": (
                        sample_rate_hz * tone_bin / sample_count
                    ),
                    "phase_interval_count": len(continuous.phase_intervals),
                    "continuous_correctable_phase_fraction": (
                        continuous.correctable_phase_fraction
                    ),
                    "code_disagreements": code_disagreements,
                    "correctable_disagreements": correctable_disagreements,
                    "maximum_code_error": maximum_code_error,
                    "uncorrectable_samples": uncorrectable_samples,
                    "maximum_spectrum_power_absolute_error": float(
                        np.max(np.abs(predicted_power - observed_power))
                    ),
                    "continuous_dc_code": continuous_metrics.dc_code,
                    "continuous_fundamental_rms": (
                        continuous_metrics.fundamental_rms
                    ),
                    "continuous_total_ac_power": (
                        continuous_metrics.total_ac_power
                    ),
                    "continuous_sndr_db": continuous_metrics.sndr_db,
                    "continuous_snr_db": continuous_metrics.snr_db,
                    "continuous_thd_db": continuous_metrics.thd_db,
                    "continuous_enob_bits": continuous_metrics.enob_bits,
                    "finite_continuous_dc_error_code": abs(
                        predicted_metrics.dc_code - continuous_metrics.dc_code
                    ),
                    "finite_continuous_fundamental_rms_error_code": abs(
                        predicted_metrics.fundamental_rms
                        - continuous_metrics.fundamental_rms
                    ),
                    "finite_continuous_total_ac_power_error": abs(
                        finite_total_ac_power
                        - continuous_metrics.total_ac_power
                    ),
                    "finite_continuous_fundamental_coefficient_error": abs(
                        predicted.complex_spectrum[tone_bin]
                        - continuous_fundamental
                    ),
                    "finite_continuous_sndr_error_db": abs(
                        predicted_metrics.sndr_db - continuous_metrics.sndr_db
                    ),
                }
                for name, value in asdict(predicted_metrics).items():
                    row[f"theory_{name}"] = value
                for name, value in asdict(observed_metrics).items():
                    row[f"platform_{name}"] = value
                for name, value in metric_errors.items():
                    row[f"{name}_absolute_error_db"] = value
                rows.append(row)
                print(
                    f"completed {case_name}, A={amplitude}, bin={tone_bin}: "
                    f"{code_disagreements} code disagreements",
                    flush=True,
                )

    frequency_spreads: list[dict] = []
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

    maxima = {
        "code_disagreements": max(row["code_disagreements"] for row in rows),
        "correctable_disagreements": max(
            row["correctable_disagreements"] for row in rows
        ),
        "uncorrectable_samples": max(row["uncorrectable_samples"] for row in rows),
        "metric_absolute_error_db": max(
            row[f"{name}_absolute_error_db"]
            for row in rows
            for name in DB_METRIC_NAMES
        ),
        "spectrum_power_absolute_error": max(
            row["maximum_spectrum_power_absolute_error"] for row in rows
        ),
        "static_frequency_sndr_spread_db": max(
            row["sndr_spread_db"] for row in frequency_spreads
        ),
        "static_frequency_sfdr_spread_db": max(
            row["sfdr_spread_db"] for row in frequency_spreads
        ),
        "finite_continuous_sndr_error_db": max(
            row["finite_continuous_sndr_error_db"] for row in rows
        ),
    }
    acceptance = experiment["acceptance"]
    pass_status = all(
        (
            maxima["code_disagreements"]
            <= int(acceptance["maximum_code_disagreements"]),
            maxima["correctable_disagreements"]
            <= int(acceptance["maximum_correctable_disagreements"]),
            maxima["metric_absolute_error_db"]
            <= float(acceptance["maximum_metric_absolute_error_db"]),
            maxima["spectrum_power_absolute_error"]
            <= float(acceptance["maximum_spectrum_power_absolute_error"]),
            maxima["static_frequency_sndr_spread_db"]
            <= float(acceptance["maximum_static_frequency_sndr_spread_db"]),
            maxima["static_frequency_sfdr_spread_db"]
            <= float(acceptance["maximum_static_frequency_sfdr_spread_db"]),
            maxima["finite_continuous_sndr_error_db"]
            <= float(acceptance["maximum_finite_continuous_sndr_error_db"]),
            maxima["uncorrectable_samples"]
            <= int(acceptance["maximum_uncorrectable_samples"]),
        )
    )

    metrics = {
        "experiment_id": experiment["experiment_id"],
        "prediction_scope": (
            "memoryless static transfer under a deterministic sinusoidal input"
        ),
        "continuous_method": (
            "exact sine-phase partition and closed-form Fourier integration"
        ),
        "finite_record_method": (
            "theory transfer evaluation on coherent phases followed by the "
            "shared rectangular-window FFT metric protocol"
        ),
        "sfdr_scope": (
            "finite first-Nyquist-zone record; continuous staircase SFDR is "
            "not claimed from a finite harmonic subset"
        ),
        "record_count": len(rows),
        "total_holdout_samples": len(rows) * sample_count,
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
    with (output_dir / "continuous_harmonics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=harmonic_rows[0].keys())
        writer.writeheader()
        writer.writerows(harmonic_rows)
    (output_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(
            {
                "experiment": experiment,
                "architecture": architecture,
                "nonidealities": nonidealities,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    tracked_sources = [
        EXPERIMENT_CONFIG,
        architecture_path,
        nonidealities_path,
        ROOT / "src" / "adc_research" / "theory" / "static_spectrum.py",
        ROOT / "src" / "adc_research" / "theory" / "static_transfer.py",
        ROOT / "src" / "adc_research" / "metrics" / "spectral.py",
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
    print(json.dumps({"maxima": maxima, "pass": pass_status}, indent=2))
    print(output_dir)
    if not pass_status:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
