"""Paired Gu calibration with affine-proxy versus independent linear auxiliary path."""

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
from adc_research.calibration.two_stage import correct_two_stage_observed
from adc_research.evaluation.observations import digital_sample
from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.platform.amplifier import StaticCubicTruthConfig
from adc_research.platform.dual_path_settling import (
    DualPathSettlingConfig,
    DualPathSettlingState,
    process as process_dual_path,
)
from adc_research.platform.pipeline import (
    StaticPipelineNonidealities,
    process as process_proxy,
)
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stage import StaticStageNonidealities
from adc_research.platform.stimulus import CoherentSineConfig, coherent_sine


ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(__file__).with_name("config.yaml")
MODES = ("proxy", "independent")


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _truth(case: dict | None) -> StaticPipelineNonidealities:
    if case is None:
        return StaticPipelineNonidealities()
    if case["kind"] != "cubic":
        raise ValueError("EXP-024 supports only the two frozen cubic cases")
    return StaticPipelineNonidealities(
        stage1=StaticStageNonidealities(
            cubic_truth=StaticCubicTruthConfig(**case["stage1"])
        ),
        stage2=StaticStageNonidealities(
            cubic_truth=StaticCubicTruthConfig(**case["stage2"])
        ),
    )


def _stream(config: dict, pairs: list[tuple[int, int]]):
    rng = random.Random(config["seed"])
    low, high = map(float, config["input_range"])
    for _ in range(config["sample_count"]):
        yield rng.uniform(low, high), pairs[rng.randrange(len(pairs))]


def _overload(raw) -> bool:
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


def _pair(value, symbols, sample_index, pipeline, nonidealities, settling):
    proxy = process_proxy(
        value, pipeline, sample_index=sample_index,
        dither_symbols=symbols, nonidealities=nonidealities,
    )
    independent = process_dual_path(
        value, pipeline, settling, DualPathSettlingState(),
        sample_index=sample_index, dither_symbols=symbols,
        nonidealities=nonidealities,
    ).pipeline
    if (
        proxy.stage1.quantizer.symbol != independent.stage1.quantizer.symbol
        or proxy.stage1.residue != independent.stage1.residue
        or proxy.stage2.main_input != independent.stage2.main_input
    ):
        raise AssertionError("the paired comparison changed the stage-1 main path")
    return proxy, independent


def _counts() -> dict:
    return {
        "sample_count": 0,
        "stage2_decision_differences": 0,
        "backend_code_differences": 0,
        "nominal_final_code_differences": 0,
        "proxy_physical_overloads": 0,
        "independent_physical_overloads": 0,
    }


def _observe(counts: dict, proxy, independent) -> None:
    counts["sample_count"] += 1
    counts["stage2_decision_differences"] += (
        proxy.stage2.quantizer.symbol != independent.stage2.quantizer.symbol
    )
    counts["backend_code_differences"] += (
        proxy.backend.centered_code != independent.backend.centered_code
    )
    counts["nominal_final_code_differences"] += (
        proxy.reconstruction.output_code != independent.reconstruction.output_code
    )
    counts["proxy_physical_overloads"] += _overload(proxy)
    counts["independent_physical_overloads"] += _overload(independent)


def _record_pair(pipeline, nonidealities, settling, stream):
    records = {mode: [] for mode in MODES}
    counts = _counts()
    for sample_index, (value, symbols) in enumerate(stream):
        proxy, independent = _pair(
            float(value), symbols, sample_index, pipeline, nonidealities, settling
        )
        _observe(counts, proxy, independent)
        expected = min(max(math.floor((float(value) + 1.0) * 2048), 0), 4095)
        for mode, raw in zip(MODES, (proxy, independent), strict=True):
            records[mode].append((
                expected,
                raw.reconstruction.output_code,
                digital_sample(raw),
                raw.reconstruction.saturated_low
                or raw.reconstruction.saturated_high,
            ))
    return records, counts


def _score(record, cascade=None, *, tone=None):
    codes = []
    errors = []
    saturations = 0
    for expected, nominal, observed, nominal_saturated in record:
        if cascade is None:
            code = nominal
            saturations += nominal_saturated
        else:
            corrected = correct_two_stage_observed(observed, cascade)
            code = min(max(round(corrected.unclipped_output_code), 0), 4095)
            saturations += corrected.saturated_low or corrected.saturated_high
        codes.append(code)
        errors.append(abs(code - expected))
    result = {
        "sample_count": len(record),
        "mae_codes": sum(errors) / len(errors),
        "maximum_absolute_error_codes": max(errors),
        "digital_saturations": saturations,
    }
    if tone is not None:
        result["spectrum"] = asdict(analyze_coherent_tone(
            codes, sample_rate_hz=float(tone["sample_rate_hz"]),
            fundamental_bin=tone["tone_bin"], full_scale_peak=2048.0,
        ).metrics)
    return result, codes


def _adaptive_config(baseline, training):
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


def _source_hash(paths):
    digest = hashlib.sha256()
    for path in paths:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def run() -> dict:
    config = _yaml(CONFIG)
    reference_path = ROOT / config["reference_protocol"]
    reference = _yaml(reference_path)
    architecture_path = ROOT / reference["architecture_config"]
    architecture = _yaml(architecture_path)
    pipeline = build_gu_static_hypothesis_a(architecture)
    baseline = build_gu_two_stage_baseline(pipeline, architecture["pwl_implications"])
    training = reference["training"]
    adaptive = _adaptive_config(baseline, training)
    pairs = [tuple(pair) for pair in training["dither_symbol_pairs"]]
    factors = tuple(config["auxiliary_hypotheses"]["independent_settling_factors"])
    if factors != (0.0, 0.0, 0.0):
        raise ValueError("EXP-024 is the zero-memory independent-path comparison")
    settling = DualPathSettlingConfig(*factors)
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
    paths = [
        CONFIG, reference_path, architecture_path, Path(__file__),
        ROOT / "src/adc_research/platform/amplifier.py",
        ROOT / "src/adc_research/platform/stage.py",
        ROOT / "src/adc_research/platform/pipeline.py",
        ROOT / "src/adc_research/platform/dual_path_settling.py",
        ROOT / "src/adc_research/platform/finite_settling.py",
        ROOT / "src/adc_research/platform/presets.py",
        ROOT / "src/adc_research/platform/quantizer.py",
        ROOT / "src/adc_research/platform/cdac.py",
        ROOT / "src/adc_research/platform/backend_sar.py",
        ROOT / "src/adc_research/platform/reconstruct.py",
        ROOT / "src/adc_research/platform/stimulus.py",
        ROOT / "src/adc_research/calibration/gu_baseline.py",
        ROOT / "src/adc_research/calibration/adaptive_two_stage.py",
        ROOT / "src/adc_research/calibration/gated_lms.py",
        ROOT / "src/adc_research/calibration/two_stage.py",
        ROOT / "src/adc_research/evaluation/observations.py",
        ROOT / "src/adc_research/metrics/spectral.py",
    ]
    result = {
        "experiment_id": config["experiment_id"],
        "source_sha256": _source_hash(paths),
        "reference_protocol": config["reference_protocol"],
        "auxiliary_hypotheses": config["auxiliary_hypotheses"],
        "training_protocol": training,
        "validation_protocol": reference["validation"],
        "heldout_random_protocol": reference["heldout_random"],
        "heldout_tone_protocol": tone,
        "cases": {},
    }
    for name in config["cases"]:
        case = None if name == "linear_control" else reference["cases"][name]
        nonidealities = _truth(case)
        validation, validation_counts = _record_pair(
            pipeline, nonidealities, settling,
            _stream(reference["validation"], pairs),
        )
        heldout, heldout_counts = _record_pair(
            pipeline, nonidealities, settling,
            _stream(reference["heldout_random"], pairs),
        )
        tone_record, tone_counts = _record_pair(
            pipeline, nonidealities, settling, tone_stream,
        )
        states = {
            mode: TwoStageAdaptiveState(
                stage1=GatedLmsState.unity(baseline.stage1_pwl.slice_count),
                stage2=GatedLmsState.unity(baseline.stage2_pwl.slice_count),
            )
            for mode in MODES
        }
        train_counts = _counts()
        validation_trajectory = []

        def checkpoint(sample_count):
            validation_trajectory.append({
                "training_samples": sample_count,
                **{
                    f"{mode}_mae_codes": _score(
                        validation[mode], cascade_from_state(baseline, states[mode])
                    )[0]["mae_codes"]
                    for mode in MODES
                },
            })

        checkpoints = training["checkpoint_samples"]
        next_checkpoint = 1
        checkpoint(0)
        for sample_index, (value, symbols) in enumerate(_stream(training, pairs), 1):
            proxy, independent = _pair(
                value, symbols, sample_index - 1, pipeline, nonidealities, settling
            )
            _observe(train_counts, proxy, independent)
            for mode, raw in zip(MODES, (proxy, independent), strict=True):
                states[mode] = correct_and_update(
                    digital_sample(raw), states[mode], adaptive
                ).state
            if sample_index == checkpoints[next_checkpoint]:
                checkpoint(sample_index)
                next_checkpoint += 1
        scores = {}
        gu_codes = {}
        cascades = {
            mode: cascade_from_state(baseline, states[mode]) for mode in MODES
        }
        for mode in MODES:
            adapted = cascades[mode]
            random_nominal, _ = _score(heldout[mode])
            random_gu, gu_random_codes = _score(heldout[mode], adapted)
            tone_nominal, _ = _score(tone_record[mode], tone=tone)
            tone_gu, gu_tone_codes = _score(tone_record[mode], adapted, tone=tone)
            scores[mode] = {
                "heldout_random": {"nominal": random_nominal, "gu": random_gu},
                "heldout_tone": {"nominal": tone_nominal, "gu": tone_gu},
                "stage1_coefficients": states[mode].stage1.coefficients,
                "stage2_coefficients": states[mode].stage2.coefficients,
                "stage1_gate_counts": states[mode].stage1.gate_counts,
                "stage2_gate_counts": states[mode].stage2.gate_counts,
            }
            gu_codes[mode] = (gu_random_codes, gu_tone_codes)
        cross_application = {}
        for label, records, tone_config, own_index in (
            ("heldout_random", heldout, None, 0),
            ("heldout_tone", tone_record, tone, 1),
        ):
            independent_record_proxy_coeff, independent_codes_proxy_coeff = _score(
                records["independent"], cascades["proxy"], tone=tone_config
            )
            proxy_record_independent_coeff, proxy_codes_independent_coeff = _score(
                records["proxy"], cascades["independent"], tone=tone_config
            )
            proxy_codes_proxy_coeff = gu_codes["proxy"][own_index]
            independent_codes_independent_coeff = gu_codes["independent"][own_index]
            cross_application[label] = {
                "independent_record_proxy_coeff": independent_record_proxy_coeff,
                "proxy_record_independent_coeff": proxy_record_independent_coeff,
                "record_effect_code_differences_at_proxy_coeff": sum(
                    a != b for a, b in zip(
                        proxy_codes_proxy_coeff,
                        independent_codes_proxy_coeff,
                        strict=True,
                    )
                ),
                "record_effect_code_differences_at_independent_coeff": sum(
                    a != b for a, b in zip(
                        proxy_codes_independent_coeff,
                        independent_codes_independent_coeff,
                        strict=True,
                    )
                ),
                "coefficient_effect_code_differences_on_proxy_record": sum(
                    a != b for a, b in zip(
                        proxy_codes_proxy_coeff,
                        proxy_codes_independent_coeff,
                        strict=True,
                    )
                ),
                "coefficient_effect_code_differences_on_independent_record": sum(
                    a != b for a, b in zip(
                        independent_codes_proxy_coeff,
                        independent_codes_independent_coeff,
                        strict=True,
                    )
                ),
            }
        result["cases"][name] = {
            "analog_case": case or {"kind": "ideal_linear"},
            "training_pair_counts": train_counts,
            "validation_pair_counts": validation_counts,
            "heldout_random_pair_counts": heldout_counts,
            "heldout_tone_pair_counts": tone_counts,
            "validation_trajectory": validation_trajectory,
            "gu_random_final_code_differences": sum(
                left != right for left, right in zip(
                    gu_codes["proxy"][0], gu_codes["independent"][0], strict=True
                )
            ),
            "gu_tone_final_code_differences": sum(
                left != right for left, right in zip(
                    gu_codes["proxy"][1], gu_codes["independent"][1], strict=True
                )
            ),
            "cross_application": cross_application,
            "scores": scores,
        }
        p = scores["proxy"]["heldout_tone"]["gu"]["spectrum"]["sndr_db"]
        q = scores["independent"]["heldout_tone"]["gu"]["spectrum"]["sndr_db"]
        print(
            f"{name}: q2 differences(train/tone) "
            f"{train_counts['stage2_decision_differences']}/"
            f"{tone_counts['stage2_decision_differences']}; "
            f"Gu SNDR proxy/independent {p:.3f}/{q:.3f} dB",
            flush=True,
        )
    acceptance = config["acceptance"]
    valid = True
    for name, case in result["cases"].items():
        for key in (
            "training_pair_counts", "validation_pair_counts",
            "heldout_random_pair_counts", "heldout_tone_pair_counts",
        ):
            counts = case[key]
            valid &= (
                counts["proxy_physical_overloads"]
                + counts["independent_physical_overloads"]
                <= acceptance["maximum_physical_overloads"]
            )
            if name == "linear_control":
                valid &= all(
                    counts[field] <= acceptance["linear_control_maximum_differences"]
                    for field in (
                        "stage2_decision_differences", "backend_code_differences",
                        "nominal_final_code_differences",
                    )
                )
        for mode in MODES:
            scores = case["scores"][mode]
            valid &= sum(
                scores[record][path]["digital_saturations"]
                for record in ("heldout_random", "heldout_tone")
                for path in ("nominal", "gu")
            ) <= acceptance["maximum_heldout_digital_saturations"]
            valid &= math.isfinite(scores["heldout_tone"]["gu"]["spectrum"]["sndr_db"])
        if name == "linear_control":
            valid &= case["gu_random_final_code_differences"] == 0
            valid &= case["gu_tone_final_code_differences"] == 0
            valid &= case["scores"]["proxy"] == case["scores"]["independent"]
    result["protocol_passed"] = bool(valid)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    output_dir = ROOT / "artifacts/runs/EXP_024" / args.run_id
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
