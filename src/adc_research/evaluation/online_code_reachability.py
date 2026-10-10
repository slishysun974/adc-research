"""Exact short-horizon code reachability for the candidate online Gu update.

The caller supplies *covered* sets of possible five-field digital observations.
Taking their Cartesian product can add physically impossible histories, but it
cannot omit a physical history when every per-sample set is sound. This module
uses the existing floating candidate update and deliberately does not infer
those sets from analog measurements or assert a bit-true silicon interface.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from adc_research.calibration.adaptive_two_stage import (
    TwoStageAdaptiveConfig,
    TwoStageAdaptiveState,
    correct_and_update,
)
from adc_research.calibration.observation import DigitalCalibrationSample


@dataclass(frozen=True)
class ReachableCodePath:
    observations: tuple[DigitalCalibrationSample, ...]
    integer_codes: tuple[int, ...]
    final_state: TwoStageAdaptiveState


@dataclass(frozen=True)
class OnlineCodeReachability:
    paths: tuple[ReachableCodePath, ...]
    lower_codes: tuple[int, ...]
    upper_codes: tuple[int, ...]


def enumerate_online_code_paths(
    observation_sets: Iterable[Iterable[DigitalCalibrationSample]],
    initial_state: TwoStageAdaptiveState,
    config: TwoStageAdaptiveConfig,
    *,
    max_paths: int = 100_000,
) -> OnlineCodeReachability:
    """Enumerate all candidate histories, with current-sample pre-update codes.

    The integer rule matches EXP-023: ties-to-even rounding, then clipping to
    integer output bounds. An exceeded path limit raises instead of returning
    an incomplete envelope. No states are merged because histories with the
    same coefficients may still have different spectra.
    """
    if max_paths < 1:
        raise ValueError("max_paths must be positive")
    low, high = config.cascade.output_range
    if not (float(low).is_integer() and float(high).is_integer()):
        raise ValueError("integer output bounds are required")
    paths = (ReachableCodePath((), (), initial_state),)
    for conversion_index, alternatives in enumerate(observation_sets):
        samples = tuple(alternatives)
        if not samples:
            raise ValueError("every sample needs at least one observation")
        if any(not isinstance(sample, DigitalCalibrationSample) for sample in samples):
            raise TypeError("alternatives must be five-field digital samples")
        if len(paths) * len(samples) > max_paths:
            raise ValueError("reachable path count exceeds max_paths")
        next_paths = []
        for path in paths:
            for sample in samples:
                try:
                    result = correct_and_update(sample, path.final_state, config)
                except (ValueError, KeyError) as error:
                    raise ValueError(
                        "possible observation has no candidate online update "
                        f"at conversion {conversion_index}: {sample}"
                    ) from error
                code = min(max(round(result.calibration.unclipped_output_code), int(low)), int(high))
                next_paths.append(ReachableCodePath(
                    observations=path.observations + (sample,),
                    integer_codes=path.integer_codes + (code,),
                    final_state=result.state,
                ))
        paths = tuple(next_paths)
    if not paths or not paths[0].integer_codes:
        raise ValueError("at least one sample is required")
    records = tuple(path.integer_codes for path in paths)
    return OnlineCodeReachability(
        paths=paths,
        lower_codes=tuple(min(record[n] for record in records) for n in range(len(records[0]))),
        upper_codes=tuple(max(record[n] for record in records) for n in range(len(records[0]))),
    )
