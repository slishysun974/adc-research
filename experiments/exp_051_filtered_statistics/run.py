"""Same-four-point statistic smoothing and slower-step ADC comparison."""

import argparse
from dataclasses import replace
from fractions import Fraction as F
import json
from pathlib import Path

import yaml

from adc_research.calibration.fixed_four_lane_window import (
    FourLaneConversion,FixedFourLaneWindowConfig,correct_fixed_four_lane_window,
)
from adc_research.calibration.fixed_filtered_window import FilteredWindowState,correct_filtered_window
from adc_research.evaluation.window_trajectory_diagnostics import digital_front_window,code_error_stats
from adc_research.platform.presets import build_gu_static_hypothesis_a
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial
from experiments.exp_039_four_lane_dynamic_loop.run import code,coefficients
from experiments.exp_049_normal_start_closed_loop.run import ROOT,digest,write,frozen_codes,score,holdout_records

PROTOCOL = Path(__file__).with_name("protocol.json")


def method_config(method):
    cfg = _config()
    if method == "quarter_step":
        cfg = replace(cfg,stage1_lms=replace(cfg.stage1_lms,step_sizes=tuple(s/4 for s in cfg.stage1_lms.step_sizes)),
                      stage2_lms=replace(cfg.stage2_lms,step_sizes=tuple(s/4 for s in cfg.stage2_lms.step_sizes)))
    return cfg


def run_method(samples,targets,method,protocol,tone):
    cfg = method_config(method)
    state = _initial(cfg)
    initial = state
    filtered = FilteredWindowState(state) if method == "ema_quarter" else None
    config = FixedFourLaneWindowConfig(cfg,selection="point_products")
    shadows = [[F(0)]*4 for _ in range(3)]  # Target/error/filter-rounding, offline only.
    windows,online_codes,checkpoints = [],[],{0:state}
    training = protocol["training_samples"]
    endpoint = None
    clipping = 0
    for start in range(0,len(samples),120):
        batch,ideals = samples[start:start+120],targets[start:start+120]
        before = state
        rows = tuple(FourLaneConversion(start+i,(start+i) % 4,s) for i,s in enumerate(batch))
        if filtered is None:
            raw = correct_fixed_four_lane_window(rows,state,config)
            state = raw.state
            requested = (raw.stage1_update.requested_deltas,raw.stage2_update.requested_deltas)
            applied = (raw.stage1_update.applied_deltas,raw.stage2_update.applied_deltas)
            filter_codes = None
        else:
            old_filter = filtered.stage1_filter_codes
            result = correct_filtered_window(rows,filtered,config)
            filtered = result.state
            raw,state = result.raw,filtered.calibration
            requested,applied = result.requested_deltas,result.applied_deltas
            filter_codes = (filtered.stage1_filter_codes,filtered.stage2_filter_codes)
        outputs = [code(c) for c in raw.calibrations]
        clipping += sum(a != b for req,app in zip(requested,applied) for a,b in zip(req,app))
        frames = digital_front_window(batch,raw,cfg)
        terms = []
        for i,step in enumerate(cfg.stage1_lms.step_sizes):
            selected = [(r,8*t-16384-r["coarse"]) for r,t in zip(frames,ideals,strict=True) if r["selected"] and r["gates"][i]]
            target_sum = sum(r["dither"]*t for r,t in selected)
            error_sum = sum(r["dither"]*(r["local"]-t) for r,t in selected)
            assert target_sum+error_sum == raw.stage1_update.selected_product_sums[i]
            if filtered is None:
                shadows[0][i],shadows[1][i],shadows[2][i] = F(4*target_sum),F(4*error_sum),F(0)
                current_h = 4*(target_sum+error_sum)
            else:
                current_h = filtered.stage1_filter_codes[i]
                filter_rounding = F(current_h)-F(3*old_filter[i]+4*(target_sum+error_sum),4)
                shadows[0][i] = 3*shadows[0][i]/4+target_sum
                shadows[1][i] = 3*shadows[1][i]/4+error_sum
                shadows[2][i] = 3*shadows[2][i]/4+filter_rounding
            assert sum((shadow[i] for shadow in shadows),F(0)) == current_h
            factor = -step*30*2**22/(64*4)
            contributions = [factor*shadow[i] for shadow in shadows]
            request_rounding = F(requested[0][i])-sum(contributions,F(0))
            clipped = applied[0][i]-requested[0][i]
            assert abs(request_rounding) <= F(1,2)
            assert sum(contributions,F(0))+request_rounding+clipped == applied[0][i]
            terms.append({"gate_index":i,"target_product_sum":target_sum,"error_product_sum":error_sum,
                "target_delta_q22":contributions[0],"error_delta_q22":contributions[1],
                "filter_rounding_delta_q22":contributions[2],"request_rounding_delta_q22":request_rounding,
                "clipping_delta_q22":clipped,"applied_delta_q22":applied[0][i],
                "selected_gate_count":len(selected),"update_with_no_current_gate":not selected and applied[0][i] != 0})
        window = start//120
        windows.append({"window":window,"coefficients_before":coefficients(before,cfg),
            "coefficients_after":coefficients(state,cfg),"filters_after":filter_codes,
            "stage1_products":raw.stage1_update.selected_product_sums,"stage2_products":raw.stage2_update.selected_product_sums,
            "requested_deltas":requested,"applied_deltas":applied,"front_attribution":terms,
            "integer_error_stats":code_error_stats(outputs,ideals)})
        if window+1 in protocol["checkpoints_windows"]:
            checkpoints[window+1] = state
        if start+120 == training:
            endpoint = state
        if start >= training:
            online_codes.extend(outputs)
    assert endpoint is not None
    sine_samples,sine_targets = samples[training:],targets[training:]
    checkpoint_scores = {str(w):score(frozen_codes(sine_samples,s,cfg),sine_targets,tone) for w,s in checkpoints.items()}
    parts = []
    for phase,a,b,first,last in (("training",0,128,initial,endpoint),("online_sine",128,160,endpoint,state)):
        gates = []
        for i in range(4):
            selected = [w["front_attribution"][i] for w in windows[a:b]]
            sums = {k:sum((r[k] for r in selected),F(0)) for k in (
                "target_delta_q22","error_delta_q22","filter_rounding_delta_q22","request_rounding_delta_q22","clipping_delta_q22")}
            assert sum(sums.values(),F(0)) == last.stage1.accumulator_codes[i]-first.stage1.accumulator_codes[i]
            deltas = [r["applied_delta_q22"] for r in selected]
            mean = F(sum(deltas),len(deltas))
            variance = sum(((F(d)-mean)**2 for d in deltas),F(0))/len(deltas)
            gates.append({"gate_index":i,**sums,"applied_delta_mean_q22":float(mean),
                "applied_delta_variance_q22":float(variance),"updates_with_no_current_gate":sum(r["update_with_no_current_gate"] for r in selected)})
        parts.append({"phase":phase,"gates":gates})
    spans = {stage:[max(w["coefficients_before"][stage][i] for w in windows[128:])-min(w["coefficients_before"][stage][i] for w in windows[128:])
                    for i in range(4)] for stage in ("stage1","stage2")}
    online = score(online_codes,sine_targets,tone)
    summary = {"method":method,"online_sine":online,"frozen_checkpoint_sine":checkpoint_scores,
        "training_endpoint":coefficients(endpoint,cfg),"final_endpoint":coefficients(state,cfg),
        "clipped_requests":clipping,"sine_coefficient_spans_q10":spans,"attribution":parts,
        "online_minus_frozen_sndr_db":online["sndr_db"]-checkpoint_scores["128"]["sndr_db"],
        "additional_filter_state_bits":208 if method == "ema_quarter" else 0}
    return summary,{"summary":summary,"windows":windows,"online_sine_codes":online_codes}


def compare(cases):
    comparisons = []
    for method in ("quarter_step","ema_quarter"):
        pairs = []
        for case in cases:
            baseline = next((m for m in case["methods"] if m["method"] == "baseline"),None)
            candidate = next((m for m in case["methods"] if m["method"] == method),None)
            if baseline is None or candidate is None:
                continue
            pairs.append({"case":case["name"],"trial":case["trial"],"sndr_gain_db":candidate["online_sine"]["sndr_db"]-baseline["online_sine"]["sndr_db"],
                "mse_change":candidate["online_sine"]["mse_codes_squared"]-baseline["online_sine"]["mse_codes_squared"],
                "first_delta_variance_ratio":candidate["attribution"][1]["gates"][0]["applied_delta_variance_q22"]/baseline["attribution"][1]["gates"][0]["applied_delta_variance_q22"]})
        gains = [p["sndr_gain_db"] for p in pairs]
        mean = sum(gains)/len(gains) if gains else None
        positive,mse_better = sum(g > 0 for g in gains),sum(p["mse_change"] < 0 for p in pairs)
        comparisons.append({"method":method,"paired_cells":len(pairs),"mean_gain_db":mean,
            "positive_cells":positive,"mse_better_cells":mse_better,"minimum_gain_db":min(gains) if gains else None,
            "maximum_gain_db":max(gains) if gains else None,
            "prespecified_screen_passed":len(gains) == 24 and mean > 0 and positive >= 18 and mse_better >= 18 and min(gains) >= -3,
            "pairs":pairs})
    return comparisons


def run(output):
    output.relative_to(ROOT/"artifacts/runs/EXP_051")
    output.mkdir(parents=True,exist_ok=False)
    protocol_bytes = PROTOCOL.read_bytes()
    protocol = json.loads(protocol_bytes)
    (output/"protocol.json").write_bytes(protocol_bytes)
    previous_path = ROOT/"artifacts/runs/EXP_050/phases_v1/summary.json"
    prior = json.loads(previous_path.read_text())
    fingerprints = {**prior["source_evidence_sha256"],str(previous_path):digest(previous_path)}
    own = [Path(__file__),PROTOCOL,ROOT/"src/adc_research/calibration/fixed_filtered_window.py",
           ROOT/"src/adc_research/theory/filtered_mean_dynamics.py"]
    fingerprints.update({str(p):digest(p) for p in own})
    for path,expected in fingerprints.items():
        assert digest(Path(path)) == expected,path
    pipeline = build_gu_static_hypothesis_a(yaml.safe_load((ROOT/"configs/architectures/gu_behavioral_v1.yaml").read_text()))
    cases = []
    for trial in protocol["trials"]:
        for curve in protocol["curves"]:
            for base in protocol["inputs"]:
                inputs = dict(base)
                label = inputs["name"]
                inputs.update(input_seed=trial[label+"_input_seed"],dither_seed=trial[label+"_dither_seed"])
                for history in protocol["histories"]:
                    name = f"t{trial['id']}__{curve['name']}__{label}__{history['name']}"
                    directory = output/name
                    directory.mkdir()
                    record_path = directory/"analog_digital_records.jsonl"
                    samples,targets,overloads = holdout_records(curve,inputs,history,protocol,pipeline,record_path)
                    methods,failures = [],[]
                    for method in protocol["methods"]:
                        try:
                            summary,detail = run_method(samples,targets,method,protocol,inputs["tone_bin"])
                        except ValueError as exc:
                            failures.append({"method":method,"error":str(exc)})
                            print(f"{name}/{method}: FAILED {exc}",flush=True)
                            continue
                        path = directory/(method+".json")
                        write(path,detail)
                        summary["artifact_sha256"] = digest(path)
                        methods.append(summary)
                        print(f"{name}/{method}: online {summary['online_sine']['sndr_db']:.3f}, frozen {summary['frozen_checkpoint_sine']['128']['sndr_db']:.3f} dB",flush=True)
                    cases.append({"name":name,"trial":trial["id"],"tone_bin":inputs["tone_bin"],"input_name":label,
                        "curve_name":curve["name"],"history_name":history["name"],"methods":methods,"failures":failures,
                        "physical_overloads":overloads,"record_sha256":digest(record_path)})
                    write(output/"progress.json",{"completed_cells":len(cases),"cases":cases})
    for path,expected in fingerprints.items():
        assert digest(Path(path)) == expected,path
    assert PROTOCOL.read_bytes() == protocol_bytes
    summary = {"protocol_sha256":digest(PROTOCOL),"cases":cases,"comparisons":compare(cases),
        "source_evidence_sha256":fingerprints,"new_analog_conversions":len(cases)*19200,
        "existing_gu_core_changed":False,"rtl_changed":False,"cadence_used":False,"approximate_fft":True}
    write(output/"summary.json",summary)
    print(json.dumps([{k:v for k,v in c.items() if k != "pairs"} for c in summary["comparisons"]]),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    run(parser.parse_args().output.resolve())
