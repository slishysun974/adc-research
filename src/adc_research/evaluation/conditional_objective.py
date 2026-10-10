"""Exact one-coefficient audit for a fixed two-stage digital correction bank.

The analog truth and target codes belong to offline evaluation.  None of these
functions is used by the online coefficient update.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import fsum, isfinite
from typing import Sequence

from adc_research.calibration.two_stage import TwoStagePwlCalibrationResult


@dataclass(frozen=True)
class FirstSliceAffineSample:
    target_code: float
    output_at_reference: float
    local_at_reference: float
    dither_copy: float
    basis: float


def first_slice_affine_sample(
    result: TwoStagePwlCalibrationResult,
    target_code: float,
    stage1_slice_width: float,
) -> FirstSliceAffineSample:
    """Extract the first-slope basis with all other coefficients fixed."""

    pwl = result.stage1_pwl
    basis = pwl.sign * min(pwl.magnitude, stage1_slice_width)
    return FirstSliceAffineSample(
        target_code=target_code,
        output_at_reference=result.unclipped_output_code,
        local_at_reference=pwl.corrected_code - result.stage1_dither_copy,
        dither_copy=result.stage1_dither_copy,
        basis=basis,
    )


def conditional_first_slice_objectives(
    samples: Sequence[FirstSliceAffineSample], reference_coefficient: float
) -> dict:
    """Return the exact empirical correlation root and MAE minimum interval.

    The output is affine in the first slope.  MAE is a weighted absolute-value
    objective, so its minimizers are weighted medians of zero-error slopes.
    """

    if not samples or not isfinite(reference_coefficient):
        raise ValueError("samples and finite reference coefficient are required")
    weight_and_breakpoint = sorted(
        (
            reference_coefficient
            + (sample.target_code - sample.output_at_reference) / sample.basis,
            abs(sample.basis),
        )
        for sample in samples
        if sample.basis != 0
    )
    if not weight_and_breakpoint:
        raise ValueError("first-slice slope has no effect on any sample")
    correlation_at_reference = fsum(
        sample.dither_copy * sample.local_at_reference for sample in samples
    ) / len(samples)
    correlation_slope = fsum(
        sample.dither_copy * sample.basis for sample in samples
    ) / len(samples)
    if correlation_slope == 0:
        raise ValueError("dither correlation is independent of first-slice slope")
    total_weight = fsum(weight for _, weight in weight_and_breakpoint)
    half_weight = total_weight / 2
    cumulative = 0.0
    lower = upper = None
    for index, (breakpoint, weight) in enumerate(weight_and_breakpoint):
        cumulative += weight
        if cumulative >= half_weight:
            lower = breakpoint
            upper = (
                weight_and_breakpoint[index + 1][0]
                if cumulative == half_weight and index + 1 < len(weight_and_breakpoint)
                else breakpoint
            )
            break
    assert lower is not None and upper is not None
    return {
        "sample_count": len(samples),
        "nonzero_basis_count": len(weight_and_breakpoint),
        "reference_coefficient": reference_coefficient,
        "correlation_at_reference": correlation_at_reference,
        "correlation_slope": correlation_slope,
        "correlation_zero_coefficient": (
            reference_coefficient - correlation_at_reference / correlation_slope
        ),
        "mae_minimizer_interval": [lower, upper],
        "total_mae_basis_weight": total_weight,
    }


def score_affine_samples(
    samples: Sequence[FirstSliceAffineSample],
    reference_coefficient: float,
    candidate_coefficient: float,
) -> dict:
    """Score an offline candidate without regenerating identical raw samples."""

    delta = candidate_coefficient - reference_coefficient
    return {
        "mae_codes": fsum(
            abs(sample.output_at_reference + delta * sample.basis - sample.target_code)
            for sample in samples
        ) / len(samples),
        "mean_dither_local_product": fsum(
            sample.dither_copy * (sample.local_at_reference + delta * sample.basis)
            for sample in samples
        ) / len(samples),
    }
