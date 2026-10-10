"""Exact constrained correlation roots, gate consistency, and fixed-root checks."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, is_dataclass, replace
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

from adc_research.calibration.fixed_adaptive_two_stage import cascade_from_fixed_state
from adc_research.calibration.fixed_gated_lms import exported_coefficient_codes
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.theory.gated_correlation_roots import (
    WeightedStageRow, scan_two_slope_roots, stage_basis, stage_correlations,
)
from adc_research.theory.constrained_mean_root import certify_low4_root, weighted_cascade_mean
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial


ROOT = Path(__file__).resolve().parents[2]
FIT = 96*120
TRAINING_END = 128*120
PARTITIONS = {"fit": (0, FIT), "training_suffix": (FIT, TRAINING_END),
              "online_sine": (TRAINING_END, 160*120)}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plain(value):
    if is_dataclass(value):
        return plain(asdict(value))
    if isinstance(value, F):
        return str(value)
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(x) for x in value]
    return value


def write(path, value):
    path.write_text(json.dumps(plain(value), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def histogram(samples):
    return tuple(Counter(samples).items())


def stage_rows(samples, stage, k2=None):
    counts = Counter()
    for sample in samples:
        if stage == 2:
            raw, dither = F(sample.backend_centered_code), F(16*sample.stage2_dither_symbol)
        else:
            raw2 = F(sample.backend_centered_code)
            local2 = sum((k*b for k, b in zip(k2, stage_basis(raw2, F(32)))), F(0))-16*sample.stage2_dither_symbol
            raw, dither = 128*sample.stage2_symbol+local2, F(64*sample.stage1_dither_symbol)
        counts[(raw, dither)] += 1
    return tuple(WeightedStageRow(raw, dither, count) for (raw, dither), count in sorted(counts.items()))


def check_scan(scan, rows, width):
    """Check the saved partition's zero exclusion and selected direct values."""
    for cell in scan.cells:
        if cell.correlation_slope:
            root = -cell.correlation_intercept/cell.correlation_slope
            assert not cell.low < root < cell.high or any(r.parameter == root for r in scan.roots)
        else:
            assert cell.correlation_intercept != 0 or (cell.low, cell.high) in scan.zero_intervals
    for root in scan.roots:
        assert stage_correlations(rows, root.coefficients, width)[:2] == (F(0), F(0))
    # Direct checks at all jumps that cross zero; bracketing would be unsafe here.
    checks = [b for b in scan.boundaries if b.left_limit*b.right_limit < 0]
    for boundary in checks:
        coefficients = tuple(p*boundary.parameter+q for p, q in zip(
            scan.coefficient_line_slopes, scan.coefficient_line_intercepts))+(F(1),)*2
        assert stage_correlations(rows, coefficients, width)[:2] == (F(0), boundary.value)
    return {"complete": scan.complete_on_declared_domain, "status": scan.status,
            "cells": len(scan.cells), "boundaries": len(scan.boundaries), "isolated_roots": len(scan.roots),
            "zero_intervals": len(scan.zero_intervals),
            "sign_crossing_jumps_without_zero": sum(b.value != 0 for b in checks),
            "crossing_jump_checks": checks}


def quantized_reference(slopes, cfg):
    initial = _initial(cfg)
    accumulators = tuple(round_fraction(x.numerator*2**22, x.denominator, "nearest_even") for x in slopes)
    state = replace(initial, stage2=replace(initial.stage2, accumulator_codes=accumulators[:4]),
                    stage1=replace(initial.stage1, accumulator_codes=accumulators[4:]))
    cascade = cascade_from_fixed_state(cfg.cascade, state, cfg.stage1_lms, cfg.stage2_lms)
    codes = (*exported_coefficient_codes(state.stage2, cfg.stage2_lms),
             *exported_coefficient_codes(state.stage1, cfg.stage1_lms))
    return state, cascade, tuple(F(x, 1024) for x in codes)


def fixed_correlation_mean(samples, cascade, cfg):
    # Thresholds use the same exported codes as the fixed corrector.
    k2 = cascade.stage2_pwl.coefficient_codes
    k1 = cascade.stage1_pwl.coefficient_codes
    from adc_research.calibration.fixed_gated_lms import adaptive_lower_thresholds_scaled
    thresholds = (adaptive_lower_thresholds_scaled(k2, cfg.stage2_lms),
                  adaptive_lower_thresholds_scaled(k1, cfg.stage1_lms))
    sums = [0]*8
    for sample, count in histogram(samples):
        result = correct_two_stage_fixed_observed(sample, cascade)
        outputs = (result.stage2_pwl.corrected_code_scaled-result.stage2_dither_scaled,
                   result.stage1_pwl.corrected_code_scaled-result.stage1_dither_scaled)
        dithers = (result.stage2_dither_scaled, result.stage1_dither_scaled)
        for bank in range(2):
            for i in range(4):
                if i == 0 or abs(outputs[bank]) >= thresholds[bank][i]:
                    sums[4*bank+i] += count*dithers[bank]*outputs[bank]
    return tuple(F(value, 64*len(samples)) for value in sums)


def offline_score(samples, ideals, cascade, *, spectrum=False):
    outputs = []
    clips = 0
    for sample in samples:
        result = correct_two_stage_fixed_observed(sample, cascade)
        value = round_fraction(result.unclipped_output_scaled, 8, "nearest_even")
        clips += int(value < 0 or value > 4095)
        outputs.append(min(max(value, 0), 4095))
    errors = [abs(actual-ideal) for actual, ideal in zip(outputs, ideals, strict=True)]
    result = {"mae_codes": F(sum(errors), len(errors)), "maximum_error_codes": max(errors),
              "final_code_clip_count": clips}
    if spectrum:
        metrics = analyze_coherent_tone(outputs, sample_rate_hz=3e9, fundamental_bin=67).metrics
        result["spectrum_float"] = {"sndr_db": metrics.sndr_db, "sfdr_dbc": metrics.sfdr_dbc}
    return result


def offline_front_target_identity(samples, ideals, mean):
    """Separate ideal-residue correlation from error correlation, offline only.

    The ideal integer target is never passed into the root solver or the
    digital mean calculation. Gate selection is that of this fixed root.
    """
    lookup = {sample: row for (sample, count), row in zip(histogram(samples), mean.base.rows)}
    signal, error = [F(0)]*4, [F(0)]*4
    for sample, ideal in zip(samples, ideals, strict=True):
        row = lookup[sample]
        target = F(ideal-2048-512*sample.stage1_symbol)
        for i in range(4):
            if row.gates1[i]:
                signal[i] += row.dither1*target
                error[i] += row.dither1*(row.local1-target)
    signal, error = tuple(x/len(samples) for x in signal), tuple(x/len(samples) for x in error)
    assert tuple(a+b for a,b in zip(signal,error)) == mean.mean_products[4:]
    return {"ideal_local_code_definition": "ideal_integer_code-2048-512*stage1_symbol",
            "target_signal_correlations": signal, "continuous_error_correlations": error,
            "sum_equals_front_learning_correlations": True}


def run(source, output):
    output.mkdir(parents=True, exist_ok=False)
    originals = {}
    summary = json.loads((source/"summary.json").read_text())
    originals[source/"summary.json"] = digest(source/"summary.json")
    for name, expected in summary["source_sha256"].items():
        assert digest(ROOT/name) == expected, name
        originals[ROOT/name] = expected
    cfg = _config()
    steps = tuple(120*x for x in (*cfg.stage2_lms.step_sizes, *cfg.stage1_lms.step_sizes))
    cases = []
    for case in summary["cases"]:
        name = case["name"]
        path = source/name/"analog_digital_records.jsonl"
        expected = case["physical"]["raw_record_sha256"]
        assert digest(path) == expected
        originals[path] = expected
        lines = [json.loads(line) for line in path.read_text().splitlines()]
        samples = tuple(Sample(**row["sample"]) for row in lines)
        # Offline targets are passed only to the separate scoring function.
        ideals = tuple(row["ideal_code_offline_only"] for row in lines)
        fitting = samples[:FIT]
        rows2 = stage_rows(fitting, 2)
        scan2 = scan_two_slope_roots(rows2, 32)
        brief2 = check_scan(scan2, rows2, 32)
        stage1_scans, candidates = [], []
        complete = scan2.complete_on_declared_domain and not scan2.zero_intervals
        for back_index, root2 in enumerate(scan2.roots):
            rows1 = stage_rows(fitting, 1, root2.coefficients)
            scan1 = scan_two_slope_roots(rows1, 128)
            brief1 = check_scan(scan1, rows1, 128)
            complete &= scan1.complete_on_declared_domain and not scan1.zero_intervals
            stage1_scans.append({"backend_root": back_index, "summary": brief1, "scan": scan1})
            for front_index, root1 in enumerate(scan1.roots):
                coefficients = (*root2.coefficients, *root1.coefficients)
                mean = weighted_cascade_mean(histogram(fitting), coefficients)
                assert all(mean.mean_products[i] == 0 for i in (0, 1, 4, 5))
                stability = certify_low4_root(mean, steps)
                state, cascade, exported = quantized_reference(coefficients, cfg)
                partitions = {}
                for label, (start, end) in PARTITIONS.items():
                    record = samples[start:end]
                    continuous = weighted_cascade_mean(histogram(record), coefficients)
                    integer_mean = fixed_correlation_mean(record, cascade, cfg)
                    requests = tuple(round_fraction((-step*value*2**22).numerator,
                                                    (-step*value*2**22).denominator, "nearest_even")
                                     for step, value in zip(steps, integer_mean))
                    partitions[label] = {"continuous_mean_products": continuous.mean_products,
                        "integer_mean_products": integer_mean,
                        "virtual_120_conversion_q22_request": requests,
                        "offline_front_target_identity": offline_front_target_identity(record, ideals[start:end], continuous),
                        "offline_quantized_root_score": offline_score(record, ideals[start:end], cascade,
                                                                       spectrum=label == "online_sine")}
                candidates.append({"backend_root": back_index, "front_root": front_index,
                    "coefficients": coefficients, "at_low_gate_boundary": root2.at_gate_boundary or root1.at_gate_boundary,
                    "all_eight_fit_correlations": mean.mean_products,
                    "stability": stability, "nearest_q22_accumulators": (*state.stage2.accumulator_codes, *state.stage1.accumulator_codes),
                    "exported_q1_10_coefficients": exported,
                    "actual_export_distance_to_root": max(abs(a-b) for a,b in zip(exported, coefficients)),
                    "partitions": partitions})
        _, unit_cascade, _ = quantized_reference((F(1),)*8, cfg)
        unit_scores = {label: offline_score(samples[start:end], ideals[start:end], unit_cascade,
                                          spectrum=label == "online_sine")
                       for label, (start, end) in PARTITIONS.items()}
        target = output/(name+".json")
        write(target, {"stage2_summary": brief2, "stage2_scan": scan2, "stage1_scans": stage1_scans,
                       "full_low4_search_complete": complete, "candidates": candidates,
                       "unit_coefficient_offline_scores": unit_scores})
        compact = {"name": name, "stage2": brief2,
            "stage1": [item["summary"] for item in stage1_scans],
            "full_low4_search_complete": complete, "two_stage_root_candidates": len(candidates),
            "full_eight_correlations_zero_candidates": sum(c["stability"]["frozen_correlations_exactly_zero"] for c in candidates),
            "frozen_gates_closed_candidates": sum(c["stability"]["frozen_gates_all_closed"] for c in candidates),
            "uniform_clamped_contraction_candidates": sum(c["stability"]["constrained_empirical_map_locally_contracts"] for c in candidates),
            "gu_empirical_invariant_box_candidates": sum(c["stability"]["full_gu_empirical_map_has_same_invariant_box"] for c in candidates),
            "coefficient_export_half_lsb_fits_candidates": sum(c["stability"]["coefficient_export_half_lsb_fits_box"] for c in candidates),
            "output_sha256": digest(target)}
        cases.append(compact)
        print(json.dumps({k: v for k, v in compact.items() if k not in ("stage2", "stage1", "output_sha256")}), flush=True)
    for path, expected in originals.items():
        assert digest(path) == expected, path
    sources = ("src/adc_research/theory/gated_correlation_roots.py",
        "src/adc_research/theory/constrained_mean_root.py", "src/adc_research/theory/window_mean_map.py",
        "src/adc_research/theory/window_excitation.py", "experiments/exp_042_correlation_roots/run.py",
        "tests/test_gated_correlation_roots.py", "tests/test_constrained_mean_root.py",
        "src/adc_research/calibration/fixed_point.py",
        "src/adc_research/calibration/fixed_pwl.py", "src/adc_research/calibration/fixed_gated_lms.py",
        "src/adc_research/calibration/fixed_adaptive_two_stage.py",
        "experiments/exp_032_online_lms_rtl/generate_vectors.py", "experiments/exp_033_fixed_online_box/run.py")
    write(output/"summary.json", {"scope": "exact constrained finite-record roots, gate jumps, uniform clamped mean neighborhoods",
        "state_order": "stage2[0..3],stage1[0..3]", "fixed_coordinates": {"2": "1", "3": "1", "6": "1", "7": "1"},
        "coefficient_domain": "0<each slope<2", "partitions": PARTITIONS,
        "holdout_scope": "suffix and sine excluded from this root solve; previously inspected by earlier experiments",
        "virtual_integer_request_scope": "120 times pooled fixed mean; not an actual 120-row update or integer equilibrium proof",
        "step_per_window": steps, "cadence_used": False, "online_algorithm_changed": False,
        "new_training_samples": 0, "physical_guarantee": False, "q22_algorithm_convergence_certified": False,
        "source_package_unchanged": True, "source_summary_sha256": originals[source/"summary.json"],
        "source_sha256": {name: digest(ROOT/name) for name in sources}, "cases": cases})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    source, output = ((ROOT/p).resolve() for p in (args.source, args.output))
    source.relative_to(ROOT/"artifacts/runs/EXP_039")
    output.relative_to(ROOT/"artifacts/runs/EXP_042")
    run(source, output)
