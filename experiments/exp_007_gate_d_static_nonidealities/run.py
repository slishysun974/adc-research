from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import sys
from pathlib import Path

import yaml

from adc_research.platform.amplifier import (
    AmplifierResult,
    PwlAmplifierResult,
    StaticPwlTruthConfig,
    amplify_static_pwl_truth,
)
from adc_research.platform.cdac import CdacMismatch
from adc_research.platform.pipeline import (
    StaticPipelineNonidealities,
    process,
)
from adc_research.platform.presets import (
    GU_GATE_D_EFFECTS,
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
)
from adc_research.platform.stage import (
    STATIC_NONIDEALITY_ORDER,
    StaticStageNonidealities,
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


def explicit_zero_bundle(pipeline) -> StaticPipelineNonidealities:
    identity = StaticPwlTruthConfig(
        (0.0, 0.25, 0.5, 0.75, 1.0),
        (0.0, 0.25, 0.5, 0.75, 1.0),
    )

    def stage_zero(stage_config) -> StaticStageNonidealities:
        return StaticStageNonidealities(
            threshold_offsets=(0.0,) * len(stage_config.quantizer.thresholds),
            cdac_mismatch=CdacMismatch(
                code_level_errors={symbol: 0.0 for symbol in range(-4, 5)}
            ),
            actual_interstage_gain=stage_config.nominal_interstage_gain,
            pwl_truth=identity,
        )

    return StaticPipelineNonidealities(
        stage1=stage_zero(pipeline.stage1),
        stage2=stage_zero(pipeline.stage2),
    )


def numeric_fingerprint(result) -> tuple:
    return (
        result.stage1.quantizer.symbol,
        result.stage1.cdac.actual_dac_value,
        result.stage1.residue_preamp,
        result.stage1.residue,
        result.stage2.quantizer.symbol,
        result.stage2.cdac.actual_dac_value,
        result.stage2.residue_preamp,
        result.stage2.residue,
        result.backend.centered_code,
        result.reconstruction.unclipped_output_code,
        result.reconstruction.output_code,
        result.reconstruction.correctable,
    )


def close_fingerprint(left: tuple, right: tuple, *, tolerance: float = 1e-12) -> bool:
    for actual, expected in zip(left, right, strict=True):
        if isinstance(actual, float) or isinstance(expected, float):
            if abs(actual - expected) > tolerance:
                return False
        elif actual != expected:
            return False
    return True


def trace_activation_counts(result) -> dict[str, int]:
    stages = (result.stage1, result.stage2)
    return {
        "flash_threshold_offsets": sum(
            any(offset != 0 for offset in stage.quantizer.applied_threshold_offsets)
            for stage in stages
        ),
        "cdac_code_level_mismatch": sum(
            stage.cdac.mismatch_contribution != 0 for stage in stages
        ),
        "linear_interstage_gain": sum(
            stage.amplifier.actual_gain != stage.amplifier.nominal_gain
            for stage in stages
        ),
        "static_pwl_truth": sum(
            isinstance(stage.amplifier, PwlAmplifierResult) for stage in stages
        ),
    }


def composition_failures(result, pipeline, applied) -> tuple[int, int]:
    failures = 0
    noncommutative_examples = 0
    for stage, stage_config, stage_effects in (
        (result.stage1, pipeline.stage1, applied.stage1),
        (result.stage2, pipeline.stage2, applied.stage2),
    ):
        offsets = stage_effects.threshold_offsets or (
            (0.0,) * len(stage_config.quantizer.thresholds)
        )
        expected_thresholds = tuple(
            threshold + offset
            for threshold, offset in zip(
                stage_config.quantizer.thresholds, offsets, strict=True
            )
        )
        failures += stage.quantizer.effective_thresholds != expected_thresholds

        expected_mismatch = 0.0
        if stage_effects.cdac_mismatch is not None:
            expected_mismatch = stage_effects.cdac_mismatch.code_level_errors.get(
                stage.quantizer.symbol, 0.0
            )
        failures += abs(stage.cdac.mismatch_contribution - expected_mismatch) > 1e-12
        expected_preamp = (
            stage.main_input
            - stage.cdac.nominal_value
            - expected_mismatch
            + stage.cdac.dither_contribution
        )
        failures += abs(stage.residue_preamp - expected_preamp) > 1e-12

        actual_gain = (
            stage_config.nominal_interstage_gain
            if stage_effects.actual_interstage_gain is None
            else stage_effects.actual_interstage_gain
        )
        if stage_effects.pwl_truth is None:
            failures += not isinstance(stage.amplifier, AmplifierResult)
            expected_output = actual_gain * expected_preamp
        else:
            failures += not isinstance(stage.amplifier, PwlAmplifierResult)
            expected_output = amplify_static_pwl_truth(
                expected_preamp,
                nominal_gain=stage_config.nominal_interstage_gain,
                actual_gain=actual_gain,
                truth=stage_effects.pwl_truth,
            ).output_value
            if actual_gain != stage_config.nominal_interstage_gain:
                counterfactual = amplify_static_pwl_truth(
                    expected_preamp,
                    nominal_gain=stage_config.nominal_interstage_gain,
                    truth=stage_effects.pwl_truth,
                ).output_value
                counterfactual *= actual_gain / stage_config.nominal_interstage_gain
                noncommutative_examples += abs(counterfactual - expected_output) > 1e-12
        failures += abs(stage.residue - expected_output) > 1e-12
        failures += stage.applied_nonideality_order != STATIC_NONIDEALITY_ORDER
    return failures, noncommutative_examples


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()

    experiment = read_yaml(EXPERIMENT_CONFIG)
    architecture_path = ROOT / experiment["architecture_config"]
    nonidealities_path = ROOT / experiment["nonidealities_config"]
    architecture = read_yaml(architecture_path)
    profile = read_yaml(nonidealities_path)
    output_dir = ROOT / "artifacts" / "runs" / "EXP_007" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    output_dir.mkdir(parents=True)

    pipeline = build_gu_static_hypothesis_a(
        architecture,
        dither_profile=experiment["dither_profile"],
    )
    if tuple(profile["composition_order"]) != STATIC_NONIDEALITY_ORDER:
        raise ValueError("profile and runtime nonideality order disagree")

    case_rows = []
    representative_traces = []
    baseline_code_failures = 0
    zero_numeric_failures = 0
    trace_leakage_events = 0
    composition_equation_failures = 0
    repeatability_failures = 0
    all_combined_noncommutative_examples = 0

    for case_name, case in experiment["cases"].items():
        if case["kind"] == "explicit_zero":
            applied = explicit_zero_bundle(pipeline)
            enabled = frozenset(GU_GATE_D_EFFECTS)
            leakage_audit = False
        else:
            enabled = frozenset(case["enabled_effects"])
            applied = build_gu_gate_d_nonidealities(
                profile, enabled_effects=tuple(enabled)
            )
            leakage_audit = True

        checks = 0
        output_code_changes = 0
        stage1_symbol_changes = 0
        stage2_symbol_changes = 0
        stage1_residue_changes = 0
        stage2_residue_changes = 0
        physical_overloads = 0
        final_saturations = 0
        maximum_output_error = 0
        activation_counts = {effect: 0 for effect in GU_GATE_D_EFFECTS}
        case_composition_failures = 0
        case_noncommutative_examples = 0

        for pair_list in experiment["dither_symbol_pairs"]:
            pair = tuple(pair_list)
            for expected in range(4096):
                value = -1 + (expected + 0.5) / 2048
                baseline = process(
                    value,
                    pipeline,
                    sample_index=expected,
                    dither_symbols=pair,
                )
                result = process(
                    value,
                    pipeline,
                    sample_index=expected,
                    dither_symbols=pair,
                    nonidealities=applied,
                )
                checks += 1
                if case_name == "baseline_disabled":
                    baseline_code_failures += (
                        result.reconstruction.output_code != expected
                        or not result.reconstruction.correctable
                    )
                if case_name == "explicit_zero_bundle":
                    zero_numeric_failures += not close_fingerprint(
                        numeric_fingerprint(result), numeric_fingerprint(baseline)
                    )

                output_code_changes += (
                    result.reconstruction.output_code
                    != baseline.reconstruction.output_code
                )
                stage1_symbol_changes += (
                    result.stage1.quantizer.symbol
                    != baseline.stage1.quantizer.symbol
                )
                stage2_symbol_changes += (
                    result.stage2.quantizer.symbol
                    != baseline.stage2.quantizer.symbol
                )
                stage1_residue_changes += (
                    abs(result.stage1.residue - baseline.stage1.residue) > 1e-12
                )
                stage2_residue_changes += (
                    abs(result.stage2.residue - baseline.stage2.residue) > 1e-12
                )
                physical_overloads += any(
                    not stage.correctable
                    or stage.main_input_overload_low
                    or stage.main_input_overload_high
                    for stage in (result.stage1, result.stage2)
                ) or result.backend.overload_low or result.backend.overload_high
                final_saturations += (
                    result.reconstruction.saturated_low
                    or result.reconstruction.saturated_high
                )
                maximum_output_error = max(
                    maximum_output_error,
                    abs(result.reconstruction.unclipped_output_code - expected),
                )

                activations = trace_activation_counts(result)
                for effect, count in activations.items():
                    activation_counts[effect] += count
                    if leakage_audit and effect not in enabled:
                        trace_leakage_events += count

                failures, noncommutative = composition_failures(
                    result, pipeline, applied
                )
                case_composition_failures += failures
                case_noncommutative_examples += noncommutative

                if expected in (0, 2048, 4095) and pair == (-1, 1):
                    representative_traces.append(
                        {
                            "case": case_name,
                            "expected_code": expected,
                            "dither_symbols": pair,
                            "stage1_symbol": result.stage1.quantizer.symbol,
                            "stage1_threshold_offsets": result.stage1.quantizer.applied_threshold_offsets,
                            "stage1_cdac_mismatch": result.stage1.cdac.mismatch_contribution,
                            "stage1_residue_preamp": result.stage1.residue_preamp,
                            "stage1_actual_gain": result.stage1.amplifier.actual_gain,
                            "stage1_amplifier_model": type(result.stage1.amplifier).__name__,
                            "stage1_residue": result.stage1.residue,
                            "stage2_symbol": result.stage2.quantizer.symbol,
                            "stage2_threshold_offsets": result.stage2.quantizer.applied_threshold_offsets,
                            "stage2_cdac_mismatch": result.stage2.cdac.mismatch_contribution,
                            "stage2_residue_preamp": result.stage2.residue_preamp,
                            "stage2_actual_gain": result.stage2.amplifier.actual_gain,
                            "stage2_amplifier_model": type(result.stage2.amplifier).__name__,
                            "stage2_residue": result.stage2.residue,
                            "output_code": result.reconstruction.output_code,
                            "correctable": result.reconstruction.correctable,
                        }
                    )

        repeatability_probes = (0, 511, 1024, 2048, 3072, 4095)
        for expected in repeatability_probes:
            value = -1 + (expected + 0.5) / 2048
            first = process(
                value,
                pipeline,
                sample_index=expected,
                dither_symbols=(1, -1),
                nonidealities=applied,
            )
            second = process(
                value,
                pipeline,
                sample_index=expected,
                dither_symbols=(1, -1),
                nonidealities=applied,
            )
            repeatability_failures += first != second

        composition_equation_failures += case_composition_failures
        if case_name == "all_combined":
            all_combined_noncommutative_examples = case_noncommutative_examples
        case_rows.append(
            {
                "case": case_name,
                "enabled_effects": "+".join(sorted(enabled)),
                "checks": checks,
                "output_code_changes": output_code_changes,
                "stage1_symbol_changes": stage1_symbol_changes,
                "stage2_symbol_changes": stage2_symbol_changes,
                "stage1_residue_changes": stage1_residue_changes,
                "stage2_residue_changes": stage2_residue_changes,
                "maximum_unclipped_output_error_codes": maximum_output_error,
                "physical_overloads": physical_overloads,
                "final_saturations": final_saturations,
                "threshold_activation_events": activation_counts[
                    "flash_threshold_offsets"
                ],
                "cdac_activation_events": activation_counts[
                    "cdac_code_level_mismatch"
                ],
                "gain_activation_events": activation_counts[
                    "linear_interstage_gain"
                ],
                "pwl_activation_events": activation_counts["static_pwl_truth"],
                "composition_equation_failures": case_composition_failures,
                "gain_pwl_noncommutative_examples": case_noncommutative_examples,
            }
        )

    activation_failures = 0
    minimum_activation = experiment["acceptance"][
        "minimum_activation_events_per_enabled_effect"
    ]
    for row in case_rows:
        if row["case"] in ("baseline_disabled", "explicit_zero_bundle"):
            continue
        enabled = set(row["enabled_effects"].split("+"))
        counts = {
            "flash_threshold_offsets": row["threshold_activation_events"],
            "cdac_code_level_mismatch": row["cdac_activation_events"],
            "linear_interstage_gain": row["gain_activation_events"],
            "static_pwl_truth": row["pwl_activation_events"],
        }
        activation_failures += sum(
            count < minimum_activation
            for effect, count in counts.items()
            if effect in enabled
        )

    acceptance = experiment["acceptance"]
    pass_status = all(
        (
            baseline_code_failures
            <= acceptance["maximum_baseline_code_failures"],
            zero_numeric_failures
            <= acceptance["maximum_explicit_zero_numeric_failures"],
            trace_leakage_events <= acceptance["maximum_trace_leakage_events"],
            composition_equation_failures
            <= acceptance["maximum_composition_equation_failures"],
            activation_failures == 0,
            all_combined_noncommutative_examples
            >= acceptance["minimum_noncommutative_gain_pwl_examples"],
            repeatability_failures
            <= acceptance["maximum_repeatability_failures"],
        )
    )

    metrics = {
        "experiment_id": experiment["experiment_id"],
        "architecture_config": architecture["config_id"],
        "nonidealities_config": profile["config_id"],
        "claim_scope": profile["claim_scope"],
        "composition_order": STATIC_NONIDEALITY_ORDER,
        "checks_per_case": 4096 * len(experiment["dither_symbol_pairs"]),
        "gate_d": {
            "baseline_code_failures": baseline_code_failures,
            "explicit_zero_numeric_failures": zero_numeric_failures,
            "trace_leakage_events": trace_leakage_events,
            "activation_failures": activation_failures,
            "composition_equation_failures": composition_equation_failures,
            "all_combined_gain_pwl_noncommutative_examples": all_combined_noncommutative_examples,
            "repeatability_failures": repeatability_failures,
        },
        "cases": case_rows,
        "pass": pass_status,
    }

    with (output_dir / "case_metrics.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=case_rows[0].keys())
        writer.writeheader()
        writer.writerows(case_rows)
    (output_dir / "representative_traces.json").write_text(
        json.dumps(representative_traces, indent=2), encoding="utf-8"
    )
    (output_dir / "metrics.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    (output_dir / "resolved_config.yaml").write_text(
        yaml.safe_dump(
            {
                "experiment": experiment,
                "architecture": architecture,
                "nonidealities": profile,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    tracked_sources = [
        EXPERIMENT_CONFIG,
        architecture_path,
        nonidealities_path,
        ROOT / "src" / "adc_research" / "platform" / "quantizer.py",
        ROOT / "src" / "adc_research" / "platform" / "cdac.py",
        ROOT / "src" / "adc_research" / "platform" / "amplifier.py",
        ROOT / "src" / "adc_research" / "platform" / "stage.py",
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
    if not pass_status:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
