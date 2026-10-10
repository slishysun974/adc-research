"""Check an exact integer simplification of the unchanged candidate-A update.

This is an offline hardware arithmetic audit, not a new update algorithm or
an assumption about analog gain. No RTL or synthesis results are modified.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.fixed_pwl import FixedPwlArithmetic, FixedPwlConfig, correct_fixed


def corrected_range(width: int, raw_codes: range) -> tuple[int, int]:
    arithmetic = FixedPwlArithmetic()
    high = FixedPwlConfig(width, (2047,) * 4, (2047/1024,) * 4,
                         arithmetic, (False,) * 4)
    zero = FixedPwlConfig(width, (0,) * 4, (0.,) * 4,
                         arithmetic, (False,) * 4)
    results = []
    for raw in raw_codes:
        value = correct_fixed(raw, high).corrected_code_scaled
        assert correct_fixed(raw, zero).corrected_code_scaled == 0
        results.append(value)
    return min(results), max(results)


def audit() -> dict:
    stages = {}
    for name, width, raw_codes, dither, denominator, scale in (
        ("stage1", 1024, range(-4096, 4096), 512, 4000, 16),
        ("stage2", 256, range(-1024, 1024, 8), 128, 250, 64),
    ):
        corrected_low, corrected_high = corrected_range(width, raw_codes)
        learning_low, learning_high = corrected_low-dither, corrected_high+dither
        count = 0
        max_numerator = max_magnitude_with_bias = max_delta = 0
        for y in range(learning_low, learning_high+1):
            for sign in (-1, 1):
                for j in (1, 3, 6, 12):
                    original = round_fraction(-j*sign*dither*y, denominator, "nearest_even")
                    numerator = -sign*scale*j*y
                    simplified = ((abs(numerator)+62)//125) * (-1 if numerator < 0 else 1)
                    if original != simplified:
                        raise AssertionError((name, y, sign, j, original, simplified))
                    max_numerator = max(max_numerator, abs(numerator))
                    max_magnitude_with_bias = max(max_magnitude_with_bias, abs(numerator)+62)
                    max_delta = max(max_delta, abs(simplified))
                    count += 1
        stages[name] = {"raw_count_checked": len(raw_codes),
                        "corrected_q3_range": [corrected_low, corrected_high],
                        "learning_q3_range": [learning_low, learning_high],
                        "integer_update_cases_checked": count,
                        "maximum_reduced_numerator_magnitude": max_numerator,
                        "maximum_biased_magnitude": max_magnitude_with_bias,
                        "maximum_requested_delta": max_delta}
    assert stages["stage1"]["learning_q3_range"] == [-8700, 8698]
    assert stages["stage2"]["learning_q3_range"] == [-2175, 2159]
    assert all(s["maximum_biased_magnitude"] < 2**21 for s in stages.values())
    return {"scope": "candidate_a_top_level_exact_update_arithmetic_audit",
            "rtl_changed": False,
            "physical_assumption_added": False,
            "stages": stages,
            "all_integer_cases_passed": True,
            "proof_scope": "bounded digital candidate; monotonic coefficient argument in companion note",
            "safe_direct_widths": {"reduced_signed_numerator": 22,
                                   "unsigned_magnitude_plus_62": 21,
                                   "unsigned_quotient": 14,
                                   "signed_requested_delta": 15,
                                   "signed_accumulator_plus_delta": 25}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    summary = audit()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
