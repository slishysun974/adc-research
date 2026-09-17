"""Periodic first-order settling theory for the three-stage ADC.

The model treats each front-stage static residue as a target and retains a
fraction of the previous settled-output error.  For periodic input records the
unique cyclic steady state is solved analytically, avoiding an arbitrary
warm-up or initial condition.  This theory module does not import the dynamic
reference platform.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from math import exp, floor, isfinite, log2, pi
from typing import Iterable

from adc_research.theory.static_transfer import (
    FrontStageTheoryConfig,
    StaticPipelineTheoryConfig,
)


@dataclass(frozen=True)
class PeriodicSettlingConfig:
    """Per-stage residual factors for a periodic steady-state prediction."""

    residual_factors: tuple[float, float]

    def __post_init__(self) -> None:
        if len(self.residual_factors) != 2:
            raise ValueError("three-stage pipeline requires two settling factors")
        if any(
            not isfinite(value) or value < 0 or value >= 1
            for value in self.residual_factors
        ):
            raise ValueError("settling residual factors must lie in [0,1)")


@dataclass(frozen=True)
class PeriodicSettlingPrediction:
    """One complete cyclic steady-state record and its internal theory traces."""

    input_values: tuple[float, ...]
    stage1_symbols: tuple[int, ...]
    stage1_targets: tuple[float, ...]
    stage1_residues: tuple[float, ...]
    stage2_symbols: tuple[int, ...]
    stage2_targets: tuple[float, ...]
    stage2_residues: tuple[float, ...]
    backend_centered_codes: tuple[int, ...]
    unclipped_output_codes: tuple[int, ...]
    output_codes: tuple[int, ...]
    correctable: tuple[bool, ...]


def first_order_residual_factor(
    bandwidth_hz: float,
    phase_duration_s: float,
) -> float:
    """Return ``exp(-2 pi bandwidth duration)`` for a one-pole response."""

    if not isfinite(bandwidth_hz) or bandwidth_hz <= 0:
        raise ValueError("bandwidth_hz must be finite and positive")
    if not isfinite(phase_duration_s) or phase_duration_s <= 0:
        raise ValueError("phase_duration_s must be finite and positive")
    return exp(-2.0 * pi * bandwidth_hz * phase_duration_s)


def equivalent_settling_bits(residual_factor: float) -> float:
    """Convert a remaining full-scale error fraction to ``-log2(rho)``."""

    if not isfinite(residual_factor) or residual_factor < 0 or residual_factor >= 1:
        raise ValueError("residual_factor must lie in [0,1)")
    return float("inf") if residual_factor == 0 else -log2(residual_factor)


def periodic_first_order_response(
    targets: Iterable[float],
    residual_factor: float,
) -> tuple[float, ...]:
    """Solve the unique periodic response of ``r[n]=(1-rho)u[n]+rho r[n-1]``."""

    values = tuple(float(value) for value in targets)
    if not values:
        raise ValueError("periodic target record must be nonempty")
    if any(not isfinite(value) for value in values):
        raise ValueError("periodic targets must be finite")
    if not isfinite(residual_factor) or residual_factor < 0 or residual_factor >= 1:
        raise ValueError("residual_factor must lie in [0,1)")
    if residual_factor == 0:
        return values

    settled_fraction = 1.0 - residual_factor
    end_from_zero = 0.0
    for target in values:
        end_from_zero = (
            settled_fraction * target + residual_factor * end_from_zero
        )
    cycle_memory = residual_factor ** len(values)
    previous = end_from_zero / (1.0 - cycle_memory)
    result = []
    for target in values:
        previous = settled_fraction * target + residual_factor * previous
        result.append(previous)
    return tuple(result)


def _pwl_value(value: float, config: FrontStageTheoryConfig) -> float:
    if config.pwl is None:
        return value
    pwl = config.pwl
    sign = -1 if value < 0 else (1 if value > 0 else 0)
    magnitude = abs(value)
    if magnitude > pwl.input_edges[-1]:
        raise ValueError("stage target lies outside the configured PWL domain")
    index = min(
        bisect_right(pwl.input_edges, magnitude) - 1,
        pwl.slice_count - 1,
    )
    offset = pwl.output_edges[index]
    local = magnitude - pwl.input_edges[index]
    return sign * (offset + pwl.slopes[index] * local)


def _stage_target(
    main_input: float,
    config: FrontStageTheoryConfig,
) -> tuple[int, float, bool]:
    auxiliary = (
        config.auxiliary_gain_ratio * main_input + config.auxiliary_offset
    )
    region = bisect_right(config.effective_thresholds, auxiliary)
    symbol = config.output_symbols[region]
    preamp = (
        main_input
        - config.actual_dac_levels[region]
        + config.dither_value
    )
    target = _pwl_value(config.gain * preamp, config)
    input_ok = config.input_range[0] <= main_input < config.input_range[1]
    return symbol, target, input_ok


def predict_periodic_settling(
    input_values: Iterable[float],
    config: StaticPipelineTheoryConfig,
    settling: PeriodicSettlingConfig,
) -> PeriodicSettlingPrediction:
    """Predict the cyclic steady-state codes of the settling-limited pipeline."""

    values = tuple(float(value) for value in input_values)
    if not values:
        raise ValueError("input record must be nonempty")
    if any(
        not isfinite(value)
        or value < config.input_range[0]
        or value >= config.input_range[1]
        for value in values
    ):
        raise ValueError("input record lies outside the pipeline domain")

    stage1_evaluated = tuple(_stage_target(value, config.stage1) for value in values)
    stage1_symbols = tuple(item[0] for item in stage1_evaluated)
    stage1_targets = tuple(item[1] for item in stage1_evaluated)
    stage1_input_ok = tuple(item[2] for item in stage1_evaluated)
    stage1_residues = periodic_first_order_response(
        stage1_targets,
        settling.residual_factors[0],
    )

    stage2_evaluated = tuple(
        _stage_target(value, config.stage2) for value in stage1_residues
    )
    stage2_symbols = tuple(item[0] for item in stage2_evaluated)
    stage2_targets = tuple(item[1] for item in stage2_evaluated)
    stage2_input_ok = tuple(item[2] for item in stage2_evaluated)
    stage2_residues = periodic_first_order_response(
        stage2_targets,
        settling.residual_factors[1],
    )

    backend_low, backend_high = config.backend_input_range
    backend_count = 1 << config.backend_bits
    backend_step = (backend_high - backend_low) / backend_count
    output_low, output_high = config.output_range
    dither_copy = sum(config.digital_dither_copies)
    backend_codes = []
    unclipped_codes = []
    output_codes = []
    correctable = []
    for index, residue in enumerate(stage2_residues):
        raw_unclipped = floor((residue - backend_low) / backend_step)
        raw = min(max(raw_unclipped, 0), backend_count - 1)
        centered = raw - backend_count // 2
        unclipped = (
            config.front_stage_weights[0] * stage1_symbols[index]
            + config.front_stage_weights[1] * stage2_symbols[index]
            + config.backend_weight * centered
            - dither_copy
            + config.output_offset
        )
        output = min(max(unclipped, output_low), output_high)
        stage1_output_ok = (
            config.stage1.next_stage_range[0]
            <= stage1_residues[index]
            < config.stage1.next_stage_range[1]
        )
        stage2_output_ok = (
            config.stage2.next_stage_range[0]
            <= residue
            < config.stage2.next_stage_range[1]
        )
        backend_ok = backend_low <= residue < backend_high
        output_ok = output_low <= unclipped <= output_high
        backend_codes.append(centered)
        unclipped_codes.append(unclipped)
        output_codes.append(output)
        correctable.append(
            stage1_input_ok[index]
            and stage1_output_ok
            and stage2_input_ok[index]
            and stage2_output_ok
            and backend_ok
            and output_ok
        )

    return PeriodicSettlingPrediction(
        input_values=values,
        stage1_symbols=stage1_symbols,
        stage1_targets=stage1_targets,
        stage1_residues=stage1_residues,
        stage2_symbols=stage2_symbols,
        stage2_targets=stage2_targets,
        stage2_residues=stage2_residues,
        backend_centered_codes=tuple(backend_codes),
        unclipped_output_codes=tuple(unclipped_codes),
        output_codes=tuple(output_codes),
        correctable=tuple(correctable),
    )


@dataclass(frozen=True)
class DualPathPeriodicSettlingConfig:
    """One-pole candidate factors for stage-1 main/aux and stage-2 main."""

    stage1_main_factor: float
    stage1_auxiliary_factor: float
    stage2_main_factor: float

    def __post_init__(self) -> None:
        if any(
            not isfinite(value) or value < 0 or value >= 1
            for value in (
                self.stage1_main_factor,
                self.stage1_auxiliary_factor,
                self.stage2_main_factor,
            )
        ):
            raise ValueError("dual-path settling factors must lie in [0,1)")


@dataclass(frozen=True)
class DualPathPeriodicPrediction:
    """Closed-cycle trace of the independent auxiliary settling hypothesis."""

    input_values: tuple[float, ...]
    stage1_symbols: tuple[int, ...]
    stage1_main_targets: tuple[float, ...]
    stage1_main_outputs: tuple[float, ...]
    stage1_auxiliary_targets: tuple[float, ...]
    stage1_auxiliary_outputs: tuple[float, ...]
    stage2_symbols: tuple[int, ...]
    stage2_main_targets: tuple[float, ...]
    stage2_main_outputs: tuple[float, ...]
    backend_centered_codes: tuple[int, ...]
    unclipped_output_codes: tuple[int, ...]
    output_codes: tuple[int, ...]
    correctable: tuple[bool, ...]


def predict_periodic_dual_path_settling(
    input_values: Iterable[float],
    config: StaticPipelineTheoryConfig,
    settling: DualPathPeriodicSettlingConfig,
) -> DualPathPeriodicPrediction:
    """Solve three feedforward periodic states without a sample-wise warm-up.

    The auxiliary static target is linear in the stage-1 CDAC summing node.
    It does not inherit a selected synthetic main-amplifier PWL distortion.
    This is a conditional behavioral candidate, not a fitted silicon model.
    """

    values = tuple(float(value) for value in input_values)
    if not values:
        raise ValueError("input record must be nonempty")
    if any(
        not isfinite(value)
        or value < config.input_range[0]
        or value >= config.input_range[1]
        for value in values
    ):
        raise ValueError("input record lies outside the pipeline domain")

    first = config.stage1
    second = config.stage2
    first_evaluated = tuple(_stage_target(value, first) for value in values)
    q1 = tuple(item[0] for item in first_evaluated)
    main_targets = tuple(item[1] for item in first_evaluated)
    first_input_ok = tuple(item[2] for item in first_evaluated)
    auxiliary_targets = []
    for value in values:
        flash_input = first.auxiliary_gain_ratio * value + first.auxiliary_offset
        region = bisect_right(first.effective_thresholds, flash_input)
        preamp = value - first.actual_dac_levels[region] + first.dither_value
        auxiliary_targets.append(
            second.auxiliary_gain_ratio * first.gain * preamp
            + second.auxiliary_offset
        )

    main_outputs = periodic_first_order_response(
        main_targets, settling.stage1_main_factor
    )
    auxiliary_outputs = periodic_first_order_response(
        auxiliary_targets, settling.stage1_auxiliary_factor
    )

    q2 = []
    second_targets = []
    second_input_ok = []
    for main, auxiliary in zip(main_outputs, auxiliary_outputs, strict=True):
        region = bisect_right(second.effective_thresholds, auxiliary)
        q2.append(second.output_symbols[region])
        preamp = main - second.actual_dac_levels[region] + second.dither_value
        second_targets.append(_pwl_value(second.gain * preamp, second))
        second_input_ok.append(second.input_range[0] <= main < second.input_range[1])
    second_outputs = periodic_first_order_response(
        second_targets, settling.stage2_main_factor
    )

    backend_low, backend_high = config.backend_input_range
    backend_count = 1 << config.backend_bits
    backend_step = (backend_high - backend_low) / backend_count
    output_low, output_high = config.output_range
    dither_copy = sum(config.digital_dither_copies)
    backend_codes = []
    unclipped_codes = []
    output_codes = []
    correctable = []
    for index, residue in enumerate(second_outputs):
        raw_unclipped = floor((residue - backend_low) / backend_step)
        raw = min(max(raw_unclipped, 0), backend_count - 1)
        centered = raw - backend_count // 2
        unclipped = (
            config.front_stage_weights[0] * q1[index]
            + config.front_stage_weights[1] * q2[index]
            + config.backend_weight * centered
            - dither_copy
            + config.output_offset
        )
        stage1_output_ok = (
            first.next_stage_range[0]
            <= main_outputs[index]
            < first.next_stage_range[1]
        )
        stage2_output_ok = (
            second.next_stage_range[0]
            <= residue
            < second.next_stage_range[1]
        )
        backend_codes.append(centered)
        unclipped_codes.append(unclipped)
        output_codes.append(min(max(unclipped, output_low), output_high))
        correctable.append(
            first_input_ok[index]
            and stage1_output_ok
            and second_input_ok[index]
            and stage2_output_ok
            and backend_low <= residue < backend_high
            and output_low <= unclipped <= output_high
        )

    return DualPathPeriodicPrediction(
        input_values=values,
        stage1_symbols=q1,
        stage1_main_targets=main_targets,
        stage1_main_outputs=main_outputs,
        stage1_auxiliary_targets=tuple(auxiliary_targets),
        stage1_auxiliary_outputs=auxiliary_outputs,
        stage2_symbols=tuple(q2),
        stage2_main_targets=tuple(second_targets),
        stage2_main_outputs=second_outputs,
        backend_centered_codes=tuple(backend_codes),
        unclipped_output_codes=tuple(unclipped_codes),
        output_codes=tuple(output_codes),
        correctable=tuple(correctable),
    )
