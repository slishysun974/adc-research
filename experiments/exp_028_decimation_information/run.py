"""Reproduce the gate-boundary exposure audit and digital information examples."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from adc_research.calibration.adaptive_two_stage import observe
from adc_research.calibration.gated_lms import adaptive_lower_thresholds
from adc_research.calibration.gu_baseline import build_gu_two_stage_baseline
from adc_research.evaluation.observations import digital_sample
from adc_research.platform.presets import build_gu_static_hypothesis_a
from experiments.exp_025_auxiliary_update_schedules import run as source


ROOT = Path(__file__).resolve().parents[2]
CONFIG = Path(__file__).with_name("config.yaml")


def _correlation(dither: tuple[int, ...], output: tuple[int, ...]) -> int:
    return sum(d * y for d, y in zip(dither, output, strict=True))


def run() -> dict:
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    if config["coefficient_state"] != "frozen_unity":
        raise ValueError("this audit only supports frozen unity coefficients")
    source_config = source._yaml(ROOT / config["source_experiment"])
    reference = source._yaml(ROOT / source_config["reference_protocol"])
    architecture = source._yaml(ROOT / reference["architecture_config"])
    pipeline = build_gu_static_hypothesis_a(architecture)
    baseline = build_gu_two_stage_baseline(
        pipeline, architecture["pwl_implications"]
    )
    state = source._initial_state(baseline)
    adaptive = source._adaptive_config(baseline, reference["training"])
    truth = source._truth(reference["cases"][config["curve"]])
    pairs = [tuple(pair) for pair in reference["training"]["dither_symbol_pairs"]]
    training = dict(reference["training"], sample_count=config["sample_count"])
    equalities = [[0] * 3, [0] * 3]
    equality_product_sums = [[0.0] * 3, [0.0] * 3]

    for index, (value, symbols) in enumerate(
        source._random_stream(training, pairs, config["seed"])
    ):
        raw = source._raw(value, symbols, index, pipeline, truth)
        local = observe(digital_sample(raw), state, adaptive)
        banks = (
            (
                state.stage1,
                local.stage1_local_learning_output,
                local.calibration.stage1_dither_copy,
                adaptive.stage1_lms,
            ),
            (
                state.stage2,
                local.stage2_local_learning_output,
                local.calibration.stage2_dither_copy,
                adaptive.stage2_lms,
            ),
        )
        for stage, (bank, output, dither, settings) in enumerate(banks):
            thresholds = adaptive_lower_thresholds(
                bank.coefficients, settings.slice_width
            )
            for section, threshold in enumerate(thresholds[1:]):
                if abs(output) == threshold:
                    equalities[stage][section] += 1
                    equality_product_sums[stage][section] += dither * output

    dither = (1, -1)
    output_a = (1, -1)
    output_b = (-1, 1)
    first_section = {
        "mean_dither": sum(dither) / 2,
        "mean_output_a": sum(output_a) / 2,
        "mean_output_b": sum(output_b) / 2,
        "correlation_a": _correlation(dither, output_a),
        "correlation_b": _correlation(dither, output_b),
    }
    second_dither = (1, 1)
    second_a = (2, 0)
    second_b = (1, 1)
    threshold = 1.5
    higher_section = {
        "mean_output_a": sum(second_a) / 2,
        "mean_output_b": sum(second_b) / 2,
        "correlation_a": _correlation(second_dither, second_a),
        "correlation_b": _correlation(second_dither, second_b),
        "gated_correlation_a": sum(
            d * y for d, y in zip(second_dither, second_a, strict=True)
            if abs(y) > threshold
        ),
        "gated_correlation_b": sum(
            d * y for d, y in zip(second_dither, second_b, strict=True)
            if abs(y) > threshold
        ),
    }
    return {
        "experiment_id": config["experiment_id"],
        "curve": config["curve"],
        "seed": config["seed"],
        "sample_count": config["sample_count"],
        "coefficient_state": config["coefficient_state"],
        "equalities_by_stage_and_higher_gate": equalities,
        "equality_dither_output_sums_by_stage_and_higher_gate": equality_product_sums,
        "first_section_example": first_section,
        "higher_section_example": higher_section,
    }


if __name__ == "__main__":
    result = run()
    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    output = ROOT / config["output_path"]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
