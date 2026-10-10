"""Reproducible synthetic long-record check of fixed Gu state boxes."""

from __future__ import annotations

import argparse
import json
from math import isfinite, pi, sin
from pathlib import Path

from adc_research.calibration.fixed_adaptive_two_stage import (
    FixedTwoStageAdaptiveState,
    correct_and_update_fixed,
)
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.evaluation.fixed_online_state_bounds import (
    FixedStateBox,
    bound_fixed_online_codes,
)
from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.theory.finite_record_bounds import (
    bound_finite_coherent_sfdr_binwise,
    bound_finite_coherent_tone,
)
from experiments.exp_032_online_lms_rtl.generate_vectors import _config


SAMPLE_COUNT = 512
FUNDAMENTAL_BIN = 19


def _initial(config) -> FixedTwoStageAdaptiveState:
    return FixedTwoStageAdaptiveState(
        FixedGatedLmsState.unity(config.stage1_lms),
        FixedGatedLmsState.unity(config.stage2_lms),
    )


def _observations():
    for index in range(SAMPLE_COUNT):
        d1 = 1 if index % 2 else -1
        d2 = 1 if index % 3 else -1
        base = (round(40 * sin(2 * pi * FUNDAMENTAL_BIN * index / SAMPLE_COUNT))
                + 64 * d1 + 16 * d2)
        yield tuple(
            DigitalCalibrationSample(0, 0, base + offset, d1, d2)
            for offset in (0, 1)
        )


def _endpoint_record(observations, initial, config, index: int):
    state = initial
    codes = []
    for alternatives in observations:
        result = correct_and_update_fixed(alternatives[index], state, config)
        codes.append(min(max(round_fraction(
            result.calibration.unclipped_output_scaled, 8, "nearest_even"
        ), 0), 4095))
        state = result.state
    return tuple(codes), state


def _db_interval(interval):
    return {
        "lower": interval.lower if isfinite(interval.lower) else None,
        "upper": interval.upper if isfinite(interval.upper) else None,
    }


def run() -> dict:
    config = _config()
    initial = _initial(config)
    observations = tuple(_observations())
    bounds = bound_fixed_online_codes(
        observations, FixedStateBox.from_state(initial), config
    )
    endpoints = [_endpoint_record(observations, initial, config, choice)
                 for choice in (0, 1)]
    for codes, state in endpoints:
        assert all(low <= code <= high for low, code, high in zip(
            bounds.lower_codes, codes, bounds.upper_codes, strict=True
        ))
        for bank, intervals in (
            (state.stage1, bounds.final_state_box.stage1_accumulators),
            (state.stage2, bounds.final_state_box.stage2_accumulators),
        ):
            assert all(item.lower <= code <= item.upper for code, item in zip(
                bank.accumulator_codes, intervals, strict=True
            ))
    parseval = bound_finite_coherent_tone(
        endpoints[0][0], bounds.lower_codes, bounds.upper_codes,
        fundamental_bin=FUNDAMENTAL_BIN,
    )
    binwise = bound_finite_coherent_sfdr_binwise(
        bounds.lower_codes, bounds.upper_codes,
        fundamental_bin=FUNDAMENTAL_BIN,
    )
    endpoint_metrics = [analyze_coherent_tone(
        codes, sample_rate_hz=SAMPLE_COUNT, fundamental_bin=FUNDAMENTAL_BIN,
        harmonic_orders=(2, 3, 4, 5),
    ).metrics for codes, _ in endpoints]
    for metrics in endpoint_metrics:
        assert parseval.sndr_db.lower <= metrics.sndr_db <= parseval.sndr_db.upper
        assert parseval.sfdr_dbc.lower <= metrics.sfdr_dbc <= parseval.sfdr_dbc.upper
        assert binwise.sfdr_dbc.lower <= metrics.sfdr_dbc <= binwise.sfdr_dbc.upper
    spans = [high - low for low, high in zip(
        bounds.lower_codes, bounds.upper_codes, strict=True
    )]
    return {
        "scope": "synthetic_digital_observation_sets_fixed_q22_candidate",
        "sample_count": SAMPLE_COUNT,
        "fundamental_bin": FUNDAMENTAL_BIN,
        "base_code_rule": "round(40*sin(2*pi*19*n/512))+64*d1+16*d2",
        "observation_choices_per_conversion": 2,
        "dither_rule": "d1=+1 for odd n else -1; d2=+1 if n mod 3 else -1",
        "code_interval_width": {"minimum": min(spans), "maximum": max(spans),
                                "mean": sum(spans) / len(spans)},
        "final_accumulator_width_q22": {
            "stage1": [item.upper - item.lower for item in
                       bounds.final_state_box.stage1_accumulators],
            "stage2": [item.upper - item.lower for item in
                       bounds.final_state_box.stage2_accumulators],
        },
        "parseval_sndr_db": _db_interval(parseval.sndr_db),
        "parseval_sfdr_dbc": _db_interval(parseval.sfdr_dbc),
        "binwise_sfdr_dbc": _db_interval(binwise.sfdr_dbc),
        "endpoint_metrics": [
            {"sndr_db": metrics.sndr_db, "sfdr_dbc": metrics.sfdr_dbc}
            for metrics in endpoint_metrics
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    summary = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2,
                                      allow_nan=False), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
