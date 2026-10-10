"""Offline final-code envelope for a bounded backend voltage.

The front-stage symbols, dither tags and Gu coefficients are held fixed.  This
is a conditional bound for the declared behavioral candidate, not a silicon
bit-true model or an online calibration input.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite

from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.calibration.two_stage import (
    TwoStagePwlCalibrationConfig,
    correct_two_stage_observed,
)
from adc_research.platform.backend_sar import SarConfig, convert as convert_sar


@dataclass(frozen=True)
class BackendCodeEnvelope:
    lower_output_code: int
    upper_output_code: int
    lower_backend_centered_code: int
    upper_backend_centered_code: int
    backend_overload_possible: bool


def bound_backend_voltage_to_gu_code(
    observed: DigitalCalibrationSample,
    backend: SarConfig,
    calibration: TwoStagePwlCalibrationConfig,
    voltage_lower: float,
    voltage_upper: float,
) -> BackendCodeEnvelope:
    """Enumerate candidate SAR codes and Gu integer outputs in a voltage interval.

    The interval is closed, matching the SAR model's left-closed/right-open
    bins at both included endpoints.  Final codes use Python's ties-to-even
    ``round`` followed by clipping to the calibration output range, as in
    EXP-023.  The caller must establish that the analog interval contains the
    actual backend voltage for every circuit being claimed.
    """
    if not isinstance(observed, DigitalCalibrationSample):
        raise TypeError("observed must contain only the five digital fields")
    if not (isfinite(voltage_lower) and isfinite(voltage_upper)):
        raise ValueError("voltage interval endpoints must be finite")
    if voltage_lower > voltage_upper:
        raise ValueError("voltage interval must be increasing")
    output_low, output_high = calibration.output_range
    if not (float(output_low).is_integer() and float(output_high).is_integer()):
        raise ValueError("the integer output-code rule requires integer bounds")
    first = convert_sar(voltage_lower, backend).raw_code
    last = convert_sar(voltage_upper, backend).raw_code
    centered_zero = backend.code_count // 2
    outputs = []
    for raw_code in range(first, last + 1):
        candidate = replace(
            observed, backend_centered_code=raw_code - centered_zero
        )
        corrected = correct_two_stage_observed(candidate, calibration)
        outputs.append(
            min(max(round(corrected.unclipped_output_code), int(output_low)),
                int(output_high))
        )
    low_voltage, high_voltage = backend.input_range
    return BackendCodeEnvelope(
        lower_output_code=min(outputs),
        upper_output_code=max(outputs),
        lower_backend_centered_code=first - centered_zero,
        upper_backend_centered_code=last - centered_zero,
        backend_overload_possible=(
            voltage_lower < low_voltage or voltage_upper >= high_voltage
        ),
    )
