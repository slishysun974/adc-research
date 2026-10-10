"""Read-only paired diagnostics of selection and training-state propagation."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path

from adc_research.calibration.fixed_adaptive_two_stage import cascade_from_fixed_state, correct_and_update_fixed
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.metrics.spectral import analyze_coherent_tone
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial
from experiments.exp_039_four_lane_dynamic_loop.run import ROOT, TRAINING, TONE, code, write


def read_records(directory):
    rows = [json.loads(line) for line in (directory/"analog_digital_records.jsonl").read_text().splitlines()]
    return rows, [(row["ideal_code_offline_only"], DigitalCalibrationSample(**row["sample"])) for row in rows]


def frozen(records, endpoint, cfg):
    initial = _initial(cfg)
    state = replace(initial, stage1=replace(initial.stage1, accumulator_codes=tuple(endpoint["stage1_q22"])),
                    stage2=replace(initial.stage2, accumulator_codes=tuple(endpoint["stage2_q22"])))
    cascade = cascade_from_fixed_state(cfg.cascade, state, cfg.stage1_lms, cfg.stage2_lms)
    codes = [code(correct_two_stage_fixed_observed(sample, cascade)) for _, sample in records]
    metrics = analyze_coherent_tone(codes, sample_rate_hz=3e9, fundamental_bin=TONE).metrics
    return {"sndr_db": metrics.sndr_db, "sfdr_dbc": metrics.sfdr_dbc,
            "mae_codes": sum(abs(actual-ideal) for actual, (ideal, _) in zip(codes, records))/len(codes)}, codes


def audit(directory):
    original_summary = (directory/"summary.json").read_bytes()
    summary = json.loads(original_summary)
    for name, digest in summary["source_sha256"].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest, name
    for case in summary["cases"]:
        case_directory = directory/case["name"]
        assert hashlib.sha256((case_directory/"analog_digital_records.jsonl").read_bytes()).hexdigest() == case["physical"]["raw_record_sha256"]
        for method in case["methods"]:
            assert hashlib.sha256((case_directory/(method["method"]+".json")).read_bytes()).hexdigest() == method["artifact_sha256"]
    cfg = _config()
    diagnostics = []
    for kind in ("iid", "periodic255"):
        reset_rows, reset = read_records(directory/f"{kind}_reset")
        hold_rows, hold = read_records(directory/f"{kind}_direct_hold")
        assert len(reset) == len(hold)
        for r, h in zip(reset_rows, hold_rows):
            assert r["input_normalized"] == h["input_normalized"]
            assert r["sample"]["stage1_dither_symbol"] == h["sample"]["stage1_dither_symbol"]
            assert r["sample"]["stage2_dither_symbol"] == h["sample"]["stage2_dither_symbol"]
        changed = {"training": {}, "online_sine": {}}
        for label, start, stop in (("training", 0, TRAINING), ("online_sine", TRAINING, len(reset))):
            for field in ("stage1_symbol", "stage2_symbol", "backend_centered_code"):
                changed[label][field] = sum(getattr(r[1], field) != getattr(h[1], field)
                                           for r, h in zip(reset[start:stop], hold[start:stop]))
        matrices = []
        for method in ("all_products", "point_products"):
            endpoints = {model: json.loads((directory/f"{kind}_{model}"/(method+".json")).read_text())["training_endpoint"]
                         for model in ("reset", "direct_hold")}
            cells, codes = {}, {}
            for record_model, records in (("reset", reset), ("direct_hold", hold)):
                for coefficient_model, endpoint in endpoints.items():
                    key = f"records_{record_model}__coefficients_{coefficient_model}"
                    cells[key], codes[key] = frozen(records[TRAINING:], endpoint, cfg)
            rr = "records_reset__coefficients_reset"
            rd = "records_reset__coefficients_direct_hold"
            dr = "records_direct_hold__coefficients_reset"
            dd = "records_direct_hold__coefficients_direct_hold"
            effects = {metric: {
                "direct_record_change_at_reset_coefficients": cells[dr][metric]-cells[rr][metric],
                "coefficient_change_on_reset_records": cells[rd][metric]-cells[rr][metric],
                "interaction": cells[dd][metric]-cells[dr][metric]-cells[rd][metric]+cells[rr][metric],
                "total_diagonal_change": cells[dd][metric]-cells[rr][metric],
            } for metric in ("sndr_db", "sfdr_dbc", "mae_codes")}
            matrices.append({"method": method, "cells": cells, "effects": effects,
                             "changed_integer_codes_on_reset_records_when_only_coefficients_change":
                             sum(a != b for a, b in zip(codes[rr], codes[rd]))})
        diagnostics.append({"dither_kind": kind, "changed_digital_fields": changed,
                            "frozen_holdout_cross_matrices": matrices})
    first = json.loads((directory/"periodic255_direct_hold/all_products.json").read_text())["trajectory"][0]["products"]["stage2"]
    point = json.loads((directory/"periodic255_direct_hold/point_products.json").read_text())["trajectory"][0]["products"]["stage2"]
    rows, _ = read_records(directory/"periodic255_direct_hold")
    support = [row["conversion_id"] for row in rows[:120]
               if abs(8*row["sample"]["backend_centered_code"]-128*row["sample"]["stage2_dither_symbol"]) >= 512]
    assert len(support) == first["selected_gate_counts"][2] == 2
    assert point["selected_gate_counts"][2] == 0
    assert all(n >= 4 for n in support)
    branches = [correct_and_update_fixed(sample, _initial(cfg), cfg) for sample in (
        DigitalCalibrationSample(0, 0, 79, 1, 1), DigitalCalibrationSample(0, 1, -49, 1, 1))]
    assert all(code(branch.calibration) == 2047 for branch in branches)
    assert [branch.stage2_update.gate_mask[2] for branch in branches] == [False, True]
    assert (directory/"summary.json").read_bytes() == original_summary
    result = {
        "scope": "frozen-coefficient causal controls supplementing the online-sine comparison; not chip evidence",
        "input_summary_sha256": hashlib.sha256(original_summary).hexdigest(),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "source_file": "experiments/exp_039_four_lane_dynamic_loop/audit_cross_effects.py",
        "diagnostics": diagnostics,
        "redundant_branch_learning_counterexample": {
            "scope": "nominal candidate, exact digital words; not a measured chip",
            "system_input_normalized": "-1/2048", "stage2_main_input_normalized": "63/512",
            "auxiliary_offset_options_normalized": ["0", "1/256"],
            "stage2_symbols": [0, 1], "backend_centered_codes": [79, -49],
            "final_integer_codes": [code(branch.calibration) for branch in branches],
            "stage2_learning_outputs_q3": [branch.stage2_local_learning_output_scaled for branch in branches],
            "stage2_third_gate": [branch.stage2_update.gate_mask[2] for branch in branches],
            "stage2_third_requested_q22_deltas": [branch.stage2_update.requested_accumulator_deltas[2] for branch in branches],
        },
        "first_window_dynamic_gate_event": {
            "case": "periodic255_direct_hold", "gate": "stage2 coefficient 3",
            "active_conversion_ids": support,
            "full_product_sum": first["selected_product_sums"][2],
            "full_requested_q22_delta": first["requested_deltas"][2],
            "point_product_sum": point["selected_product_sums"][2],
            "point_requested_q22_delta": point["requested_deltas"][2],
            "selected_point_conversion_ids": [0, 1, 2, 3],
        },
    }
    write(directory/"cross_effects.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    directory = (ROOT/args.directory).resolve()
    directory.relative_to(ROOT/"artifacts/runs/EXP_039")
    audit(directory)
