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

from adc_research.calibration.known_truth import (
    build_two_stage_oracle,
    correct_two_stage,
)
from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.metrics.static import CodeDensityMetrics, code_density_metrics
from adc_research.platform.pipeline import PipelineResult, process
from adc_research.platform.presets import (
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
)
from adc_research.platform.stimulus import (
    CoherentSineConfig,
    UniformRampConfig,
    coherent_sine,
    uniform_ramp,
)


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_CONFIG = Path(__file__).resolve().with_name("config.yaml")
SPECTRAL_MODE_NAMES = (
    "ideal",
    "pwl_uncalibrated",
    "pwl_known_truth_corrected",
)
STATIC_MODE_NAMES = SPECTRAL_MODE_NAMES + (
    "pwl_known_truth_corrected_balanced_dither",
)
DITHER_SYMBOL_PAIRS = ((-1, -1), (-1, 1), (1, -1), (1, 1))


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def source_hash(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def corrected_integer_code(raw: PipelineResult, oracle) -> int:
    value = round(correct_two_stage(raw, oracle).unclipped_output_code)
    return min(max(value, 0), 4095)


def maximum_absolute(values: tuple[float, ...]) -> float:
    return max(abs(value) for value in values)


def static_summary(metrics: CodeDensityMetrics) -> dict:
    return {
        "sample_count": metrics.sample_count,
        "ideal_count_per_code": metrics.ideal_count_per_code,
        "missing_code_count": len(metrics.missing_codes),
        "missing_codes": metrics.missing_codes,
        "minimum_dnl_lsb": metrics.minimum_dnl_lsb,
        "maximum_dnl_lsb": metrics.maximum_dnl_lsb,
        "maximum_absolute_dnl_lsb": maximum_absolute(metrics.dnl_lsb),
        "minimum_transition_inl_lsb": metrics.minimum_inl_lsb,
        "maximum_transition_inl_lsb": metrics.maximum_inl_lsb,
        "maximum_absolute_transition_inl_lsb": maximum_absolute(
            metrics.transition_inl_lsb
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
    output_dir = ROOT / "artifacts" / "runs" / "EXP_014" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    output_dir.mkdir(parents=True)

    pipeline = build_gu_static_hypothesis_a(architecture)
    pwl_nonidealities = build_gu_gate_d_nonidealities(
        truth_profile,
        enabled_effects=("static_pwl_truth",),
    )
    oracle = build_two_stage_oracle(pipeline, pwl_nonidealities)

    static_config = experiment["static_code_density"]
    ramp = uniform_ramp(
        UniformRampConfig(
            code_count=(
                static_config["maximum_code"]
                - static_config["minimum_code"]
                + 1
            ),
            samples_per_code=static_config["samples_per_code"],
        )
    )
    static_codes = {mode: [] for mode in STATIC_MODE_NAMES}
    static_physical_overloads = 0
    for sample_index, value in enumerate(ramp):
        ideal = process(float(value), pipeline, sample_index=sample_index)
        raw = process(
            float(value),
            pipeline,
            sample_index=sample_index,
            nonidealities=pwl_nonidealities,
        )
        raw_balanced_dither = process(
            float(value),
            pipeline,
            sample_index=sample_index,
            dither_symbols=DITHER_SYMBOL_PAIRS[sample_index % 4],
            nonidealities=pwl_nonidealities,
        )
        static_codes["ideal"].append(ideal.reconstruction.output_code)
        static_codes["pwl_uncalibrated"].append(
            raw.reconstruction.output_code
        )
        static_codes["pwl_known_truth_corrected"].append(
            corrected_integer_code(raw, oracle)
        )
        static_codes["pwl_known_truth_corrected_balanced_dither"].append(
            corrected_integer_code(raw_balanced_dither, oracle)
        )
        for result in (raw, raw_balanced_dither):
            static_physical_overloads += int(
                any(
                    not stage.correctable
                    or stage.main_input_overload_low
                    or stage.main_input_overload_high
                    for stage in (result.stage1, result.stage2)
                )
                or result.backend.overload_low
                or result.backend.overload_high
            )
    static_metrics = {
        mode: code_density_metrics(
            codes,
            minimum_code=static_config["minimum_code"],
            maximum_code=static_config["maximum_code"],
        )
        for mode, codes in static_codes.items()
    }
    static_results = {
        mode: static_summary(result) for mode, result in static_metrics.items()
    }

    with (output_dir / "static_code_density.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        fieldnames = ["code"]
        for mode in STATIC_MODE_NAMES:
            fieldnames.extend(
                (
                    f"{mode}_count",
                    f"{mode}_dnl_lsb",
                    f"{mode}_transition_inl_before_code_lsb",
                )
            )
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for index, code in enumerate(
            range(
                static_config["minimum_code"],
                static_config["maximum_code"] + 1,
            )
        ):
            row = {"code": code}
            for mode in STATIC_MODE_NAMES:
                metric = static_metrics[mode]
                row[f"{mode}_count"] = metric.histogram[index]
                row[f"{mode}_dnl_lsb"] = metric.dnl_lsb[index]
                row[f"{mode}_transition_inl_before_code_lsb"] = (
                    metric.transition_inl_lsb[index]
                )
            writer.writerow(row)

    spectral_config = experiment["spectral"]
    spectral_rows = []
    spectrum_arrays = {}
    spectral_physical_overloads = 0
    for tone_bin in spectral_config["coherent_tone_bins"]:
        tone = CoherentSineConfig(
            sample_rate_hz=float(spectral_config["sample_rate_hz"]),
            sample_count=spectral_config["sample_count"],
            tone_bin=tone_bin,
            amplitude_peak=spectral_config["amplitude_peak_normalized"],
        )
        values = coherent_sine(tone)
        codes = {mode: [] for mode in SPECTRAL_MODE_NAMES}
        for sample_index, value in enumerate(values):
            ideal = process(float(value), pipeline, sample_index=sample_index)
            raw = process(
                float(value),
                pipeline,
                sample_index=sample_index,
                nonidealities=pwl_nonidealities,
            )
            codes["ideal"].append(ideal.reconstruction.output_code)
            codes["pwl_uncalibrated"].append(raw.reconstruction.output_code)
            codes["pwl_known_truth_corrected"].append(
                corrected_integer_code(raw, oracle)
            )
            spectral_physical_overloads += int(
                any(
                    not stage.correctable
                    or stage.main_input_overload_low
                    or stage.main_input_overload_high
                    for stage in (raw.stage1, raw.stage2)
                )
                or raw.backend.overload_low
                or raw.backend.overload_high
            )
        for mode in SPECTRAL_MODE_NAMES:
            result = analyze_coherent_tone(
                codes[mode],
                sample_rate_hz=tone.sample_rate_hz,
                fundamental_bin=tone.tone_bin,
                harmonic_orders=tuple(spectral_config["harmonic_orders"]),
                full_scale_peak=spectral_config["full_scale_peak_codes"],
            )
            row = {"mode": mode, **asdict(result.metrics)}
            spectral_rows.append(row)
            prefix = f"{mode}_bin_{tone_bin}"
            spectrum_arrays[f"{prefix}_frequency_hz"] = np.asarray(
                result.frequencies_hz
            )
            spectrum_arrays[f"{prefix}_rms_power"] = np.asarray(result.rms_power)
        print(
            f"completed coherent tone bin {tone_bin} "
            f"({tone.tone_frequency_hz / 1e6:.6f} MHz)",
            flush=True,
        )

    with (output_dir / "spectral_summary.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=spectral_rows[0].keys())
        writer.writeheader()
        writer.writerows(spectral_rows)
    np.savez_compressed(output_dir / "spectra.npz", **spectrum_arrays)

    ideal_sndr = [
        row["sndr_db"] for row in spectral_rows if row["mode"] == "ideal"
    ]
    corrections = []
    for tone_bin in spectral_config["coherent_tone_bins"]:
        uncalibrated = next(
            row
            for row in spectral_rows
            if row["mode"] == "pwl_uncalibrated"
            and row["fundamental_bin"] == tone_bin
        )
        corrected = next(
            row
            for row in spectral_rows
            if row["mode"] == "pwl_known_truth_corrected"
            and row["fundamental_bin"] == tone_bin
        )
        corrections.append(
            {
                "fundamental_bin": tone_bin,
                "frequency_hz": corrected["fundamental_frequency_hz"],
                "sndr_improvement_db": (
                    corrected["sndr_db"] - uncalibrated["sndr_db"]
                ),
                "sfdr_improvement_db": (
                    corrected["sfdr_dbc"] - uncalibrated["sfdr_dbc"]
                ),
                "thd_change_db": corrected["thd_db"] - uncalibrated["thd_db"],
            }
        )

    acceptance = experiment["acceptance"]
    ideal_static = static_results["ideal"]
    corrected_balanced_static = static_results[
        "pwl_known_truth_corrected_balanced_dither"
    ]
    pass_status = all(
        (
            ideal_static["maximum_absolute_dnl_lsb"]
            <= acceptance["maximum_ideal_absolute_dnl_lsb"],
            ideal_static["maximum_absolute_transition_inl_lsb"]
            <= acceptance["maximum_ideal_absolute_inl_lsb"],
            ideal_static["missing_code_count"]
            <= acceptance["maximum_ideal_missing_codes"],
            min(ideal_sndr) >= acceptance["minimum_ideal_sndr_db"],
            max(ideal_sndr) <= acceptance["maximum_ideal_sndr_db"],
            max(ideal_sndr) - min(ideal_sndr)
            <= acceptance["maximum_ideal_sndr_spread_db"],
            min(item["sfdr_improvement_db"] for item in corrections)
            >= acceptance["minimum_pwl_corrected_sfdr_improvement_db"],
            min(item["sndr_improvement_db"] for item in corrections)
            >= acceptance["minimum_pwl_corrected_sndr_improvement_db"],
            corrected_balanced_static["missing_code_count"]
            <= acceptance[
                "maximum_pwl_corrected_balanced_dither_missing_codes"
            ],
            static_physical_overloads + spectral_physical_overloads
            <= acceptance["maximum_physical_overloads"],
        )
    )

    metrics = {
        "experiment_id": experiment["experiment_id"],
        "architecture_config": architecture["config_id"],
        "truth_config": truth_profile["config_id"],
        "protocol": {
            "static": "uniform full-range code density",
            "dnl": "observed code count divided by mean count minus one",
            "inl": "cumulative DNL from the lower endpoint at code transitions",
            "spectral": "rectangular-window coherent single-tone real FFT",
            "bandwidth": "dc to first Nyquist frequency",
            "dc": "removed before FFT and excluded from power ratios",
            "fundamental": "configured single FFT bin",
            "harmonics": "orders 2 through 5 folded into the first Nyquist zone",
            "final_integer_rounding": "nearest even for known-truth correction",
            "static_dither_comparison": (
                "known-truth correction is reported both without dither and "
                "with the four dither-symbol pairs used equally often"
            ),
        },
        "paper_directional_anchors": {
            "simulated_four_slice_thd_nominal_db": -80.0,
            "simulated_four_slice_thd_worst_case_db": -75.0,
            "measured_1ghz_without_gain_nonlinearity_calibration": {
                "sndr_db": 54.0,
                "sfdr_db": 62.7,
            },
            "measured_1ghz_with_gain_nonlinearity_calibration": {
                "sndr_db": 60.3,
                "sfdr_db": 76.0,
            },
            "claim_limit": (
                "directional comparison only; the static platform does not "
                "model measurement noise, input-buffer distortion, sampling "
                "distortion, or complete SHA-less timing"
            ),
        },
        "static_code_density": static_results,
        "spectral_summary": spectral_rows,
        "pwl_correction_changes": corrections,
        "physical_overloads": {
            "static": static_physical_overloads,
            "spectral": spectral_physical_overloads,
        },
        "pass": pass_status,
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )
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
        ROOT / "src" / "adc_research" / "metrics" / "static.py",
        ROOT / "src" / "adc_research" / "metrics" / "spectral.py",
        ROOT / "src" / "adc_research" / "platform" / "stimulus.py",
        ROOT / "src" / "adc_research" / "platform" / "pipeline.py",
        ROOT / "src" / "adc_research" / "calibration" / "known_truth.py",
    ]
    (output_dir / "environment.json").write_text(
        json.dumps(
            {
                "python": sys.version,
                "numpy": np.__version__,
                "platform": platform.platform(),
                "argv": sys.argv,
                "source_sha256": source_hash(tracked_sources),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    compact = {
        "experiment_id": metrics["experiment_id"],
        "static_code_density": metrics["static_code_density"],
        "spectral_summary": [
            {
                key: row[key]
                for key in (
                    "mode",
                    "fundamental_frequency_hz",
                    "fundamental_dbfs",
                    "sndr_db",
                    "thd_db",
                    "sfdr_dbc",
                    "enob_bits",
                )
            }
            for row in spectral_rows
        ],
        "pwl_correction_changes": corrections,
        "pass": pass_status,
    }
    print(json.dumps(compact, indent=2))
    print(output_dir)
    if not pass_status:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
