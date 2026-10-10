"""Independent stored-state and source-request audit for EXP-053."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from experiments.exp_049_normal_start_closed_loop.run import ROOT, digest, write


def verify(output: Path):
    summary = json.loads((output/"summary.json").read_text(encoding="utf-8"))
    protocol = json.loads((output/"protocol.json").read_text(encoding="utf-8"))
    assert digest(output/"protocol.json") == summary["protocol_sha256"]
    source = ROOT/protocol["source"]
    assert digest(source/"summary.json") == summary["source_summary_sha256"]
    prior = json.loads((source/"summary.json").read_text(encoding="utf-8"))
    assert len(summary["cases"]) == len(prior["cases"]) == protocol["cells"]
    requests = windows = conversions = 0
    for case, original in zip(summary["cases"], prior["cases"], strict=True):
        assert case["name"] == original["name"]
        assert digest(source/case["name"]/"analog_digital_records.jsonl") == case["record_sha256"]
        for outcome in case["methods"]:
            method = outcome["method"]
            source_detail_path = source/case["name"]/(method+".json")
            stored_path = output/(case["name"]+"__"+method+".json")
            assert digest(source_detail_path) == outcome["source_detail_sha256"]
            source_detail = json.loads(source_detail_path.read_text(encoding="utf-8"))
            stored = json.loads(stored_path.read_text(encoding="utf-8"))
            assert stored["summary"] == outcome
            assert outcome["source_clipped_requests"] == 0
            assert len(stored["windows"]) == len(source_detail["windows"]) == protocol["windows_per_method"]
            for actual, saved in zip(stored["windows"], source_detail["windows"], strict=True):
                before, after = saved["coefficients_before"], saved["coefficients_after"]
                assert actual["window"] == saved["window"]
                for stage in ("stage1", "stage2"):
                    request = saved[stage+"_requested_deltas"]
                    change = [b-a for a,b in zip(before[stage+"_q22"], after[stage+"_q22"], strict=True)]
                    assert request == change
                    requests += 4
                assert actual["delta_q22"] == saved["stage1_requested_deltas"]
                windows += 1
                conversions += protocol["samples_per_window"]
    result = {"protocol_sha256": summary["protocol_sha256"],
              "source_summary_sha256": summary["source_summary_sha256"],
              "run_source_sha256": digest(Path(__file__).with_name("run.py")),
              "verified_windows": windows, "verified_digital_conversions": conversions,
              "verified_requested_coordinates": requests,
              "all_source_requests_unclipped": True}
    assert windows == 24*4*160
    write(output/"verification.json", result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    verify(parser.parse_args().output.resolve())
