"""Unit-start closed-loop attribution and predeclared synthetic holdouts."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import random

import yaml

from adc_research.calibration.fixed_adaptive_two_stage import cascade_from_fixed_state
from adc_research.calibration.fixed_four_lane_window import (
    FourLaneConversion, FixedFourLaneWindowConfig, correct_fixed_four_lane_window,
)
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.evaluation.observations import digital_sample
from adc_research.evaluation.window_trajectory_diagnostics import (
    digital_front_window, offline_front_attribution, code_error_stats,
)
from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.platform.amplifier import StaticCubicTruthConfig
from adc_research.platform.dual_path_settling import DualPathSettlingState
from adc_research.platform.pipeline import StaticPipelineNonidealities
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stage import StaticStageNonidealities
from adc_research.platform.two_phase_dual_path import TwoPhaseDualPathConfig, TwoPhasePath, process
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial
from experiments.exp_039_four_lane_dynamic_loop.run import code, coefficients

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL_PATH = Path(__file__).with_name("protocol.json")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False,
                               default=lambda x: str(x) if isinstance(x, F) else x), encoding="utf-8")


def frozen_codes(samples, state, cfg):
    cascade = cascade_from_fixed_state(cfg.cascade, state, cfg.stage1_lms, cfg.stage2_lms)
    return tuple(code(correct_two_stage_fixed_observed(s, cascade)) for s in samples)


def score(codes, targets, tone):
    stats = code_error_stats(codes, targets)
    stats = {k: float(v) if isinstance(v, F) else v for k, v in stats.items()}
    metrics = analyze_coherent_tone(codes, sample_rate_hz=3e9, fundamental_bin=tone).metrics
    stats.update(sndr_db=metrics.sndr_db, sfdr_dbc=metrics.sfdr_dbc)
    return stats


def phase_summary(windows, start_state, end_state):
    result = []
    for i in range(4):
        rows = tuple(w["front_attribution"][i] for w in windows)
        totals = {key: sum((r[key] for r in rows), F(0)) for key in (
            "target_delta_q22", "error_delta_q22", "rounding_delta_q22", "clipping_delta_q22")}
        observed = end_state.stage1.accumulator_codes[i]-start_state.stage1.accumulator_codes[i]
        assert sum(totals.values(), F(0)) == observed
        result.append({"gate_index": i, **totals, "observed_delta_q22": observed,
            "selected_gate_count": sum(r["selected_gate_count"] for r in rows),
            "zero_basis_selected_count": sum(r["zero_basis_selected_count"] for r in rows),
            "learning_opposes_error_windows": sum(r["learning_opposes_error"] for r in rows),
            "target_opposes_error_windows": sum(r["target_opposes_error"] for r in rows),
            "selection_opposes_full_windows": sum(r["selection_opposes_full"] for r in rows)})
    return {"windows": len(windows), "front": result,
        "same_window_update_mse_increased": sum(w["same_window_counterfactual"]["sse_change_all"] > 0 for w in windows),
        "same_window_update_mse_decreased": sum(w["same_window_counterfactual"]["sse_change_all"] < 0 for w in windows),
        "same_window_update_mse_unchanged": sum(w["same_window_counterfactual"]["sse_change_all"] == 0 for w in windows)}


def analyze(samples, targets, method, protocol, tone, prior=None):
    """Offline driver. The unchanged learner receives only five-field samples."""
    cfg = _config()
    state = _initial(cfg)
    initial = state
    window_size = protocol["window_size"]
    training = protocol["training_samples"]
    train_windows = training//window_size
    config = FixedFourLaneWindowConfig(cfg, selection=method)
    windows, online_codes, checkpoints = [], [], {0: state}
    minima = [1024]*4
    training_state = None
    replayed = 0
    for start in range(0, len(samples), window_size):
        batch = samples[start:start+window_size]
        ideals = targets[start:start+window_size]
        before = state
        result = correct_fixed_four_lane_window(tuple(FourLaneConversion(start+i, (start+i) % 4, s)
            for i, s in enumerate(batch)), before, config)
        state = result.state
        outputs = tuple(code(c) for c in result.calibrations)
        frame = digital_front_window(batch, result, cfg)
        evidence = offline_front_attribution(frame, ideals, result, cfg)
        after_backend = replace(before, stage2=state.stage2)
        backend_codes = frozen_codes(batch, after_backend, cfg)
        after_codes = frozen_codes(batch, state, cfg)
        sse_old = sum((a-b)**2 for a,b in zip(outputs, ideals, strict=True))
        sse_backend = sum((a-b)**2 for a,b in zip(backend_codes, ideals, strict=True))
        sse_after = sum((a-b)**2 for a,b in zip(after_codes, ideals, strict=True))
        window = start//window_size
        if prior is not None:
            old = prior["trajectory"][window]
            assert coefficients(before, cfg) == old["coefficients_before"]
            assert coefficients(state, cfg) == old["coefficients_after"]
            assert asdict(result.stage1_update) == old["products"]["stage1"] or json.loads(json.dumps(asdict(result.stage1_update))) == old["products"]["stage1"]
            assert json.loads(json.dumps(asdict(result.stage2_update))) == old["products"]["stage2"]
            assert F(sum(abs(a-b) for a,b in zip(outputs, ideals)), window_size) == F(str(old["mae_codes"])) or abs(float(F(sum(abs(a-b) for a,b in zip(outputs, ideals)), window_size))-old["mae_codes"]) < 1e-12
            replayed += 1
        minima = [min(a,b) for a,b in zip(minima, result.stage1_update.coefficient_codes_before)]
        windows.append({"window": window, "phase": "training" if start < training else "online_sine",
            "coefficients_before": coefficients(before, cfg), "coefficients_after": coefficients(state, cfg),
            "front_attribution": evidence,
            "stage2_requested_deltas": result.stage2_update.requested_deltas,
            "same_window_counterfactual": {"sse_old": sse_old, "sse_after_backend": sse_backend,
                "sse_after_all": sse_after, "sse_change_backend_first": sse_backend-sse_old,
                "sse_change_front_second": sse_after-sse_backend, "sse_change_all": sse_after-sse_old,
                "changed_integer_codes": sum(a != b for a,b in zip(outputs, after_codes))},
            "integer_error_stats": code_error_stats(outputs, ideals)})
        if start >= training:
            online_codes.extend(outputs)
        if window+1 in protocol["checkpoints_windows"]:
            checkpoints[window+1] = state
        if window+1 == train_windows:
            training_state = state
    assert training_state is not None
    if prior is not None:
        assert list(online_codes) == prior["online_sine_codes"]
    sine_samples, sine_targets = samples[training:], targets[training:]
    frozen_scores = {str(w): score(frozen_codes(sine_samples,s,cfg), sine_targets, tone)
                     for w,s in checkpoints.items()}
    online_score = score(online_codes, sine_targets, tone)
    summary = {"method": method, "normal_unit_start": True, "replayed_original_windows": replayed,
        "minimum_front_exported_codes_before": minima, "training_endpoint": coefficients(training_state,cfg),
        "final_endpoint": coefficients(state,cfg), "frozen_checkpoint_sine": frozen_scores,
        "online_sine": online_score, "training_attribution": phase_summary(windows[:train_windows], initial, training_state),
        "online_sine_attribution": phase_summary(windows[train_windows:], training_state, state),
        "frozen_sndr_gain_from_unit_db": frozen_scores[str(train_windows)]["sndr_db"]-frozen_scores["0"]["sndr_db"],
        "online_sndr_gain_from_unit_db": online_score["sndr_db"]-frozen_scores["0"]["sndr_db"]}
    return summary, {"summary": summary, "windows": windows, "online_sine_codes": online_codes}


def holdout_records(curve, inputs, history, protocol, pipeline, path):
    x_rng, d_rng = random.Random(inputs["input_seed"]), random.Random(inputs["dither_seed"])
    phases = TwoPhaseDualPathConfig(*(TwoPhasePath(a, history["tracking_factor"])
        for a in protocol["amplification_factors"]), auxiliary_truth=StaticCubicTruthConfig(*curve["auxiliary"]))
    truth = StaticPipelineNonidealities(
        stage1=StaticStageNonidealities(cubic_truth=StaticCubicTruthConfig(*curve["stage1"])),
        stage2=StaticStageNonidealities(cubic_truth=StaticCubicTruthConfig(*curve["stage2"])))
    state = DualPathSettlingState()
    samples, targets, overloads = [], [], 0
    with path.open("w", encoding="utf-8") as stream:
        for n in range(protocol["training_samples"]+protocol["sine_samples"]):
            if n < protocol["training_samples"]:
                peak = inputs["training_peak"]
                x = x_rng.uniform(-peak,peak) if inputs["distribution"] == "uniform" else x_rng.triangular(-peak,peak,0.0)
            else:
                x = inputs["sine_dc"]+inputs["sine_peak"]*math.sin(2*math.pi*inputs["tone_bin"]*(n-protocol["training_samples"])/protocol["sine_samples"])
            tags = (d_rng.choice((-1,1)),d_rng.choice((-1,1)))
            result = process(x,pipeline,phases,state,sample_index=n,dither_symbols=tags,nonidealities=truth)
            state = result.next_state
            raw = result.pipeline
            overload = (any(not s.correctable or s.main_input_overload_low or s.main_input_overload_high
                for s in (raw.stage1,raw.stage2)) or raw.backend.overload_low or raw.backend.overload_high)
            overloads += int(overload)
            sample = digital_sample(raw)
            target = min(max(math.floor((x+1)*2048),0),4095)
            samples.append(sample)
            targets.append(target)
            stream.write(json.dumps({"conversion_id":n,"input_normalized":x,"sample":asdict(sample),
                "ideal_code_offline_only":target,"tracking_starts":result.tracking_starts,
                "outputs":state.as_tuple(),"physical_overload":bool(overload)},allow_nan=False)+"\n")
    return tuple(samples), tuple(targets), overloads


def run(source, output, section):
    output.resolve().relative_to(ROOT/"artifacts/runs/EXP_049")
    output.mkdir(parents=True,exist_ok=False)
    protocol_bytes = PROTOCOL_PATH.read_bytes()
    protocol = json.loads(protocol_bytes)
    (output/"protocol.json").write_bytes(protocol_bytes)
    fingerprints, cases = {}, []
    original = json.loads((source/"summary.json").read_text())
    if section in ("prior","all"):
        fingerprints[str(source/"summary.json")] = digest(source/"summary.json")
        for name, expected in original["source_sha256"].items():
            assert digest(ROOT/name) == expected, name
            fingerprints[str(ROOT/name)] = expected
        for case in original["cases"]:
            path = source/case["name"]/"analog_digital_records.jsonl"
            assert digest(path) == case["physical"]["raw_record_sha256"]
            fingerprints[str(path)] = digest(path)
            rows = tuple(json.loads(line) for line in path.read_text().splitlines())
            samples = tuple(Sample(**r["sample"]) for r in rows)
            targets = tuple(r["ideal_code_offline_only"] for r in rows)
            compact = []
            directory = output/case["name"]
            directory.mkdir()
            for method in protocol["methods"]:
                prior_path = source/case["name"]/(method+".json")
                expected = next(m for m in case["methods"] if m["method"] == method)["artifact_sha256"]
                assert digest(prior_path) == expected
                fingerprints[str(prior_path)] = expected
                summary, detail = analyze(samples,targets,method,protocol,original["tone_bin"],json.loads(prior_path.read_text()))
                write(directory/(method+".json"),detail)
                compact.append(summary)
                print(f"prior {case['name']}/{method}: frozen gain {summary['frozen_sndr_gain_from_unit_db']:.3f} dB",flush=True)
            cases.append({"name":case["name"],"section":"prior","physical_overloads":case["physical"]["physical_overloads"],"methods":compact})
    if section in ("holdout","all"):
        pipeline = build_gu_static_hypothesis_a(yaml.safe_load((ROOT/"configs/architectures/gu_behavioral_v1.yaml").read_text()))
        for curve in protocol["curves"]:
            for inputs in protocol["inputs"]:
                for history in protocol["histories"]:
                    name = "__".join((curve["name"],inputs["name"],history["name"]))
                    directory = output/name
                    directory.mkdir()
                    path = directory/"analog_digital_records.jsonl"
                    samples,targets,overloads = holdout_records(curve,inputs,history,protocol,pipeline,path)
                    compact, failures = [], []
                    for method in protocol["methods"]:
                        try:
                            summary,detail = analyze(samples,targets,method,protocol,inputs["tone_bin"])
                        except ValueError as exc:
                            failures.append({"method":method,"error":str(exc)})
                            print(f"holdout {name}/{method}: FAILED {exc}",flush=True)
                            continue
                        write(directory/(method+".json"),detail)
                        compact.append(summary)
                        print(f"holdout {name}/{method}: frozen gain {summary['frozen_sndr_gain_from_unit_db']:.3f} dB",flush=True)
                    cases.append({"name":name,"section":"holdout","physical_overloads":overloads,
                        "record_sha256":digest(path),"methods":compact,"failures":failures})
    assert all(digest(Path(p)) == expected for p,expected in fingerprints.items())
    assert PROTOCOL_PATH.read_bytes() == protocol_bytes
    source_paths = [Path(__file__),PROTOCOL_PATH,ROOT/"src/adc_research/evaluation/window_trajectory_diagnostics.py"]
    summary = {"protocol_sha256":hashlib.sha256(protocol_bytes).hexdigest(),"section":section,"cases":cases,
        "source_evidence_sha256":fingerprints,"source_sha256":{str(p):digest(p) for p in source_paths},
        "source_package_unchanged":True,"cadence_used":False,"online_algorithm_changed":False,"rtl_changed":False,
        "spectrum_numeric_certification":False,"new_algorithm_compared":False,
        "counterfactual_scope":"same-record old/new frozen states, backend changed first; neither an actual resubmission nor a gradient claim"}
    write(output/"summary.json",summary)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source",type=Path)
    parser.add_argument("output",type=Path)
    parser.add_argument("--section",choices=("prior","holdout","all"),default="all")
    args = parser.parse_args()
    run(args.source.resolve(),args.output.resolve(),args.section)
