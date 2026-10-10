"""Prespecified four-point phase selection with fresh-seed online ADC tests."""

import argparse
from fractions import Fraction as F
import json
from pathlib import Path

import yaml

from adc_research.calibration.fixed_four_lane_window import (
    FourLaneConversion, FixedFourLaneWindowConfig, correct_fixed_four_lane_window,
)
from adc_research.calibration.window_phase_selection import WindowPhaseSchedule
from adc_research.evaluation.window_trajectory_diagnostics import (
    digital_front_window, offline_front_attribution, code_error_stats,
)
from adc_research.platform.presets import build_gu_static_hypothesis_a
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial
from experiments.exp_039_four_lane_dynamic_loop.run import code, coefficients
from experiments.exp_049_normal_start_closed_loop.run import (
    ROOT, digest, write, frozen_codes, score, holdout_records,
)

PROTOCOL = Path(__file__).with_name("protocol.json")


def attribution_summary(windows, before, after):
    totals = []
    for i in range(4):
        rows = [w["front_attribution"][i] for w in windows]
        parts = {k:sum((r[k] for r in rows),F(0)) for k in (
            "target_delta_q22","error_delta_q22","rounding_delta_q22","clipping_delta_q22")}
        observed = after.stage1.accumulator_codes[i]-before.stage1.accumulator_codes[i]
        assert sum(parts.values(),F(0)) == observed
        target_deltas = [r["target_delta_q22"]/2**22 for r in rows]
        mean = sum(target_deltas,F(0))/len(rows)
        variance = sum(((d-mean)**2 for d in target_deltas),F(0))/len(rows)
        totals.append({"gate_index":i,**parts,"observed_delta_q22":observed,
            "target_delta_mean_slope":float(mean),"target_delta_variance_slope":float(variance),
            "selected_gate_count":sum(r["selected_gate_count"] for r in rows),
            "zero_basis_selected_count":sum(r["zero_basis_selected_count"] for r in rows),
            "learning_opposes_error_windows":sum(r["learning_opposes_error"] for r in rows),
            "selection_opposes_full_windows":sum(r["selection_opposes_full"] for r in rows)})
    return totals


def run_method(samples, targets, method, seed, protocol, tone):
    cfg = _config()
    state = _initial(cfg)
    initial = state
    schedule = None if method == "all_reference" else WindowPhaseSchedule(method,seed if method == "xorshift32" else 0)
    trajectory, online_codes = [], []
    training = protocol["training_samples"]
    width = protocol["window_size"]
    endpoint = None
    clips, histogram, test_histogram = 0,[0]*30,[0]*30
    for start in range(0,len(samples),width):
        batch, ideals = samples[start:start+width],targets[start:start+width]
        before = state
        phase = 0 if schedule is None else schedule.phase
        config = FixedFourLaneWindowConfig(cfg,selection="all_products" if schedule is None else "point_products",point_phase=phase)
        result = correct_fixed_four_lane_window(tuple(FourLaneConversion(start+i,(start+i) % 4,s)
            for i,s in enumerate(batch)),before,config)
        state = result.state
        outputs = [code(c) for c in result.calibrations]
        frame = digital_front_window(batch,result,cfg)
        attribution = offline_front_attribution(frame,ideals,result,cfg)
        for update in (result.stage1_update,result.stage2_update):
            clips += sum(a != b for a,b in zip(update.requested_deltas,update.applied_deltas,strict=True))
        if schedule is not None:
            assert len(result.selected_conversion_ids) == 4
            assert result.selected_conversion_ids == tuple(start+4*phase+i for i in range(4))
            histogram[phase] += 1
            if start >= training:
                test_histogram[phase] += 1
        trajectory.append({"window":start//width,"phase":phase,
            "selection_state_before":None if schedule is None else schedule.state,
            "coefficients_before":coefficients(before,cfg),"coefficients_after":coefficients(state,cfg),
            "front_attribution":attribution,"selected_conversion_ids":result.selected_conversion_ids,
            "stage1_products":result.stage1_update.selected_product_sums,
            "stage2_products":result.stage2_update.selected_product_sums,
            "stage1_requested_deltas":result.stage1_update.requested_deltas,
            "stage2_requested_deltas":result.stage2_update.requested_deltas,
            "integer_error_stats":code_error_stats(outputs,ideals)})
        if start+width == training:
            endpoint = state
        if start >= training:
            online_codes.extend(outputs)
        if schedule is not None:
            schedule = schedule.advance()
    assert endpoint is not None
    train_windows = training//width
    sine_samples,sine_targets = samples[training:],targets[training:]
    unit = score(frozen_codes(sine_samples,initial,cfg),sine_targets,tone)
    frozen = score(frozen_codes(sine_samples,endpoint,cfg),sine_targets,tone)
    online = score(online_codes,sine_targets,tone)
    before_codes = [w["coefficients_before"] for w in trajectory[train_windows:]]
    interface_spans = {stage:[max(w[stage][i] for w in before_codes)-min(w[stage][i] for w in before_codes)
                            for i in range(4)] for stage in ("stage1","stage2")}
    summary = {"method":method,"training_endpoint":coefficients(endpoint,cfg),"final_endpoint":coefficients(state,cfg),
        "unit_sine":unit,"frozen_endpoint_sine":frozen,"online_sine":online,
        "online_minus_frozen_sndr_db":online["sndr_db"]-frozen["sndr_db"],
        "online_minus_unit_sndr_db":online["sndr_db"]-unit["sndr_db"],
        "clipped_requested_deltas":clips,"commits":len(trajectory),
        "selected_samples_per_window":120 if schedule is None else 4,
        "phase_histogram":histogram,"sine_phase_histogram":test_histogram,
        "sine_phase_coverage":sum(n != 0 for n in test_histogram),
        "sine_coefficient_interface_spans_q10":interface_spans,
        "training_attribution":attribution_summary(trajectory[:train_windows],initial,endpoint),
        "sine_attribution":attribution_summary(trajectory[train_windows:],endpoint,state)}
    return summary,{"summary":summary,"windows":trajectory,"online_sine_codes":online_codes}


def paired_summary(cases):
    comparisons = []
    for method in ("rotate","xorshift32"):
        pairs = []
        for case in cases:
            fixed = next((m for m in case["methods"] if m["method"] == "fixed"),None)
            candidate = next((m for m in case["methods"] if m["method"] == method),None)
            if fixed is None or candidate is None:
                continue
            gain = candidate["online_sine"]["sndr_db"]-fixed["online_sine"]["sndr_db"]
            pairs.append({"case":case["name"],"trial":case["trial"],"input":case["input_name"],
                "sndr_gain_db":gain,"mse_change_codes_squared":candidate["online_sine"]["mse_codes_squared"]-fixed["online_sine"]["mse_codes_squared"],
                "front_first_target_variance_ratio":candidate["sine_attribution"][0]["target_delta_variance_slope"]/fixed["sine_attribution"][0]["target_delta_variance_slope"]
                    if fixed["sine_attribution"][0]["target_delta_variance_slope"] else None})
        gains = [p["sndr_gain_db"] for p in pairs]
        mean = sum(gains)/len(gains) if gains else None
        positives = sum(g > 0 for g in gains)
        supported = len(gains) == 24 and mean > 0 and positives >= 18 and min(gains) >= -3
        comparisons.append({"method":method,"paired_cells":len(pairs),"mean_online_sndr_gain_db":mean,
            "positive_cells":positives,"negative_cells":sum(g < 0 for g in gains),
            "minimum_gain_db":min(gains) if gains else None,"maximum_gain_db":max(gains) if gains else None,
            "prespecified_screen_passed":supported,"pairs":pairs})
    return comparisons


def run(output):
    output.relative_to(ROOT/"artifacts/runs/EXP_050")
    output.mkdir(parents=True,exist_ok=False)
    protocol_bytes = PROTOCOL.read_bytes()
    protocol = json.loads(protocol_bytes)
    (output/"protocol.json").write_bytes(protocol_bytes)
    prior_path = ROOT/"artifacts/runs/EXP_049/closed_loop_v1/summary.json"
    prior = json.loads(prior_path.read_text())
    fingerprints = {**prior["source_sha256"],**prior["source_evidence_sha256"],str(prior_path):digest(prior_path)}
    own_sources = [Path(__file__),PROTOCOL,ROOT/"src/adc_research/calibration/window_phase_selection.py"]
    fingerprints.update({str(p):digest(p) for p in own_sources})
    for p,expected in fingerprints.items():
        assert digest(Path(p)) == expected,p
    pipeline = build_gu_static_hypothesis_a(yaml.safe_load((ROOT/"configs/architectures/gu_behavioral_v1.yaml").read_text()))
    cases = []
    for trial in protocol["trials"]:
        for curve in protocol["curves"]:
            for base_input in protocol["inputs"]:
                inputs = dict(base_input)
                label = inputs["name"]
                inputs.update(input_seed=trial[label+"_input_seed"],dither_seed=trial[label+"_dither_seed"],tone_bin=trial[label+"_tone"])
                for history in protocol["histories"]:
                    name = f"t{trial['id']}__{curve['name']}__{label}__{history['name']}"
                    directory = output/name
                    directory.mkdir()
                    record_path = directory/"analog_digital_records.jsonl"
                    samples,targets,overloads = holdout_records(curve,inputs,history,protocol,pipeline,record_path)
                    compact,failures = [],[]
                    for method in protocol["methods"]:
                        try:
                            summary,detail = run_method(samples,targets,method,trial["phase_seed"],protocol,inputs["tone_bin"])
                        except ValueError as exc:
                            failures.append({"method":method,"error":str(exc)})
                            print(f"{name}/{method}: FAILED {exc}",flush=True)
                            continue
                        path = directory/(method+".json")
                        write(path,detail)
                        summary["artifact_sha256"] = digest(path)
                        compact.append(summary)
                        print(f"{name}/{method}: online {summary['online_sine']['sndr_db']:.3f}, frozen {summary['frozen_endpoint_sine']['sndr_db']:.3f} dB",flush=True)
                    cases.append({"name":name,"trial":trial["id"],"input_name":label,"curve_name":curve["name"],
                        "history_name":history["name"],"tone_bin":inputs["tone_bin"],"phase_seed":trial["phase_seed"],
                        "physical_overloads":overloads,"record_sha256":digest(record_path),"methods":compact,"failures":failures})
                    write(output/"progress.json",{"completed_cells":len(cases),"prespecified_cells":24,"cases":cases})
    for p,expected in fingerprints.items():
        assert digest(Path(p)) == expected,p
    assert PROTOCOL.read_bytes() == protocol_bytes
    summary = {"protocol_sha256":digest(PROTOCOL),"cases":cases,"paired_comparisons":paired_summary(cases),
        "source_evidence_sha256":fingerprints,"source_package_unchanged":True,
        "new_analog_conversions":sum(protocol["training_samples"]+protocol["sine_samples"] for _ in cases),
        "existing_gu_core_changed":False,"rtl_changed":False,"cadence_used":False,
        "approximate_fft":True,"chip_verified":False,"hardware_area_timing_power_verified":False}
    write(output/"summary.json",summary)
    print(json.dumps([{k:v for k,v in c.items() if k != "pairs"} for c in summary["paired_comparisons"]]),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    run(parser.parse_args().output.resolve())
