"""The trace audit must fail closed on missing alignment or moving coefficients."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from adc_research.evaluation.digital_extraction_trace import (
    TraceFormatError,
    audit_trace,
)


FIXTURE = Path(__file__).with_name("fixtures") / "digital_extraction_trace_candidate_v1.json"


def _fixture() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _block(result: dict, channel: int, stage: int) -> dict:
    return next(
        row
        for row in result["blocks"]
        if row["channel_id"] == channel and row["stage"] == stage
    )


class DigitalExtractionTraceTests(unittest.TestCase):
    def test_equality_selects_inclusive_candidate_only_when_observed(self) -> None:
        result = audit_trace(_fixture())
        stage1 = _block(result, 0, 1)
        self.assertEqual(stage1["inclusive_product_sums"], [1, 2, 0, 0])
        self.assertEqual(stage1["strict_product_sums"], [1, 0, 0, 0])
        self.assertEqual(stage1["equality_product_sums"], [2, 0, 0])
        self.assertEqual(stage1["status"], "inclusive_candidate_matches")
        self.assertEqual(_block(result, 0, 2)["status"], "both_candidates_match")
        self.assertEqual(_block(result, 1, 1)["status"], "unverified")

    def test_strict_and_neither_are_reported_without_relabeling_chip(self) -> None:
        trace = _fixture()
        del trace["samples"][0]["stage1"]["gate_mask"]
        del trace["samples"][4]["stage1"]["gate_mask"]
        trace["extractor"][0]["product_sums"] = [1, 0, 0, 0]
        self.assertEqual(
            _block(audit_trace(trace), 0, 1)["status"],
            "strict_candidate_matches",
        )
        trace["extractor"][0]["product_sums"] = [99, 0, 0, 0]
        self.assertEqual(
            _block(audit_trace(trace), 0, 1)["status"],
            "neither_candidate_matches",
        )

    def test_misaligned_dither_rejected(self) -> None:
        trace = _fixture()
        trace["samples"][0]["stage1"]["dither_conversion_index"] = 1
        with self.assertRaisesRegex(TraceFormatError, "not aligned"):
            audit_trace(trace)

    def test_coefficient_change_within_claimed_block_rejected(self) -> None:
        trace = _fixture()
        trace["samples"][4]["stage1"]["coefficient_epoch"] = 1
        with self.assertRaisesRegex(TraceFormatError, "frozen-block audit is inapplicable"):
            audit_trace(trace)
        trace = _fixture()
        trace["samples"][4]["stage1"]["coefficient_codes"][3] = 2
        with self.assertRaisesRegex(TraceFormatError, "frozen-block audit is inapplicable"):
            audit_trace(trace)

    def test_serial_phase_or_missing_conversion_rejected(self) -> None:
        trace = _fixture()
        trace["samples"][4]["channel_id"] = 1
        with self.assertRaisesRegex(TraceFormatError, "serial phase|multiple serial phases"):
            audit_trace(trace)
        trace = _fixture()
        trace["samples"].pop(3)
        with self.assertRaisesRegex(TraceFormatError, "contains gaps"):
            audit_trace(trace)
        trace = _fixture()
        trace["samples"] = trace["samples"][:3]
        trace["metadata"].pop("expected_block_size")
        with self.assertRaisesRegex(TraceFormatError, "all four serial phases"):
            audit_trace(trace)

    def test_four_channel_pool_requires_complete_shared_state(self) -> None:
        trace = _fixture()
        trace["extractor"].append(
            {"channel_id": "all", "block_id": 0, "stage": 1, "product_sums": [1, 2, 0, 0]}
        )
        pooled = audit_trace(trace)["pooled_blocks"]
        self.assertEqual(len(pooled), 1)
        self.assertEqual(pooled[0]["conversion_count"], 8)
        self.assertEqual(pooled[0]["status"], "inclusive_candidate_matches")
        trace["samples"][1]["stage1"]["coefficient_epoch"] = 1
        trace["samples"][5]["stage1"]["coefficient_epoch"] = 1
        with self.assertRaisesRegex(TraceFormatError, "different coefficient states"):
            audit_trace(trace)
        trace = _fixture()
        trace["extractor"].append(
            {"channel_id": "all", "block_id": 0, "stage": 1, "product_sums": [1, 2, 0, 0]}
        )
        trace["samples"][3]["block_id"] = 1
        trace["samples"][7]["block_id"] = 1
        with self.assertRaisesRegex(TraceFormatError, "lacks one or more channel records"):
            audit_trace(trace)


if __name__ == "__main__":
    unittest.main()
