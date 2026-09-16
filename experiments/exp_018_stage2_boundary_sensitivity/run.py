from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import yaml

from adc_research.platform.pipeline import process
from adc_research.platform.presets import (
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
)
from adc_research.theory.static_sensitivity import (
    first_stage_threshold_sensitivity,
    moving_step_fourier_derivatives,
)
from adc_research.theory.static_spectrum import predict_continuous_tone
from adc_research.theory.static_transfer import (
    StaticPipelineTheoryConfig,
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


def shifted_threshold(
    config: StaticPipelineTheoryConfig, index: int, amount: float
) -> StaticPipelineTheoryConfig:
    offsets = list(config.stage1.threshold_offsets or (0.0,) * len(config.stage1.thresholds))
    offsets[index] += amount
    return replace(config, stage1=replace(config.stage1, threshold_offsets=tuple(offsets)))


def toy_checks(experiment: dict) -> dict:
    rows = []
    for threshold in experiment["toy_thresholds"]:
        derivatives, _, _ = moving_step_fourier_derivatives(
            input_boundary=float(threshold),
            input_boundary_derivative=1.0,
            code_jump_with_increasing_input=1.0,
            amplitude_peak=1.0,
            orders=(0, 1),
        )
        expected_dc = -1 / (math.pi * math.sqrt(1 - threshold * threshold))
        expected_fundamental = 1j * threshold / (
            math.pi * math.sqrt(1 - threshold * threshold)
        )
        rows.append(
            {
                "threshold": threshold,
                "dc_derivative_absolute_error": abs(derivatives[0] - expected_dc),
                "fundamental_derivative_absolute_error": abs(
                    derivatives[1] - expected_fundamental
                ),
            }
        )

    # A separate continuous readout has a nonzero interior term and no moving
    # boundary: y_a(phi)=a*sin(phi), c_1(a)=-j*a/2.
    phases = 2 * math.pi * np.arange(65536) / 65536
    def continuous_coefficient(gain: float) -> complex:
        return complex(np.mean(gain * np.sin(phases) * np.exp(-1j * phases)))
    internal_difference = (
        continuous_coefficient(1.0001) - continuous_coefficient(0.9999)
    ) / 0.0002
    internal_error = abs(internal_difference + 0.5j)

    # At fixed M, no sample crosses a threshold under a sufficiently small
    # change, so the code-record DC difference is exactly zero.
    sample_count = int(experiment["fixed_record_sample_count"])
    phase_offset = float(experiment["fixed_record_phase_radians"])
    grid = 2 * math.pi * np.arange(sample_count) / sample_count + phase_offset
    values = np.sin(grid)
    threshold = float(experiment["toy_thresholds"][0])
    nearest_sample_distance = float(np.min(np.abs(values - threshold)))
    finite_step = nearest_sample_distance / 4
    finite_difference = float(
        (np.mean(values >= threshold + finite_step)
         - np.mean(values >= threshold - finite_step))
        / (2 * finite_step)
    )

    tangent_low = abs(-1 / (math.pi * math.sqrt(1 - 0.9**2)))
    tangent_high = abs(-1 / (math.pi * math.sqrt(1 - 0.99**2)))
    return {
        "toy_rows": rows,
        "maximum_toy_derivative_absolute_error": max(
            max(row["dc_derivative_absolute_error"], row["fundamental_derivative_absolute_error"])
            for row in rows
        ),
        "continuous_internal_derivative_absolute_error": internal_error,
        "fixed_record_nearest_sample_distance": nearest_sample_distance,
        "fixed_record_step": finite_step,
        "fixed_record_dc_finite_difference": finite_difference,
        "continuous_dc_derivative_at_same_threshold": -1
        / (math.pi * math.sqrt(1 - threshold**2)),
        "tangent_derivative_amplification_ratio_099_over_09": tangent_high / tangent_low,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    experiment = read_yaml(EXPERIMENT_CONFIG)
    architecture_path = ROOT / experiment["architecture_config"]
    nonideality_path = ROOT / experiment["nonideality_config"]
    architecture = read_yaml(architecture_path)
    nonideality = read_yaml(nonideality_path)
    effects = tuple(experiment["enabled_effects"])

    config = build_gu_theory_config(
        architecture, nonidealities=nonideality, enabled_effects=effects
    )
    transfer = predict_static_transfer(config)
    platform_config = build_gu_static_hypothesis_a(architecture)
    platform_effects = build_gu_gate_d_nonidealities(
        nonideality, enabled_effects=effects
    )
    orders = tuple(int(order) for order in experiment["harmonic_orders"])
    amplitudes = tuple(float(value) for value in experiment["amplitude_peaks_normalized"])
    steps = tuple(float(value) for value in experiment["threshold_offset_steps"])
    rows = []
    code_jump_disagreements = 0

    for threshold_index in experiment["first_stage_threshold_indices"]:
        index = int(threshold_index)
        first = first_stage_threshold_sensitivity(
            transfer, config, threshold_index=index, amplitude_peak=amplitudes[0], orders=orders
        )
        boundary_probe = first.nearest_other_boundary_distance / 4
        left_observed = process(
            first.input_boundary - boundary_probe,
            platform_config,
            sample_index=0,
            nonidealities=platform_effects,
        ).reconstruction.output_code
        right_observed = process(
            first.input_boundary + boundary_probe,
            platform_config,
            sample_index=1,
            nonidealities=platform_effects,
        ).reconstruction.output_code
        code_jump_disagreements += int(
            (left_observed, right_observed) != (first.left_code, first.right_code)
        )

        for step in steps:
            if step >= first.nearest_other_boundary_distance / 4:
                raise ValueError("step is too large for the local topology margin")
            plus = predict_static_transfer(shifted_threshold(config, index, step))
            minus = predict_static_transfer(shifted_threshold(config, index, -step))
            for amplitude in amplitudes:
                sensitivity = first_stage_threshold_sensitivity(
                    transfer,
                    config,
                    threshold_index=index,
                    amplitude_peak=amplitude,
                    orders=orders,
                )
                upper = predict_continuous_tone(
                    plus, amplitude_peak=amplitude, harmonic_orders=orders
                )
                lower = predict_continuous_tone(
                    minus, amplitude_peak=amplitude, harmonic_orders=orders
                )
                for order in orders:
                    analytic = sensitivity.coefficient_derivative(order)
                    finite_difference = (
                        upper.coefficient(order) - lower.coefficient(order)
                    ) / (2 * step)
                    rows.append(
                        {
                            "threshold_index": index,
                            "input_boundary": sensitivity.input_boundary,
                            "nearest_other_boundary_distance": sensitivity.nearest_other_boundary_distance,
                            "left_code": sensitivity.left_code,
                            "right_code": sensitivity.right_code,
                            "platform_left_code": left_observed,
                            "platform_right_code": right_observed,
                            "amplitude_peak": amplitude,
                            "step": step,
                            "harmonic_order": order,
                            "analytic_real": analytic.real,
                            "analytic_imag": analytic.imag,
                            "finite_difference_real": finite_difference.real,
                            "finite_difference_imag": finite_difference.imag,
                            "absolute_error": abs(finite_difference - analytic),
                        }
                    )

    toy = toy_checks(experiment)
    maximum_full_error = max(row["absolute_error"] for row in rows)
    acceptance = experiment["acceptance"]
    passed = (
        toy["maximum_toy_derivative_absolute_error"]
        <= acceptance["maximum_toy_derivative_absolute_error"]
        and toy["continuous_internal_derivative_absolute_error"]
        <= acceptance["maximum_toy_derivative_absolute_error"]
        and code_jump_disagreements <= acceptance["maximum_full_adc_code_jump_disagreements"]
        and maximum_full_error
        <= acceptance["maximum_full_adc_derivative_absolute_error"]
        and toy["tangent_derivative_amplification_ratio_099_over_09"]
        >= acceptance["minimum_tangent_amplification_ratio"]
        and toy["fixed_record_dc_finite_difference"] == 0
    )

    output_dir = ROOT / "artifacts" / "runs" / "EXP_018" / args.run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(experiment, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    with (output_dir / "derivative_rows.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    metrics = {
        "experiment_id": "EXP_018",
        "run_id": args.run_id,
        "scope": "continuous static integer-code spectrum; one isolated stage-1 threshold offset",
        "toy": toy,
        "full_adc": {
            "case_count": len(rows),
            "maximum_derivative_absolute_error": maximum_full_error,
            "maximum_error_by_step": {
                str(step): max(row["absolute_error"] for row in rows if row["step"] == step)
                for step in steps
            },
            "platform_code_jump_disagreements": code_jump_disagreements,
        },
        "acceptance": {"criteria": acceptance, "passed": passed},
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    sources = [
        Path(__file__).resolve(),
        EXPERIMENT_CONFIG,
        architecture_path,
        nonideality_path,
        ROOT / "src/adc_research/theory/static_sensitivity.py",
        ROOT / "src/adc_research/theory/static_spectrum.py",
        ROOT / "src/adc_research/theory/static_transfer.py",
        ROOT / "src/adc_research/platform/pipeline.py",
    ]
    (output_dir / "environment.json").write_text(
        json.dumps(
            {"python": platform.python_version(), "platform": platform.platform(), "source_sha256": source_hash(sources)},
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(metrics, indent=2))
    if not passed:
        raise SystemExit("EXP-018 phase 1 acceptance failed")


if __name__ == "__main__":
    main()
