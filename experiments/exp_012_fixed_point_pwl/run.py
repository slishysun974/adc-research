from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import platform
import sys
from math import floor
from pathlib import Path

import yaml

from adc_research.calibration.fixed_point import (
    UnsignedFixedFormat,
    fixed_to_float,
    round_shift,
)
from adc_research.calibration.fixed_pwl import (
    FixedPwlArithmetic,
    FixedPwlConfig,
    correct_fixed,
    correct_two_stage_fixed,
    quantize_two_stage_config,
)
from adc_research.calibration.known_truth import (
    build_two_stage_oracle,
    correct_two_stage,
)
from adc_research.platform.pipeline import PipelineResult, process
from adc_research.platform.presets import (
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
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


def pwl_step_summary(config: FixedPwlConfig) -> dict:
    steps = []
    boundary_steps = []
    for raw_scaled in range(0, config.full_scale_scaled - 1):
        current = correct_fixed(raw_scaled, config).corrected_code_scaled
        following = correct_fixed(raw_scaled + 1, config).corrected_code_scaled
        step = following - current
        steps.append(step)
        if (raw_scaled + 1) % config.slice_width_scaled == 0:
            boundary_steps.append(step)
    return {
        "checks": len(steps),
        "minimum_step_q3_lsb": min(steps),
        "maximum_step_q3_lsb": max(steps),
        "zero_steps": sum(step == 0 for step in steps),
        "negative_steps": sum(step < 0 for step in steps),
        "boundary_steps_q3_lsb": boundary_steps,
    }


def final_integer_code(value_scaled: int, fractional_bits: int, mode: str) -> int:
    value = round_shift(value_scaled, fractional_bits, mode)
    return min(max(value, 0), 4095)


def floating_final_integer_code(value: float, mode: str) -> int:
    if mode == "nearest_even":
        code = round(value)
    elif mode == "floor":
        code = floor(value)
    else:
        raise ValueError(f"unsupported final integer rounding mode: {mode}")
    return min(max(code, 0), 4095)


def evaluate_variant(
    *,
    variant_name: str,
    arithmetic: FixedPwlArithmetic,
    oracle,
    samples: list[tuple[int, tuple[int, int], PipelineResult]],
    final_rounding_modes: list[str],
) -> dict:
    config = quantize_two_stage_config(oracle, arithmetic)
    scale = arithmetic.data_scale
    internal_absolute_error = 0.0
    internal_error_sum = 0.0
    internal_maximum_error = 0.0
    fixed_minus_float_absolute = 0.0
    fixed_minus_float_maximum = 0.0
    saturations = 0
    physical_overloads = 0
    coefficient_saturations = sum(config.stage1_pwl.coefficient_saturations) + sum(
        config.stage2_pwl.coefficient_saturations
    )
    maximum_signed_bits = 0
    maximum_product_bits = {"stage1": 0, "stage2": 0}
    maximum_offset_bits = {"stage1": 0, "stage2": 0}
    internal_outputs: dict[tuple[int, int], list[int]] = {
        pair: [] for pair in ((-1, -1), (-1, 1), (1, -1), (1, 1))
    }
    final_metrics = {
        mode: {
            "absolute_error": 0.0,
            "error_sum": 0.0,
            "maximum_error": 0.0,
            "outputs": {pair: [] for pair in internal_outputs},
        }
        for mode in final_rounding_modes
    }

    for expected, pair, raw in samples:
        floating = correct_two_stage(raw, oracle)
        fixed = correct_two_stage_fixed(raw, config)
        output = fixed_to_float(
            fixed.unclipped_output_scaled,
            arithmetic.data_fractional_bits,
        )
        error = output - expected
        internal_absolute_error += abs(error)
        internal_error_sum += error
        internal_maximum_error = max(internal_maximum_error, abs(error))
        difference = output - floating.unclipped_output_code
        fixed_minus_float_absolute += abs(difference)
        fixed_minus_float_maximum = max(
            fixed_minus_float_maximum,
            abs(difference),
        )
        saturations += int(fixed.saturated_low or fixed.saturated_high)
        physical_overloads += int(
            any(
                not stage.correctable
                or stage.main_input_overload_low
                or stage.main_input_overload_high
                for stage in (raw.stage1, raw.stage2)
            )
            or raw.backend.overload_low
            or raw.backend.overload_high
        )
        maximum_signed_bits = max(
            maximum_signed_bits,
            fixed.maximum_signed_data_bits_required,
        )
        maximum_product_bits["stage1"] = max(
            maximum_product_bits["stage1"],
            fixed.stage1_pwl.product_bits_required,
        )
        maximum_product_bits["stage2"] = max(
            maximum_product_bits["stage2"],
            fixed.stage2_pwl.product_bits_required,
        )
        maximum_offset_bits["stage1"] = max(
            maximum_offset_bits["stage1"],
            fixed.stage1_pwl.offset_bits_required,
        )
        maximum_offset_bits["stage2"] = max(
            maximum_offset_bits["stage2"],
            fixed.stage2_pwl.offset_bits_required,
        )
        internal_outputs[pair].append(fixed.unclipped_output_scaled)
        for mode in final_rounding_modes:
            code = final_integer_code(
                fixed.unclipped_output_scaled,
                arithmetic.data_fractional_bits,
                mode,
            )
            final_error = code - expected
            metrics = final_metrics[mode]
            metrics["absolute_error"] += abs(final_error)
            metrics["error_sum"] += final_error
            metrics["maximum_error"] = max(
                metrics["maximum_error"],
                abs(final_error),
            )
            metrics["outputs"][pair].append(code)

    count = len(samples)
    internal_negative_steps = sum(
        current > following
        for outputs in internal_outputs.values()
        for current, following in zip(outputs, outputs[1:])
    )
    internal_zero_steps = sum(
        current == following
        for outputs in internal_outputs.values()
        for current, following in zip(outputs, outputs[1:])
    )
    final_results = {}
    for mode, metrics in final_metrics.items():
        negative_steps = sum(
            current > following
            for outputs in metrics["outputs"].values()
            for current, following in zip(outputs, outputs[1:])
        )
        zero_steps = sum(
            current == following
            for outputs in metrics["outputs"].values()
            for current, following in zip(outputs, outputs[1:])
        )
        final_results[mode] = {
            "mae_codes": metrics["absolute_error"] / count,
            "mean_error_codes": metrics["error_sum"] / count,
            "maximum_absolute_error_codes": metrics["maximum_error"],
            "negative_steps": negative_steps,
            "zero_steps": zero_steps,
        }

    return {
        "variant": variant_name,
        "arithmetic": {
            "coefficient_total_bits": arithmetic.coefficient_format.total_bits,
            "coefficient_fractional_bits": (
                arithmetic.coefficient_format.fractional_bits
            ),
            "data_fractional_bits": arithmetic.data_fractional_bits,
            "coefficient_rounding": arithmetic.coefficient_rounding,
            "multiplication_rounding": arithmetic.multiplication_rounding,
            "offset_rounding": arithmetic.offset_rounding,
        },
        "coefficient_codes": {
            "stage1": config.stage1_pwl.coefficient_codes,
            "stage2": config.stage2_pwl.coefficient_codes,
        },
        "quantized_coefficients": {
            "stage1": config.stage1_pwl.quantized_slopes,
            "stage2": config.stage2_pwl.quantized_slopes,
        },
        "coefficient_errors": {
            "stage1": config.stage1_pwl.coefficient_errors,
            "stage2": config.stage2_pwl.coefficient_errors,
        },
        "coefficient_saturations": coefficient_saturations,
        "internal_q3": {
            "checks": count,
            "mae_codes": internal_absolute_error / count,
            "mean_error_codes": internal_error_sum / count,
            "maximum_absolute_error_codes": internal_maximum_error,
            "mean_absolute_difference_from_float_oracle_codes": (
                fixed_minus_float_absolute / count
            ),
            "maximum_absolute_difference_from_float_oracle_codes": (
                fixed_minus_float_maximum
            ),
            "saturations": saturations,
            "physical_overloads": physical_overloads,
            "negative_steps": internal_negative_steps,
            "zero_steps": internal_zero_steps,
        },
        "final_integer": final_results,
        "required_widths": {
            "maximum_signed_data_bits": maximum_signed_bits,
            "maximum_unsigned_product_bits": maximum_product_bits,
            "maximum_unsigned_offset_product_bits": maximum_offset_bits,
        },
        "stage_pwl_steps": {
            "stage1": pwl_step_summary(config.stage1_pwl),
            "stage2": pwl_step_summary(config.stage2_pwl),
        },
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
    output_dir = ROOT / "artifacts" / "runs" / "EXP_012" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    output_dir.mkdir(parents=True)

    pipeline = build_gu_static_hypothesis_a(architecture)
    nonidealities = build_gu_gate_d_nonidealities(
        truth_profile,
        enabled_effects=("static_pwl_truth",),
    )
    oracle = build_two_stage_oracle(pipeline, nonidealities)
    samples: list[tuple[int, tuple[int, int], PipelineResult]] = []
    for pair in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
        for expected in range(4096):
            value = -1.0 + (expected + 0.5) / 2048.0
            raw = process(
                value,
                pipeline,
                sample_index=len(samples),
                dither_symbols=pair,
                nonidealities=nonidealities,
            )
            samples.append((expected, pair, raw))

    fixed = experiment["fixed_point"]
    coefficient_format = UnsignedFixedFormat(
        fixed["coefficient_total_bits"],
        fixed["coefficient_fractional_bits"],
    )
    variants = []
    for coefficient_rounding, multiplication_rounding, offset_rounding in itertools.product(
        fixed["coefficient_rounding_modes"],
        fixed["multiplication_rounding_modes"],
        fixed["offset_rounding_modes"],
    ):
        variant_name = (
            f"coefficient_{coefficient_rounding}__"
            f"multiply_{multiplication_rounding}__"
            f"offset_{offset_rounding}"
        )
        arithmetic = FixedPwlArithmetic(
            coefficient_format=coefficient_format,
            data_fractional_bits=fixed["data_fractional_bits"],
            coefficient_rounding=coefficient_rounding,
            multiplication_rounding=multiplication_rounding,
            coefficient_overflow=fixed["coefficient_overflow"],
            offset_rounding=offset_rounding,
        )
        variants.append(
            evaluate_variant(
                variant_name=variant_name,
                arithmetic=arithmetic,
                oracle=oracle,
                samples=samples,
                final_rounding_modes=fixed["final_integer_rounding_modes"],
            )
        )

    recommended = next(
        variant
        for variant in variants
        if variant["arithmetic"]["coefficient_rounding"] == "nearest_even"
        and variant["arithmetic"]["multiplication_rounding"] == "nearest_even"
        and variant["arithmetic"]["offset_rounding"] == "after_coefficient_sum"
    )
    floating_absolute_error = 0.0
    floating_maximum_error = 0.0
    floating_final = {
        mode: {"absolute_error": 0.0, "error_sum": 0.0, "maximum_error": 0.0}
        for mode in fixed["final_integer_rounding_modes"]
    }
    for expected, _, raw in samples:
        result = correct_two_stage(raw, oracle)
        error = result.unclipped_output_code - expected
        floating_absolute_error += abs(error)
        floating_maximum_error = max(floating_maximum_error, abs(error))
        for mode, accumulator in floating_final.items():
            code = floating_final_integer_code(result.unclipped_output_code, mode)
            integer_error = code - expected
            accumulator["absolute_error"] += abs(integer_error)
            accumulator["error_sum"] += integer_error
            accumulator["maximum_error"] = max(
                accumulator["maximum_error"],
                abs(integer_error),
            )
    floating_evaluation = {
        "checks": len(samples),
        "mae_codes": floating_absolute_error / len(samples),
        "maximum_absolute_error_codes": floating_maximum_error,
        "final_integer": {
            mode: {
                "mae_codes": accumulator["absolute_error"] / len(samples),
                "mean_error_codes": accumulator["error_sum"] / len(samples),
                "maximum_absolute_error_codes": accumulator["maximum_error"],
            }
            for mode, accumulator in floating_final.items()
        },
    }

    acceptance = experiment["acceptance"]
    pass_status = all(
        (
            max(variant["coefficient_saturations"] for variant in variants)
            <= acceptance["maximum_coefficient_saturations"],
            max(
                variant["internal_q3"]["physical_overloads"]
                for variant in variants
            )
            <= acceptance["maximum_physical_overloads"],
            max(
                variant["internal_q3"]["negative_steps"] for variant in variants
            )
            <= acceptance["maximum_internal_negative_steps"],
            max(
                result["negative_steps"]
                for variant in variants
                for result in variant["final_integer"].values()
            )
            <= acceptance["maximum_final_integer_negative_steps"],
            recommended["internal_q3"]["mae_codes"]
            <= acceptance["maximum_nearest_even_internal_mae_codes"],
            recommended["internal_q3"]["maximum_absolute_error_codes"]
            <= acceptance["maximum_nearest_even_internal_maximum_error_codes"],
            max(
                variant["required_widths"]["maximum_signed_data_bits"]
                for variant in variants
            )
            <= acceptance["maximum_signed_data_bits_required"],
        )
    )
    summary_rows = [
        {
            "variant": variant["variant"],
            "coefficient_rounding": variant["arithmetic"]["coefficient_rounding"],
            "multiplication_rounding": variant["arithmetic"][
                "multiplication_rounding"
            ],
            "offset_rounding": variant["arithmetic"]["offset_rounding"],
            "internal_mae_codes": variant["internal_q3"]["mae_codes"],
            "internal_mean_error_codes": variant["internal_q3"]["mean_error_codes"],
            "internal_maximum_error_codes": variant["internal_q3"][
                "maximum_absolute_error_codes"
            ],
            "difference_from_float_mae_codes": variant["internal_q3"][
                "mean_absolute_difference_from_float_oracle_codes"
            ],
            "nearest_integer_mae_codes": variant["final_integer"]["nearest_even"][
                "mae_codes"
            ],
            "floor_integer_mae_codes": variant["final_integer"]["floor"][
                "mae_codes"
            ],
            "maximum_signed_data_bits": variant["required_widths"][
                "maximum_signed_data_bits"
            ],
        }
        for variant in variants
    ]
    metrics = {
        "experiment_id": experiment["experiment_id"],
        "architecture_config": architecture["config_id"],
        "truth_config": truth_profile["config_id"],
        "paper_reported": {
            "coefficient_total_bits": 11,
            "coefficient_fractional_bits": 10,
            "processing_fractional_bits": 3,
        },
        "unresolved_hardware_rules": [
            "coefficient quantization rounding",
            "multiplier output rounding",
            "offset accumulation rounding",
            "negative signed shift behavior",
            "intermediate total widths and saturation placement",
            "final integer-code rounding",
        ],
        "floating_oracle_evaluation": floating_evaluation,
        "recommended_behavioral_variant": recommended["variant"],
        "variants": variants,
        "pass": pass_status,
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )
    with (output_dir / "summary.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=summary_rows[0].keys())
        writer.writeheader()
        writer.writerows(summary_rows)
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
        ROOT / "src" / "adc_research" / "calibration" / "fixed_point.py",
        ROOT / "src" / "adc_research" / "calibration" / "fixed_pwl.py",
        ROOT / "src" / "adc_research" / "calibration" / "pwl.py",
        ROOT / "src" / "adc_research" / "calibration" / "known_truth.py",
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
    print(json.dumps({key: value for key, value in metrics.items() if key != "variants"}, indent=2))
    print(output_dir)
    if not pass_status:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
