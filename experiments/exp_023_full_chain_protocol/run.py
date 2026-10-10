"""Full-chain integer-code comparison under one frozen Gu candidate protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from dataclasses import asdict
from pathlib import Path

import yaml

from adc_research.calibration.adaptive_two_stage import (
    TwoStageAdaptiveConfig,
    TwoStageAdaptiveState,
    cascade_from_state,
    correct_and_update,
)
from adc_research.calibration.gated_lms import GatedLmsConfig, GatedLmsState
from adc_research.calibration.gu_baseline import build_gu_two_stage_baseline
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.calibration.two_stage import correct_two_stage_observed
from adc_research.evaluation.observations import digital_sample
from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.platform.amplifier import StaticCubicTruthConfig
from adc_research.platform.pipeline import StaticPipelineNonidealities, process
from adc_research.platform.presets import (
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
)
from adc_research.platform.stage import StaticStageNonidealities
from adc_research.platform.stimulus import CoherentSineConfig, coherent_sine


ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(__file__).with_name("config.yaml")


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _truth(case: dict, historical_profile: dict) -> StaticPipelineNonidealities:
    if case["kind"] == "historical_pwl":
        return build_gu_gate_d_nonidealities(
            historical_profile, enabled_effects=("static_pwl_truth",)
        )
    if case["kind"] == "cubic":
        return StaticPipelineNonidealities(
            stage1=StaticStageNonidealities(
                cubic_truth=StaticCubicTruthConfig(**case["stage1"])
            ),
            stage2=StaticStageNonidealities(
                cubic_truth=StaticCubicTruthConfig(**case["stage2"])
            ),
        )
    raise ValueError(f"unknown analog case: {case['kind']}")


def _stream(config: dict, pairs: list[tuple[int, int]]):
    rng = random.Random(config["seed"])
    low, high = map(float, config["input_range"])
    for _ in range(config["sample_count"]):
        yield rng.uniform(low, high), pairs[rng.randrange(len(pairs))]


def _physical_overload(raw) -> bool:
    return (
        any(
            not stage.correctable
            or stage.main_input_overload_low
            or stage.main_input_overload_high
            for stage in (raw.stage1, raw.stage2)
        )
        or raw.backend.overload_low
        or raw.backend.overload_high
    )


def _record(pipeline, nonidealities, stream):
    record = []
    overloads = 0
    for sample_index, (value, pair) in enumerate(stream):
        raw = process(
            float(value), pipeline, sample_index=sample_index,
            dither_symbols=pair, nonidealities=nonidealities,
        )
        overloads += _physical_overload(raw)
        expected = min(max(math.floor((float(value) + 1.0) * 2048), 0), 4095)
        record.append((
            expected,
            raw.reconstruction.output_code,
            digital_sample(raw),
            raw.reconstruction.saturated_low or raw.reconstruction.saturated_high,
        ))
    return record, overloads


def _integer_code(value: float, low: int = 0, high: int = 4095) -> int:
    return min(max(round(value), low), high)


def _score(record, cascade=None, *, tone=None) -> dict:
    errors = []
    codes = []
    saturations = 0
    for expected, nominal_code, observed, nominal_saturated in record:
        if cascade is None:
            code = nominal_code
            saturations += nominal_saturated
        else:
            assert isinstance(observed, DigitalCalibrationSample)
            corrected = correct_two_stage_observed(observed, cascade)
            code = _integer_code(corrected.unclipped_output_code)
            saturations += corrected.saturated_low or corrected.saturated_high
        errors.append(abs(code - expected))
        codes.append(code)
    result = {
        "sample_count": len(record),
        "mae_codes": sum(errors) / len(errors),
        "maximum_absolute_error_codes": max(errors),
        "digital_saturations": saturations,
    }
    if tone is not None:
        result["spectrum"] = asdict(analyze_coherent_tone(
            codes,
            sample_rate_hz=float(tone["sample_rate_hz"]),
            fundamental_bin=tone["tone_bin"],
            full_scale_peak=2048.0,
        ).metrics)
    return result


def _adaptive_config(baseline, training: dict) -> TwoStageAdaptiveConfig:
    normalized = tuple(map(float, training["normalized_step_sizes"]))
    bounds = tuple(map(float, training["coefficient_bounds"]))
    return TwoStageAdaptiveConfig(
        cascade=baseline,
        stage1_lms=GatedLmsConfig(
            baseline.stage1_pwl.slice_width,
            tuple(step / baseline.stage1_pwl.full_scale_magnitude**2
                  for step in normalized), bounds,
        ),
        stage2_lms=GatedLmsConfig(
            baseline.stage2_pwl.slice_width,
            tuple(step / baseline.stage2_pwl.full_scale_magnitude**2
                  for step in normalized), bounds,
        ),
    )


def _first_persistent_checkpoint(trajectory: list[dict], fraction: float):
    threshold = fraction * trajectory[0]["validation_mae_codes"]
    for index in range(1, len(trajectory)):
        if all(row["validation_mae_codes"] <= threshold
               for row in trajectory[index:]):
            return trajectory[index]["training_samples"]
    return None


def _check_unity_equivalence(record, baseline) -> None:
    """The nominal dither-subtracted reconstruction must equal unity PWL."""
    for _, nominal_code, observed, _ in record:
        corrected = correct_two_stage_observed(observed, baseline)
        if _integer_code(corrected.unclipped_output_code) != nominal_code:
            raise AssertionError("nominal reconstruction differs from unity PWL")


def run() -> dict:
    config = _yaml(CONFIG)
    architecture_path = ROOT / config["architecture_config"]
    historical_path = ROOT / config["historical_truth_config"]
    architecture = _yaml(architecture_path)
    historical_profile = _yaml(historical_path)
    pipeline = build_gu_static_hypothesis_a(architecture)
    baseline = build_gu_two_stage_baseline(pipeline, architecture["pwl_implications"])
    training = config["training"]
    adaptive = _adaptive_config(baseline, training)
    pairs = [tuple(pair) for pair in training["dither_symbol_pairs"]]
    checkpoints = training["checkpoint_samples"]
    if checkpoints[0] != 0 or checkpoints[-1] != training["sample_count"]:
        raise ValueError("checkpoints must include training start and end")
    if sorted(set(checkpoints)) != checkpoints:
        raise ValueError("checkpoints must increase strictly")
    expected_fields = set(config["online_observation_fields"])
    if expected_fields != set(DigitalCalibrationSample.__dataclass_fields__):
        raise ValueError("frozen online field list differs from the digital sample type")
    if config["convergence"]["require_all_later_checkpoints"] is not True:
        raise ValueError("this protocol requires all later checkpoints to meet target")

    tone = config["heldout_tone"]
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
    source_paths = [
        CONFIG, architecture_path, historical_path, Path(__file__),
        ROOT / "src/adc_research/platform/amplifier.py",
        ROOT / "src/adc_research/platform/pipeline.py",
        ROOT / "src/adc_research/platform/stage.py",
        ROOT / "src/adc_research/platform/reconstruct.py",
        ROOT / "src/adc_research/calibration/adaptive_two_stage.py",
        ROOT / "src/adc_research/calibration/gu_baseline.py",
        ROOT / "src/adc_research/calibration/gated_lms.py",
        ROOT / "src/adc_research/calibration/two_stage.py",
        ROOT / "src/adc_research/evaluation/observations.py",
        ROOT / "src/adc_research/metrics/spectral.py",
    ]
    digest = hashlib.sha256()
    for path in source_paths:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    result = {
        "experiment_id": config["experiment_id"],
        "source_sha256": digest.hexdigest(),
        "model_conditions": config["model_conditions"],
        "online_observation_fields": config["online_observation_fields"],
        "training_protocol": training,
        "validation_protocol": config["validation"],
        "heldout_random_protocol": config["heldout_random"],
        "heldout_tone_protocol": tone,
        "convergence_protocol": config["convergence"],
        "integer_rule": "Python round ties to even, then clip to [0, 4095]",
        "cases": {},
    }
    for name, case in config["cases"].items():
        nonidealities = _truth(case, historical_profile)
        validation, validation_overloads = _record(
            pipeline, nonidealities, _stream(config["validation"], pairs)
        )
        heldout, heldout_overloads = _record(
            pipeline, nonidealities, _stream(config["heldout_random"], pairs)
        )
        tone_record, tone_overloads = _record(
            pipeline, nonidealities, tone_stream
        )
        _check_unity_equivalence(validation, baseline)
        _check_unity_equivalence(heldout, baseline)
        _check_unity_equivalence(tone_record, baseline)
        state = TwoStageAdaptiveState(
            stage1=GatedLmsState.unity(baseline.stage1_pwl.slice_count),
            stage2=GatedLmsState.unity(baseline.stage2_pwl.slice_count),
        )
        trajectory = []

        def checkpoint(sample_count: int) -> None:
            trajectory.append({
                "training_samples": sample_count,
                "validation_mae_codes": _score(
                    validation, cascade_from_state(baseline, state)
                )["mae_codes"],
                "stage1_coefficients": state.stage1.coefficients,
                "stage2_coefficients": state.stage2.coefficients,
                "stage1_gate_counts": state.stage1.gate_counts,
                "stage2_gate_counts": state.stage2.gate_counts,
            })

        checkpoint(0)
        training_overloads = 0
        next_checkpoint = 1
        for sample_index, (value, pair) in enumerate(_stream(training, pairs), 1):
            raw = process(
                value, pipeline, sample_index=sample_index - 1,
                dither_symbols=pair, nonidealities=nonidealities,
            )
            training_overloads += _physical_overload(raw)
            state = correct_and_update(digital_sample(raw), state, adaptive).state
            if sample_index == checkpoints[next_checkpoint]:
                checkpoint(sample_index)
                next_checkpoint += 1

        adapted = cascade_from_state(baseline, state)
        random_nominal = _score(heldout)
        random_adapted = _score(heldout, adapted)
        tone_nominal = _score(tone_record, tone=tone)
        tone_adapted = _score(tone_record, adapted, tone=tone)
        case_result = {
            "analog_case": case,
            "unity_matches_nominal_record_count": (
                len(validation) + len(heldout) + len(tone_record)
            ),
            "physical_overloads": {
                "training": training_overloads,
                "validation": validation_overloads,
                "heldout_random": heldout_overloads,
                "heldout_tone": tone_overloads,
            },
            "trajectory": trajectory,
            "first_persistent_half_mae_checkpoint_samples": (
                _first_persistent_checkpoint(
                    trajectory,
                    float(config["convergence"]["validation_mae_fraction_of_unity"]),
                )
            ),
            "heldout_random": {"nominal": random_nominal, "gu": random_adapted},
            "heldout_tone": {"nominal": tone_nominal, "gu": tone_adapted},
        }
        result["cases"][name] = case_result
        print(
            f"{name}: integer MAE {random_nominal['mae_codes']:.4f} -> "
            f"{random_adapted['mae_codes']:.4f}; SNDR "
            f"{tone_nominal['spectrum']['sndr_db']:.3f} -> "
            f"{tone_adapted['spectrum']['sndr_db']:.3f} dB",
            flush=True,
        )
    acceptance = config["acceptance"]
    result["protocol_passed"] = all(
        sum(case["physical_overloads"].values())
        <= acceptance["maximum_physical_overloads"]
        and case["heldout_random"]["gu"]["digital_saturations"]
        + case["heldout_tone"]["gu"]["digital_saturations"]
        + case["heldout_random"]["nominal"]["digital_saturations"]
        + case["heldout_tone"]["nominal"]["digital_saturations"]
        <= acceptance["maximum_heldout_digital_saturations"]
        and math.isfinite(case["heldout_tone"]["gu"]["spectrum"]["sndr_db"])
        for case in result["cases"].values()
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    output_dir = ROOT / "artifacts/runs/EXP_023" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    result = run()
    output_dir.mkdir(parents=True)
    (output_dir / "summary.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "protocol_passed": result["protocol_passed"],
        "output": str(output_dir / "summary.json"),
    }, indent=2))
    if not result["protocol_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
