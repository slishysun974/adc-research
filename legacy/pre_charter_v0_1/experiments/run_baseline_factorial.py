"""Experiment 001: designed interventions on an uncalibrated pipeline ADC."""

from __future__ import annotations

import json
from pathlib import Path

from adc_research.causal import (
    InterventionFactor,
    exact_shapley,
    metric_loss_values,
    run_factorial_interventions,
)
from adc_research.pipeline import MismatchRealization, PipelineConfig


N_SAMPLES = 32768
TONE_BIN = 127


def subset_label(subset: frozenset[str]) -> str:
    return "+".join(sorted(subset)) if subset else "ideal"


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    base = PipelineConfig(amplitude=0.90, seed=20260914)
    factors = [
        InterventionFactor("gain_error", 0.015),
        InterventionFactor("cdac_mismatch_lsb", 0.080),
        InterventionFactor("comparator_offset_lsb", 0.060),
    ]
    realization = MismatchRealization.sample(base, N_SAMPLES)
    factorial_results = run_factorial_interventions(
        base,
        factors,
        N_SAMPLES,
        TONE_BIN,
        realization,
    )

    names = [factor.name for factor in factors]
    attributions: dict[str, dict[str, float]] = {}
    for metric in ("sfdr_db", "sndr_db"):
        losses = metric_loss_values(factorial_results, metric)
        attributions[metric] = exact_shapley(losses, names)

    serializable_runs = {
        subset_label(subset): result
        for subset, result in sorted(
            factorial_results.items(),
            key=lambda item: (len(item[0]), subset_label(item[0])),
        )
    }
    all_active = frozenset(names)
    ideal = factorial_results[frozenset()]
    combined = factorial_results[all_active]
    payload = {
        "experiment": "001_uncalibrated_factorial_baseline",
        "description": (
            "Common-random-number interventions for gain error, code-dependent "
            "CDAC mismatch, and comparator threshold offset in a two-stage ADC."
        ),
        "configuration": {
            "n_samples": N_SAMPLES,
            "tone_bin": TONE_BIN,
            "base": {
                field: getattr(base, field)
                for field in base.__dataclass_fields__
            },
            "active_factors": {
                factor.name: factor.active_value for factor in factors
            },
        },
        "runs": serializable_runs,
        "shapley_metric_loss_db": attributions,
        "combined_loss_db": {
            "sfdr_db": float(ideal["sfdr_db"]) - float(combined["sfdr_db"]),
            "sndr_db": float(ideal["sndr_db"]) - float(combined["sndr_db"]),
        },
        "interpretation_limits": [
            "Attributions apply to this designed simulator and intervention range.",
            "They are not observational causal estimates from silicon data.",
            "One mismatch seed is a reproducibility baseline, not a population result.",
        ],
    }

    output_path = root / "results" / "experiment_001_baseline.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print("Experiment 001: uncalibrated pipeline ADC factorial baseline")
    print(f"{'intervention':68s} {'SFDR/dB':>9s} {'SNDR/dB':>9s} {'cross/%':>9s} {'fold/%':>9s}")
    for label, result in serializable_runs.items():
        print(
            f"{label:68s} "
            f"{float(result['sfdr_db']):9.2f} "
            f"{float(result['sndr_db']):9.2f} "
            f"{100.0 * float(result['threshold_crossing_rate']):9.4f} "
            f"{100.0 * float(result['overload_rate']):9.4f}"
        )
    print("\nExact Shapley attribution of metric loss (dB):")
    for metric, values in attributions.items():
        rendered = ", ".join(f"{name}={value:.3f}" for name, value in values.items())
        print(f"  {metric}: {rendered}")
    print(f"\nSaved: {output_path}")


if __name__ == "__main__":
    main()

