"""Generate digital-only, sequential oracle vectors for candidate-A RTL."""

from __future__ import annotations

import argparse
import json
from fractions import Fraction
from pathlib import Path
from random import Random

from adc_research.calibration.fixed_adaptive_two_stage import (
    FixedTwoStageAdaptiveConfig,
    FixedTwoStageAdaptiveState,
    cascade_from_fixed_state,
    correct_and_update_fixed,
)
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsConfig, FixedGatedLmsState
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.fixed_pwl import (
    FixedPwlArithmetic,
    FixedPwlConfig,
    FixedTwoStageConfig,
    correct_fixed,
)
from adc_research.calibration.observation import DigitalCalibrationSample


def _pwl(width: int) -> FixedPwlConfig:
    return FixedPwlConfig(
        slice_width_scaled=width,
        coefficient_codes=(1024,) * 4,
        source_slopes=(1.0,) * 4,
        arithmetic=FixedPwlArithmetic(),
        coefficient_saturations=(False,) * 4,
    )


def _config() -> FixedTwoStageAdaptiveConfig:
    cascade = FixedTwoStageConfig(
        stage1_pwl=_pwl(1024),
        stage2_pwl=_pwl(256),
        stage1_symbol_weight_scaled=4096,
        stage2_symbol_weight_scaled=1024,
        backend_weight_scaled=8,
        output_offset_scaled=16384,
        output_range_scaled=(0, 32760),
        dither_code_copies_scaled=({-1: -512, 1: 512}, {-1: -128, 1: 128}),
        data_fractional_bits=3,
    )
    normalized = (1, 3, 6, 12)
    return FixedTwoStageAdaptiveConfig(
        cascade=cascade,
        stage1_lms=FixedGatedLmsConfig(
            slice_width_scaled=1024,
            step_sizes=tuple(Fraction(n, 1000 * 512 * 512) for n in normalized),
            accumulator_fractional_bits=22,
        ),
        stage2_lms=FixedGatedLmsConfig(
            slice_width_scaled=256,
            step_sizes=tuple(Fraction(n, 1000 * 128 * 128) for n in normalized),
            accumulator_fractional_bits=22,
        ),
    )


def _input_rows():
    # The first rows force an invalid word, both dither polarities, and large
    # local outputs. Remaining words are fixed-seed digital stress inputs.
    yield 0, 7, 128, 1, 1
    for q2 in (-4, -3, 0, 3, 4):
        for backend in (0, 32, 64, 127, 128, 192, 255):
            for d2 in (-1, 1):
                yield 4 if backend & 1 else -4, q2, backend, -d2, d2
    rng = Random(20261003)
    for _ in range(8192):
        yield (
            rng.randrange(-4, 5),
            rng.randrange(-4, 5),
            rng.randrange(256),
            rng.choice((-1, 1)),
            rng.choice((-1, 1)),
        )


def generate(path: Path) -> dict:
    config = _config()
    state = FixedTwoStageAdaptiveState(
        stage1=FixedGatedLmsState.unity(config.stage1_lms),
        stage2=FixedGatedLmsState.unity(config.stage2_lms),
    )
    counts = {"valid": 0, "invalid": 0, "low_clip": 0, "high_clip": 0}
    gate_counts = [[0] * 4 for _ in range(2)]
    tie_counts = [0, 0]
    threshold_equalities = [0, 0]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="ascii", newline="\n") as output:
        for q1, q2, backend, d1, d2 in _input_rows():
            sample = DigitalCalibrationSample(
                stage1_symbol=q1,
                stage2_symbol=q2,
                backend_centered_code=backend - 128,
                stage1_dither_symbol=d1,
                stage2_dither_symbol=d2,
            )
            valid = -4 <= q1 <= 4 and -4 <= q2 <= 4
            if valid:
                active = cascade_from_fixed_state(
                    config.cascade, state, config.stage1_lms, config.stage2_lms
                )
                stage2 = correct_fixed((backend - 128) * 8, active.stage2_pwl)
                stage1_raw = q2 * 1024 + stage2.corrected_code_scaled - d2 * 128
                valid = -4096 <= stage1_raw < 4096
            if valid:
                result = correct_and_update_fixed(sample, state, config)
                state = result.state
                code = min(max(round_fraction(
                    result.calibration.unclipped_output_scaled, 8, "nearest_even"
                ), 0), 4095)
                gates = (result.stage1_update.gate_mask, result.stage2_update.gate_mask)
                packed_gates = [sum(int(bit) << i for i, bit in enumerate(mask))
                                for mask in gates]
                learning = (result.stage1_local_learning_output_scaled,
                            result.stage2_local_learning_output_scaled)
                counts["valid"] += 1
                counts["low_clip"] += result.calibration.saturated_low
                counts["high_clip"] += result.calibration.saturated_high
                for stage, mask in enumerate(gates):
                    update = (result.stage1_update, result.stage2_update)[stage]
                    denominator = (4000, 250)[stage]
                    for i in range(1, 4):
                        threshold_equalities[stage] += (
                            abs(update.corrected_output_scaled)
                            == update.adaptive_lower_thresholds_scaled[i]
                        )
                    for i, bit in enumerate(mask):
                        gate_counts[stage][i] += bit
                        if bit:
                            numerator = (1, 3, 6, 12)[i] * abs(
                                update.dither_code_scaled * update.corrected_output_scaled
                            )
                            tie_counts[stage] += numerator % denominator == denominator // 2
            else:
                code = 0
                packed_gates = [0, 0]
                learning = (0, 0)
                counts["invalid"] += 1
            values = (
                q1, q2, backend, int(d1 > 0), int(d2 > 0),
                int(valid), code, *packed_gates, *learning,
                *state.stage1.accumulator_codes,
                *state.stage2.accumulator_codes,
            )
            output.write(" ".join(map(str, values)) + "\n")
    summary = {
        "scope": "sequential_digital_candidate_a_online_lms",
        "total_vectors": counts["valid"] + counts["invalid"],
        "counts": counts,
        "gate_counts": gate_counts,
        "update_rounding_half_ties": tie_counts,
        "gate_threshold_equalities": threshold_equalities,
        "stage1_coefficient_changes": state.stage1.coefficient_change_counts,
        "stage2_coefficient_changes": state.stage2.coefficient_change_counts,
        "final_stage1_accumulators_q22": state.stage1.accumulator_codes,
        "final_stage2_accumulators_q22": state.stage2.accumulator_codes,
        "rule": "one conversion per clock; current coefficients score and gate; both banks update at edge",
    }
    path.with_suffix(".json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(generate(args.output), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
