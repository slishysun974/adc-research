"""Paired shared-window Gu candidates with two-phase synthetic analog history."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import random

import yaml

from adc_research.calibration.fixed_adaptive_two_stage import correct_and_update_fixed
from adc_research.calibration.fixed_four_lane_window import (
    FourLaneConversion, FixedFourLaneWindowConfig, correct_fixed_four_lane_window,
)
from adc_research.calibration.fixed_gated_lms import exported_coefficient_codes
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.evaluation.observations import digital_sample
from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.platform.amplifier import StaticCubicTruthConfig
from adc_research.platform.dual_path_settling import DualPathSettlingState
from adc_research.platform.pipeline import StaticPipelineNonidealities
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stage import StaticStageNonidealities
from adc_research.platform.two_phase_dual_path import TwoPhaseDualPathConfig, TwoPhasePath, process
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial


ROOT = Path(__file__).resolve().parents[2]
WINDOW = 120
TRAINING = 15360
HOLDOUT = 3840
TONE = 67
PERIOD = 255
METHODS = ("sequential", "all_products", "point_products")


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def code(calibration):
    return min(max(round_fraction(calibration.unclipped_output_scaled, 8, "nearest_even"), 0), 4095)


def coefficients(state, cfg):
    return {"stage1": list(exported_coefficient_codes(state.stage1, cfg.stage1_lms)),
            "stage2": list(exported_coefficient_codes(state.stage2, cfg.stage2_lms)),
            "stage1_q22": list(state.stage1.accumulator_codes),
            "stage2_q22": list(state.stage2.accumulator_codes)}


def inputs_and_tags(kind):
    x_rng, d_rng = random.Random(20261009), random.Random(20261010)
    periods = []
    for stage in range(2):
        signs = [1]*127+[-1]*128
        random.Random(20261040+stage).shuffle(signs)
        assert all(any(signs[n] != signs[(n+d) % PERIOD] for n in range(PERIOD))
                   for d in (1, 3, 5, 15, 17, 51, 85))
        periods.append(signs)
    rows = []
    for n in range(TRAINING+HOLDOUT):
        x = x_rng.uniform(-0.82, 0.82) if n < TRAINING else (
            0.82*math.sin(2*math.pi*TONE*(n-TRAINING)/HOLDOUT))
        dither = tuple(periods[stage][n % PERIOD] if kind == "periodic255" else
                       d_rng.choice((-1, 1)) for stage in range(2))
        rows.append((x, dither))
    return rows


def analog_records(kind, tracking, pipeline, output):
    phases = TwoPhaseDualPathConfig(TwoPhasePath(0.001, tracking), TwoPhasePath(0.03, tracking),
                                    TwoPhasePath(0.001, tracking), auxiliary_gain=4.0,
                                    auxiliary_truth=StaticCubicTruthConfig(1.0, 0.02))
    truth = StaticPipelineNonidealities(
        stage1=StaticStageNonidealities(cubic_truth=StaticCubicTruthConfig(0.98, -0.06)),
        stage2=StaticStageNonidealities(cubic_truth=StaticCubicTruthConfig(0.97, -0.05)),
    )
    state = DualPathSettlingState()
    records, overloads = [], 0
    path = output / "analog_digital_records.jsonl"
    with path.open("w", encoding="utf-8") as stream:
        for n, (x, dither) in enumerate(inputs_and_tags(kind)):
            result = process(x, pipeline, phases, state, sample_index=n,
                             dither_symbols=dither, nonidealities=truth)
            state = result.next_state
            raw = result.pipeline
            overload = (any(not stage.correctable or stage.main_input_overload_low or
                            stage.main_input_overload_high for stage in (raw.stage1, raw.stage2)) or
                        raw.backend.overload_low or raw.backend.overload_high)
            overloads += int(overload)
            sample = digital_sample(raw)
            ideal = min(max(math.floor((x+1)*2048), 0), 4095)
            records.append((ideal, sample))
            stream.write(json.dumps({"conversion_id": n, "input_normalized": x,
                "sample": asdict(sample), "ideal_code_offline_only": ideal,
                "tracking_starts": result.tracking_starts, "targets": result.static_targets,
                "outputs": state.as_tuple(), "auxiliary_output": result.auxiliary_output,
                "physical_overload": bool(overload)}, allow_nan=False)+"\n")
    assert overloads == 0, "the predeclared synthetic domain produced physical overload"
    return records, {"physical_overloads": overloads,
        "memory_factors": [phases.stage1_main.memory_factor,
                           phases.stage1_auxiliary.memory_factor, phases.stage2_main.memory_factor],
        "raw_record_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def run_method(records, method, cfg):
    state = _initial(cfg)
    trajectory, train_errors, test_codes = [], [], []
    config = None if method == "sequential" else FixedFourLaneWindowConfig(cfg, selection=method)
    commits = clips = 0
    training_endpoint = None
    for start in range(0, len(records), WINDOW):
        batch = records[start:start+WINDOW]
        before = coefficients(state, cfg)
        if method == "sequential":
            outputs = []
            for _, sample in batch:
                result = correct_and_update_fixed(sample, state, cfg)
                state = result.state
                outputs.append(code(result.calibration))
                commits += 1
                clips += sum(a != b for update in (result.stage1_update, result.stage2_update)
                             for a, b in zip(update.requested_accumulator_deltas, update.applied_accumulator_deltas))
            products = None
        else:
            result = correct_fixed_four_lane_window(tuple(
                FourLaneConversion(start+i, (start+i) % 4, sample) for i, (_, sample) in enumerate(batch)
            ), state, config)
            state = result.state
            outputs = [code(calibration) for calibration in result.calibrations]
            commits += 1
            clips += sum(a != b for update in (result.stage1_update, result.stage2_update)
                         for a, b in zip(update.requested_deltas, update.applied_deltas))
            products = {"stage1": asdict(result.stage1_update), "stage2": asdict(result.stage2_update)}
        errors = [abs(actual-ideal) for actual, (ideal, _) in zip(outputs, batch)]
        if start < TRAINING:
            train_errors.extend(errors)
        else:
            test_codes.extend(outputs)
        trajectory.append({"window": start//WINDOW, "start": start, "end": start+WINDOW-1,
                           "phase": "training" if start < TRAINING else "online_sine",
                           "coefficients_before": before, "coefficients_after": coefficients(state, cfg),
                           "mae_codes": sum(errors)/WINDOW,
                           "maximum_error_codes": max(errors), "products": products})
        if start+WINDOW == TRAINING:
            training_endpoint = coefficients(state, cfg)
    metrics = analyze_coherent_tone(test_codes, sample_rate_hz=3e9, fundamental_bin=TONE,
                                    full_scale_peak=2048).metrics
    test_errors = [abs(actual-ideal) for actual, (ideal, _) in zip(test_codes, records[TRAINING:])]
    return {
        "method": method, "training_mae_codes": sum(train_errors)/len(train_errors),
        "training_endpoint": training_endpoint, "final_endpoint": coefficients(state, cfg),
        "online_sine_mae_codes": sum(test_errors)/len(test_errors),
        "online_sine_maximum_error_codes": max(test_errors),
        "online_sine_metrics_approximate": asdict(metrics),
        "commit_count_training_and_online_sine": commits,
        "clipped_requested_coefficient_deltas": clips,
        "online_sine_codes": test_codes, "trajectory": trajectory,
    }


def alias_counterexample(cfg):
    rows = tuple(FourLaneConversion(n, n % 4,
        DigitalCalibrationSample(0, 0, 64*d1+16*d2+8, d1, d2))
        for n in range(WINDOW) for d1, d2 in [(-1 if n % 2 == 0 else 1, 1 if n < 60 else -1)])
    results = {method: correct_fixed_four_lane_window(rows, _initial(cfg),
               FixedFourLaneWindowConfig(cfg, selection=method)) for method in METHODS[1:]}
    assert results["all_products"].calibrations == results["point_products"].calibrations
    assert results["all_products"].stage2_update.requested_deltas[0] == 0
    assert results["point_products"].stage2_update.requested_deltas[0] == -3932
    return {"scope": "synthetic valid digital words, not a measured circuit or PRNG",
            "old_state_output_codes_equal": True,
            "all_products_stage2_update": asdict(results["all_products"].stage2_update),
            "point_products_stage2_update": asdict(results["point_products"].stage2_update)}


def tag_audit(records):
    selected = [sample for n, (_, sample) in enumerate(records[:TRAINING]) if (n % WINDOW)//4 == 0]
    full = [sample for _, sample in records[:TRAINING]]
    return {"training_conversions": len(full), "selected_conversion_count": len(selected),
        "full_dither_means": [str(F(sum(getattr(s, f"stage{i}_dither_symbol") for s in full), len(full))) for i in (1, 2)],
        "selected_dither_means": [str(F(sum(getattr(s, f"stage{i}_dither_symbol") for s in selected), len(selected))) for i in (1, 2)],
        "periodic255_selected_phases_across_four_lanes": len({n % PERIOD for n in range(TRAINING) if (n % WINDOW)//4 == 0})}


def run(output):
    architecture = ROOT/"configs/architectures/gu_behavioral_v1.yaml"
    pipeline = build_gu_static_hypothesis_a(yaml.safe_load(architecture.read_text()))
    cfg = _config()
    write(output/"digital_alias_counterexample.json", alias_counterexample(cfg))
    cases = []
    for kind in ("iid", "periodic255"):
        for phase_name, tracking in (("reset", 0.0), ("two_phase", 0.1), ("direct_hold", 1.0)):
            name = f"{kind}_{phase_name}"
            directory = output/name
            directory.mkdir(parents=True, exist_ok=True)
            records, physical = analog_records(kind, tracking, pipeline, directory)
            print(f"Generated {name}: {len(records)} conversions, {physical['physical_overloads']} overloads", flush=True)
            results = []
            for method in METHODS:
                result = run_method(records, method, cfg)
                write(directory/f"{method}.json", result)
                compact = {k: v for k, v in result.items() if k not in ("trajectory", "online_sine_codes")}
                compact["artifact_sha256"] = hashlib.sha256((directory/f"{method}.json").read_bytes()).hexdigest()
                results.append(compact)
                print(f"{name}/{method}: SNDR={compact['online_sine_metrics_approximate']['sndr_db']:.6f}, "
                      f"SFDR={compact['online_sine_metrics_approximate']['sfdr_dbc']:.6f}", flush=True)
            cases.append({"name": name, "dither_kind": kind, "tracking_factor_assumed": tracking,
                          "physical": physical, "tag_audit": tag_audit(records), "methods": results})
    sources = (
        "src/adc_research/calibration/fixed_four_lane_window.py",
        "src/adc_research/platform/two_phase_dual_path.py",
        "src/adc_research/calibration/fixed_adaptive_two_stage.py",
        "src/adc_research/calibration/fixed_gated_lms.py",
        "src/adc_research/calibration/fixed_pwl.py",
        "src/adc_research/calibration/fixed_point.py",
        "src/adc_research/platform/stage.py", "src/adc_research/platform/amplifier.py",
        "src/adc_research/platform/quantizer.py", "src/adc_research/platform/backend_sar.py",
        "src/adc_research/platform/reconstruct.py", "src/adc_research/platform/presets.py",
        "src/adc_research/evaluation/observations.py", "src/adc_research/metrics/spectral.py",
        "experiments/exp_032_online_lms_rtl/generate_vectors.py",
        "experiments/exp_033_fixed_online_box/run.py",
        "experiments/exp_039_four_lane_dynamic_loop/run.py",
        "tests/test_fixed_four_lane_window.py", "tests/test_two_phase_dual_path.py",
        "configs/architectures/gu_behavioral_v1.yaml",
    )
    summary = {
        "scope": "synthetic two-phase analog history and declared shared Q22 four-lane window contracts",
        "cadence_used": False, "chip_timing_verified": False, "physical_guarantee": False,
        "training_samples": TRAINING, "online_sine_samples": HOLDOUT, "tone_bin": TONE,
        "training_input": "fixed-seed uniform [-0.82,0.82]", "sine_peak": 0.82,
        "window_conversions": WINDOW, "lane_period": 30, "point_phase": 0,
        "state_contract": "old coefficients score/gate all samples; shared banks commit once after complete window",
        "update_scale": "full mu*sum(120 products); point 30*mu*sum(4 products); round and saturate once",
        "source_numeric_note": "floating synthetic voltages and spectral scoring; integer digital update arithmetic",
        "analog_truth": {"stage1": [0.98, -0.06], "stage2": [0.97, -0.05], "auxiliary": [1.0, 0.02]},
        "amplification_factors_assumed": [0.001, 0.03, 0.001],
        "periodic_source": "two fixed shuffled sign tables of exact period 255, 127 positive and 128 negative signs; not claimed chip PRNG",
        "seeds": {"inputs": 20261009, "iid_dither": 20261010, "periodic_tables": [20261040, 20261041]},
        "methods": list(METHODS), "cases": cases,
        "source_sha256": {s: hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources},
    }
    write(output/"summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = (ROOT/args.output).resolve()
    output.relative_to(ROOT/"artifacts/runs/EXP_039")
    output.mkdir(parents=True, exist_ok=True)
    run(output)


if __name__ == "__main__":
    main()
