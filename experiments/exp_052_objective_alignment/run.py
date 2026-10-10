"""Offline digital-basis direction audit of existing normal-start Gu windows."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from fractions import Fraction
import json
from pathlib import Path

from adc_research.calibration.fixed_pwl import correct_fixed, correct_two_stage_fixed_observed
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.observation import DigitalCalibrationSample
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_049_normal_start_closed_loop.run import ROOT, digest, write


PROTOCOL = Path(__file__).with_name("protocol.json")


def code_from_scaled(scaled: int) -> int:
    return min(max(round_fraction(scaled, 8, "nearest_even"), 0), 4095)


def basis(result, width: int) -> tuple[int, ...]:
    """Signed PWL basis in Q3 raw-code units per unit slope."""
    part = result.stage1_pwl
    return tuple(part.sign * (width if i < part.slice_index else
                              part.local_code_scaled if i == part.slice_index else 0)
                 for i in range(4))


def direction(value: int) -> str:
    return "favorable" if value < 0 else "adverse" if value > 0 else "neutral"


def analyze_window(samples, targets, old, new, update, cfg):
    old_q, new_q = old["stage1"], new["stage1"]
    old_pwl = replace(cfg.cascade.stage1_pwl, coefficient_codes=tuple(old_q))
    new_pwl = replace(cfg.cascade.stage1_pwl, coefficient_codes=tuple(new_q))
    cascade = replace(cfg.cascade, stage1_pwl=old_pwl,
                      stage2_pwl=replace(cfg.cascade.stage2_pwl,
                                         coefficient_codes=tuple(old["stage2"])))
    dq10 = tuple(b-a for a, b in zip(old_q, new_q, strict=True))
    dq22 = tuple(new["stage1_q22"][i]-old["stage1_q22"][i] for i in range(4))
    assert list(dq22) == update["applied_deltas"][0]
    grad = [0]*4
    old_sse = new_sse = 0
    old_q3_sse = new_q3_sse = 0
    continuous_delta_numer = 0
    model_old_sse = model_new_sse = 0
    changed_codes = 0
    for sample, target in zip(samples, targets, strict=True):
        result = correct_two_stage_fixed_observed(sample, cascade)
        b = basis(result, old_pwl.slice_width_scaled)
        constant = result.unclipped_output_scaled-result.stage1_pwl.corrected_code_scaled
        residual_numer = 1024*(constant-8*target)+sum(x*q for x, q in zip(b, old_q, strict=True))
        step_numer = sum(x*q for x, q in zip(b, dq10, strict=True))
        continuous_delta_numer += 2*residual_numer*step_numer+step_numer**2
        model_old_sse += residual_numer**2
        model_new_sse += (residual_numer+step_numer)**2
        for i in range(4):
            grad[i] += residual_numer*b[i]
        before_code = code_from_scaled(result.unclipped_output_scaled)
        revised = correct_fixed(result.stage1_raw_scaled, new_pwl)
        after_scaled = result.unclipped_output_scaled + revised.corrected_code_scaled-result.stage1_pwl.corrected_code_scaled
        after_code = code_from_scaled(after_scaled)
        old_sse += (before_code-target)**2
        new_sse += (after_code-target)**2
        old_q3_sse += (result.unclipped_output_scaled-8*target)**2
        new_q3_sse += (after_scaled-8*target)**2
        changed_codes += before_code != after_code
    # Directly verify the continuous affine-model identity at this finite window.
    assert continuous_delta_numer == model_new_sse-model_old_sse
    dot_q22 = sum(grad[i]*dq22[i] for i in range(4))
    dot_q10 = sum(grad[i]*dq10[i] for i in range(4))
    return {
        "direction_q22": direction(dot_q22),
        "direction_exported_q10": direction(dot_q10),
        "coordinate_directions_q22": [direction(grad[i]*dq22[i]) for i in range(4)],
        "coordinate_directions_q10": [direction(grad[i]*dq10[i]) for i in range(4)],
        "direction_dot_q22": dot_q22,
        "direction_dot_q10": dot_q10,
        "gradient_numerators": grad,
        "delta_q22": dq22,
        "delta_q10": dq10,
        "continuous_sse_change_codes_squared": continuous_delta_numer/(1024**2*8**2),
        "q3_sse_change_codes_squared": (new_q3_sse-old_q3_sse)/64,
        "integer_sse_change_codes_squared": new_sse-old_sse,
        "old_integer_sse_codes_squared": old_sse,
        "new_integer_sse_codes_squared": new_sse,
        "changed_integer_codes": changed_codes,
    }


def aggregate(rows):
    joint = Counter(r["direction_q22"] for r in rows)
    exported = Counter(r["direction_exported_q10"] for r in rows)
    integer = Counter("improved" if r["integer_sse_change_codes_squared"] < 0 else
                      "worsened" if r["integer_sse_change_codes_squared"] > 0 else "unchanged"
                      for r in rows)
    cross = Counter((r["direction_q22"],
                     "target_dominant" if abs(r["target_product_sum_first"]) >
                     abs(r["error_product_sum_first"]) else "error_or_tie")
                    for r in rows)
    return {
        "windows": len(rows), "joint_q22_direction": dict(joint),
        "exported_q10_direction": dict(exported), "integer_same_window": dict(integer),
        "coordinate_q22_direction": [dict(Counter(r["coordinate_directions_q22"][i] for r in rows))
                                      for i in range(4)],
        "integer_sse_change_total": sum(r["integer_sse_change_codes_squared"] for r in rows),
        "continuous_sse_change_total": sum(r["continuous_sse_change_codes_squared"] for r in rows),
        "q3_sse_change_total": sum(r["q3_sse_change_codes_squared"] for r in rows),
        "changed_integer_codes": sum(r["changed_integer_codes"] for r in rows),
        "first_target_dominance_by_joint_direction": {f"{a}|{b}": n for (a,b),n in cross.items()},
    }


def run(output: Path):
    output.relative_to(ROOT/"artifacts/runs/EXP_052")
    output.mkdir(parents=True, exist_ok=False)
    protocol_bytes = PROTOCOL.read_bytes()
    protocol = json.loads(protocol_bytes)
    (output/"protocol.json").write_bytes(protocol_bytes)
    source = ROOT/protocol["source"]
    source_summary = source/"summary.json"
    source_digest = digest(source_summary)
    prior = json.loads(source_summary.read_text(encoding="utf-8"))
    assert digest(source/"protocol.json") == prior["protocol_sha256"]
    cfg = _config()
    cases = []
    for case in prior["cases"]:
        name = case["name"]
        record_path = source/name/"analog_digital_records.jsonl"
        method = next(m for m in case["methods"] if m["method"] == "baseline")
        detail_path = source/name/"baseline.json"
        assert digest(record_path) == case["record_sha256"]
        assert digest(detail_path) == method["artifact_sha256"]
        detail = json.loads(detail_path.read_text(encoding="utf-8"))
        records = (json.loads(line) for line in record_path.open(encoding="utf-8"))
        rows = []
        for window in detail["windows"]:
            batch = tuple(next(records) for _ in range(120))
            assert all(r["conversion_id"] == window["window"]*120+i for i,r in enumerate(batch))
            samples = tuple(DigitalCalibrationSample(**r["sample"]) for r in batch)
            targets = tuple(r["ideal_code_offline_only"] for r in batch)
            result = analyze_window(samples, targets, window["coefficients_before"],
                                    window["coefficients_after"], window, cfg)
            assert result["old_integer_sse_codes_squared"] == 120*Fraction(
                window["integer_error_stats"]["mse_codes_squared"])
            first = window["front_attribution"][0]
            result.update(window=window["window"], phase="training" if window["window"] < 128 else "online_sine",
                          target_product_sum_first=first["target_product_sum"],
                          error_product_sum_first=first["error_product_sum"])
            assert first["target_product_sum"]+first["error_product_sum"] == window["stage1_products"][0]
            rows.append(result)
        assert len(rows) == protocol["windows_per_cell"]
        try:
            next(records)
        except StopIteration:
            pass
        else:
            raise AssertionError("unexpected extra source conversions")
        compact = {phase: aggregate([r for r in rows if r["phase"] == phase])
                   for phase in ("training", "online_sine")}
        cases.append({"name": name, "trial": case["trial"], "curve_name": case["curve_name"],
                      "input_name": case["input_name"], "history_name": case["history_name"],
                      "summary": compact})
        write(output/(name+".json"), {"source_record_sha256": case["record_sha256"],
                                      "source_detail_sha256": method["artifact_sha256"],
                                      "summary": compact, "windows": rows})
        print(f"{name}: sine {compact['online_sine']['joint_q22_direction']}", flush=True)
    assert len(cases) == 24
    totals = {phase: aggregate([r for case in cases for r in json.loads(
        (output/(case["name"]+".json")).read_text(encoding="utf-8"))["windows"]
        if r["phase"] == phase]) for phase in ("training", "online_sine")}
    assert PROTOCOL.read_bytes() == protocol_bytes
    assert digest(source_summary) == source_digest
    summary = {"protocol_sha256": digest(PROTOCOL), "source_summary_sha256": source_digest,
               "cases": cases, "totals": totals, "new_analog_conversions": 0,
               "online_algorithm_changed": False, "rtl_changed": False, "cadence_used": False}
    write(output/"summary.json", summary)
    print(json.dumps(totals), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    run(parser.parse_args().output.resolve())
