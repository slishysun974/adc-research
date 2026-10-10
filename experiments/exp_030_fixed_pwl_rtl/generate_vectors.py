"""Generate exact fixed-PWL oracle vectors for candidate-A RTL verification.

The file contains only digital input words and expected digital results. The
online candidate receives no analog truth or ideal target code.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from adc_research.calibration.fixed_pwl import (
    FixedPwlArithmetic,
    FixedPwlConfig,
    correct_fixed,
)


COEFFICIENT_SETS = (
    (1024, 1024, 1024, 1024),
    (963, 1097, 751, 1385),
    (0, 2047, 1023, 1),
    (2047, 2046, 2045, 2044),
)
STAGES = ((1, 1024), (2, 256))


def _config(width: int, coefficients: tuple[int, ...]) -> FixedPwlConfig:
    return FixedPwlConfig(
        slice_width_scaled=width,
        coefficient_codes=coefficients,
        source_slopes=tuple(code / 1024 for code in coefficients),
        arithmetic=FixedPwlArithmetic(),
        coefficient_saturations=(False,) * 4,
        negative_full_scale_policy="extend_last_slice",
    )


def generate(path: Path) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    product_half_ties = 0
    offset_half_ties = 0
    with path.open("w", encoding="ascii", newline="\n") as stream:
        for stage, width in STAGES:
            stage_count = 0
            for coefficients in COEFFICIENT_SETS:
                config = _config(width, coefficients)
                invalid_inputs = (-32768, -4 * width - 1, 4 * width, 32767)
                for raw in (*range(-4 * width, 4 * width), *invalid_inputs):
                    valid = -4 * width <= raw < 4 * width
                    if valid:
                        result = correct_fixed(raw, config)
                        corrected = result.corrected_code_scaled
                        slice_index = result.slice_index
                        if coefficients == COEFFICIENT_SETS[0] and corrected != raw:
                            raise AssertionError("unity coefficients must be identity")
                        product_half_ties += result.product_wide % 1024 == 512
                        offset_half_ties += result.offset_wide % 1024 == 512
                    else:
                        corrected = 0
                        slice_index = 0
                    if not -65536 <= corrected <= 65535:
                        raise AssertionError("candidate 17-bit output is too narrow")
                    stream.write(
                        f"{stage} {raw} {' '.join(map(str, coefficients))} "
                        f"{int(valid)} {slice_index} {corrected}\n"
                    )
                    stage_count += 1
            counts[f"stage{stage}"] = stage_count
    summary = {
        "scope": "candidate_a_fixed_pwl_digital_equivalence",
        "vector_file": str(path),
        "coefficient_sets_q10": COEFFICIENT_SETS,
        "vectors_by_stage": counts,
        "total_vectors": sum(counts.values()),
        "product_half_ties": product_half_ties,
        "offset_half_ties": offset_half_ties,
        "numeric_rules": {
            "data_fractional_bits": 3,
            "coefficient_fractional_bits": 10,
            "rounding": "nearest_even",
            "offset_rounding": "after_coefficient_sum",
            "negative_full_scale": "extend_last_slice",
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
