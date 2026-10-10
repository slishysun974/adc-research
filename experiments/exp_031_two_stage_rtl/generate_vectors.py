"""Freeze digital five-field records for the candidate two-stage RTL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.fixed_pwl import (
    FixedPwlArithmetic,
    FixedPwlConfig,
    FixedTwoStageConfig,
    correct_fixed,
    correct_two_stage_fixed_observed,
)
from adc_research.calibration.observation import DigitalCalibrationSample


COEFFICIENT_PAIRS = (
    ((1024, 1024, 1024, 1024), (1024, 1024, 1024, 1024)),
    ((963, 1097, 751, 1385), (1001, 1057, 923, 1205)),
    ((2047, 2046, 2045, 2044), (0, 2047, 1023, 1)),
    ((0, 2047, 1023, 1), (2047, 2046, 2045, 2044)),
)


def _pwl(width: int, coefficients: tuple[int, ...]) -> FixedPwlConfig:
    return FixedPwlConfig(
        slice_width_scaled=width,
        coefficient_codes=coefficients,
        source_slopes=tuple(code / 1024 for code in coefficients),
        arithmetic=FixedPwlArithmetic(),
        coefficient_saturations=(False,) * 4,
        negative_full_scale_policy="extend_last_slice",
    )


def _cascade(first: tuple[int, ...], second: tuple[int, ...]) -> FixedTwoStageConfig:
    return FixedTwoStageConfig(
        stage1_pwl=_pwl(1024, first),
        stage2_pwl=_pwl(256, second),
        stage1_symbol_weight_scaled=4096,
        stage2_symbol_weight_scaled=1024,
        backend_weight_scaled=8,
        output_offset_scaled=16384,
        output_range_scaled=(0, 32760),
        dither_code_copies_scaled=({-1: -512, 1: 512}, {-1: -128, 1: 128}),
        data_fractional_bits=3,
    )


def generate(path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    counts = {"valid": 0, "out_of_domain": 0, "saturated_low": 0,
              "saturated_high": 0, "final_rounding_half_ties": 0}
    with path.open("w", encoding="ascii", newline="\n") as stream:
        for first, second in COEFFICIENT_PAIRS:
            config = _cascade(first, second)
            for q2 in range(-4, 5):
                for backend_raw in range(256):
                    for d2 in (-1, 1):
                        q1 = (backend_raw + q2 + 4) % 9 - 4
                        d1 = 1 if (backend_raw + q2) & 1 else -1
                        sample = DigitalCalibrationSample(
                            stage1_symbol=q1,
                            stage2_symbol=q2,
                            backend_centered_code=backend_raw - 128,
                            stage1_dither_symbol=d1,
                            stage2_dither_symbol=d2,
                        )
                        stage2 = correct_fixed((backend_raw - 128) * 8,
                                               config.stage2_pwl)
                        stage1_raw = q2 * 1024 + stage2.corrected_code_scaled - d2 * 128
                        valid = -4096 <= stage1_raw < 4096
                        if valid:
                            result = correct_two_stage_fixed_observed(sample, config)
                            stage1_corrected = result.stage1_pwl.corrected_code_scaled
                            output_q3 = result.output_scaled
                            final_code = min(max(round_fraction(
                                result.unclipped_output_scaled, 8, "nearest_even"
                            ), 0), 4095)
                            sat_low = int(result.saturated_low)
                            sat_high = int(result.saturated_high)
                            counts["valid"] += 1
                            counts["saturated_low"] += sat_low
                            counts["saturated_high"] += sat_high
                            counts["final_rounding_half_ties"] += (
                                result.output_scaled % 8 == 4
                            )
                        else:
                            stage1_corrected = output_q3 = final_code = 0
                            sat_low = sat_high = 0
                            counts["out_of_domain"] += 1
                        values = (
                            q1, q2, backend_raw, int(d1 > 0), int(d2 > 0),
                            *first, *second, int(valid),
                            stage2.corrected_code_scaled, stage1_raw,
                            stage1_corrected, output_q3, final_code,
                            sat_low, sat_high,
                        )
                        stream.write(" ".join(map(str, values)) + "\n")
    summary = {
        "scope": "frozen_coefficient_candidate_a_two_stage_digital_equivalence",
        "vector_file": str(path),
        "coefficient_pairs_q10": COEFFICIENT_PAIRS,
        "counts": counts,
        "total_vectors": counts["valid"] + counts["out_of_domain"],
        "rules": {
            "stage1_slice_width_q3": 1024,
            "stage2_slice_width_q3": 256,
            "dither_code_copies": [64, 16],
            "final_integer_rounding": "nearest_even_then_clip_0_4095",
        },
    }
    path.with_suffix(".json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(generate(args.output), ensure_ascii=False, indent=2))
