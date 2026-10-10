"""Read-only objective-direction audit across existing extraction schedules."""

from __future__ import annotations

import argparse
from fractions import Fraction
import json
from pathlib import Path

from adc_research.calibration.observation import DigitalCalibrationSample
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_049_normal_start_closed_loop.run import ROOT, digest, write
from experiments.exp_052_objective_alignment.run import analyze_window, aggregate


PROTOCOL = Path(__file__).with_name("protocol.json")


def run(output: Path):
    output.relative_to(ROOT/"artifacts/runs/EXP_053")
    output.mkdir(parents=True, exist_ok=False)
    protocol_bytes = PROTOCOL.read_bytes()
    protocol = json.loads(protocol_bytes)
    (output/"protocol.json").write_bytes(protocol_bytes)
    source = ROOT/protocol["source"]
    source_summary_path = source/"summary.json"
    source_digest = digest(source_summary_path)
    prior = json.loads(source_summary_path.read_text(encoding="utf-8"))
    assert digest(source/"protocol.json") == prior["protocol_sha256"]
    assert len(prior["cases"]) == protocol["cells"]
    cfg = _config()
    cases = []
    for case in prior["cases"]:
        name = case["name"]
        record_path = source/name/"analog_digital_records.jsonl"
        assert digest(record_path) == case["record_sha256"]
        with record_path.open(encoding="utf-8") as stream:
            records = tuple(json.loads(line) for line in stream)
        assert len(records) == protocol["windows_per_method"]*protocol["samples_per_window"]
        samples = tuple(DigitalCalibrationSample(**r["sample"]) for r in records)
        targets = tuple(r["ideal_code_offline_only"] for r in records)
        outcomes = []
        for method_name in protocol["methods"]:
            method = next(m for m in case["methods"] if m["method"] == method_name)
            detail_path = source/name/(method_name+".json")
            assert digest(detail_path) == method["artifact_sha256"]
            detail = json.loads(detail_path.read_text(encoding="utf-8"))
            assert len(detail["windows"]) == protocol["windows_per_method"]
            rows = []
            for window in detail["windows"]:
                index = window["window"]
                start = index*protocol["samples_per_window"]
                stop = start+protocol["samples_per_window"]
                before, after = window["coefficients_before"], window["coefficients_after"]
                applied = ([b-a for a,b in zip(before["stage1_q22"],after["stage1_q22"],strict=True)],
                           [b-a for a,b in zip(before["stage2_q22"],after["stage2_q22"],strict=True)])
                result = analyze_window(samples[start:stop], targets[start:stop], before, after,
                                        {"applied_deltas": applied}, cfg)
                assert result["old_integer_sse_codes_squared"] == (
                    protocol["samples_per_window"]*Fraction(
                        window["integer_error_stats"]["mse_codes_squared"]))
                first = window["front_attribution"][0]
                assert first["learning_product_sum"] == window["stage1_products"][0]
                assert first["target_product_sum"]+first["error_product_sum"] == first["learning_product_sum"]
                selected = window["selected_conversion_ids"]
                assert len(selected) == (120 if method_name == "all_reference" else 4)
                if method_name != "all_reference":
                    assert selected == [start+4*window["phase"]+i for i in range(4)]
                result.update(window=index, phase="training" if index < protocol["training_windows"] else "online_sine",
                              target_product_sum_first=first["target_product_sum"],
                              error_product_sum_first=first["error_product_sum"])
                rows.append(result)
            summary = {phase: aggregate([r for r in rows if r["phase"] == phase])
                       for phase in ("training", "online_sine")}
            summary.update(method=method_name, source_detail_sha256=method["artifact_sha256"],
                           selected_samples_per_window=method["selected_samples_per_window"],
                           source_online_minus_unit_sndr_db=method["online_minus_unit_sndr_db"],
                           source_online_sndr_db=method["online_sine"]["sndr_db"],
                           source_clipped_requests=method["clipped_requested_deltas"])
            write(output/(name+"__"+method_name+".json"),
                  {"source_record_sha256": case["record_sha256"], "summary": summary, "windows": rows})
            outcomes.append(summary)
        cases.append({"name": name, "trial": case["trial"], "curve_name": case["curve_name"],
                      "input_name": case["input_name"], "history_name": case["history_name"],
                      "record_sha256": case["record_sha256"], "methods": outcomes})
        print(f"{name}: " + ", ".join(f"{m['method']} {m['online_sine']['integer_sse_change_total']:+d}"
                                     for m in outcomes), flush=True)
    totals = {}
    for method_name in protocol["methods"]:
        phase_totals = {}
        for phase in ("training", "online_sine"):
            rows = tuple(r for case in cases for r in json.loads((output/(
                case["name"]+"__"+method_name+".json")).read_text(encoding="utf-8"))["windows"]
                if r["phase"] == phase)
            phase_totals[phase] = aggregate(rows)
            values = [next(m for m in case["methods"] if m["method"] == method_name)[phase]
                      ["integer_sse_change_total"] for case in cases]
            phase_totals[phase]["cells_net_worsened"] = sum(v > 0 for v in values)
            phase_totals[phase]["cells_net_improved"] = sum(v < 0 for v in values)
            phase_totals[phase]["cells_net_unchanged"] = sum(v == 0 for v in values)
        totals[method_name] = phase_totals
    assert PROTOCOL.read_bytes() == protocol_bytes
    assert digest(source_summary_path) == source_digest
    write(output/"summary.json", {"protocol_sha256": digest(PROTOCOL),
                                  "source_summary_sha256": source_digest,
                                  "cases": cases, "totals": totals,
                                  "new_analog_conversions": 0,
                                  "new_online_training": False,
                                  "gu_chip_schedule_verified": False,
                                  "online_algorithm_changed": False,
                                  "rtl_changed": False,
                                  "cadence_used": False})
    print(json.dumps(totals), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output.resolve())
