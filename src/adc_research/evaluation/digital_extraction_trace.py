"""Audit recorded Gu extraction words against two explicit gate candidates.

This module consumes decoded *digital* trace words. It does not infer the ADC's
physical bus encoding, decimator transfer function, or coefficient update rule.
Products are accumulated as exact Python integers before any hardware rounding.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any


class TraceFormatError(ValueError):
    """The record cannot support the declared fixed-coefficient audit."""


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TraceFormatError(f"{label} must be an object")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise TraceFormatError(f"{label} must be a list")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TraceFormatError(f"{label} must be an integer code")
    return value


def _nonnegative(value: Any, label: str) -> int:
    result = _integer(value, label)
    if result < 0:
        raise TraceFormatError(f"{label} must be nonnegative")
    return result


def _thresholds(value: Any, label: str) -> tuple[int, int, int]:
    values = _list(value, label)
    if len(values) != 3:
        raise TraceFormatError(f"{label} must contain three higher-slice thresholds")
    codes = tuple(_nonnegative(item, label) for item in values)
    if codes != tuple(sorted(codes)):
        raise TraceFormatError(f"{label} must be nondecreasing")
    return codes[0], codes[1], codes[2]


def _coefficients(value: Any, label: str) -> tuple[int, int, int, int]:
    values = _list(value, label)
    if len(values) != 4:
        raise TraceFormatError(f"{label} must contain four coefficient register codes")
    codes = tuple(_integer(item, label) for item in values)
    return codes[0], codes[1], codes[2], codes[3]


def _gate_mask(value: Any, label: str) -> tuple[bool, bool, bool, bool]:
    values = _list(value, label)
    if len(values) != 4 or any(not isinstance(item, bool) for item in values):
        raise TraceFormatError(f"{label} must contain four Boolean gate bits")
    return values[0], values[1], values[2], values[3]


def audit_trace(document: Mapping[str, Any]) -> dict[str, Any]:
    """Check alignment and compare observed words with inclusive/strict gates.

    A result matching a candidate describes only the supplied finite record.
    ``block_id`` is supplied by the trace source, never inferred from Fig. 18.
    ``learning_output_code`` and ``threshold_codes`` must use the same integer
    scale for each stage; hardware product rounding is outside this audit.
    """

    source = _mapping(document, "trace")
    samples = _list(source.get("samples"), "samples")
    if not samples:
        raise TraceFormatError("samples must contain at least one conversion")
    metadata = _mapping(source.get("metadata", {}), "metadata")
    expected_size = metadata.get("expected_block_size")
    if expected_size is not None:
        expected_size = _integer(expected_size, "expected_block_size")
        if expected_size <= 0:
            raise TraceFormatError("expected_block_size must be positive")
    phase_check = metadata.get("check_four_way_phase", False)
    if not isinstance(phase_check, bool):
        raise TraceFormatError("check_four_way_phase must be Boolean")

    # All global and local ordering checks use source-provided conversion labels.
    ordered: list[tuple[int, Mapping[str, Any]]] = []
    for position, raw in enumerate(samples):
        row = _mapping(raw, f"samples[{position}]")
        index = _nonnegative(row.get("conversion_index"), "conversion_index")
        ordered.append((index, row))
    ordered.sort(key=lambda pair: pair[0])
    indices = [index for index, _ in ordered]
    if len(set(indices)) != len(indices):
        raise TraceFormatError("conversion_index contains duplicates")
    if indices != list(range(indices[0], indices[0] + len(indices))):
        raise TraceFormatError("conversion_index contains gaps")

    phase_to_channel: dict[int, int] = {}
    channel_to_phase: dict[int, int] = {}
    last_block_by_channel: dict[int, int] = {}
    groups: dict[tuple[int, int, int], dict[str, Any]] = {}
    for index, row in ordered:
        channel = _nonnegative(row.get("channel_id"), "channel_id")
        if channel > 3:
            raise TraceFormatError("channel_id must be in 0..3")
        block = _nonnegative(row.get("block_id"), "block_id")
        if channel in last_block_by_channel and block < last_block_by_channel[channel]:
            raise TraceFormatError(f"channel {channel} reopens an earlier block")
        last_block_by_channel[channel] = block
        if phase_check:
            phase = index % 4
            if phase in phase_to_channel and phase_to_channel[phase] != channel:
                raise TraceFormatError("one serial phase maps to multiple channels")
            if channel in channel_to_phase and channel_to_phase[channel] != phase:
                raise TraceFormatError("one channel occupies multiple serial phases")
            phase_to_channel[phase] = channel
            channel_to_phase[channel] = phase

        for stage in (1, 2):
            label = f"conversion {index} stage{stage}"
            data = _mapping(row.get(f"stage{stage}"), label)
            dither_index = _nonnegative(
                data.get("dither_conversion_index"), f"{label} dither index"
            )
            output_index = _nonnegative(
                data.get("output_conversion_index"), f"{label} output index"
            )
            if dither_index != index or output_index != index:
                raise TraceFormatError(f"{label} dither/output is not aligned")
            dither = _integer(data.get("dither_code"), f"{label} dither_code")
            output = _integer(
                data.get("learning_output_code"), f"{label} learning_output_code"
            )
            epoch = _nonnegative(data.get("coefficient_epoch"), f"{label} epoch")
            coefficients = _coefficients(
                data.get("coefficient_codes"), f"{label} coefficient_codes"
            )
            thresholds = _thresholds(data.get("threshold_codes"), f"{label} thresholds")
            recorded_mask = (
                _gate_mask(data["gate_mask"], f"{label} gate_mask")
                if "gate_mask" in data
                else None
            )
            key = (channel, block, stage)
            if key not in groups:
                groups[key] = {
                    "epoch": epoch,
                    "coefficients": coefficients,
                    "thresholds": thresholds,
                    "count": 0,
                    "inclusive_sums": [0, 0, 0, 0],
                    "strict_sums": [0, 0, 0, 0],
                    "equality_counts": [0, 0, 0],
                    "equality_product_sums": [0, 0, 0],
                    "mask_evidence": 0,
                    "inclusive_mask_matches": True,
                    "strict_mask_matches": True,
                }
            group = groups[key]
            if (
                epoch != group["epoch"]
                or coefficients != group["coefficients"]
                or thresholds != group["thresholds"]
            ):
                raise TraceFormatError(
                    f"channel {channel} block {block} stage {stage} changes "
                    "coefficient epoch or thresholds; frozen-block audit is inapplicable"
                )
            magnitude = abs(output)
            inclusive = (True,) + tuple(magnitude >= t for t in thresholds)
            strict = (True,) + tuple(magnitude > t for t in thresholds)
            product = dither * output
            for section in range(4):
                if inclusive[section]:
                    group["inclusive_sums"][section] += product
                if strict[section]:
                    group["strict_sums"][section] += product
                if section > 0 and magnitude == thresholds[section - 1]:
                    group["equality_counts"][section - 1] += 1
                    group["equality_product_sums"][section - 1] += product
            if recorded_mask is not None:
                group["mask_evidence"] += 1
                group["inclusive_mask_matches"] &= recorded_mask == inclusive
                group["strict_mask_matches"] &= recorded_mask == strict
            group["count"] += 1

    if phase_check and len(phase_to_channel) != 4:
        raise TraceFormatError("four-way phase check requires all four serial phases")

    extractor_rows = _list(source.get("extractor", []), "extractor")
    extractor: dict[tuple[int, int, int], tuple[int, int, int, int]] = {}
    pooled_extractor: dict[tuple[int, int], tuple[int, int, int, int]] = {}
    for position, raw in enumerate(extractor_rows):
        row = _mapping(raw, f"extractor[{position}]")
        channel_value = row.get("channel_id")
        channel = (
            "all"
            if channel_value == "all"
            else _nonnegative(channel_value, "extractor channel_id")
        )
        block = _nonnegative(row.get("block_id"), "extractor block_id")
        stage = _integer(row.get("stage"), "extractor stage")
        if stage not in (1, 2):
            raise TraceFormatError("extractor stage must be 1 or 2")
        raw_sums = _list(row.get("product_sums"), "extractor product_sums")
        if len(raw_sums) != 4:
            raise TraceFormatError("extractor product_sums needs four integer codes")
        decoded = tuple(_integer(value, "extractor product sum") for value in raw_sums)
        if channel == "all":
            pooled_key = (block, stage)
            if pooled_key in pooled_extractor:
                raise TraceFormatError(f"extractor[{position}] repeats a pooled group")
            pooled_extractor[pooled_key] = (
                decoded[0], decoded[1], decoded[2], decoded[3]
            )
        else:
            key = (channel, block, stage)
            if key not in groups or key in extractor:
                raise TraceFormatError(f"extractor[{position}] has unknown or duplicate group")
            extractor[key] = decoded[0], decoded[1], decoded[2], decoded[3]

    result_blocks: list[dict[str, Any]] = []
    for key in sorted(groups):
        channel, block, stage = key
        group = groups[key]
        count = group["count"]
        if expected_size is not None and count != expected_size:
            raise TraceFormatError(
                f"channel {channel} block {block} stage {stage} has {count} "
                f"conversions, expected {expected_size}"
            )
        if group["mask_evidence"] not in (0, count):
            raise TraceFormatError(
                f"channel {channel} block {block} stage {stage} has partial gate masks"
            )
        observed = key in extractor or group["mask_evidence"] == count
        inclusive_match = group["inclusive_mask_matches"]
        strict_match = group["strict_mask_matches"]
        if key in extractor:
            inclusive_match &= tuple(group["inclusive_sums"]) == extractor[key]
            strict_match &= tuple(group["strict_sums"]) == extractor[key]
        if not observed:
            status = "unverified"
        elif inclusive_match and strict_match:
            status = "both_candidates_match"
        elif inclusive_match:
            status = "inclusive_candidate_matches"
        elif strict_match:
            status = "strict_candidate_matches"
        else:
            status = "neither_candidate_matches"
        result_blocks.append(
            {
                "channel_id": channel,
                "block_id": block,
                "stage": stage,
                "conversion_count": count,
                "coefficient_epoch": group["epoch"],
                "coefficient_codes": list(group["coefficients"]),
                "inclusive_product_sums": group["inclusive_sums"],
                "strict_product_sums": group["strict_sums"],
                "equality_counts": group["equality_counts"],
                "equality_product_sums": group["equality_product_sums"],
                "observed_gate_masks": group["mask_evidence"],
                "observed_extractor_sums": list(extractor[key]) if key in extractor else None,
                "status": status,
            }
        )
    pooled_blocks: list[dict[str, Any]] = []
    for (block, stage), observed_sums in sorted(pooled_extractor.items()):
        keys = [(channel, block, stage) for channel in range(4)]
        if any(key not in groups for key in keys):
            raise TraceFormatError(
                f"pooled block {block} stage {stage} lacks one or more channel records"
            )
        values = [groups[key] for key in keys]
        if len(
            {
                (value["epoch"], value["coefficients"], value["thresholds"])
                for value in values
            }
        ) != 1:
            raise TraceFormatError(
                f"pooled block {block} stage {stage} has different coefficient states"
            )
        inclusive = [sum(value["inclusive_sums"][j] for value in values) for j in range(4)]
        strict = [sum(value["strict_sums"][j] for value in values) for j in range(4)]
        if tuple(inclusive) == observed_sums and tuple(strict) == observed_sums:
            status = "both_candidates_match"
        elif tuple(inclusive) == observed_sums:
            status = "inclusive_candidate_matches"
        elif tuple(strict) == observed_sums:
            status = "strict_candidate_matches"
        else:
            status = "neither_candidate_matches"
        pooled_blocks.append(
            {
                "block_id": block,
                "stage": stage,
                "conversion_count": sum(value["count"] for value in values),
                "coefficient_epoch": values[0]["epoch"],
                "coefficient_codes": list(values[0]["coefficients"]),
                "inclusive_product_sums": inclusive,
                "strict_product_sums": strict,
                "observed_extractor_sums": list(observed_sums),
                "status": status,
            }
        )
    return {
        "audit": "fixed_coefficient_digital_extraction_v1",
        "sample_count": len(samples),
        "four_way_phase_checked": phase_check,
        "blocks": result_blocks,
        "pooled_blocks": pooled_blocks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path, help="JSON digital trace document")
    args = parser.parse_args()
    document = json.loads(args.trace.read_text(encoding="utf-8"))
    result = audit_trace(_mapping(document, "trace"))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
