"""Post-hoc validation-only coefficient ablation for EXP-021."""

from __future__ import annotations

import argparse
import json

from adc_research.calibration.adaptive_two_stage import (
    TwoStageAdaptiveState,
    cascade_from_state,
    observe,
)
from adc_research.calibration.gated_lms import GatedLmsState
from adc_research.calibration.gu_baseline import build_gu_two_stage_baseline
from adc_research.evaluation.observations import digital_sample
from adc_research.platform.pipeline import process
from adc_research.platform.presets import build_gu_static_hypothesis_a

from run import (
    CONFIG, ROOT, _adaptive_config, _load_yaml, _random_record, _score, _truth,
)


def _cascade(baseline, stage1, stage2):
    return cascade_from_state(
        baseline,
        TwoStageAdaptiveState(
            stage1=GatedLmsState(tuple(stage1), (0,) * len(stage1)),
            stage2=GatedLmsState(tuple(stage2), (0,) * len(stage2)),
        ),
    )


def diagnose(summary: dict) -> dict:
    config = _load_yaml(CONFIG)
    architecture = _load_yaml(ROOT / config["architecture_config"])
    historical = _load_yaml(ROOT / config["historical_truth_config"])
    pipeline = build_gu_static_hypothesis_a(architecture)
    baseline = build_gu_two_stage_baseline(pipeline, architecture["pwl_implications"])
    case = config["cases"]["cubic_compression"]
    nonidealities = _truth(case, historical)
    pairs = [tuple(pair) for pair in config["training"]["dither_symbol_pairs"]]
    validation, overloads = _random_record(
        pipeline, nonidealities, config["validation"], pairs
    )
    if overloads:
        raise ValueError("validation ablation requires no physical overload")
    trajectory = {
        item["epoch"]: item
        for item in summary["cases"]["cubic_compression"]["validation_trajectory"]
    }
    c2, c32, c64 = (trajectory[epoch] for epoch in (2, 32, 64))
    s1_64 = list(c64["stage1_coefficients"])
    s2_64 = list(c64["stage2_coefficients"])
    s1_64_k1_32 = s1_64.copy()
    s1_64_k1_32[0] = c32["stage1_coefficients"][0]
    s1_64_k2_32 = s1_64.copy()
    s1_64_k2_32[1] = c32["stage1_coefficients"][1]
    s2_64_k3_32 = s2_64.copy()
    s2_64_k3_32[2] = c32["stage2_coefficients"][2]
    s2_64_k3_unity = s2_64.copy()
    s2_64_k3_unity[2] = 1.0
    variants = {
        "epoch_2": (c2["stage1_coefficients"], c2["stage2_coefficients"]),
        "epoch_32": (c32["stage1_coefficients"], c32["stage2_coefficients"]),
        "epoch_64": (s1_64, s2_64),
        "epoch_64_with_stage2_k3_from_32": (s1_64, s2_64_k3_32),
        "epoch_64_with_stage2_k3_unity": (s1_64, s2_64_k3_unity),
        "epoch_64_with_stage1_from_32": (
            c32["stage1_coefficients"], s2_64
        ),
        "epoch_64_with_stage1_k1_from_32": (s1_64_k1_32, s2_64),
        "epoch_64_with_stage1_k2_from_32": (s1_64_k2_32, s2_64),
        "epoch_64_with_stage2_from_32": (
            s1_64, c32["stage2_coefficients"]
        ),
    }
    training_observations = []
    for pair in pairs:
        for code in range(config["training"]["code_centers"]):
            value = -1.0 + (code + 0.5) / 2048.0
            raw = process(
                value, pipeline, sample_index=len(training_observations),
                dither_symbols=pair, nonidealities=nonidealities,
            )
            training_observations.append(digital_sample(raw))
    adaptive_config = _adaptive_config(baseline, config["training"])
    fixed_bank_correlation = {}
    def mean_stage1_product(stage1_coefficients, stage2_coefficients):
        state = TwoStageAdaptiveState(
            stage1=GatedLmsState(tuple(stage1_coefficients), (0,) * 4),
            stage2=GatedLmsState(tuple(stage2_coefficients), (0,) * 4),
        )
        total = 0.0
        for observed in training_observations:
            value = observe(observed, state, adaptive_config)
            total += (
                value.calibration.stage1_dither_copy
                * value.stage1_local_learning_output
            )
        return total / len(training_observations)

    for epoch, checkpoint in (
        ("2", c2), ("32", c32), ("64", c64),
        ("64_k1_from_32", {
            "stage1_coefficients": s1_64_k1_32,
            "stage2_coefficients": s2_64,
        }),
    ):
        mean_product = mean_stage1_product(
            checkpoint["stage1_coefficients"], checkpoint["stage2_coefficients"]
        )
        fixed_bank_correlation[epoch] = {
            "stage1_k1_mean_dither_product": mean_product,
            "stage1_k1_frozen_one_epoch_delta_without_clipping": (
                -adaptive_config.stage1_lms.step_sizes[0]
                * mean_product * len(training_observations)
            ),
        }
    low, high = s1_64_k1_32[0], s1_64[0]
    if not (
        fixed_bank_correlation["64_k1_from_32"]["stage1_k1_mean_dither_product"] < 0
        < fixed_bank_correlation["64"]["stage1_k1_mean_dither_product"]
    ):
        raise ValueError("frozen first-stage correlation is not bracketed")
    for _ in range(12):
        midpoint = (low + high) / 2
        candidate = s1_64.copy()
        candidate[0] = midpoint
        if mean_stage1_product(candidate, s2_64) < 0:
            low = midpoint
        else:
            high = midpoint
    root_k1 = (low + high) / 2
    root_stage1 = s1_64.copy()
    root_stage1[0] = root_k1
    return {
        "scope": "post_hoc_training_correlation_and_validation_ablation_no_final_holdout",
        "validation_samples": len(validation),
        "mae_codes": {
            name: _score(validation, _cascade(baseline, stage1, stage2))["mae_codes"]
            for name, (stage1, stage2) in variants.items()
        },
        "stage2_k3_epoch_32": c32["stage2_coefficients"][2],
        "stage2_k3_epoch_64": c64["stage2_coefficients"][2],
        "fixed_bank_training_correlation": fixed_bank_correlation,
        "frozen_other_coefficients_correlation_zero": {
            "stage1_k1": root_k1,
            "validation_mae_codes": _score(
                validation, _cascade(baseline, root_stage1, s2_64)
            )["mae_codes"],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    directory = ROOT / "artifacts/runs/EXP_021" / args.run_id
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    result = diagnose(summary)
    path = directory / "validation_diagnostic_v6.json"
    if path.exists():
        raise FileExistsError(f"refusing to overwrite existing diagnostic: {path}")
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
