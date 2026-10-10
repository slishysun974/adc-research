"""Export original Python results and independently compare Simulink traces.

The exporter calls the existing platform/calibration functions. It does not
reimplement their equations. MATLAB consumes only parameter/input files.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(HERE / ".deps"), str(ROOT / "src")]
import numpy as np
import yaml

from adc_research.calibration.adaptive_two_stage import (
    TwoStageAdaptiveConfig, TwoStageAdaptiveState, correct_and_update,
    cascade_from_state, observe, update_block_mean_observations,
)
from adc_research.calibration.gated_lms import (
    GatedLmsConfig, GatedLmsState, adaptive_lower_thresholds, update,
)
from adc_research.calibration.gu_baseline import build_gu_two_stage_baseline
from adc_research.calibration.pwl import PwlConfig, correct
from adc_research.calibration.two_stage import correct_two_stage_observed
from adc_research.evaluation.observations import digital_sample
from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.platform.amplifier import StaticCubicTruthConfig
from adc_research.platform.backend_sar import SarConfig, convert as sar_convert
from adc_research.platform.pipeline import process, StaticPipelineNonidealities
from adc_research.platform.presets import build_gu_static_hypothesis_a, build_gu_gate_d_nonidealities
from adc_research.platform.stage import StaticStageNonidealities
from adc_research.platform.finite_settling import (
    process as finite_process, FiniteSettlingConfig, SettlingState,
)
from adc_research.platform.dual_path_settling import (
    process as dual_process, DualPathSettlingConfig, DualPathSettlingState,
)
from adc_research.platform.two_phase_dual_path import (
    process as phase_process, TwoPhasePath, TwoPhaseDualPathConfig,
)


def names() -> dict[str, list[str]]:
    physical = []
    for stage in (1, 2):
        physical += [f"s{stage}_{n}" for n in (
            "auxiliary", "symbol", "region", "dac_nominal", "dac_mismatch",
            "dac_actual", "analog_dither", "preamp", "static_target",
            "tracking_start", "residue",
        )]
        physical += [f"s{stage}_thermometer{j}" for j in range(8)]
    physical += ["auxiliary_target", "auxiliary_tracking_start", "sar_raw",
                 "sar_centered", "sar_channel", "sar_quantized"]
    physical += ["input_low", "input_high", "aux1_low", "aux1_high",
                 "r1_low", "r1_high", "aux2_low", "aux2_high", "r2_low", "r2_high",
                 "raw_clip_low", "raw_clip_high", "corrected_clip_low", "corrected_clip_high",
                 "raw_physical_correctable", "digital_correctable", "corrected_physical_correctable"]
    digital = ["output", "uncalibrated_output", "unclipped", "uncalibrated_unclipped",
               "raw1", "pwl1", "pwl2", "local1", "local2", "slice1", "slice2", "D1", "D2"]
    learning = []
    for kind in ("before", "after", "threshold", "gate", "product", "count"):
        learning += [f"{kind}_s{s}_{j}" for s in (1, 2) for j in range(1, 5)]
    learning += ["observations", "commits", "selected", "commit"]
    return {"stimulus_trace": ["index", "input", "tag1", "tag2"],
            "physical_trace": physical, "digital_trace": digital, "learning_trace": learning}


def read_yaml(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def configurations():
    architecture = read_yaml(ROOT / "configs/architectures/gu_behavioral_v1.yaml")
    effects = read_yaml(ROOT / "configs/nonidealities/gu_gate_d_static_v0_1.yaml")
    steps = json.loads((ROOT / "experiments/exp_057_static_two_stage_million/protocol.json").read_text())
    return architecture, effects, steps


def stage_parameters(stage, effects):
    thresholds = [t+o for t, o in zip(stage.quantizer.thresholds, effects.threshold_offsets or (0,)*8)]
    levels = [stage.cdac.nominal_levels[q] for q in range(-4, 5)]
    errors = [effects.cdac_mismatch.code_level_errors.get(q, 0) if effects.cdac_mismatch else 0 for q in range(-4, 5)]
    analog = [0, 1, 0, 1] + [0, .25, .5, .75, 1] * 2
    if effects.cubic_truth:
        truth = effects.cubic_truth
        analog[:4] = [1, truth.linear_scale, truth.cubic_coefficient, truth.maximum_ideal_output_magnitude]
    if effects.pwl_truth:
        analog = [2, 1, 0, 1] + list(effects.pwl_truth.ideal_output_edges) + list(effects.pwl_truth.distorted_output_edges)
    return dict(thresholds=thresholds, levels=levels, errors=errors,
                gain=effects.actual_interstage_gain or stage.nominal_interstage_gain, analog=analog)


def cases(architecture, effects, steps):
    rng = np.random.default_rng(2026101001)
    # Exact ADC endpoints, every ideal code boundary and adjacent double.
    edges = np.arange(4097)/2048-1
    grid = np.unique(np.r_[np.nextafter(edges, -np.inf), edges, np.nextafter(edges, np.inf)])
    grid = grid[(grid >= -1) & (grid < 1)]
    control = rng.uniform(-.82, .82, 480)
    training = rng.uniform(-.82, .82, 2400)
    tags = rng.choice([-1, 1], size=(2400, 2))
    specs = []
    def add(name, x=control, nonideal=None, analog_mode=0, digital_mode=1,
            dither=True, pipeline=None, phase=None, initial1=(1,)*4, initial2=(1,)*4):
        specs.append(dict(name=name, x=np.asarray(x), nonideal=nonideal or StaticPipelineNonidealities(),
                          analog_mode=analog_mode, digital_mode=digital_mode, dither=dither,
                          pipeline=pipeline or build_gu_static_hypothesis_a(architecture), phase=phase,
                          initial1=initial1, initial2=initial2))
    add("ideal_grid", grid, dither=False)
    add("ideal_dither", np.repeat(grid, 4))
    for name, enabled in (
        ("flash_offsets", ("flash_threshold_offsets",)),
        ("cdac_mismatch", ("cdac_code_level_mismatch",)),
        ("gain_error", ("linear_interstage_gain",)),
        ("analog_pwl", ("static_pwl_truth",)),
        ("all_static_effects", tuple(sorted(effects["effects"]))),
    ):
        add(name, nonideal=build_gu_gate_d_nonidealities(effects, enabled_effects=enabled))
    add("auxiliary_mismatch", pipeline=build_gu_static_hypothesis_a(
        architecture, stage2_flash_auxiliary_gain_ratio=1.03, stage2_flash_auxiliary_offset=.005))
    truths = {}
    for entry in steps["cases"]:
        if entry["name"] == "ideal":
            continue
        truths[entry["name"]] = StaticPipelineNonidealities(*[
            StaticStageNonidealities(cubic_truth=StaticCubicTruthConfig(*entry[bank]))
            for bank in ("stage1", "stage2")])
        add(entry["name"], nonideal=truths[entry["name"]])
    add("frozen_pwl", nonideal=truths["both_smooth"], initial1=(1.02, 1.04, 1.07, 1.1), initial2=(1.01, 1.03, 1.04, 1.05))
    add("finite_settling", nonideal=truths["both_smooth"], analog_mode=1)
    add("dual_path_settling", nonideal=truths["both_smooth"], analog_mode=2)
    phases = TwoPhaseDualPathConfig(TwoPhasePath(.04, .7, .01), TwoPhasePath(.06, .6, -.02),
                                   TwoPhasePath(.03, .5, .015), 3.98, StaticCubicTruthConfig(.985, -.025))
    add("two_phase", nonideal=truths["both_smooth"], analog_mode=3, phase=phases)
    zero = TwoPhaseDualPathConfig(TwoPhasePath(0, 1), TwoPhasePath(0, 1), TwoPhasePath(0, 1))
    add("zero_two_phase", analog_mode=3, phase=zero)
    add("instantaneous_lms", training, nonideal=truths["both_smooth"], digital_mode=2)
    add("point30_window", training, nonideal=truths["both_smooth"], digital_mode=3)
    add("full120_window", training, nonideal=truths["both_smooth"], digital_mode=4)
    add("dynamic_full120", training, nonideal=truths["both_smooth"], analog_mode=3, digital_mode=4, phase=phases)
    add("overload_bypass", np.array([-1.2, -1, -.99999, 0, .99999, 1, 1.2]), digital_mode=0, dither=False)
    tone = .82*np.sin(2*np.pi*127*np.arange(4096)/4096)
    add("demo_tone", tone, nonideal=truths["both_smooth"], digital_mode=3)
    assert [s["name"] for s in specs] == json.loads((HERE/"validation_protocol.json").read_text())["cases"]
    for s in specs:
        if s["name"] == "ideal_dither":
            s["tags"] = np.tile(np.array([[-1,-1],[-1,1],[1,-1],[1,1]]), (len(grid),1))
        elif not s["dither"]:
            s["tags"] = np.zeros((len(s["x"]),2), dtype=int)
        elif len(s["x"]) <= len(tags):
            s["tags"] = tags[:len(s["x"])]
        else:
            s["tags"] = rng.choice([-1,1], size=(len(s["x"]),2))
    return specs


def reference_case(spec, architecture, steps):
    pipeline, ni, mode, digital_mode = (spec[k] for k in ("pipeline", "nonideal", "analog_mode", "digital_mode"))
    cascade = build_gu_two_stage_baseline(pipeline, architecture["pwl_implications"])
    mu = [tuple(v/steps["steps"][f"stage{s}_denominator"] for v in steps["steps"]["numerators"]) for s in (1,2)]
    config = TwoStageAdaptiveConfig(cascade, GatedLmsConfig(128,mu[0]), GatedLmsConfig(32,mu[1]))
    state = TwoStageAdaptiveState(GatedLmsState(spec["initial1"],(0,)*4), GatedLmsState(spec["initial2"],(0,)*4))
    physical_state = SettlingState() if mode == 1 else DualPathSettlingState()
    C = dict(digital_mode=digital_mode, initial1=list(spec["initial1"]), initial2=list(spec["initial2"]),
             initial_analog=[0,0,0], mu1=list(mu[0]), mu2=list(mu[1]),
             aux1_gain=pipeline.auxiliary_gain_ratios[0], aux1_offset=pipeline.auxiliary_offsets[0],
             dither_amplitude=pipeline.stage1.cdac.dither_levels[1], copy1=cascade.dither_code_copies[0][1], copy2=cascade.dither_code_copies[1][1])
    for s, stage, eff in ((1,pipeline.stage1,ni.stage1),(2,pipeline.stage2,ni.stage2)):
        C.update({f"s{s}_{k}": v for k,v in stage_parameters(stage,eff).items()})
        C[f"s{s}_phase"] = [mode, .04 if s==1 else .03, 1, 0]
        if mode==3:
            phase = spec["phase"].stage1_main if s==1 else spec["phase"].stage2_main
            C[f"s{s}_phase"] = [3, phase.amplification_factor, phase.tracking_factor, phase.tracking_target]
    C["aux_parameters"] = [mode,pipeline.auxiliary_gain_ratios[1],pipeline.auxiliary_offsets[1],C["s1_gain"],4,1,0,1,.06,1,0]
    if mode==3:
        phases=spec["phase"]; p=phases.stage1_auxiliary
        C["aux_parameters"][4:] = [phases.auxiliary_gain,phases.auxiliary_truth.linear_scale,
            phases.auxiliary_truth.cubic_coefficient,phases.auxiliary_truth.maximum_ideal_output_magnitude,
            p.amplification_factor,p.tracking_factor,p.tracking_target]
    traces = {k:[] for k in names()}
    observations=[]; gate_counts=np.zeros(8); observation_count=0; commits=0
    for n,(x,t) in enumerate(zip(spec["x"],spec["tags"])):
        d=tuple(int(v) if v else None for v in t)
        kw=dict(sample_index=n,dither_symbols=d,nonidealities=ni)
        start=[0.,0.,0.]
        if mode==0:
            raw=process(float(x),pipeline,**kw)
            targets=[raw.stage1.residue,raw.stage2.auxiliary_input,raw.stage2.residue]
        elif mode==1:
            prior=physical_state.as_tuple()
            result=finite_process(float(x),pipeline,FiniteSettlingConfig((.04,.03)),physical_state,**kw)
            raw=result.pipeline; physical_state=result.next_state
            start=[prior[0],0.,prior[1]]
            targets=[result.stage1_target_residue,raw.stage2.auxiliary_input,result.stage2_target_residue]
        elif mode==2:
            start=list(physical_state.as_tuple())
            result=dual_process(float(x),pipeline,DualPathSettlingConfig(.04,.06,.03),physical_state,**kw)
            raw=result.pipeline; physical_state=result.next_state
            targets=[result.stage1_main_target,result.stage1_auxiliary_target,result.stage2_main_target]
        else:
            result=phase_process(float(x),pipeline,spec["phase"],physical_state,**kw)
            raw=result.pipeline; physical_state=result.next_state
            targets=list(result.static_targets); start=list(result.tracking_starts)
        before=state
        if digital_mode==0:
            p2=float(raw.backend.centered_code); D1=C["copy1"]*t[0]; D2=C["copy2"]*t[1]
            r1=128*raw.stage2.quantizer.symbol+p2-D2; p1=r1
            y1=p1-D1; y2=p2-D2; u=512*raw.stage1.quantizer.symbol+y1+2048
            output=min(max(u,0),4095); slice1=slice2=-1
        else:
            corrected=correct_two_stage_observed(digital_sample(raw),cascade_from_state(cascade,state))
            p1=corrected.stage1_pwl.corrected_code; p2=corrected.stage2_pwl.corrected_code
            r1=corrected.stage1_raw_code; D1=corrected.stage1_dither_copy; D2=corrected.stage2_dither_copy
            y1=p1-D1; y2=p2-D2; u=corrected.unclipped_output_code; output=corrected.output_code
            slice1=corrected.stage1_pwl.slice_index; slice2=corrected.stage2_pwl.slice_index
        thresholds=np.r_[adaptive_lower_thresholds(state.stage1.coefficients,128),adaptive_lower_thresholds(state.stage2.coefficients,32)]
        gates=np.r_[np.abs(y1)>=thresholds[:4],np.abs(y2)>=thresholds[4:]].astype(float)
        products=gates*np.r_[np.repeat(D1*y1,4),np.repeat(D2*y2,4)]
        selected = digital_mode in (2,4) or (digital_mode==3 and n%120<4)
        commit=False
        if selected:
            observation_count+=1; gate_counts+=gates
            if digital_mode==2:
                adapted=correct_and_update(digital_sample(raw),state,config)
                state=adapted.state; commit=True
            else:
                observations.append(observe(digital_sample(raw),state,config))
        if digital_mode in (3,4) and n%120==119:
            multiplier=30 if digital_mode==3 else 1
            number=len(observations)
            adapted=replace(config,
                stage1_lms=replace(config.stage1_lms,step_sizes=tuple(v*multiplier*number for v in mu[0])),
                stage2_lms=replace(config.stage2_lms,step_sizes=tuple(v*multiplier*number for v in mu[1])))
            state=update_block_mean_observations(state,observations,adapted).state
            observations=[]; commit=True
        commits+=int(commit)
        physical=[]
        for s,st in enumerate((raw.stage1,raw.stage2)):
            physical += [st.auxiliary_input,st.quantizer.symbol,st.quantizer.region_index,st.cdac.nominal_value,
                         st.cdac.mismatch_contribution,st.cdac.actual_dac_value,st.cdac.dither_contribution,
                         st.residue_preamp,targets[2*s],start[2*s],st.residue]
            physical += [int(st.auxiliary_input>=th) for th in st.quantizer.effective_thresholds]
        physical += [targets[1],start[1],raw.backend.raw_code,raw.backend.centered_code,
                     raw.backend.channel_index,raw.backend.quantized_value]
        raw_u=raw.reconstruction.unclipped_output_code
        flags=[x < -1,x >= 1,raw.stage1.auxiliary_input < -1,raw.stage1.auxiliary_input >= 1,
               raw.stage1.residue < -1,raw.stage1.residue >= 1,
               raw.stage2.auxiliary_input < -1,raw.stage2.auxiliary_input >= 1,
               raw.stage2.residue < -1,raw.stage2.residue >= 1,
               raw_u < 0,raw_u > 4095,u < 0,u > 4095]
        physical_bad=any(flags[j] for j in (0,1,4,5,8,9))
        flags += [raw.reconstruction.correctable,not any(flags[12:14]),not physical_bad and not any(flags[12:14])]
        physical += [int(v) for v in flags]
        traces["stimulus_trace"].append([n,x,*t])
        traces["physical_trace"].append(physical)
        traces["digital_trace"].append([output,raw.reconstruction.output_code,u,raw_u,r1,p1,p2,y1,y2,slice1,slice2,D1,D2])
        traces["learning_trace"].append([*before.stage1.coefficients,*before.stage2.coefficients,
            *state.stage1.coefficients,*state.stage2.coefficients,*thresholds,*gates,*products,*gate_counts,
            observation_count,commits,int(selected),int(commit)])
    return C,{k:np.asarray(v,dtype=float) for k,v in traces.items()}


def export(folder):
    folder.mkdir(parents=True,exist_ok=True)
    architecture,effects,steps=configurations()
    entries=[]
    for spec in cases(architecture,effects,steps):
        C,traces=reference_case(spec,architecture,steps)
        np.savetxt(folder/f"{spec['name']}_input.csv",traces["stimulus_trace"],delimiter=",",fmt="%.17g")
        for group,values in traces.items():
            assert values.shape[1]==len(names()[group]),(group,values.shape)
            np.savetxt(folder/f"{spec['name']}_{group}.csv",values,delimiter=",",fmt="%.17g")
        entries.append(dict(name=spec["name"],samples=len(spec["x"]),parameters=C))
        print(f"Python reference: {spec['name']} ({len(spec['x'])} conversions)",flush=True)
    sources=list((ROOT/"src/adc_research/platform").glob("*.py"))+list((ROOT/"src/adc_research/calibration").glob("*.py"))
    sources += [ROOT/"configs/architectures/gu_behavioral_v1.yaml",ROOT/"configs/nonidealities/gu_gate_d_static_v0_1.yaml",
                ROOT/"experiments/exp_057_static_two_stage_million/protocol.json",HERE/"validation_protocol.json",Path(__file__)]
    manifest=dict(version="adc-simulink-parity-v1",generated_at=datetime.now().isoformat(),
                  cases=entries,columns=names(),source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
    (folder/"manifest.json").write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    export_primitives(folder)


def export_primitives(folder):
    pwl_rows=[]; gate_rows=[]; sar_rows=[]
    slopes=(1.02,1.04,1.07,1.1)
    for width in (32,128):
        edges=np.arange(-4,5)*width
        probes=np.unique(np.r_[edges,np.nextafter(edges,-np.inf),np.nextafter(edges,np.inf)])
        for raw in probes[(probes>=-4*width)&(probes<4*width)]:
            r=correct(float(raw),PwlConfig(width,slopes))
            pwl_rows.append([width,raw,*slopes,r.corrected_code,r.slice_index])
        thresholds=adaptive_lower_thresholds(slopes,width)
        for local in np.unique(np.r_[thresholds,-np.array(thresholds),np.nextafter(thresholds,-np.inf),np.nextafter(thresholds,np.inf)]):
            r=update(GatedLmsState(slopes,(0,)*4),dither_code=16,corrected_output=float(local),config=GatedLmsConfig(width,(1e-9,)*4))
            gate_rows.append([width,*slopes,16,local,*r.adaptive_lower_thresholds,*r.gate_mask,
                              *[16*local if g else 0 for g in r.gate_mask]])
    edges=np.arange(257)/128-1
    for n,x in enumerate(np.r_[np.nextafter(edges,-np.inf),edges,np.nextafter(edges,np.inf),-1.2,1.2]):
        r=sar_convert(float(x),SarConfig(8,channels=4),sample_index=n)
        sar_rows.append([x,n,r.raw_code,r.centered_code,r.channel_index,r.quantized_value])
    for name,rows in (("pwl",pwl_rows),("gate",gate_rows),("sar",sar_rows)):
        np.savetxt(folder/f"primitive_{name}.csv",np.asarray(rows),delimiter=",",fmt="%.17g")


def tolerance(group,name):
    if group=="stimulus_trace":
        return 0.0
    if group=="physical_trace":
        discrete = any(n in name for n in ("symbol","region","thermometer","sar_raw","sar_centered","sar_channel","_low","_high","correctable"))
        return 0.0 if discrete else 1e-12
    if group=="digital_trace":
        return 0.0 if name in ("uncalibrated_output","uncalibrated_unclipped","slice1","slice2","D1","D2") else 1e-9
    if name.startswith(("gate_","count_")) or name in ("observations","commits","selected","commit"):
        return 0.0
    if name.startswith("product_"):
        return 1e-7
    return 1e-11 if name.startswith(("before_","after_")) else 1e-9


def compare(reference,actual,report):
    manifest=json.loads((reference/"manifest.json").read_text(encoding="utf-8"))
    results=[]; failures=[]
    for entry in manifest["cases"]:
        for group,columns in manifest["columns"].items():
            expected=np.loadtxt(reference/f"{entry['name']}_{group}.csv",delimiter=",",ndmin=2)
            observed=np.loadtxt(actual/f"{entry['name']}_{group}.csv",delimiter=",",ndmin=2)
            if expected.shape!=observed.shape or not np.isfinite(observed).all():
                failures.append(dict(case=entry["name"],group=group,error="shape or nonfinite",expected=list(expected.shape),actual=list(observed.shape)))
                continue
            for j,column in enumerate(columns):
                error=np.abs(expected[:,j]-observed[:,j]); limit=tolerance(group,column)
                max_error=float(np.max(error)); passed=max_error<=limit
                row=dict(case=entry["name"],group=group,column=column,max_absolute_error=max_error,tolerance=limit,passed=passed)
                if not passed:
                    bad=int(np.flatnonzero(error>limit)[0]); row.update(first_sample=bad,python=float(expected[bad,j]),simulink=float(observed[bad,j]))
                    failures.append(row)
                results.append(row)
        print(f"Compared: {entry['name']}",flush=True)
    metrics={}
    for label,path in (("python",reference),("simulink",actual)):
        data=np.loadtxt(path/"demo_tone_digital_trace.csv",delimiter=",")
        metrics[label]={key:asdict(analyze_coherent_tone(data[:,j],sample_rate_hz=3e9,fundamental_bin=127,full_scale_peak=2048).metrics)
                        for key,j in (("calibrated",0),("uncalibrated",1))}
    for output in metrics["python"]:
        for field in ("sndr_db","sfdr_dbc","enob_bits"):
            diff=abs(metrics["python"][output][field]-metrics["simulink"][output][field])
            if diff>1e-7:
                failures.append(dict(metric=output+"."+field,error=diff))
    hashes={str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in HERE.glob("*.m")}
    hashes.update({str(p.relative_to(HERE)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (HERE/"blocks").glob("*.m")})
    if (HERE/"adc_behavioral.slx").exists():
        hashes["adc_behavioral.slx"]=hashlib.sha256((HERE/"adc_behavioral.slx").read_bytes()).hexdigest()
    result=dict(passed=not failures,total_cases=len(manifest["cases"]),total_conversions=sum(c["samples"] for c in manifest["cases"]),
                field_checks=len(results),failures=failures,metrics=metrics,checks=results,
                source_sha256=manifest["source_sha256"],simulink_source_sha256=hashes)
    report.parent.mkdir(parents=True,exist_ok=True)
    report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("passed","total_cases","total_conversions","field_checks","failures")},indent=2))
    if failures:
        raise SystemExit(1)


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="command",required=True)
    generate=sub.add_parser("export"); generate.add_argument("folder",type=Path)
    check=sub.add_parser("compare"); check.add_argument("reference",type=Path); check.add_argument("actual",type=Path); check.add_argument("report",type=Path)
    args=parser.parse_args()
    if args.command=="export": export(args.folder)
    else: compare(args.reference,args.actual,args.report)
