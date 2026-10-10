"""Conditional digital observations from independent analog path envelopes.

Each transfer callback must enclose *every* admissible output for the entire
input interval it receives, including all allowed code, channel, and PVT
conditions not separately indexed by this interface. This module cannot
establish that physical coverage; it only propagates a supplied static
contract. It is independent of the sample-wise platform and of any particular
digital calibration law.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import floor, isfinite
from typing import Callable


@dataclass(frozen=True)
class ClosedInterval:
    lower: float
    upper: float

    def __post_init__(self) -> None:
        if not (isfinite(self.lower) and isfinite(self.upper)) or self.lower > self.upper:
            raise ValueError("interval endpoints must be finite and increasing")

    def shifted(self, amount: float) -> "ClosedInterval":
        if not isfinite(amount):
            raise ValueError("interval shift must be finite")
        return ClosedInterval(self.lower + amount, self.upper + amount)

    def add(self, other: "ClosedInterval") -> "ClosedInterval":
        return ClosedInterval(self.lower + other.lower, self.upper + other.upper)

    def subtract(self, other: "ClosedInterval") -> "ClosedInterval":
        return ClosedInterval(self.lower - other.upper, self.upper - other.lower)


TransferEnvelope = Callable[[ClosedInterval], ClosedInterval]


@dataclass(frozen=True)
class StaticCandidateArchitecture:
    """Candidate geometry with optional CDAC and quantizer uncertainty.

    Float CDAC levels are normalized to point intervals. An explicitly
    supplied backend threshold table replaces the uniform ideal SAR rule;
    every allowed table must stay strictly ordered.
    """

    stage1_thresholds: tuple[ClosedInterval, ...]
    stage2_thresholds: tuple[ClosedInterval, ...]
    stage1_symbols: tuple[int, ...]
    stage2_symbols: tuple[int, ...]
    stage1_dac_levels: tuple[float | Fraction | ClosedInterval, ...]
    stage2_dac_levels: tuple[float | Fraction | ClosedInterval, ...]
    front_nominal_range: tuple[float, float]
    backend_range: tuple[float, float]
    backend_bits: int
    backend_thresholds: tuple[ClosedInterval, ...] | None = None

    def __post_init__(self) -> None:
        for thresholds, symbols, levels in (
            (self.stage1_thresholds, self.stage1_symbols, self.stage1_dac_levels),
            (self.stage2_thresholds, self.stage2_symbols, self.stage2_dac_levels),
        ):
            if len(symbols) != len(thresholds) + 1 or len(levels) != len(symbols):
                raise ValueError("each stage needs one symbol and DAC level per region")
            if any(left.upper >= right.lower for left, right in zip(thresholds, thresholds[1:])):
                raise ValueError("threshold intervals must remain strictly ordered")
            if any(
                not isinstance(level, ClosedInterval) and
                (not isinstance(level, (int, float, Fraction)) or not isfinite(level))
                for level in levels
            ):
                raise ValueError("DAC levels must be finite points or intervals")
        for low, high in (self.front_nominal_range, self.backend_range):
            if not (isfinite(low) and isfinite(high)) or low >= high:
                raise ValueError("quantizer input range must be finite and increasing")
        if self.backend_bits <= 0:
            raise ValueError("backend_bits must be positive")
        if self.backend_thresholds is not None:
            if len(self.backend_thresholds) != (1 << self.backend_bits) - 1:
                raise ValueError("backend needs one fewer threshold than codes")
            if any(not isinstance(item, ClosedInterval) for item in self.backend_thresholds):
                raise TypeError("backend thresholds must be ClosedInterval values")
            if any(
                left.upper >= right.lower
                for left, right in zip(self.backend_thresholds, self.backend_thresholds[1:])
            ):
                raise ValueError("backend threshold intervals must remain ordered")

        for name in ("stage1_dac_levels", "stage2_dac_levels"):
            levels = getattr(self, name)
            object.__setattr__(self, name, tuple(
                level if isinstance(level, ClosedInterval)
                else ClosedInterval(level, level) if isinstance(level, Fraction)
                else ClosedInterval(float(level), float(level))
                for level in levels
            ))


@dataclass(frozen=True)
class StaticDigitalOutcome:
    stage1_symbol: int
    stage2_symbol: int
    backend_centered_code: int


@dataclass(frozen=True)
class StaticObservationEnvelope:
    outcomes: tuple[StaticDigitalOutcome, ...]
    stage1_input_overload_possible: bool
    stage1_main_overload_possible: bool
    stage2_aux_outside_nominal_range_possible: bool
    backend_overload_possible: bool


def _outside_nominal(interval: ClosedInterval, nominal: tuple[float, float]) -> bool:
    return interval.lower < nominal[0] or interval.upper >= nominal[1]


def _possible_regions(
    value: ClosedInterval, thresholds: tuple[ClosedInterval, ...]
) -> range:
    # A comparator reports high at equality.  The lower count uses the
    # highest allowed thresholds and lowest allowed input; the upper count
    # uses the lowest thresholds and highest input. Correlations are dropped.
    first = sum(bound.upper <= value.lower for bound in thresholds)
    last = sum(bound.lower <= value.upper for bound in thresholds)
    return range(first, last + 1)


def _possible_input_for_region(
    value: ClosedInterval, thresholds: tuple[ClosedInterval, ...], index: int
) -> ClosedInterval:
    # In region index, the preceding threshold was reached and the next was
    # not. Their extreme allowed positions give a closed outer interval.
    lower = max(value.lower, thresholds[index - 1].lower) if index else value.lower
    upper = min(value.upper, thresholds[index].upper) if index < len(thresholds) else value.upper
    return ClosedInterval(lower, upper)


def _backend_codes(
    voltage: ClosedInterval,
    nominal: tuple[float, float],
    bits: int,
    thresholds: tuple[ClosedInterval, ...] | None,
) -> range:
    count = 1 << bits
    if thresholds is not None:
        regions = _possible_regions(voltage, thresholds)
        return range(regions.start - count // 2, regions.stop - count // 2)
    step = (nominal[1] - nominal[0]) / count

    def raw(value: float) -> int:
        return min(max(floor((value - nominal[0]) / step), 0), count - 1)

    return range(raw(voltage.lower) - count // 2, raw(voltage.upper) - count // 2 + 1)


def propagate_static_observations(
    input_voltage: ClosedInterval,
    dither1_preamp: ClosedInterval,
    dither2_preamp: ClosedInterval,
    architecture: StaticCandidateArchitecture,
    stage1_main: TransferEnvelope,
    stage1_auxiliary: TransferEnvelope,
    stage2_main: TransferEnvelope,
) -> StaticObservationEnvelope:
    """Enclose all static five-field digital records with fixed dither tags.

    Analog dither voltages and CDAC levels may be intervals; optional backend
    thresholds may be intervals too. The digital dither tags are carried
    separately by the caller when it evaluates the correction.
    Main and auxiliary outputs of stage one share a preamplifier input, but
    their independent ranges may include mutually impossible combinations;
    this widens the result without losing coverage.
    """
    outcomes: set[StaticDigitalOutcome] = set()
    main_overload = False
    aux_outside = False
    backend_overload = False
    for index1 in _possible_regions(input_voltage, architecture.stage1_thresholds):
        branch_input = _possible_input_for_region(
            input_voltage, architecture.stage1_thresholds, index1
        )
        preamp1 = branch_input.subtract(architecture.stage1_dac_levels[index1]).add(
            dither1_preamp
        )
        main1 = stage1_main(preamp1)
        aux1 = stage1_auxiliary(preamp1)
        if not isinstance(main1, ClosedInterval) or not isinstance(aux1, ClosedInterval):
            raise TypeError("transfer envelopes must return ClosedInterval")
        main_overload |= _outside_nominal(main1, architecture.front_nominal_range)
        aux_outside |= _outside_nominal(aux1, architecture.front_nominal_range)
        for index2 in _possible_regions(aux1, architecture.stage2_thresholds):
            preamp2 = main1.subtract(architecture.stage2_dac_levels[index2]).add(
                dither2_preamp
            )
            main2 = stage2_main(preamp2)
            if not isinstance(main2, ClosedInterval):
                raise TypeError("transfer envelopes must return ClosedInterval")
            backend_overload |= _outside_nominal(main2, architecture.backend_range)
            for centered in _backend_codes(
                main2, architecture.backend_range, architecture.backend_bits,
                architecture.backend_thresholds,
            ):
                outcomes.add(StaticDigitalOutcome(
                    architecture.stage1_symbols[index1],
                    architecture.stage2_symbols[index2],
                    centered,
                ))
    return StaticObservationEnvelope(
        outcomes=tuple(sorted(outcomes, key=lambda item: (
            item.stage1_symbol, item.stage2_symbol, item.backend_centered_code
        ))),
        stage1_input_overload_possible=_outside_nominal(
            input_voltage, architecture.front_nominal_range
        ),
        stage1_main_overload_possible=main_overload,
        stage2_aux_outside_nominal_range_possible=aux_outside,
        backend_overload_possible=backend_overload,
    )
