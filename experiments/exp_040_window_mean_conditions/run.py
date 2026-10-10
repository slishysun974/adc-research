"""Read-only analytic mean/margin audit of every EXP-039 full-window state."""

from __future__ import annotations

import argparse
from dataclasses import replace
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

from adc_research.calibration.fixed_adaptive_two_stage import cascade_from_fixed_state
from adc_research.calibration.fixed_gated_lms import adaptive_lower_thresholds_scaled
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.theory.window_mean_map import (
    MeanGeometry, analyze_window_mean, certify_mean_cell, certify_q3_mean_error, exact_matrix_rank,
    mean_update_infinity_bound, phase_product_means,
)
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial


ROOT = Path(__file__).resolve().parents[2]


def plain(value):
    if isinstance(value, F):
        return str(value)
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    return value


def write(path, value):
    path.write_text(json.dumps(plain(value), indent=2, allow_nan=False), encoding="utf-8")


def slopes(snapshot):
    return tuple(F(x, 1024) for x in (*snapshot["stage2"], *snapshot["stage1"]))


def sign(value):
    return (value > 0)-(value < 0)


def audit_window(samples, trajectory, cfg, geometry):
    before = slopes(trajectory["coefficients_before"])
    after = slopes(trajectory["coefficients_after"])
    result = analyze_window_mean(samples, before, geometry)
    q3_certificate = certify_q3_mean_error(result)
    point_means = phase_product_means(result)
    assert tuple(sum((p[i] for p in point_means), F(0))/30 for i in range(8)) == result.mean_products
    variance = tuple(sum(((p[i]-result.mean_products[i])**2 for p in point_means), F(0))/30 for i in range(8))
    radius = max(abs(a-b) for a, b in zip(before, after))
    actual_cell = certify_mean_cell(result, radius)
    one_lsb_cell = certify_mean_cell(result, F(1, 1024))
    changed = analyze_window_mean(samples, after, geometry)
    delta = tuple(a-b for a, b in zip(after, before))
    predicted = tuple(mean+sum((entry*change for entry, change in zip(row, delta)), F(0))
                      for mean, row in zip(result.mean_products, result.fixed_mask_jacobian))
    residual = tuple(abs(a-b) for a, b in zip(changed.mean_products, predicted))
    if actual_cell.all_masks_and_domains_stable:
        assert all(error <= bound for error, bound in zip(residual, actual_cell.taylor_remainder_bounds))
    actual_gate_changes = [sum(a != b for r, s in zip(result.rows, changed.rows)
                              for a, b in zip(getattr(r, bank), getattr(s, bank)))
                           for bank in ("gates2", "gates1")]
    actual_selector_changes = sum(a.selector1 != b.selector1 for a, b in zip(result.rows, changed.rows))

    initial = _initial(cfg)
    snapshot = trajectory["coefficients_before"]
    state = replace(initial,
        stage2=replace(initial.stage2, accumulator_codes=tuple(snapshot["stage2_q22"])),
        stage1=replace(initial.stage1, accumulator_codes=tuple(snapshot["stage1_q22"])))
    dynamic = cascade_from_fixed_state(cfg.cascade, state, cfg.stage1_lms, cfg.stage2_lms)
    threshold_codes = (adaptive_lower_thresholds_scaled(snapshot["stage2"], cfg.stage2_lms),
                       adaptive_lower_thresholds_scaled(snapshot["stage1"], cfg.stage1_lms))
    fixed_phase_sums = [[0]*8 for _ in range(30)]
    protected = [0]*8
    gate_differences = [0]*8
    bounds = (F(1, 8), (1+max(before[4:]))/8)
    for n, (sample, row) in enumerate(zip(samples, result.rows)):
        calibration = correct_two_stage_fixed_observed(sample, dynamic)
        local_codes = (calibration.stage2_pwl.corrected_code_scaled-calibration.stage2_dither_scaled,
                       calibration.stage1_pwl.corrected_code_scaled-calibration.stage1_dither_scaled)
        dither_codes = (calibration.stage2_dither_scaled, calibration.stage1_dither_scaled)
        for bank in range(2):
            exact_local = (row.local2, row.local1)[bank]
            actual_local = F(local_codes[bank], 8)
            assert abs(actual_local-exact_local) <= bounds[bank]
            gates = (row.gates2, row.gates1)[bank]
            margins = (row.gate_margins2, row.gate_margins1)[bank]
            for i in range(4):
                gate = i == 0 or abs(local_codes[bank]) >= threshold_codes[bank][i]
                coordinate = 4*bank+i
                if gate:
                    fixed_phase_sums[n//4][coordinate] += dither_codes[bank]*local_codes[bank]
                gate_differences[coordinate] += int(gate != gates[i])
                if i == 0 or margins[i-1] > bounds[bank]+F(1, 16):
                    protected[coordinate] += 1
                    assert gate == gates[i]
    sums = tuple(sum(phase[i] for phase in fixed_phase_sums) for i in range(8))
    source_sums = (*trajectory["products"]["stage2"]["selected_product_sums"],
                   *trajectory["products"]["stage1"]["selected_product_sums"])
    assert sums == source_sums
    fixed_mean = tuple(F(value, 64*120) for value in sums)
    assert all(abs(actual-exact) <= bound for actual, exact, bound in zip(
        fixed_mean, result.mean_products, q3_certificate.mean_product_error_bounds))
    assert all(not preserved or actual*exact > 0 for actual, exact, preserved in zip(
        fixed_mean, result.mean_products, q3_certificate.correlation_sign_preserved))
    fixed_phase_means = tuple(tuple(F(value, 64*4) for value in phase) for phase in fixed_phase_sums)
    assert tuple(sum((phase[i] for phase in fixed_phase_means), F(0))/30 for i in range(8)) == fixed_mean
    steps = (*cfg.stage2_lms.step_sizes, *cfg.stage1_lms.step_sizes)
    def request(product, step, multiplier):
        return round_fraction(-step.numerator*multiplier*product*2**22, step.denominator*64, "nearest_even")
    full_requests = tuple(request(value, step, 1) for value, step in zip(sums, steps))
    assert full_requests == (*trajectory["products"]["stage2"]["requested_deltas"],
                             *trajectory["products"]["stage1"]["requested_deltas"])
    phase_requests = tuple(tuple(request(value, step, 30) for value, step in zip(phase, steps))
                           for phase in fixed_phase_sums)
    request_mean_error = tuple(sum((F(phase[i]) for phase in phase_requests), F(0))/30-full_requests[i]
                               for i in range(8))
    assert all(abs(value) <= 1 for value in request_mean_error)
    opposite_counts = tuple(sum(sign(phase[i]) == -sign(full_requests[i]) for phase in phase_requests)
                            if full_requests[i] else 0 for i in range(8))
    zero_mean_drift_counts = tuple(sum(phase[i] != 0 for phase in phase_requests)
                                  if not full_requests[i] else 0 for i in range(8))
    unexcited = tuple(all(not getattr(row, "gates2" if i < 4 else "gates1")[i % 4]
                         for row in result.rows) for i in range(8))
    norm_bound = mean_update_infinity_bound(result, tuple(120*step for step in steps))
    return {
        "window": trajectory["window"], "phase": trajectory["phase"],
        "analytic_mean": result.mean_products, "integer_reference_mean": fixed_mean,
        "q3_mean_product_error_bounds": q3_certificate.mean_product_error_bounds,
        "q3_correlation_sign_certified": q3_certificate.correlation_sign_preserved,
        "analytic_fixed_mask_jacobian": result.fixed_mask_jacobian,
        "open_cell_regular": result.open_cell_regular,
        "analytic_matrix_rank": exact_matrix_rank(result.fixed_mask_jacobian),
        "inactive_coordinates": [i for i, inactive in enumerate(unexcited) if inactive],
        "mean_update_infinity_norm_bound": norm_bound,
        "one_coefficient_lsb_cell_certified": one_lsb_cell.all_masks_and_domains_stable,
        "actual_exported_change_radius": radius,
        "actual_change_cell_certified": actual_cell.all_masks_and_domains_stable,
        "actual_gate_changes_stage2_stage1": actual_gate_changes,
        "actual_stage1_selector_changes": actual_selector_changes,
        "taylor_residual": residual, "conditional_taylor_bound": actual_cell.taylor_remainder_bounds,
        "quantization_gate_protected_counts": protected,
        "quantization_gate_differences": gate_differences,
        "phase_product_variance_unrounded": variance,
        "point_phase_means_integer_reference": fixed_phase_means,
        "full_requested_q22_deltas": full_requests,
        "all_phase_requested_q22_deltas": phase_requests,
        "phase_mean_request_minus_full_request_q22": request_mean_error,
        "opposite_request_phase_counts": opposite_counts,
        "zero_full_request_nonzero_phase_counts": zero_mean_drift_counts,
    }


def run(source, output):
    source_summary_path = source/"summary.json"
    original = source_summary_path.read_bytes()
    source_summary = json.loads(original)
    for name, digest in source_summary["source_sha256"].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest, name
    cfg = _config()
    geometry = MeanGeometry()
    cases = []
    for case in source_summary["cases"]:
        directory = source/case["name"]
        record_file = directory/"analog_digital_records.jsonl"
        method_file = directory/"all_products.json"
        assert hashlib.sha256(record_file.read_bytes()).hexdigest() == case["physical"]["raw_record_sha256"]
        source_method = next(m for m in case["methods"] if m["method"] == "all_products")
        assert hashlib.sha256(method_file.read_bytes()).hexdigest() == source_method["artifact_sha256"]
        samples = [DigitalCalibrationSample(**json.loads(line)["sample"])
                   for line in record_file.read_text().splitlines()]
        trajectory = json.loads(method_file.read_text())["trajectory"]
        audits = []
        for item in trajectory:
            start = item["start"]
            audits.append(audit_window(samples[start:start+120], item, cfg, geometry))
        target = output/(case["name"]+".json")
        write(target, {"state_order": "stage2[0..3],stage1[0..3]", "windows": audits})
        regular = [w for w in audits if w["open_cell_regular"]]
        compact = {"name": case["name"], "windows": len(audits), "conversions": len(samples),
            "regular_open_cells": len(regular),
            "regular_cells_rank_deficient": sum(w["analytic_matrix_rank"] < 8 for w in regular),
            "one_coefficient_lsb_certified_windows": sum(w["one_coefficient_lsb_cell_certified"] for w in audits),
            "actual_export_change_certified_windows": sum(w["actual_change_cell_certified"] for w in audits),
            "actual_gate_change_windows": sum(any(w["actual_gate_changes_stage2_stage1"]) for w in audits),
            "actual_selector_change_windows": sum(w["actual_stage1_selector_changes"] > 0 for w in audits),
            "rank_minimum": min(w["analytic_matrix_rank"] for w in audits),
            "rank_maximum": max(w["analytic_matrix_rank"] for w in audits),
            "full_eight_state_contraction_certified_windows": sum(
                w["open_cell_regular"] and w["mean_update_infinity_norm_bound"] < 1 for w in audits),
            "gate_quantization_differences": [sum(w["quantization_gate_differences"][i] for w in audits) for i in range(8)],
            "gate_quantization_protected_counts": [sum(w["quantization_gate_protected_counts"][i] for w in audits) for i in range(8)],
            "q3_correlation_sign_certified_windows": [sum(w["q3_correlation_sign_certified"][i] for w in audits) for i in range(8)],
            "full_nonzero_request_windows": [sum(w["full_requested_q22_deltas"][i] != 0 for w in audits) for i in range(8)],
            "opposite_request_phase_counts": [sum(w["opposite_request_phase_counts"][i] for w in audits) for i in range(8)],
            "phase0_opposite_request_windows": [sum(w["full_requested_q22_deltas"][i] != 0 and
                sign(w["all_phase_requested_q22_deltas"][0][i]) == -sign(w["full_requested_q22_deltas"][i])
                for w in audits) for i in range(8)],
            "max_absolute_mean_request_rounding_difference_q22": max(
                abs(v) for w in audits for v in w["phase_mean_request_minus_full_request_q22"]),
            "source_record_sha256": case["physical"]["raw_record_sha256"],
            "source_method_sha256": source_method["artifact_sha256"],
            "output_sha256": hashlib.sha256(target.read_bytes()).hexdigest()}
        cases.append(compact)
        print(json.dumps(plain(compact)), flush=True)
    assert source_summary_path.read_bytes() == original
    sources = (
        "src/adc_research/theory/window_mean_map.py",
        "experiments/exp_040_window_mean_conditions/run.py",
        "tests/test_window_mean_map.py",
        "src/adc_research/calibration/fixed_pwl.py",
        "src/adc_research/calibration/fixed_gated_lms.py",
        "src/adc_research/calibration/fixed_point.py",
    )
    summary = {"scope": "analytic finite-window mean/margin conditions on EXP-039 full-product states",
        "cadence_used": False, "online_algorithm_changed": False, "new_training_samples": 0,
        "physical_guarantee": False, "convergence_theorem_established": False,
        "state_order": "stage2[0..3],stage1[0..3]", "geometry": {k: str(v) for k, v in geometry.__dict__.items()},
        "phase_interpretation": "all 30 conditional phase replays at the same full-product path state, not the actual point-product training path",
        "source_summary_sha256": hashlib.sha256(original).hexdigest(), "source_package_unchanged": True,
        "source_sha256": {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in sources},
        "cases": cases}
    write(output/"summary.json", summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source, output = (ROOT/args.source).resolve(), (ROOT/args.output).resolve()
    source.relative_to(ROOT/"artifacts/runs/EXP_039")
    output.relative_to(ROOT/"artifacts/runs/EXP_040")
    output.mkdir(parents=True, exist_ok=True)
    run(source, output)
