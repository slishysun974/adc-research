"""Compose covered static analog observations with online Gu reachability.

This is an offline analysis entry point. The running calibration algorithm
receives only five-field digital observations; analog intervals and transfer
envelopes never enter its update. Every supplied transfer callback must cover
the declared physical conditions at every frame's decision time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Iterable

from adc_research.calibration.adaptive_two_stage import (
    TwoStageAdaptiveConfig,
    TwoStageAdaptiveState,
)
from adc_research.calibration.fixed_adaptive_two_stage import FixedTwoStageAdaptiveConfig
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.evaluation.fixed_online_state_bounds import (
    FixedOnlineCodeBounds,
    FixedStateBox,
    bound_fixed_online_codes,
)
from adc_research.evaluation.online_code_reachability import (
    OnlineCodeReachability,
    enumerate_online_code_paths,
)
from adc_research.theory.rational_static_reachability import (
    propagate_rational_static_observations,
)
from adc_research.theory.static_observation_reachability import (
    ClosedInterval,
    StaticCandidateArchitecture,
    StaticObservationEnvelope,
    TransferEnvelope,
    propagate_static_observations,
)


@dataclass(frozen=True)
class StaticAnalogFrame:
    """One conversion's covered analog inputs and aligned digital tags."""

    input_voltage: ClosedInterval
    stage1_dither_preamp: ClosedInterval
    stage2_dither_preamp: ClosedInterval
    stage1_dither_symbol: Hashable
    stage2_dither_symbol: Hashable


@dataclass(frozen=True)
class StaticOnlineReachability:
    observation_envelopes: tuple[StaticObservationEnvelope, ...]
    code_reachability: OnlineCodeReachability


@dataclass(frozen=True)
class StaticFixedOnlineBounds:
    observation_envelopes: tuple[StaticObservationEnvelope, ...]
    code_bounds: FixedOnlineCodeBounds


def _static_digital_sets(
    frames: Iterable[StaticAnalogFrame],
    architecture: StaticCandidateArchitecture,
    stage1_main: TransferEnvelope,
    stage1_auxiliary: TransferEnvelope,
    stage2_main: TransferEnvelope,
    *,
    propagator=propagate_static_observations,
) -> tuple[tuple[StaticObservationEnvelope, ...],
           tuple[tuple[DigitalCalibrationSample, ...], ...]]:
    envelopes = []
    observation_sets = []
    for frame in frames:
        if not isinstance(frame, StaticAnalogFrame):
            raise TypeError("frames must be StaticAnalogFrame values")
        envelope = propagator(
            frame.input_voltage,
            frame.stage1_dither_preamp,
            frame.stage2_dither_preamp,
            architecture,
            stage1_main,
            stage1_auxiliary,
            stage2_main,
        )
        envelopes.append(envelope)
        observation_sets.append(tuple(
            DigitalCalibrationSample(
                outcome.stage1_symbol,
                outcome.stage2_symbol,
                outcome.backend_centered_code,
                frame.stage1_dither_symbol,
                frame.stage2_dither_symbol,
            )
            for outcome in envelope.outcomes
        ))
    if not envelopes:
        raise ValueError("at least one analog frame is required")
    return tuple(envelopes), tuple(observation_sets)


def propagate_static_online_codes(
    frames: Iterable[StaticAnalogFrame],
    architecture: StaticCandidateArchitecture,
    stage1_main: TransferEnvelope,
    stage1_auxiliary: TransferEnvelope,
    stage2_main: TransferEnvelope,
    initial_state: TwoStageAdaptiveState,
    calibration: TwoStageAdaptiveConfig,
    *,
    max_paths: int = 100_000,
) -> StaticOnlineReachability:
    """Enumerate short floating candidate histories under covered inputs.

    The caller must establish that each digital dither tag belongs to the
    *same conversion* as its analog injection interval. Per-frame uncertainty
    is combined freely across time. This can add impossible histories when a
    shared physical parameter constrains multiple frames, but cannot exclude
    an actual history if every physical and digital contract is sound.
    """
    envelopes, observation_sets = _static_digital_sets(
        frames, architecture, stage1_main, stage1_auxiliary, stage2_main
    )
    codes = enumerate_online_code_paths(
        observation_sets, initial_state, calibration, max_paths=max_paths
    )
    return StaticOnlineReachability(envelopes, codes)


def propagate_static_fixed_online_codes(
    frames: Iterable[StaticAnalogFrame],
    architecture: StaticCandidateArchitecture,
    stage1_main: TransferEnvelope,
    stage1_auxiliary: TransferEnvelope,
    stage2_main: TransferEnvelope,
    initial_state_box: FixedStateBox,
    calibration: FixedTwoStageAdaptiveConfig,
) -> StaticFixedOnlineBounds:
    """Join fixed-point accumulator ranges after every analog conversion.

    This avoids storing exponential histories but can give wide ranges or
    stop when a widened box reaches an undefined correction input. Physical
    coverage and same-conversion dither alignment remain caller premises.
    """
    envelopes, observation_sets = _static_digital_sets(
        frames, architecture, stage1_main, stage1_auxiliary, stage2_main
    )
    codes = bound_fixed_online_codes(observation_sets, initial_state_box, calibration)
    return StaticFixedOnlineBounds(envelopes, codes)


def propagate_rational_static_fixed_online_codes(
    frames: Iterable[StaticAnalogFrame],
    architecture: StaticCandidateArchitecture,
    stage1_main: TransferEnvelope,
    stage1_auxiliary: TransferEnvelope,
    stage2_main: TransferEnvelope,
    initial_state_box: FixedStateBox,
    calibration: FixedTwoStageAdaptiveConfig,
) -> StaticFixedOnlineBounds:
    """Exact voltages to integer observations, Q states, and final code bounds.

    Physical coverage, aligned dither tags, and the declared fixed candidate
    update remain premises. No floating-point spectrum computation is part
    of this arithmetic scope. Analog callbacks cannot enter the online LMS.
    """
    envelopes, observation_sets = _static_digital_sets(
        frames, architecture, stage1_main, stage1_auxiliary, stage2_main,
        propagator=propagate_rational_static_observations,
    )
    codes = bound_fixed_online_codes(observation_sets, initial_state_box, calibration)
    return StaticFixedOnlineBounds(envelopes, codes)
