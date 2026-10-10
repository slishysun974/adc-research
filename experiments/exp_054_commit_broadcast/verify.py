"""Independent request arithmetic, coefficient visibility and scored-code audit."""

from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction
import json
from pathlib import Path

from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.observation import DigitalCalibrationSample
from dataclasses import replace
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_049_normal_start_closed_loop.run import ROOT, digest, write, score


def nearest(value):
    """Independent rational nearest-even, including negative ties."""
    q, remainder = divmod(value.numerator, value.denominator)
    twice = 2*remainder
    return q+int(twice > value.denominator or (twice == value.denominator and q % 2 != 0))


def snapshot(state, cfg):
    result = {}
    for stage, bank_cfg in (("stage1", cfg.stage1_lms), ("stage2", cfg.stage2_lms)):
        q22 = state[stage]["accumulator_codes"]
        result[stage+"_q22"] = q22
        result[stage] = [min(max(nearest(Fraction(a, 1 << bank_cfg.guard_fractional_bits)), 0),
                             bank_cfg.coefficient_format.maximum_code) for a in q22]
    return result


def cascade(q, cfg):
    return replace(cfg.cascade,
        stage1_pwl=replace(cfg.cascade.stage1_pwl, coefficient_codes=tuple(q["stage1"])),
        stage2_pwl=replace(cfg.cascade.stage2_pwl, coefficient_codes=tuple(q["stage2"])))


def verify(output):
    summary = json.loads((output/"summary.json").read_text(encoding="utf-8"))
    protocol = json.loads((output/"protocol.json").read_text(encoding="utf-8"))
    assert digest(output/"protocol.json") == summary["protocol_sha256"]
    for path, expected in summary["source_sha256"].items():
        assert digest(Path(path)) == expected
    cfg = _config()
    source = ROOT/protocol["source"]
    windows = conversions = requests = probes = commits = 0
    for case in summary["cases"]:
        record_path = source/case["name"]/"analog_digital_records.jsonl"
        assert digest(record_path) == case["record_sha256"]
        records = [json.loads(line) for line in record_path.open(encoding="utf-8")]
        for outcome in case["methods"]:
            path = output/(case["name"]+"__"+outcome["method"]+".json")
            assert digest(path) == outcome["artifact_sha256"]
            stored = json.loads(path.read_text(encoding="utf-8"))
            assert stored["summary"] == {k: v for k, v in outcome.items() if k != "artifact_sha256"}
            old_master = old_visible = None
            sine_codes, selected_total = [], 0
            for w in stored["windows"]:
                start = w["window"]*120
                batch = records[start:start+120]
                if old_master is not None:
                    assert old_master == w["master_before"]
                    assert old_visible == w["visible_before"]
                else:
                    assert all(a == 2**22 for stage in ("stage1_q22", "stage2_q22")
                               for a in w["master_before"][stage])
                    assert w["master_before"] == w["visible_before"]
                actual_codes = []
                visible = w["visible_before"]
                current_master = w["master_before"]
                events_by_id = {e["after_conversion_id"]: e for e in w["commits"]}
                selected_ids = [n for e in w["commits"] for n in e["selected_conversion_ids"]]
                assert selected_ids == [start+i for i in range(4)]
                for row in batch:
                    cal = correct_two_stage_fixed_observed(DigitalCalibrationSample(**row["sample"]), cascade(visible, cfg))
                    actual_codes.append(min(max(nearest(Fraction(cal.unclipped_output_scaled, 8)), 0), 4095))
                    event = events_by_id.get(row["conversion_id"])
                    if event is None:
                        continue
                    learning = snapshot(event["learning_state"], cfg)
                    before = snapshot(event["master_before"], cfg)
                    after = snapshot(event["master_after"], cfg)
                    assert before == current_master and learning == visible
                    selected = [records[n] for n in event["selected_conversion_ids"]]
                    local_cals = [correct_two_stage_fixed_observed(DigitalCalibrationSample(**r["sample"]), cascade(learning, cfg))
                                  for r in selected]
                    for index, (stage, bank_cfg) in enumerate((("stage1", cfg.stage1_lms), ("stage2", cfg.stage2_lms))):
                        # Derive thresholds from exported Q10 and PWL geometry independently.
                        thresholds = [nearest(Fraction(bank_cfg.slice_width_scaled*sum(learning[stage][:i]), 1024))
                                      for i in range(4)]
                        sums, gates, rounded = [0]*4, [0]*4, [0]*4
                        for c in local_cals:
                            d = getattr(c, stage+"_dither_scaled")
                            local = getattr(c, stage+"_pwl").corrected_code_scaled-d
                            for i in range(4):
                                p = d*local if i == 0 or abs(local) >= thresholds[i] else 0
                                sums[i] += p
                                gates[i] += int(i == 0 or abs(local) >= thresholds[i])
                                rounded[i] += nearest(-bank_cfg.step_sizes[i]*30*p*2**22/64)
                        wanted = rounded if outcome["method"] == "lane_rounded_boundary" else [
                            nearest(-bank_cfg.step_sizes[i]*30*sums[i]*2**22/64) for i in range(4)]
                        assert sums == event["products"][index] and gates == event["gate_counts"][index]
                        assert wanted == event["requested"][index]
                        capped = [min(max(a+d, 0), bank_cfg.maximum_accumulator_code)
                                  for a, d in zip(before[stage+"_q22"], wanted)]
                        assert capped == after[stage+"_q22"]
                        assert [a-b for a, b in zip(capped, before[stage+"_q22"])] == event["applied"][index]
                        requests += 4
                    current_master = after
                    if outcome["method"] == "serial_immediate":
                        visible = after
                    selected_total += len(selected)
                    commits += 1
                assert actual_codes == w["integer_codes"]
                assert sum((a-r["ideal_code_offline_only"])**2 for a, r in zip(actual_codes, batch)) == w["integer_sse"]
                assert current_master == w["master_after"]
                expected_visible = w["master_before"] if outcome["method"] == "delayed_broadcast" else w["master_after"]
                assert w["visible_after"] == expected_visible
                for p, e in zip(w["probes"], w["commits"], strict=True):
                    if p["invalid"]:
                        continue
                    assert p["delta_q22"] == e["applied"][0]
                    dot = sum(a*b for a, b in zip(p["gradient_numerators"], p["delta_q22"]))
                    assert dot == p["direction_dot_q22"]
                    assert p["direction_q22"] == ("adverse" if dot > 0 else "favorable" if dot < 0 else "neutral")
                    probes += 1
                old_master, old_visible = w["master_after"], w["visible_after"]
                if w["window"] >= protocol["training_windows"]:
                    sine_codes.extend(actual_codes)
                windows += 1
                conversions += len(batch)
            assert selected_total == outcome["selected_samples"] == 640
            assert sine_codes == stored["online_sine_codes"]
            targets = [r["ideal_code_offline_only"] for r in records[128*120:]]
            assert score(sine_codes, targets, case["tone"]) == outcome["online_sine"]
            print(f"verified {case['name']}/{outcome['method']}", flush=True)
    assert windows == 24*4*160 and conversions == windows*120
    assert commits == 24*(1+1+4+1)*160 and requests == commits*8
    assert probes == commits  # No invalid immediate probes in this run.
    result = {"verified_windows": windows, "verified_digital_conversions": conversions,
        "verified_commits": commits, "verified_request_coordinates": requests,
        "verified_probe_direction_arithmetic": probes,
        "basis_gradient_independently_recomputed": False,
        "all_actual_integer_codes_recomputed": True,
        "all_visibility_and_request_arithmetic_recomputed": True,
        "protocol_sha256": summary["protocol_sha256"], "verifier_sha256": digest(Path(__file__))}
    write(output/"verification.json", result)
    print(json.dumps(result), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    verify(parser.parse_args().output.resolve())
