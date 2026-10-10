"""Frozen protocol: shared-bank merge, commit and broadcast sensitivity."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, replace
import json
from pathlib import Path

from adc_research.calibration.fixed_commit_broadcast import CommitBroadcastState, correct_commit_broadcast_window
from adc_research.calibration.fixed_four_lane_window import FourLaneConversion, FixedFourLaneWindowConfig
from adc_research.calibration.observation import DigitalCalibrationSample
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial
from experiments.exp_039_four_lane_dynamic_loop.run import code, coefficients
from experiments.exp_049_normal_start_closed_loop.run import ROOT, digest, write, frozen_codes, score
from experiments.exp_052_objective_alignment.run import analyze_window

PROTOCOL = Path(__file__).with_name("protocol.json")


def probe(samples, targets, event, cfg):
    """Offline immediate front-step probe at the actual learning version."""
    old = event.learning_state
    values = tuple(a+d for a, d in zip(old.stage1.accumulator_codes, event.applied[0], strict=True))
    if any(a < 0 or a > cfg.stage1_lms.maximum_accumulator_code for a in values):
        return {"invalid": True, "reason": "applied master increment leaves visible front domain"}
    new = replace(old, stage1=replace(old.stage1, accumulator_codes=values))
    result = analyze_window(samples, targets, coefficients(old, cfg), coefficients(new, cfg),
                            {"applied_deltas": [list(d) for d in event.applied]}, cfg)
    result["invalid"] = False
    return result


def compact_probes(windows):
    probes = [p for w in windows for p in w["probes"]]
    valid = [p for p in probes if not p["invalid"]]
    directions = Counter(p["direction_q22"] for p in valid)
    sse = Counter("up" if p["integer_sse_change_codes_squared"] > 0 else
                  "down" if p["integer_sse_change_codes_squared"] < 0 else "same" for p in valid)
    return {"probes": len(probes), "invalid": len(probes)-len(valid),
            "directions_q22": dict(directions), "integer_immediate_probe": dict(sse),
            "adverse_fraction": directions["adverse"]/len(valid) if valid else None}


def run_method(samples, targets, method, tone, protocol, reference):
    cfg = _config()
    initial = _initial(cfg)
    state = CommitBroadcastState(initial, initial)
    config = FixedFourLaneWindowConfig(cfg, selection="point_products")
    windows, online_codes = [], []
    endpoint = None
    width, train = protocol["window_size"], protocol["training_windows"]
    for w in range(protocol["windows"]):
        start = w*width
        batch, ideals = samples[start:start+width], targets[start:start+width]
        before = state
        result = correct_commit_broadcast_window(tuple(FourLaneConversion(start+i, (start+i) % 4, s)
                    for i, s in enumerate(batch)), state, config, method)
        state = result.state
        outputs = tuple(code(c) for c in result.calibrations)
        if method == "merged_boundary":
            saved = reference["windows"][w]
            assert coefficients(before.master, cfg) == saved["coefficients_before"]
            assert coefficients(state.master, cfg) == saved["coefficients_after"]
            assert list(result.commits[0].requested[0]) == saved["stage1_requested_deltas"]
            assert list(result.commits[0].requested[1]) == saved["stage2_requested_deltas"]
        probes = [probe(batch, ideals, e, cfg) for e in result.commits]
        windows.append({"window": w, "master_before": coefficients(before.master, cfg),
            "visible_before": coefficients(before.visible, cfg), "master_after": coefficients(state.master, cfg),
            "visible_after": coefficients(state.visible, cfg), "commits": [asdict(e) for e in result.commits],
            "probes": probes, "integer_codes": outputs,
            "integer_sse": sum((a-b)**2 for a, b in zip(outputs, ideals, strict=True))})
        if w+1 == train:
            endpoint = state
        if w >= train:
            online_codes.extend(outputs)
    assert endpoint is not None
    if method == "merged_boundary":
        assert online_codes == reference["online_sine_codes"]
    sine, ideal_sine = samples[train*width:], targets[train*width:]
    online = score(online_codes, ideal_sine, tone)
    unit = score(frozen_codes(sine, initial, cfg), ideal_sine, tone)
    frozen_visible = score(frozen_codes(sine, endpoint.visible, cfg), ideal_sine, tone)
    frozen_master = score(frozen_codes(sine, endpoint.master, cfg), ideal_sine, tone)
    events = [e for w in windows for e in w["commits"]]
    clipped = sum(a != b for e in events for a_stage, b_stage in zip(e["requested"], e["applied"])
                  for a, b in zip(a_stage, b_stage))
    summary = {"method": method, "online_sine": online, "unit_sine": unit,
        "frozen_visible_sine": frozen_visible, "frozen_master_sine": frozen_master,
        "online_minus_unit_sndr_db": online["sndr_db"]-unit["sndr_db"],
        "online_minus_frozen_visible_sndr_db": online["sndr_db"]-frozen_visible["sndr_db"],
        "training_master": coefficients(endpoint.master, cfg), "training_visible": coefficients(endpoint.visible, cfg),
        "final_master": coefficients(state.master, cfg), "final_visible": coefficients(state.visible, cfg),
        "clipped_coordinates": clipped, "commits": len(events), "selected_samples": sum(len(e["selected_conversion_ids"]) for e in events),
        "training_probes": compact_probes(windows[:train]), "sine_probes": compact_probes(windows[train:])}
    return summary, {"summary": summary, "windows": windows, "online_sine_codes": online_codes}


def run(output):
    output.relative_to(ROOT/"artifacts/runs/EXP_054")
    output.mkdir(parents=True, exist_ok=False)
    protocol_bytes = PROTOCOL.read_bytes()
    protocol = json.loads(protocol_bytes)
    (output/"protocol.json").write_bytes(protocol_bytes)
    source = ROOT/protocol["source"]
    prior = json.loads((source/"summary.json").read_text(encoding="utf-8"))
    paths = [PROTOCOL, Path(__file__), Path(__file__).with_name("verify.py"),
        ROOT/"src/adc_research/calibration/fixed_commit_broadcast.py", source/"summary.json",
        ROOT/"src/adc_research/calibration/fixed_four_lane_window.py",
        ROOT/"src/adc_research/calibration/fixed_adaptive_two_stage.py",
        ROOT/"src/adc_research/calibration/fixed_gated_lms.py", ROOT/"src/adc_research/calibration/fixed_pwl.py"]
    paths += sorted((ROOT/"rtl/gu_baseline").rglob("*.sv"))
    fingerprints = {str(p): digest(p) for p in paths}
    cases = []
    source_protocol = json.loads((source/"protocol.json").read_text(encoding="utf-8"))
    assert digest(source/"protocol.json") == prior["protocol_sha256"]
    for case in prior["cases"]:
        name = case["name"]
        record_path = source/name/"analog_digital_records.jsonl"
        assert digest(record_path) == case["record_sha256"]
        records = [json.loads(line) for line in record_path.open(encoding="utf-8")]
        assert len(records) == protocol["windows"]*protocol["window_size"]
        assert all(r["conversion_id"] == i for i, r in enumerate(records))
        # Strip all analog fields before invoking any online candidate.
        samples = tuple(DigitalCalibrationSample(**r["sample"]) for r in records)
        targets = tuple(r["ideal_code_offline_only"] for r in records)
        reference_path = source/name/"fixed.json"
        original = next(m for m in case["methods"] if m["method"] == "fixed")
        assert digest(reference_path) == original["artifact_sha256"]
        reference = json.loads(reference_path.read_text(encoding="utf-8"))
        trial = next(t for t in source_protocol["trials"] if t["id"] == case["trial"])
        tone = trial[case["input_name"]+"_tone"]
        methods = []
        for method in protocol["methods"]:
            summary, detail = run_method(samples, targets, method, tone, protocol, reference)
            path = output/(name+"__"+method+".json")
            write(path, detail)
            methods.append({**summary, "artifact_sha256": digest(path)})
            print(f"{name}/{method}: online {summary['online_sine']['sndr_db']:.4f} dB; adverse {summary['sine_probes']['adverse_fraction']:.3f}", flush=True)
        cases.append({"name": name, "trial": case["trial"], "input_name": case["input_name"],
            "record_sha256": case["record_sha256"], "reference_sha256": digest(reference_path), "tone": tone,
            "physical_overloads": sum(r["physical_overload"] for r in records), "methods": methods})
    totals = []
    for method in protocol["methods"]:
        outcomes = [next(m for m in c["methods"] if m["method"] == method) for c in cases]
        gains = [m["online_sine"]["sndr_db"]-c["methods"][0]["online_sine"]["sndr_db"] for c, m in zip(cases, outcomes)]
        totals.append({"method": method, "mean_gain_over_merged_db": sum(gains)/len(gains),
            "minimum_gain_db": min(gains), "maximum_gain_db": max(gains), "positive_cells": sum(g > 0 for g in gains),
            "above_unit_cells": sum(m["online_minus_unit_sndr_db"] > 0 for m in outcomes),
            "mean_gain_over_unit_db": sum(m["online_minus_unit_sndr_db"] for m in outcomes)/len(outcomes),
            "clipped_coordinates": sum(m["clipped_coordinates"] for m in outcomes),
            "sine_probe_count": sum(m["sine_probes"]["probes"] for m in outcomes),
            "sine_adverse_count": sum(m["sine_probes"]["directions_q22"].get("adverse", 0) for m in outcomes),
            "invalid_probes": sum(m[phase]["invalid"] for m in outcomes for phase in ("training_probes", "sine_probes"))})
    for path, expected in fingerprints.items():
        assert digest(Path(path)) == expected
    assert PROTOCOL.read_bytes() == protocol_bytes and len(cases) == protocol["cells"]
    summary = {"protocol_sha256": digest(PROTOCOL), "source_sha256": fingerprints,
        "cases": cases, "totals": totals, "new_analog_conversions": 0,
        "new_digital_paths": 72, "existing_merged_paths_replayed": 24,
        "original_gu_core_changed": False, "rtl_changed": False, "cadence_used": False}
    write(output/"summary.json", summary)
    print(json.dumps(totals), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output.resolve())
