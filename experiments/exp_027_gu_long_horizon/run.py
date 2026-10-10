"""Continue EXP-025's per-conversion Gu states on the same seeded stream."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from experiments.exp_025_auxiliary_update_schedules.run import (  # noqa: E402
    _adaptive_config, _physical_overload, _random_stream, _raw, _record, _score,
    _truth,
)
from adc_research.calibration.adaptive_two_stage import (  # noqa: E402
    TwoStageAdaptiveState, cascade_from_state, correct_and_update,
)
from adc_research.calibration.gated_lms import GatedLmsState  # noqa: E402
from adc_research.calibration.gu_baseline import build_gu_two_stage_baseline  # noqa: E402
from adc_research.evaluation.observations import digital_sample  # noqa: E402
from adc_research.platform.presets import build_gu_static_hypothesis_a  # noqa: E402
from adc_research.platform.stimulus import CoherentSineConfig, coherent_sine  # noqa: E402

CONFIG = Path(__file__).with_name("config.yaml")


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _restore(row: dict, start: int) -> TwoStageAdaptiveState:
    if row["stage1_observations_used"] != start or row["stage2_observations_used"] != start:
        raise ValueError("parent state does not end at the declared start sample")
    return TwoStageAdaptiveState(
        stage1=GatedLmsState(
            tuple(row["stage1_coefficients"]), tuple(row["stage1_gate_counts"]), start,
        ),
        stage2=GatedLmsState(
            tuple(row["stage2_coefficients"]), tuple(row["stage2_gate_counts"]), start,
        ),
    )


def _checkpoint(count, state, baseline, validation, heldout, tone_record, tone,
                spectral_checkpoints):
    cascade = cascade_from_state(baseline, state)
    point = {
        "training_samples": count,
        "validation": _score(validation, cascade),
        "stage1_coefficients": state.stage1.coefficients,
        "stage2_coefficients": state.stage2.coefficients,
        "stage1_gate_counts": state.stage1.gate_counts,
        "stage2_gate_counts": state.stage2.gate_counts,
        "stage1_observations_used": state.stage1.sample_count,
        "stage2_observations_used": state.stage2.sample_count,
    }
    if count in spectral_checkpoints:
        point["heldout_random"] = _score(heldout, cascade)
        point["heldout_tone"] = _score(tone_record, cascade, tone=tone)
    return point


def run() -> dict:
    config = _yaml(CONFIG)
    parent_path = ROOT / config["parent_summary"]
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    reference_path = ROOT / config["reference_protocol"]
    reference = _yaml(reference_path)
    architecture_path = ROOT / reference["architecture_config"]
    architecture = _yaml(architecture_path)
    start = int(config["start_sample"])
    total = int(config["total_samples"])
    checkpoints = tuple(map(int, config["checkpoints"]))
    spectral_checkpoints = frozenset(map(int, config["spectral_checkpoints"]))
    cases = config["cases"]
    seeds = config["training_seeds"]
    if (parent["experiment_id"] != "EXP_025" or not parent["protocol_passed"]
            or parent["auxiliary_model"] != config["auxiliary_model"]
            or parent["reference_protocol"] != config["reference_protocol"]
            or start != reference["training"]["sample_count"]
            or checkpoints[0] != start or checkpoints[-1] != total
            or tuple(sorted(set(checkpoints))) != checkpoints
            or not spectral_checkpoints.issubset(checkpoints)
            or not {start, total}.issubset(spectral_checkpoints)
            or set(cases) != set(parent["cases"])
            or set(seeds) != set(parent["training_seeds"])):
        raise ValueError("EXP-027 protocol does not match its frozen parent")

    pipeline = build_gu_static_hypothesis_a(architecture)
    baseline = build_gu_two_stage_baseline(pipeline, architecture["pwl_implications"])
    training = reference["training"]
    update_config = _adaptive_config(baseline, training)
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
        sine, (pairs[tone_rng.randrange(len(pairs))] for _ in sine), strict=True,
    ))
    result = {
        "experiment_id": config["experiment_id"],
        "source_sha256": {
            "config": _sha256(CONFIG), "runner": _sha256(Path(__file__)),
            "parent_summary": _sha256(parent_path),
            "parent_runner": _sha256(ROOT / "experiments/exp_025_auxiliary_update_schedules/run.py"),
            "reference_protocol": _sha256(reference_path),
            "architecture": _sha256(architecture_path),
        },
        "parent_experiment_id": parent["experiment_id"],
        "parent_source_sha256": parent["source_sha256"],
        "parent_schedule": config["parent_schedule"],
        "start_sample": start,
        "total_samples": total,
        "checkpoints": checkpoints,
        "spectral_checkpoints": sorted(spectral_checkpoints),
        "cases": {},
    }
    valid = True
    for case_name in cases:
        truth = _truth(reference["cases"][case_name])
        validation, validation_overloads = _record(
            _random_stream(reference["validation"], pairs, reference["validation"]["seed"]),
            pipeline, truth,
        )
        heldout, random_overloads = _record(
            _random_stream(reference["heldout_random"], pairs,
                           reference["heldout_random"]["seed"]), pipeline, truth,
        )
        tone_record, tone_overloads = _record(tone_stream, pipeline, truth)
        case_parent = parent["cases"][case_name]
        rows = []
        for seed in seeds:
            matches = [row for row in case_parent["runs"]
                       if row["schedule"] == config["parent_schedule"]
                       and row["training_seed"] == seed]
            if len(matches) != 1:
                raise ValueError("parent state missing or duplicated")
            parent_row = matches[0]
            state = _restore(parent_row, start)
            points = [_checkpoint(start, state, baseline, validation, heldout,
                                  tone_record, tone, spectral_checkpoints)]
            first = points[0]
            if (first["validation"]["mae_codes"] !=
                    parent_row["validation_trajectory"][-1]["validation_mae_codes"]
                    or first["heldout_random"] != parent_row["heldout_random"]
                    or json.dumps(first["heldout_tone"], sort_keys=True)
                    != json.dumps(parent_row["heldout_tone"], sort_keys=True)):
                raise ValueError(
                    f"reconstructed parent state fails endpoint replay: "
                    f"{case_name} seed {seed}"
                )
            training_overloads = 0
            stream_spec = dict(training, sample_count=total)
            for count, (value, symbols) in enumerate(
                _random_stream(stream_spec, pairs, seed), 1,
            ):
                if count <= start:
                    continue  # Consume the exact parent RNG draws without updating twice.
                raw = _raw(value, symbols, count - 1, pipeline, truth)
                training_overloads += _physical_overload(raw)
                state = correct_and_update(
                    digital_sample(raw), state, update_config,
                ).state
                if count in checkpoints:
                    points.append(_checkpoint(
                        count, state, baseline, validation, heldout, tone_record,
                        tone, spectral_checkpoints,
                    ))
                    print(f"{case_name} seed {seed}: checkpoint {count}", flush=True)
            if [point["training_samples"] for point in points] != list(checkpoints):
                raise ValueError("a checkpoint was not reached")
            for point in points:
                valid &= (point["stage1_observations_used"] == point["training_samples"]
                          and point["stage2_observations_used"] == point["training_samples"])
                for stage in ("stage1", "stage2"):
                    valid &= all(math.isfinite(k) and 0 <= k <= 2
                                 for k in point[f"{stage}_coefficients"])
            valid &= training_overloads <= config["acceptance"]["maximum_physical_overloads"]
            valid &= all(
                point["heldout_random"]["digital_saturations"]
                + point["heldout_tone"]["digital_saturations"]
                <= config["acceptance"]["maximum_heldout_digital_saturations"]
                for point in points if "heldout_random" in point
            )
            rows.append({
                "training_seed": seed,
                "continuation_physical_overloads": training_overloads,
                "trajectory": points,
            })
        valid &= (validation_overloads + random_overloads + tone_overloads
                  <= config["acceptance"]["maximum_physical_overloads"])
        result["cases"][case_name] = {
            "analog_case": reference["cases"][case_name],
            "validation_physical_overloads": validation_overloads,
            "heldout_random_physical_overloads": random_overloads,
            "heldout_tone_physical_overloads": tone_overloads,
            "runs": rows,
        }
    result["protocol_passed"] = bool(valid)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    output_dir = ROOT / "artifacts/runs/EXP_027" / args.run_id
    if output_dir.exists():
        raise FileExistsError(f"refusing to overwrite existing run: {output_dir}")
    result = run()
    output_dir.mkdir(parents=True)
    output_file = output_dir / "summary.json"
    output_file.write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    print(json.dumps({"protocol_passed": result["protocol_passed"],
                      "output": str(output_file)}, indent=2))
    if not result["protocol_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
