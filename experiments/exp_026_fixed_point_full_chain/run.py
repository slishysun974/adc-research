"""Score fixed-point Gu candidates on EXP-025's frozen full-chain records."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from dataclasses import asdict
from fractions import Fraction
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from experiments.exp_025_auxiliary_update_schedules.run import (  # noqa: E402
    _physical_overload,
    _random_stream,
    _raw,
    _record,
    _score,
    _truth,
)

from adc_research.calibration.adaptive_two_stage import (  # noqa: E402
    TwoStageAdaptiveState,
    cascade_from_state,
)
from adc_research.calibration.fixed_adaptive_two_stage import (  # noqa: E402
    FixedTwoStageAdaptiveConfig,
    FixedTwoStageAdaptiveState,
    cascade_from_fixed_state,
    correct_and_update_fixed,
)
from adc_research.calibration.fixed_gated_lms import (  # noqa: E402
    FixedGatedLmsConfig,
    FixedGatedLmsState,
    exported_coefficient_codes,
)
from adc_research.calibration.fixed_point import (  # noqa: E402
    UnsignedFixedFormat,
    round_fraction,
)
from adc_research.calibration.fixed_pwl import (  # noqa: E402
    FixedPwlArithmetic,
    correct_two_stage_fixed_observed,
    quantize_two_stage_config,
)
from adc_research.calibration.gated_lms import GatedLmsState  # noqa: E402
from adc_research.calibration.gu_baseline import build_gu_two_stage_baseline  # noqa: E402
from adc_research.calibration.two_stage import correct_two_stage_observed  # noqa: E402
from adc_research.evaluation.observations import digital_sample  # noqa: E402
from adc_research.metrics.spectral import analyze_coherent_tone  # noqa: E402
from adc_research.platform.presets import build_gu_static_hypothesis_a  # noqa: E402
from adc_research.platform.stimulus import CoherentSineConfig, coherent_sine  # noqa: E402


CONFIG = Path(__file__).with_name("config.yaml")


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixed_config(baseline, training: dict, spec: dict, accumulator_bits: int):
    arithmetic = FixedPwlArithmetic(
        coefficient_format=UnsignedFixedFormat(
            int(spec["coefficient_total_bits"]),
            int(spec["coefficient_fractional_bits"]),
        ),
        data_fractional_bits=int(spec["data_fractional_bits"]),
        coefficient_rounding=spec["coefficient_rounding"],
        multiplication_rounding=spec["multiplication_rounding"],
        offset_rounding=spec["offset_rounding"],
    )
    cascade = quantize_two_stage_config(baseline, arithmetic)
    normalized = tuple(Fraction(str(value)) for value in training["normalized_step_sizes"])
    common = {
        "coefficient_format": arithmetic.coefficient_format,
        "data_fractional_bits": arithmetic.data_fractional_bits,
        "accumulator_fractional_bits": accumulator_bits,
        "update_rounding": spec["update_rounding"],
        "coefficient_export_rounding": spec["coefficient_export_rounding"],
        "threshold_rounding": spec["threshold_rounding"],
    }

    def lms(pwl):
        full_scale = pwl.full_scale_scaled // arithmetic.data_scale
        return FixedGatedLmsConfig(
            slice_width_scaled=pwl.slice_width_scaled,
            step_sizes=tuple(step / (full_scale * full_scale) for step in normalized),
            **common,
        )

    return FixedTwoStageAdaptiveConfig(
        cascade=cascade,
        stage1_lms=lms(cascade.stage1_pwl),
        stage2_lms=lms(cascade.stage2_pwl),
    )


def _initial_state(config):
    return FixedTwoStageAdaptiveState(
        stage1=FixedGatedLmsState.unity(config.stage1_lms),
        stage2=FixedGatedLmsState.unity(config.stage2_lms),
    )


def _dynamic(config, state):
    return cascade_from_fixed_state(
        config.cascade, state, config.stage1_lms, config.stage2_lms
    )


def _float_cascade(baseline, reference_row):
    first = tuple(reference_row["stage1_coefficients"])
    second = tuple(reference_row["stage2_coefficients"])
    state = TwoStageAdaptiveState(
        GatedLmsState(first, (0,) * len(first)),
        GatedLmsState(second, (0,) * len(second)),
    )
    return cascade_from_state(baseline, state)


def _score_fixed(records, cascade, *, float_cascade=None, tone=None):
    codes = []
    disagreements = 0
    total_error = 0
    maximum_error = 0
    saturations = 0
    maximum_data_bits = 0
    scale = 1 << cascade.data_fractional_bits
    for expected, nominal, observed, _ in records:
        result = correct_two_stage_fixed_observed(observed, cascade)
        code = min(max(round_fraction(result.unclipped_output_scaled, scale,
                                      "nearest_even"), 0), 4095)
        if float_cascade is None:
            reference_code = nominal
        else:
            floating = correct_two_stage_observed(observed, float_cascade)
            reference_code = min(max(round(floating.unclipped_output_code), 0), 4095)
        disagreements += code != reference_code
        error = abs(code - expected)
        total_error += error
        maximum_error = max(maximum_error, error)
        maximum_data_bits = max(maximum_data_bits,
                                result.maximum_signed_data_bits_required)
        saturations += result.saturated_low or result.saturated_high
        codes.append(code)
    result = {
        "sample_count": len(records),
        "mae_codes": total_error / len(records),
        "maximum_absolute_error_codes": maximum_error,
        "digital_saturations": saturations,
        "integer_code_disagreements_vs_reference": disagreements,
        "maximum_signed_data_bits_required": maximum_data_bits,
    }
    if tone is not None:
        result["spectrum"] = asdict(analyze_coherent_tone(
            codes, sample_rate_hz=float(tone["sample_rate_hz"]),
            fundamental_bin=tone["tone_bin"], full_scale_peak=2048.0,
        ).metrics)
    return result


def _state_summary(state, config):
    return {
        "stage1_coefficients_q10": exported_coefficient_codes(
            state.stage1, config.stage1_lms
        ),
        "stage2_coefficients_q10": exported_coefficient_codes(
            state.stage2, config.stage2_lms
        ),
        "stage1_gate_counts": state.stage1.gate_counts,
        "stage2_gate_counts": state.stage2.gate_counts,
        "stage1_nonzero_update_counts": state.stage1.nonzero_update_counts,
        "stage2_nonzero_update_counts": state.stage2.nonzero_update_counts,
        "stage1_coefficient_change_counts": state.stage1.coefficient_change_counts,
        "stage2_coefficient_change_counts": state.stage2.coefficient_change_counts,
    }


def _training(seed, training, pairs, pipeline, truth, configs, validation):
    states = {bits: _initial_state(config) for bits, config in configs.items()}
    checkpoints = set(training["checkpoint_samples"])
    trajectories = {bits: [] for bits in configs}
    overloads = 0

    def checkpoint(sample_count):
        for bits, config in configs.items():
            score = _score_fixed(validation, _dynamic(config, states[bits]))
            trajectories[bits].append({
                "training_samples": sample_count,
                "validation_mae_codes": score["mae_codes"],
            })

    checkpoint(0)
    for sample_count, (value, symbols) in enumerate(
        _random_stream(training, pairs, seed), 1
    ):
        raw = _raw(value, symbols, sample_count - 1, pipeline, truth)
        overloads += _physical_overload(raw)
        observed = digital_sample(raw)
        for bits, config in configs.items():
            states[bits] = correct_and_update_fixed(
                observed, states[bits], config
            ).state
        if sample_count in checkpoints:
            checkpoint(sample_count)
    return states, trajectories, overloads


def _close(reference, observed, tolerance):
    return math.isclose(reference, observed, rel_tol=0.0, abs_tol=tolerance)


def run(*, selected_cases=None, selected_seeds=None):
    config = _yaml(CONFIG)
    reference_path = ROOT / config["reference_protocol"]
    reference = _yaml(reference_path)
    reference_summary_path = ROOT / config["reference_summary"]
    parent = json.loads(reference_summary_path.read_text(encoding="utf-8"))
    architecture_path = ROOT / reference["architecture_config"]
    architecture = _yaml(architecture_path)
    pipeline = build_gu_static_hypothesis_a(architecture)
    baseline = build_gu_two_stage_baseline(pipeline, architecture["pwl_implications"])
    training = reference["training"]
    pairs = [tuple(pair) for pair in training["dither_symbol_pairs"]]
    tone = reference["heldout_tone"]
    sine = coherent_sine(CoherentSineConfig(
        sample_rate_hz=float(tone["sample_rate_hz"]),
        sample_count=tone["sample_count"], tone_bin=tone["tone_bin"],
        amplitude_peak=tone["amplitude_peak"],
        phase_radians=tone["phase_radians"],
    ))
    tone_rng = random.Random(tone["dither_seed"])
    tone_stream = list(zip(
        sine, (pairs[tone_rng.randrange(len(pairs))] for _ in sine), strict=True
    ))
    cases = selected_cases or config["cases"]
    seeds = selected_seeds or config["training_seeds"]
    if not set(cases) <= set(config["cases"]) or not set(seeds) <= set(config["training_seeds"]):
        raise ValueError("case or seed is outside the frozen protocol")
    if config["schedule"] != "every_sample" or not parent["protocol_passed"]:
        raise ValueError("EXP-026 requires the accepted EXP-025 every-sample reference")
    fixed_spec = config["fixed_point"]
    configs = {int(bits): _fixed_config(baseline, training, fixed_spec, int(bits))
               for bits in fixed_spec["accumulator_fractional_bits"]}
    if len(configs) != len(fixed_spec["accumulator_fractional_bits"]):
        raise ValueError("accumulator resolutions must be unique")
    source_paths = [
        CONFIG, Path(__file__), reference_path, architecture_path,
        ROOT / "experiments/exp_025_auxiliary_update_schedules/run.py",
        ROOT / "src/adc_research/calibration/fixed_adaptive_two_stage.py",
        ROOT / "src/adc_research/calibration/fixed_gated_lms.py",
        ROOT / "src/adc_research/calibration/fixed_pwl.py",
        ROOT / "src/adc_research/calibration/fixed_point.py",
    ]
    source_hash = hashlib.sha256()
    for path in source_paths:
        source_hash.update(path.relative_to(ROOT).as_posix().encode("utf-8"))
        source_hash.update(path.read_bytes())
    result = {
        "experiment_id": config["experiment_id"],
        "source_sha256": source_hash.hexdigest(),
        "reference_summary": config["reference_summary"],
        "reference_summary_sha256": _sha256(reference_summary_path),
        "reference_protocol": config["reference_protocol"],
        "cases_selected": cases,
        "training_seeds_selected": seeds,
        "schedule": config["schedule"],
        "auxiliary_model": config["auxiliary_model"],
        "fixed_point": fixed_spec,
        "results": {},
    }
    accepted = True
    limits = config["acceptance"]
    for case_name in cases:
        truth = _truth(reference["cases"][case_name])
        validation, validation_overloads = _record(
            _random_stream(reference["validation"], pairs,
                           reference["validation"]["seed"]), pipeline, truth,
        )
        heldout, random_overloads = _record(
            _random_stream(reference["heldout_random"], pairs,
                           reference["heldout_random"]["seed"]), pipeline, truth,
        )
        tone_record, tone_overloads = _record(tone_stream, pipeline, truth)
        nominal_random = _score(heldout)
        nominal_tone = _score(tone_record, tone=tone)
        unity_fixed = configs[min(configs)].cascade
        unity_random = _score_fixed(heldout, unity_fixed)
        unity_tone = _score_fixed(tone_record, unity_fixed, tone=tone)
        parent_case = parent["cases"][case_name]
        accepted &= _close(parent_case["heldout_random_nominal"]["mae_codes"],
                           nominal_random["mae_codes"],
                           limits["maximum_reference_mae_difference"])
        accepted &= _close(parent_case["heldout_tone_nominal"]["spectrum"]["sndr_db"],
                           nominal_tone["spectrum"]["sndr_db"],
                           limits["maximum_reference_spectrum_difference_db"])
        accepted &= unity_random["integer_code_disagreements_vs_reference"] <= limits[
            "maximum_unity_code_disagreements"]
        accepted &= unity_tone["integer_code_disagreements_vs_reference"] <= limits[
            "maximum_unity_code_disagreements"]
        accepted &= (validation_overloads + random_overloads + tone_overloads
                     <= limits["maximum_physical_overloads"])
        rows = []
        for seed in seeds:
            reference_row = next(row for row in parent_case["runs"]
                                 if row["training_seed"] == seed
                                 and row["schedule"] == config["schedule"])
            floating = _float_cascade(baseline, reference_row)
            floating_random = _score(heldout, floating)
            floating_tone = _score(tone_record, floating, tone=tone)
            accepted &= _close(reference_row["heldout_random"]["mae_codes"],
                               floating_random["mae_codes"],
                               limits["maximum_reference_mae_difference"])
            for metric in ("sndr_db", "sfdr_dbc"):
                accepted &= _close(reference_row["heldout_tone"]["spectrum"][metric],
                                   floating_tone["spectrum"][metric],
                                   limits["maximum_reference_spectrum_difference_db"])
            frozen_quantized = quantize_two_stage_config(
                floating, unity_fixed.stage1_pwl.arithmetic
            )
            frozen_random = _score_fixed(heldout, frozen_quantized,
                                         float_cascade=floating)
            frozen_tone = _score_fixed(tone_record, frozen_quantized,
                                       float_cascade=floating, tone=tone)
            states, trajectories, train_overloads = _training(
                seed, training, pairs, pipeline, truth, configs, validation
            )
            accepted &= train_overloads <= limits["maximum_physical_overloads"]
            fixed_rows = {}
            for bits, fixed_config in configs.items():
                state = states[bits]
                cascade = _dynamic(fixed_config, state)
                fixed_rows[str(bits)] = {
                    "state": _state_summary(state, fixed_config),
                    "validation_trajectory": trajectories[bits],
                    "heldout_random": _score_fixed(heldout, cascade,
                                                    float_cascade=floating),
                    "heldout_tone": _score_fixed(tone_record, cascade,
                                                  float_cascade=floating, tone=tone),
                }
            rows.append({
                "training_seed": seed,
                "training_physical_overloads": train_overloads,
                "floating_random": floating_random,
                "floating_tone": floating_tone,
                "frozen_float_coefficients_quantized_random": frozen_random,
                "frozen_float_coefficients_quantized_tone": frozen_tone,
                "fixed_trained": fixed_rows,
            })
            print(f"{case_name} seed {seed}: completed", flush=True)
        result["results"][case_name] = {
            "validation_physical_overloads": validation_overloads,
            "heldout_random_physical_overloads": random_overloads,
            "heldout_tone_physical_overloads": tone_overloads,
            "nominal_random": nominal_random,
            "nominal_tone": nominal_tone,
            "unity_fixed_random": unity_random,
            "unity_fixed_tone": unity_tone,
            "runs": rows,
        }
    result["protocol_passed"] = bool(accepted)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--case", choices=_yaml(CONFIG)["cases"])
    parser.add_argument("--seed", type=int, choices=_yaml(CONFIG)["training_seeds"])
    args = parser.parse_args()
    output_dir = ROOT / "artifacts/runs/EXP_026" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    result = run(
        selected_cases=[args.case] if args.case else None,
        selected_seeds=[args.seed] if args.seed else None,
    )
    output_dir.mkdir(parents=True)
    output_path = output_dir / "summary.json"
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n",
                           encoding="utf-8")
    print(json.dumps({"protocol_passed": result["protocol_passed"],
                      "output": str(output_path)}, indent=2))
    if not result["protocol_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
