from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import random
import sys
from fractions import Fraction
from pathlib import Path

import yaml

from adc_research.calibration.fixed_adaptive_two_stage import (
    FixedTwoStageAdaptiveConfig,
    FixedTwoStageAdaptiveState,
    cascade_from_fixed_state,
    correct_and_update_fixed,
)
from adc_research.calibration.fixed_gated_lms import (
    FixedGatedLmsConfig,
    FixedGatedLmsState,
    accumulator_values,
    exported_coefficient_codes,
)
from adc_research.calibration.fixed_point import (
    UnsignedFixedFormat,
    fixed_to_float,
    round_shift,
)
from adc_research.calibration.fixed_pwl import (
    FixedPwlArithmetic,
    FixedTwoStageConfig,
    correct_two_stage_fixed,
    quantize_two_stage_config,
)
from adc_research.calibration.known_truth import build_two_stage_oracle
from adc_research.platform.pipeline import PipelineResult, process
from adc_research.platform.presets import (
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
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


def scaled_steps(
    normalized_steps: tuple[Fraction, ...],
    full_scale: int,
) -> tuple[Fraction, ...]:
    return tuple(step / (full_scale * full_scale) for step in normalized_steps)


def build_adaptive_config(
    cascade: FixedTwoStageConfig,
    normalized_steps: tuple[Fraction, ...],
    accumulator_fractional_bits: int,
    fixed: dict,
) -> FixedTwoStageAdaptiveConfig:
    data_scale = 1 << cascade.data_fractional_bits
    stage1_full_scale = cascade.stage1_pwl.full_scale_scaled // data_scale
    stage2_full_scale = cascade.stage2_pwl.full_scale_scaled // data_scale
    common = {
        "coefficient_format": cascade.stage1_pwl.arithmetic.coefficient_format,
        "data_fractional_bits": cascade.data_fractional_bits,
        "accumulator_fractional_bits": accumulator_fractional_bits,
        "update_rounding": fixed["update_rounding"],
        "coefficient_export_rounding": fixed["coefficient_export_rounding"],
        "threshold_rounding": fixed["threshold_rounding"],
    }
    return FixedTwoStageAdaptiveConfig(
        cascade=cascade,
        stage1_lms=FixedGatedLmsConfig(
            slice_width_scaled=cascade.stage1_pwl.slice_width_scaled,
            step_sizes=scaled_steps(normalized_steps, stage1_full_scale),
            **common,
        ),
        stage2_lms=FixedGatedLmsConfig(
            slice_width_scaled=cascade.stage2_pwl.slice_width_scaled,
            step_sizes=scaled_steps(normalized_steps, stage2_full_scale),
            **common,
        ),
    )


def dynamic_cascade(
    config: FixedTwoStageAdaptiveConfig,
    state: FixedTwoStageAdaptiveState,
) -> FixedTwoStageConfig:
    return cascade_from_fixed_state(
        config.cascade,
        state,
        config.stage1_lms,
        config.stage2_lms,
    )


def evaluate(
    samples: list[tuple[int, tuple[int, int], PipelineResult]],
    cascade: FixedTwoStageConfig,
) -> dict:
    fractional_bits = cascade.data_fractional_bits
    count = len(samples)
    absolute_error_sum = 0.0
    error_sum = 0.0
    maximum_error = 0.0
    integer_absolute_error_sum = 0.0
    integer_error_sum = 0.0
    integer_maximum_error = 0.0
    saturations = 0
    physical_overloads = 0
    stage1_product_sum = 0
    stage2_product_sum = 0
    for expected, _, raw in samples:
        result = correct_two_stage_fixed(raw, cascade)
        output = fixed_to_float(result.unclipped_output_scaled, fractional_bits)
        error = output - expected
        absolute_error_sum += abs(error)
        error_sum += error
        maximum_error = max(maximum_error, abs(error))
        integer_output = min(
            max(
                round_shift(
                    result.unclipped_output_scaled,
                    fractional_bits,
                    "nearest_even",
                ),
                0,
            ),
            4095,
        )
        integer_error = integer_output - expected
        integer_absolute_error_sum += abs(integer_error)
        integer_error_sum += integer_error
        integer_maximum_error = max(integer_maximum_error, abs(integer_error))
        saturations += int(result.saturated_low or result.saturated_high)
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
        stage1_product_sum += result.stage1_dither_scaled * (
            result.stage1_pwl.corrected_code_scaled
            - result.stage1_dither_scaled
        )
        stage2_product_sum += result.stage2_dither_scaled * (
            result.stage2_pwl.corrected_code_scaled
            - result.stage2_dither_scaled
        )
    data_product_scale = 1 << (2 * fractional_bits)
    return {
        "checks": count,
        "internal_q3": {
            "mae_codes": absolute_error_sum / count,
            "mean_error_codes": error_sum / count,
            "maximum_absolute_error_codes": maximum_error,
            "saturations": saturations,
            "physical_overloads": physical_overloads,
            "mean_stage1_dither_output_product": (
                stage1_product_sum / (count * data_product_scale)
            ),
            "mean_stage2_dither_output_product": (
                stage2_product_sum / (count * data_product_scale)
            ),
        },
        "final_integer_nearest_even": {
            "mae_codes": integer_absolute_error_sum / count,
            "mean_error_codes": integer_error_sum / count,
            "maximum_absolute_error_codes": integer_maximum_error,
        },
    }


def stage_summary(
    state: FixedGatedLmsState,
    config: FixedGatedLmsConfig,
    oracle_coefficients: tuple[float, ...],
) -> dict:
    codes = exported_coefficient_codes(state, config)
    coefficient_fractional_bits = config.coefficient_format.fractional_bits
    coefficients = tuple(
        fixed_to_float(code, coefficient_fractional_bits) for code in codes
    )
    return {
        "accumulator_codes": state.accumulator_codes,
        "accumulator_values": accumulator_values(state, config),
        "coefficient_codes": codes,
        "coefficients": coefficients,
        "coefficient_errors": tuple(
            actual - expected
            for actual, expected in zip(
                coefficients,
                oracle_coefficients,
                strict=True,
            )
        ),
        "gate_counts": state.gate_counts,
        "nonzero_update_counts": state.nonzero_update_counts,
        "coefficient_change_counts": state.coefficient_change_counts,
        "sample_count": state.sample_count,
    }


def checkpoint_row(
    *,
    accumulator_fractional_bits: int,
    epoch: int,
    state: FixedTwoStageAdaptiveState,
    config: FixedTwoStageAdaptiveConfig,
) -> dict:
    row = {
        "accumulator_fractional_bits": accumulator_fractional_bits,
        "guard_fractional_bits": (
            accumulator_fractional_bits
            - config.stage1_lms.coefficient_format.fractional_bits
        ),
        "epoch": epoch,
        "samples": state.stage1.sample_count,
    }
    for stage_name, stage_state, stage_config in (
        ("stage1", state.stage1, config.stage1_lms),
        ("stage2", state.stage2, config.stage2_lms),
    ):
        codes = exported_coefficient_codes(stage_state, stage_config)
        values = accumulator_values(stage_state, stage_config)
        for index in range(stage_config.coefficient_count):
            suffix = index + 1
            row[f"{stage_name}_k{suffix}_code"] = codes[index]
            row[f"{stage_name}_k{suffix}_accumulator"] = values[index]
            row[f"{stage_name}_gate{suffix}"] = stage_state.gate_counts[index]
            row[f"{stage_name}_nonzero_update{suffix}"] = (
                stage_state.nonzero_update_counts[index]
            )
            row[f"{stage_name}_coefficient_change{suffix}"] = (
                stage_state.coefficient_change_counts[index]
            )
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    experiment = read_yaml(EXPERIMENT_CONFIG)
    architecture_path = ROOT / experiment["architecture_config"]
    truth_path = ROOT / experiment["truth_config"]
    architecture = read_yaml(architecture_path)
    truth_profile = read_yaml(truth_path)
    output_dir = ROOT / "artifacts" / "runs" / "EXP_013" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    output_dir.mkdir(parents=True)

    pipeline = build_gu_static_hypothesis_a(architecture)
    nonidealities = build_gu_gate_d_nonidealities(
        truth_profile,
        enabled_effects=("static_pwl_truth",),
    )
    oracle = build_two_stage_oracle(pipeline, nonidealities)
    fixed = experiment["fixed_point"]
    coefficient_format = UnsignedFixedFormat(
        fixed["coefficient_total_bits"],
        fixed["coefficient_fractional_bits"],
    )
    arithmetic = FixedPwlArithmetic(
        coefficient_format=coefficient_format,
        data_fractional_bits=fixed["data_fractional_bits"],
        coefficient_rounding=fixed["coefficient_rounding"],
        multiplication_rounding=fixed["multiplication_rounding"],
        offset_rounding=fixed["offset_rounding"],
    )
    fixed_oracle = quantize_two_stage_config(oracle, arithmetic)
    normalized_steps = tuple(
        Fraction(str(value)) for value in experiment["training"]["normalized_step_sizes"]
    )

    samples: list[tuple[int, tuple[int, int], PipelineResult]] = []
    for pair_list in experiment["dither_symbol_pairs"]:
        pair = tuple(pair_list)
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

    variants = []
    convergence = []
    checkpoint_epochs = set(experiment["training"]["checkpoint_epochs"])
    for accumulator_fractional_bits in fixed["accumulator_fractional_bits"]:
        adaptive_config = build_adaptive_config(
            fixed_oracle,
            normalized_steps,
            accumulator_fractional_bits,
            fixed,
        )
        state = FixedTwoStageAdaptiveState(
            stage1=FixedGatedLmsState.unity(adaptive_config.stage1_lms),
            stage2=FixedGatedLmsState.unity(adaptive_config.stage2_lms),
        )
        unity_cascade = dynamic_cascade(adaptive_config, state)
        if 0 in checkpoint_epochs:
            convergence.append(
                checkpoint_row(
                    accumulator_fractional_bits=accumulator_fractional_bits,
                    epoch=0,
                    state=state,
                    config=adaptive_config,
                )
            )
        rng = random.Random(experiment["training"]["seed"])
        training_order = list(range(len(samples)))
        for epoch in range(1, experiment["training"]["epochs"] + 1):
            rng.shuffle(training_order)
            for sample_index in training_order:
                state = correct_and_update_fixed(
                    samples[sample_index][2],
                    state,
                    adaptive_config,
                ).state
            if epoch in checkpoint_epochs:
                convergence.append(
                    checkpoint_row(
                        accumulator_fractional_bits=accumulator_fractional_bits,
                        epoch=epoch,
                        state=state,
                        config=adaptive_config,
                    )
                )
            print(
                f"accumulator Q{accumulator_fractional_bits}: "
                f"completed epoch {epoch}/{experiment['training']['epochs']}",
                flush=True,
            )

        final_cascade = dynamic_cascade(adaptive_config, state)
        unity_evaluation = evaluate(samples, unity_cascade)
        adaptive_evaluation = evaluate(samples, final_cascade)
        oracle_evaluation = evaluate(samples, fixed_oracle)
        stage1 = stage_summary(
            state.stage1,
            adaptive_config.stage1_lms,
            oracle.stage1_pwl.slopes,
        )
        stage2 = stage_summary(
            state.stage2,
            adaptive_config.stage2_lms,
            oracle.stage2_pwl.slopes,
        )
        improvement = (
            unity_evaluation["internal_q3"]["mae_codes"]
            / adaptive_evaluation["internal_q3"]["mae_codes"]
        )
        variants.append(
            {
                "accumulator_fractional_bits": accumulator_fractional_bits,
                "guard_fractional_bits": (
                    accumulator_fractional_bits
                    - coefficient_format.fractional_bits
                ),
                "stage1": stage1,
                "stage2": stage2,
                "evaluations": {
                    "unity": unity_evaluation,
                    "adaptive": adaptive_evaluation,
                    "fixed_oracle": oracle_evaluation,
                },
                "mae_improvement_ratio_over_unity": improvement,
            }
        )

    acceptance = experiment["acceptance"]
    reference = next(
        variant
        for variant in variants
        if variant["accumulator_fractional_bits"]
        == acceptance["reference_accumulator_fractional_bits"]
    )
    q10 = next(
        variant
        for variant in variants
        if variant["accumulator_fractional_bits"] == 10
    )
    pass_status = all(
        (
            max(map(abs, reference["stage1"]["coefficient_errors"][:2]))
            <= acceptance["maximum_reference_stage1_k1_k2_absolute_error"],
            max(map(abs, reference["stage2"]["coefficient_errors"][:2]))
            <= acceptance["maximum_reference_stage2_k1_k2_absolute_error"],
            reference["mae_improvement_ratio_over_unity"]
            >= acceptance["minimum_reference_mae_improvement_ratio_over_unity"],
            reference["evaluations"]["adaptive"]["internal_q3"]["mae_codes"]
            <= acceptance["maximum_reference_adaptive_mae_codes"],
            reference["evaluations"]["adaptive"]["internal_q3"]["physical_overloads"]
            <= acceptance["maximum_reference_physical_overloads"],
            reference["stage1"]["gate_counts"][3]
            <= acceptance["maximum_fourth_gate_count"],
            reference["stage2"]["gate_counts"][3]
            <= acceptance["maximum_fourth_gate_count"],
            sum(q10["stage1"]["coefficient_change_counts"])
            + sum(q10["stage2"]["coefficient_change_counts"])
            <= acceptance["maximum_q10_coefficient_changes"],
        )
    )
    metrics = {
        "experiment_id": experiment["experiment_id"],
        "architecture_config": architecture["config_id"],
        "truth_config": truth_profile["config_id"],
        "paper_reported": {
            "coefficient_total_bits": 11,
            "coefficient_fractional_bits": 10,
            "processing_fractional_bits": 3,
        },
        "research_assumptions": [
            "coefficient-update accumulator fractional resolution",
            "update rounding",
            "coefficient export rounding",
            "adaptive-threshold rounding",
            "accumulator saturation at the finite Q1.10 coefficient endpoints",
        ],
        "schedule": {
            "kind": experiment["training"]["schedule"],
            "epochs": experiment["training"]["epochs"],
            "samples_per_epoch": len(samples),
            "updates_per_stage": reference["stage1"]["sample_count"],
            "seed": experiment["training"]["seed"],
        },
        "oracle_coefficients": {
            "stage1": oracle.stage1_pwl.slopes,
            "stage2": oracle.stage2_pwl.slopes,
        },
        "variants": variants,
        "pass": pass_status,
    }
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2),
        encoding="utf-8",
    )
    with (output_dir / "convergence.csv").open(
        "w",
        newline="",
        encoding="utf-8",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=convergence[0].keys())
        writer.writeheader()
        writer.writerows(convergence)
    (output_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(
            {
                "experiment": experiment,
                "architecture": architecture,
                "truth_profile": truth_profile,
                "resolved_step_sizes": {
                    "stage1": tuple(
                        str(value)
                        for value in build_adaptive_config(
                            fixed_oracle,
                            normalized_steps,
                            fixed["accumulator_fractional_bits"][0],
                            fixed,
                        ).stage1_lms.step_sizes
                    ),
                    "stage2": tuple(
                        str(value)
                        for value in build_adaptive_config(
                            fixed_oracle,
                            normalized_steps,
                            fixed["accumulator_fractional_bits"][0],
                            fixed,
                        ).stage2_lms.step_sizes
                    ),
                },
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
        ROOT / "src" / "adc_research" / "calibration" / "fixed_gated_lms.py",
        ROOT / "src" / "adc_research" / "calibration" / "fixed_adaptive_two_stage.py",
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
    compact = {
        "experiment_id": metrics["experiment_id"],
        "variants": [
            {
                "accumulator_fractional_bits": variant[
                    "accumulator_fractional_bits"
                ],
                "stage1_coefficients": variant["stage1"]["coefficients"],
                "stage2_coefficients": variant["stage2"]["coefficients"],
                "adaptive_mae_codes": variant["evaluations"]["adaptive"][
                    "internal_q3"
                ]["mae_codes"],
                "improvement_ratio": variant[
                    "mae_improvement_ratio_over_unity"
                ],
            }
            for variant in variants
        ],
        "pass": pass_status,
    }
    print(json.dumps(compact, indent=2))
    print(output_dir)
    if not pass_status:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
