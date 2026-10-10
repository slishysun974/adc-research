"""Stored-path comparison; no rerun, tuning or new observations."""

import argparse
import json
from pathlib import Path

from experiments.exp_049_normal_start_closed_loop.run import digest, write


def compare(output):
    summary = json.loads((output/"summary.json").read_text(encoding="utf-8"))
    pairs = []
    for case in summary["cases"]:
        details = {}
        for m in case["methods"]:
            p = output/(case["name"]+"__"+m["method"]+".json")
            assert digest(p) == m["artifact_sha256"]
            details[m["method"]] = json.loads(p.read_text(encoding="utf-8"))
        baseline = details["merged_boundary"]
        for method, saved in details.items():
            codes_changed = sum(a != b for wa, wb in zip(baseline["windows"], saved["windows"], strict=True)
                                for a, b in zip(wa["integer_codes"], wb["integer_codes"], strict=True))
            export_changed = sum(a != b for wa, wb in zip(baseline["windows"], saved["windows"], strict=True)
                for stage in ("stage1", "stage2") for a, b in zip(wa["master_after"][stage], wb["master_after"][stage]))
            max_acc_difference = max(abs(a-b) for wa, wb in zip(baseline["windows"], saved["windows"], strict=True)
                for stage in ("stage1_q22", "stage2_q22") for a, b in zip(wa["master_after"][stage], wb["master_after"][stage]))
            pairs.append({"case": case["name"], "method": method,
                "changed_integer_codes_all_phases": codes_changed,
                "changed_integer_codes_sine": sum(a != b for a, b in zip(baseline["online_sine_codes"], saved["online_sine_codes"], strict=True)),
                "changed_master_export_coordinates_at_boundaries": export_changed,
                "maximum_master_q22_difference_at_boundaries": max_acc_difference,
                "minimum_window_start_visible_front_first_q10": min(w["visible_before"]["stage1"][0] for w in saved["windows"]),
                "sndr_gain_over_merged_db": saved["summary"]["online_sine"]["sndr_db"]-baseline["summary"]["online_sine"]["sndr_db"]})
    totals = []
    for method in (m["method"] for m in summary["totals"]):
        rows = [p for p in pairs if p["method"] == method]
        totals.append({"method": method,
            "changed_integer_codes_all_phases": sum(r["changed_integer_codes_all_phases"] for r in rows),
            "changed_integer_codes_sine": sum(r["changed_integer_codes_sine"] for r in rows),
            "changed_master_export_coordinates_at_boundaries": sum(r["changed_master_export_coordinates_at_boundaries"] for r in rows),
            "maximum_master_q22_difference_at_boundaries": max(r["maximum_master_q22_difference_at_boundaries"] for r in rows),
            "minimum_window_start_visible_front_first_q10": min(r["minimum_window_start_visible_front_first_q10"] for r in rows)})
    paired_spreads = [max(p["sndr_gain_over_merged_db"] for p in pairs if p["case"] == c["name"])-
                      min(p["sndr_gain_over_merged_db"] for p in pairs if p["case"] == c["name"]) for c in summary["cases"]]
    below_all = [c["name"] for c in summary["cases"] if all(m["online_minus_unit_sndr_db"] < 0 for m in c["methods"])]
    result = {"summary_sha256": digest(output/"summary.json"), "comparison_source_sha256": digest(Path(__file__)),
              "totals": totals, "maximum_within_cell_sndr_spread_db": max(paired_spreads),
              "below_unit_in_all_contracts": below_all, "pairs": pairs}
    write(output/"comparison.json", result)
    print(json.dumps({"totals": totals, "maximum_within_cell_sndr_spread_db": max(paired_spreads),
                     "below_unit_in_all_contracts": len(below_all)}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    compare(parser.parse_args().output.resolve())
