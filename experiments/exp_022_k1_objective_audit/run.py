"""Compare the Gu correlation root with exact conditional code-MAE optima."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

import yaml

from adc_research.calibration.adaptive_two_stage import (
    TwoStageAdaptiveState, cascade_from_state,
)
from adc_research.calibration.gated_lms import GatedLmsState
from adc_research.calibration.gu_baseline import build_gu_two_stage_baseline
from adc_research.calibration.two_stage import correct_two_stage_observed
from adc_research.evaluation.conditional_objective import (
    conditional_first_slice_objectives, first_slice_affine_sample,
    score_affine_samples,
)
from adc_research.evaluation.observations import digital_sample
from adc_research.platform.amplifier import StaticCubicTruthConfig
from adc_research.platform.pipeline import StaticPipelineNonidealities, process
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stage import StaticStageNonidealities


ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(__file__).with_name("config.yaml")


def _record(values, pairs, pipeline, truth, cascade, *, exclude_saturated=False):
    samples = []
    physical_overloads = 0
    digital_saturations = 0
    for index, (value, pair) in enumerate(zip(values, pairs, strict=True)):
        raw = process(
            value, pipeline, sample_index=index,
            dither_symbols=pair, nonidealities=truth,
        )
        physical_overloads += (
            any(
                not stage.correctable
                or stage.main_input_overload_low
                or stage.main_input_overload_high
                for stage in (raw.stage1, raw.stage2)
            )
            or raw.backend.overload_low
            or raw.backend.overload_high
        )
        corrected = correct_two_stage_observed(digital_sample(raw), cascade)
        digital_saturations += corrected.saturated_low or corrected.saturated_high
        if exclude_saturated and (corrected.saturated_low or corrected.saturated_high):
            continue
        target = min(max(math.floor((value + 1.0) * 2048), 0), 4095)
        samples.append(first_slice_affine_sample(
            corrected, target, cascade.stage1_pwl.slice_width
        ))
    return samples, int(physical_overloads), int(digital_saturations)


def _summarize(samples, reference, epoch32):
    objectives = conditional_first_slice_objectives(samples, reference)
    root = objectives["correlation_zero_coefficient"]
    low, high = objectives["mae_minimizer_interval"]
    best = (low + high) / 2
    return {
        **objectives,
        "candidates": {
            "epoch32_k1": {"coefficient": epoch32,
                           **score_affine_samples(samples, reference, epoch32)},
            "epoch64_k1": {"coefficient": reference,
                           **score_affine_samples(samples, reference, reference)},
            "correlation_zero": {"coefficient": root,
                                 **score_affine_samples(samples, reference, root)},
            "mae_minimum": {"coefficient": best,
                            **score_affine_samples(samples, reference, best)},
        },
    }


def run() -> dict:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    architecture_path = ROOT / config["architecture_config"]
    architecture = yaml.safe_load(architecture_path.read_text(encoding="utf-8"))
    pipeline = build_gu_static_hypothesis_a(architecture)
    baseline = build_gu_two_stage_baseline(pipeline, architecture["pwl_implications"])
    stage1 = tuple(map(float, config["stage1_coefficients"]))
    stage2 = tuple(map(float, config["stage2_coefficients"]))
    cascade = cascade_from_state(
        baseline,
        TwoStageAdaptiveState(
            GatedLmsState(stage1, (0,) * len(stage1)),
            GatedLmsState(stage2, (0,) * len(stage2)),
        ),
    )
    truth = StaticPipelineNonidealities(
        stage1=StaticStageNonidealities(
            cubic_truth=StaticCubicTruthConfig(**config["stage1_truth"])
        ),
        stage2=StaticStageNonidealities(
            cubic_truth=StaticCubicTruthConfig(**config["stage2_truth"])
        ),
    )
    pairs = [tuple(pair) for pair in config["dither_symbol_pairs"]]
    if config["code_centers"] != 4096 or len(pairs) != 4:
        raise ValueError("this audit requires all code centers and four dither pairs")
    centers = [-1 + (code + 0.5) / 2048 for code in range(4096)]
    jitter = config["off_grid_jitter"]
    jitter_rng = random.Random(jitter["seed"])
    jittered = [
        center + jitter_rng.uniform(-1, 1)
        * float(jitter["max_fraction_of_half_bin"]) / 4096
        for center in centers
    ]
    validation = config["validation_random"]
    validation_rng = random.Random(validation["seed"])
    low, high = map(float, validation["input_range"])
    random_values = [
        validation_rng.uniform(low, high)
        for _ in range(validation["sample_count"])
    ]
    random_pairs = [pairs[validation_rng.randrange(4)] for _ in random_values]
    datasets = {
        "training_code_centers": (
            [value for pair in pairs for value in centers],
            [pair for pair in pairs for _ in centers],
        ),
        "stratified_off_grid": (
            [value for pair in pairs for value in jittered],
            [pair for pair in pairs for _ in jittered],
        ),
        "exp021_validation_random": (random_values, random_pairs),
    }
    source_files = [
        CONFIG, Path(__file__), architecture_path,
        ROOT / "src/adc_research/evaluation/conditional_objective.py",
        ROOT / "src/adc_research/calibration/two_stage.py",
        ROOT / "src/adc_research/calibration/pwl.py",
        ROOT / "src/adc_research/platform/amplifier.py",
        ROOT / "src/adc_research/platform/stage.py",
    ]
    digest = hashlib.sha256()
    for path in source_files:
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(path.read_bytes())
    result = {
        "experiment_id": config["experiment_id"],
        "source_sha256": digest.hexdigest(),
        "source_experiment": config["source_experiment"],
        "source_case": config["source_case"],
        "source_checkpoint_epoch": config["source_checkpoint_epoch"],
        "frozen_stage1_coefficients": stage1,
        "frozen_stage2_coefficients": stage2,
        "datasets": {},
    }
    for name, (values, symbols) in datasets.items():
        samples, physical_overloads, digital_saturations = _record(
            values, symbols, pipeline, truth, cascade
        )
        if physical_overloads:
            raise ValueError(f"{name} has physical overload")
        result["datasets"][name] = {
            "physical_overloads": physical_overloads,
            "digital_saturations_at_reference": digital_saturations,
            **_summarize(samples, stage1[0], config["epoch32_stage1_k1"]),
        }
        if name == "training_code_centers":
            retained, _, _ = _record(
                values, symbols, pipeline, truth, cascade,
                exclude_saturated=True,
            )
            result["datasets"]["training_without_reference_saturation"] = {
                "excluded_sample_count": digital_saturations,
                **_summarize(retained, stage1[0], config["epoch32_stage1_k1"]),
            }
    training = result["datasets"]["training_code_centers"]
    transferred = {
        "training_correlation_zero": training["correlation_zero_coefficient"],
        "training_mae_minimum": sum(training["mae_minimizer_interval"]) / 2,
    }
    for name, (values, symbols) in datasets.items():
        if name == "training_code_centers":
            continue
        samples, _, _ = _record(values, symbols, pipeline, truth, cascade)
        result["datasets"][name]["training_candidate_transfer"] = {
            label: {"coefficient": coefficient,
                    **score_affine_samples(samples, stage1[0], coefficient)}
            for label, coefficient in transferred.items()
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    path = ROOT / "artifacts/runs/EXP_022" / args.run_id / "summary.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite {path}")
    result = run()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
