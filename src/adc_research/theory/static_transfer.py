"""Independent interval predictor for a memoryless three-stage pipeline ADC.

The predictor composes quantizer boundaries, CDAC levels, affine residue gain,
optional PWL approximations of analog amplifier transfer, and backend SAR
thresholds. These approximations are separate from digital PWL correction.
It does not import or call the sample-wise reference platform. Its output is an exact
partition of the ADC input domain up to floating-point boundary arithmetic.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from math import isfinite
from typing import Any


_BOUNDARY_TOLERANCE = 1e-14


@dataclass(frozen=True)
class OddSymmetricPwl:
    """Monotone odd-symmetric PWL map defined by paired positive edges."""

    input_edges: tuple[float, ...]
    output_edges: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.input_edges) < 2:
            raise ValueError("PWL map requires at least one slice")
        if len(self.input_edges) != len(self.output_edges):
            raise ValueError("PWL input and output edges must have equal length")
        for name, edges in (
            ("input", self.input_edges),
            ("output", self.output_edges),
        ):
            if any(not isfinite(value) for value in edges):
                raise ValueError(f"PWL {name} edges must be finite")
            if edges[0] != 0:
                raise ValueError(f"PWL {name} edges must start at zero")
            if any(right <= left for left, right in zip(edges, edges[1:])):
                raise ValueError(f"PWL {name} edges must be strictly increasing")

    @property
    def slice_count(self) -> int:
        return len(self.input_edges) - 1

    @property
    def slopes(self) -> tuple[float, ...]:
        return tuple(
            (output_right - output_left) / (input_right - input_left)
            for input_left, input_right, output_left, output_right in zip(
                self.input_edges[:-1],
                self.input_edges[1:],
                self.output_edges[:-1],
                self.output_edges[1:],
                strict=True,
            )
        )


@dataclass(frozen=True)
class FrontStageTheoryConfig:
    """Static parameters needed to propagate one front-stage interval."""

    thresholds: tuple[float, ...]
    output_symbols: tuple[int, ...]
    dac_levels: tuple[float, ...]
    gain: float
    input_range: tuple[float, float] = (-1.0, 1.0)
    next_stage_range: tuple[float, float] = (-1.0, 1.0)
    threshold_offsets: tuple[float, ...] = ()
    cdac_level_errors: tuple[float, ...] = ()
    auxiliary_gain_ratio: float = 1.0
    auxiliary_offset: float = 0.0
    dither_value: float = 0.0
    pwl: OddSymmetricPwl | None = None

    def __post_init__(self) -> None:
        if len(self.output_symbols) != len(self.thresholds) + 1:
            raise ValueError("stage symbols must have one more item than thresholds")
        if len(self.dac_levels) != len(self.output_symbols):
            raise ValueError("each stage symbol must have one DAC level")
        if len(set(self.output_symbols)) != len(self.output_symbols):
            raise ValueError("stage symbols must be unique")
        if any(right <= left for left, right in zip(self.thresholds, self.thresholds[1:])):
            raise ValueError("stage thresholds must be strictly increasing")
        if self.threshold_offsets and len(self.threshold_offsets) != len(self.thresholds):
            raise ValueError("threshold offsets must match stage thresholds")
        if self.cdac_level_errors and len(self.cdac_level_errors) != len(self.dac_levels):
            raise ValueError("CDAC errors must match stage DAC levels")
        values = (
            *self.thresholds,
            *self.dac_levels,
            *self.threshold_offsets,
            *self.cdac_level_errors,
            self.gain,
            self.auxiliary_gain_ratio,
            self.auxiliary_offset,
            self.dither_value,
            *self.input_range,
            *self.next_stage_range,
        )
        if any(not isfinite(value) for value in values):
            raise ValueError("stage parameters must be finite")
        if self.gain <= 0 or self.auxiliary_gain_ratio <= 0:
            raise ValueError("stage and auxiliary gains must be positive")
        for name, interval in (
            ("input", self.input_range),
            ("next-stage", self.next_stage_range),
        ):
            if interval[1] <= interval[0]:
                raise ValueError(f"stage {name} range must be increasing")
        effective = self.effective_thresholds
        if any(right <= left for left, right in zip(effective, effective[1:])):
            raise ValueError("effective stage thresholds must remain increasing")

    @property
    def effective_thresholds(self) -> tuple[float, ...]:
        offsets = self.threshold_offsets or (0.0,) * len(self.thresholds)
        return tuple(
            threshold + offset
            for threshold, offset in zip(self.thresholds, offsets, strict=True)
        )

    @property
    def actual_dac_levels(self) -> tuple[float, ...]:
        errors = self.cdac_level_errors or (0.0,) * len(self.dac_levels)
        return tuple(
            level + error
            for level, error in zip(self.dac_levels, errors, strict=True)
        )


@dataclass(frozen=True)
class StaticPipelineTheoryConfig:
    """Independent theory-side description of the frozen three-stage chain."""

    stage1: FrontStageTheoryConfig
    stage2: FrontStageTheoryConfig
    backend_bits: int
    backend_input_range: tuple[float, float]
    front_stage_weights: tuple[int, int]
    backend_weight: int
    output_offset: int
    output_range: tuple[int, int]
    input_range: tuple[float, float] = (-1.0, 1.0)
    digital_dither_copies: tuple[int, int] = (0, 0)

    def __post_init__(self) -> None:
        if self.backend_bits <= 0:
            raise ValueError("backend bits must be positive")
        if self.backend_weight <= 0:
            raise ValueError("backend weight must be positive")
        if self.backend_input_range[1] <= self.backend_input_range[0]:
            raise ValueError("backend input range must be increasing")
        if self.input_range[1] <= self.input_range[0]:
            raise ValueError("pipeline input range must be increasing")
        if self.output_range[1] < self.output_range[0]:
            raise ValueError("output code range must be increasing")


@dataclass(frozen=True)
class TransferSegment:
    """One left-closed, right-open input interval with a constant output code."""

    input_lower: float
    input_upper: float
    stage1_symbol: int
    stage2_symbol: int
    backend_centered_code: int
    unclipped_output_code: int
    output_code: int
    correctable: bool
    stage1_pwl_slice: int | None
    stage2_pwl_slice: int | None

    @property
    def width(self) -> float:
        return self.input_upper - self.input_lower


@dataclass(frozen=True)
class StaticTransferPrediction:
    """Complete static transfer partition and exact uniform-input metrics.

    ``transition_inl_lsb`` is cumulative code-density DNL for compatibility
    with the frozen metrics protocol. It represents physical transition INL
    only when output codes are ordered monotonically over the input range.
    Check ``negative_step_count`` before using that interpretation.
    """

    input_range: tuple[float, float]
    output_range: tuple[int, int]
    segments: tuple[TransferSegment, ...]
    code_widths: tuple[float, ...]
    dnl_lsb: tuple[float, ...]
    transition_inl_lsb: tuple[float, ...]
    missing_codes: tuple[int, ...]
    negative_step_count: int
    uncorrectable_input_width: float

    def segment_at(self, value: float) -> TransferSegment:
        """Locate one input value with the predicted half-open semantics."""
        low, high = self.input_range
        if not isfinite(value) or value < low or value >= high:
            raise ValueError("value lies outside the predicted input range")
        left = 0
        right = len(self.segments)
        while left < right:
            index = (left + right) // 2
            segment = self.segments[index]
            if value < segment.input_lower:
                right = index
            elif value >= segment.input_upper:
                left = index + 1
            else:
                return segment
        raise RuntimeError("predicted transfer has a gap at the requested value")

    def code_at(self, value: float) -> int:
        """Evaluate the interval transfer without repeating stage equations."""

        return self.segment_at(value).output_code


@dataclass(frozen=True)
class _AffinePiece:
    lower: float
    upper: float
    slope: float
    intercept: float
    symbols: tuple[int, ...] = ()
    pwl_slices: tuple[int | None, ...] = ()
    correctable: bool = True

    def value_at(self, input_value: float) -> float:
        return self.slope * input_value + self.intercept


def _split_by_output_boundaries(
    piece: _AffinePiece,
    boundaries: Sequence[float],
) -> tuple[_AffinePiece, ...]:
    if piece.slope <= 0:
        raise ValueError("static predictor currently requires positive local slopes")
    cuts = [piece.lower, piece.upper]
    for boundary in boundaries:
        crossing = (boundary - piece.intercept) / piece.slope
        if (
            crossing > piece.lower + _BOUNDARY_TOLERANCE
            and crossing < piece.upper - _BOUNDARY_TOLERANCE
        ):
            cuts.append(crossing)
    cuts.sort()
    unique = [cuts[0]]
    for value in cuts[1:]:
        if value - unique[-1] > _BOUNDARY_TOLERANCE:
            unique.append(value)
        else:
            unique[-1] = max(unique[-1], value)
    return tuple(
        replace(piece, lower=left, upper=right)
        for left, right in zip(unique, unique[1:])
        if right - left > _BOUNDARY_TOLERANCE
    )


def _split_many(
    pieces: Sequence[_AffinePiece],
    boundaries: Sequence[float],
) -> tuple[_AffinePiece, ...]:
    return tuple(
        child
        for piece in pieces
        for child in _split_by_output_boundaries(piece, boundaries)
    )


def _apply_pwl(
    pieces: Sequence[_AffinePiece],
    pwl: OddSymmetricPwl | None,
) -> tuple[_AffinePiece, ...]:
    if pwl is None:
        return tuple(
            replace(piece, pwl_slices=piece.pwl_slices + (None,))
            for piece in pieces
        )

    positive_edges = pwl.input_edges[1:]
    signed_edges = tuple(-value for value in reversed(positive_edges)) + (0.0,) + positive_edges
    partitioned = _split_many(pieces, signed_edges)
    transformed = []
    maximum = pwl.input_edges[-1]
    slopes = pwl.slopes
    for piece in partitioned:
        midpoint = (piece.lower + piece.upper) / 2
        value = piece.value_at(midpoint)
        magnitude = abs(value)
        if magnitude > maximum + _BOUNDARY_TOLERANCE:
            raise ValueError("stage output lies outside the configured PWL domain")
        slice_index = min(bisect_right(pwl.input_edges, magnitude) - 1, pwl.slice_count - 1)
        local_slope = slopes[slice_index]
        affine_offset = (
            pwl.output_edges[slice_index]
            - local_slope * pwl.input_edges[slice_index]
        )
        signed_offset = affine_offset if value >= 0 else -affine_offset
        transformed.append(
            replace(
                piece,
                slope=local_slope * piece.slope,
                intercept=local_slope * piece.intercept + signed_offset,
                pwl_slices=piece.pwl_slices + (slice_index,),
            )
        )
    return tuple(transformed)


def _propagate_front_stage(
    pieces: Sequence[_AffinePiece],
    config: FrontStageTheoryConfig,
) -> tuple[_AffinePiece, ...]:
    main_boundaries = tuple(
        (threshold - config.auxiliary_offset) / config.auxiliary_gain_ratio
        for threshold in config.effective_thresholds
    )
    decision_pieces = _split_many(
        pieces,
        (*main_boundaries, *config.input_range),
    )
    after_gain = []
    actual_dac_levels = config.actual_dac_levels
    for piece in decision_pieces:
        midpoint = (piece.lower + piece.upper) / 2
        main_value = piece.value_at(midpoint)
        auxiliary_value = (
            config.auxiliary_gain_ratio * main_value + config.auxiliary_offset
        )
        region = bisect_right(config.effective_thresholds, auxiliary_value)
        symbol = config.output_symbols[region]
        actual_dac = actual_dac_levels[region]
        input_correctable = (
            config.input_range[0] <= main_value < config.input_range[1]
        )
        after_gain.append(
            replace(
                piece,
                slope=config.gain * piece.slope,
                intercept=(
                    config.gain
                    * (piece.intercept - actual_dac + config.dither_value)
                ),
                symbols=piece.symbols + (symbol,),
                correctable=piece.correctable and input_correctable,
            )
        )

    after_pwl = _apply_pwl(after_gain, config.pwl)
    range_split = _split_many(after_pwl, config.next_stage_range)
    result = []
    for piece in range_split:
        midpoint = (piece.lower + piece.upper) / 2
        residue = piece.value_at(midpoint)
        residue_correctable = (
            config.next_stage_range[0]
            <= residue
            < config.next_stage_range[1]
        )
        result.append(
            replace(
                piece,
                correctable=piece.correctable and residue_correctable,
            )
        )
    return tuple(result)


def _backend_segments(
    pieces: Sequence[_AffinePiece],
    config: StaticPipelineTheoryConfig,
) -> tuple[TransferSegment, ...]:
    low, high = config.backend_input_range
    code_count = 1 << config.backend_bits
    step = (high - low) / code_count
    thresholds = tuple(low + index * step for index in range(1, code_count))
    partitioned = _split_many(pieces, (low, *thresholds, high))
    segments = []
    dither_copy = sum(config.digital_dither_copies)
    output_low, output_high = config.output_range
    for piece in partitioned:
        midpoint = (piece.lower + piece.upper) / 2
        backend_value = piece.value_at(midpoint)
        raw_unclipped = int((backend_value - low) // step)
        raw_code = min(max(raw_unclipped, 0), code_count - 1)
        centered_code = raw_code - code_count // 2
        backend_correctable = low <= backend_value < high
        stage1_symbol, stage2_symbol = piece.symbols
        unclipped = (
            config.front_stage_weights[0] * stage1_symbol
            + config.front_stage_weights[1] * stage2_symbol
            + config.backend_weight * centered_code
            - dither_copy
            + config.output_offset
        )
        output_code = min(max(unclipped, output_low), output_high)
        output_correctable = output_low <= unclipped <= output_high
        segments.append(
            TransferSegment(
                input_lower=piece.lower,
                input_upper=piece.upper,
                stage1_symbol=stage1_symbol,
                stage2_symbol=stage2_symbol,
                backend_centered_code=centered_code,
                unclipped_output_code=unclipped,
                output_code=output_code,
                correctable=(
                    piece.correctable
                    and backend_correctable
                    and output_correctable
                ),
                stage1_pwl_slice=piece.pwl_slices[0],
                stage2_pwl_slice=piece.pwl_slices[1],
            )
        )
    return tuple(segments)


def _merge_equivalent_segments(
    segments: Sequence[TransferSegment],
) -> tuple[TransferSegment, ...]:
    """Merge adjacent leaves only when every reported path property agrees."""

    merged: list[TransferSegment] = []
    for segment in segments:
        if not merged:
            merged.append(segment)
            continue
        previous = merged[-1]
        same_properties = (
            previous.stage1_symbol == segment.stage1_symbol
            and previous.stage2_symbol == segment.stage2_symbol
            and previous.backend_centered_code == segment.backend_centered_code
            and previous.unclipped_output_code == segment.unclipped_output_code
            and previous.output_code == segment.output_code
            and previous.correctable == segment.correctable
            and previous.stage1_pwl_slice == segment.stage1_pwl_slice
            and previous.stage2_pwl_slice == segment.stage2_pwl_slice
        )
        if (
            same_properties
            and abs(previous.input_upper - segment.input_lower)
            <= _BOUNDARY_TOLERANCE
        ):
            merged[-1] = replace(previous, input_upper=segment.input_upper)
        else:
            merged.append(segment)
    return tuple(merged)


def predict_static_transfer(
    config: StaticPipelineTheoryConfig,
) -> StaticTransferPrediction:
    """Compose the full input partition and derive exact code-width metrics."""

    input_low, input_high = config.input_range
    pieces = (_AffinePiece(input_low, input_high, 1.0, 0.0),)
    stage1 = _propagate_front_stage(pieces, config.stage1)
    stage2 = _propagate_front_stage(stage1, config.stage2)
    segments = _merge_equivalent_segments(_backend_segments(stage2, config))

    if not segments:
        raise RuntimeError("static transfer prediction produced no segments")
    coverage = sum(segment.width for segment in segments)
    expected_coverage = input_high - input_low
    if abs(coverage - expected_coverage) > 1e-11:
        raise RuntimeError("static transfer segments do not cover the input domain")

    output_low, output_high = config.output_range
    level_count = output_high - output_low + 1
    widths = [0.0] * level_count
    for segment in segments:
        widths[segment.output_code - output_low] += segment.width
    ideal_width = expected_coverage / level_count
    dnl = tuple(width / ideal_width - 1.0 for width in widths)
    transition_inl = [0.0]
    cumulative = 0.0
    for value in dnl:
        cumulative += value
        transition_inl.append(cumulative)
    missing = tuple(
        output_low + index
        for index, width in enumerate(widths)
        if width <= _BOUNDARY_TOLERANCE
    )
    negative_steps = sum(
        right.output_code < left.output_code
        for left, right in zip(segments, segments[1:])
    )
    uncorrectable_width = sum(
        segment.width for segment in segments if not segment.correctable
    )
    return StaticTransferPrediction(
        input_range=config.input_range,
        output_range=config.output_range,
        segments=segments,
        code_widths=tuple(widths),
        dnl_lsb=dnl,
        transition_inl_lsb=tuple(transition_inl),
        missing_codes=missing,
        negative_step_count=negative_steps,
        uncorrectable_input_width=uncorrectable_width,
    )


def build_gu_theory_config(
    architecture: Mapping[str, Any],
    *,
    nonidealities: Mapping[str, Any] | None = None,
    enabled_effects: Sequence[str] = (),
    dither_symbols: tuple[int | None, int | None] = (None, None),
    dither_profile: str | None = None,
    stage2_flash_auxiliary_gain_ratio: float = 1.0,
    stage2_flash_auxiliary_offset: float = 0.0,
) -> StaticPipelineTheoryConfig:
    """Build a theory-only config from the reviewed Gu YAML mappings.

    The adapter intentionally repeats the equations on the theory side.  It
    shares only declarative parameters with the reference platform.
    """

    if architecture.get("config_id") != "gu_behavioral_v1":
        raise ValueError("unsupported architecture for Gu static theory")
    supported_effects = {
        "flash_threshold_offsets",
        "cdac_code_level_mismatch",
        "linear_interstage_gain",
        "static_pwl_truth",
    }
    enabled = set(enabled_effects)
    if enabled - supported_effects:
        raise ValueError(f"unknown static effects: {sorted(enabled - supported_effects)}")
    if enabled:
        if nonidealities is None:
            raise ValueError("enabled static effects require a nonideality profile")
        if nonidealities.get("config_id") != "gu_gate_d_static_v0_1":
            raise ValueError("unsupported Gu static nonideality profile")

    domain = architecture["normalized_domain"]
    input_range = tuple(float(value) for value in domain["input_range"])
    template = architecture["front_stage_template"]
    thresholds = tuple(float(value) for value in template["thresholds"])
    symbols = tuple(int(value) for value in template["output_symbols"])
    dac_levels = tuple(float(value) for value in template["dac_levels"])
    dither = architecture["dither_hypothesis"]
    selected_profile = dither_profile or dither["default_profile"]
    profile = dither["profiles"][selected_profile]
    amplitude = float(profile["residue_preamp_normalized_half_amplitude"])
    copy_amplitudes = tuple(int(value) for value in profile["digital_copy_centered_codes"])
    effects = nonidealities["effects"] if nonidealities is not None else {}

    def build_stage(stage_name: str, index: int) -> FrontStageTheoryConfig:
        threshold_offsets = (
            tuple(float(value) for value in effects["flash_threshold_offsets"][stage_name])
            if "flash_threshold_offsets" in enabled
            else ()
        )
        if "cdac_code_level_mismatch" in enabled:
            errors_by_symbol = effects["cdac_code_level_mismatch"][stage_name]
            cdac_errors = tuple(float(errors_by_symbol[symbol]) for symbol in symbols)
        else:
            cdac_errors = ()
        gain = (
            float(effects["linear_interstage_gain"][stage_name])
            if "linear_interstage_gain" in enabled
            else float(template["nominal_interstage_gain"])
        )
        if "static_pwl_truth" in enabled:
            truth = effects["static_pwl_truth"][stage_name]
            pwl = OddSymmetricPwl(
                tuple(float(value) for value in truth["ideal_output_edges"]),
                tuple(float(value) for value in truth["distorted_output_edges"]),
            )
        else:
            pwl = None
        symbol = dither_symbols[index]
        dither_value = 0.0 if symbol is None else float(symbol) * amplitude
        return FrontStageTheoryConfig(
            thresholds=thresholds,
            output_symbols=symbols,
            dac_levels=dac_levels,
            gain=gain,
            input_range=input_range,
            next_stage_range=input_range,
            threshold_offsets=threshold_offsets,
            cdac_level_errors=cdac_errors,
            auxiliary_gain_ratio=(
                1.0 if index == 0 else stage2_flash_auxiliary_gain_ratio
            ),
            auxiliary_offset=(
                0.0 if index == 0 else stage2_flash_auxiliary_offset
            ),
            dither_value=dither_value,
            pwl=pwl,
        )

    digital = architecture["digital_reconstruction"]
    weights = digital["centered_weights"]
    backend = architecture["backend"]
    digital_copies = tuple(
        0 if symbol is None else int(symbol) * copy_amplitudes[index]
        for index, symbol in enumerate(dither_symbols)
    )
    return StaticPipelineTheoryConfig(
        stage1=build_stage("stage1", 0),
        stage2=build_stage("stage2", 1),
        backend_bits=int(backend["bits"]),
        backend_input_range=input_range,
        front_stage_weights=(
            int(weights["stage1_symbol"]),
            int(weights["stage2_symbol"]),
        ),
        backend_weight=int(weights["backend_centered_code"]),
        output_offset=int(digital["output_offset"]),
        output_range=tuple(int(value) for value in digital["output_range"]),
        input_range=input_range,
        digital_dither_copies=digital_copies,
    )
