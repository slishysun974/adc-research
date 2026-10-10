"""Model/source audit with independent positive and stochastic controls."""

from __future__ import annotations

import argparse
from dataclasses import asdict, replace
from fractions import Fraction
import json
import math
from pathlib import Path

import numpy as np
import yaml

from adc_research.calibration.gu_baseline import build_gu_two_stage_baseline
from adc_research.calibration.gated_lms import GatedLmsConfig, GatedLmsState, update
from adc_research.calibration.two_stage import correct_two_stage_observed
from adc_research.evaluation.observations import digital_sample
from adc_research.platform.amplifier import StaticCubicTruthConfig
from adc_research.platform.pipeline import StaticPipelineNonidealities, process
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stage import StaticStageNonidealities
from adc_research.platform.dual_path_settling import DualPathSettlingState
from adc_research.platform.two_phase_dual_path import TwoPhaseDualPathConfig, TwoPhasePath, process as phase_process
from adc_research.theory.dither_information import scalar_window_moments
from experiments.exp_049_normal_start_closed_loop.run import ROOT, digest, write

PROTOCOL = Path(__file__).with_name("protocol.json")


def static_audit(protocol):
    arch = yaml.safe_load((ROOT/"configs/architectures/gu_behavioral_v1.yaml").read_text(encoding="utf-8"))
    pipeline = build_gu_static_hypothesis_a(arch)
    digital = build_gu_two_stage_baseline(pipeline, arch["pwl_implications"])
    result = []
    control = protocol["static_control"]
    low, high = control["input_domain"]
    for a1, a2 in control["gain_scales"]:
        nonideal = StaticPipelineNonidealities(
            stage1=StaticStageNonidealities(actual_interstage_gain=4*a1),
            stage2=StaticStageNonidealities(actual_interstage_gain=4*a2))
        inverse = replace(digital,
            stage1_pwl=replace(digital.stage1_pwl, slopes=(1/a1,)*4),
            stage2_pwl=replace(digital.stage2_pwl, slopes=(1/a2,)*4))
        phases = TwoPhaseDualPathConfig(*(TwoPhasePath(0,0) for _ in range(3)), auxiliary_gain=4*a1,
                                        auxiliary_truth=StaticCubicTruthConfig(1,0))
        maximum_identity_error = 0.0
        maximum_static_difference = 0.0
        overloads = 0
        for i in range(control["points"]):
            x = low+(i+0.5)*(high-low)/control["points"]
            for tags in control["dither_pairs"]:
                # Independent literal stage equations, not the theory/platform helpers.
                q1 = sum(x >= t for t in (-.875,-.625,-.375,-.125,.125,.375,.625,.875))-4
                r1 = 4*a1*(x-q1/4+tags[0]/32)
                q2 = sum(r1 >= t for t in (-.875,-.625,-.375,-.125,.125,.375,.625,.875))-4
                r2 = 4*a2*(r1-q2/4+tags[1]/32)
                c3 = math.floor(128*(r2+1))-128
                raw = process(x,pipeline,sample_index=i,dither_symbols=tuple(tags),nonidealities=nonideal)
                assert (q1,q2,c3) == (raw.stage1.quantizer.symbol,raw.stage2.quantizer.symbol,raw.backend.centered_code)
                corrected = correct_two_stage_observed(digital_sample(raw),inverse)
                eta = c3-128*r2
                expected = 2048*(x+1)+eta/(a1*a2)
                error = abs(corrected.unclipped_output_code-expected)
                maximum_identity_error = max(maximum_identity_error,error)
                assert error <= control["identity_tolerance_codes"]
                assert -1.00000000001 <= eta <= 1e-11
                if a1 == a2 == 1:
                    assert raw.reconstruction.output_code == math.floor(2048*(x+1))
                dynamic = phase_process(x,pipeline,phases,DualPathSettlingState(.63,-.47,.19),
                     sample_index=i,dither_symbols=tuple(tags),nonidealities=nonideal)
                assert digital_sample(dynamic.pipeline) == digital_sample(raw)
                maximum_static_difference = max(maximum_static_difference,abs(dynamic.pipeline.stage1.residue-raw.stage1.residue),
                    abs(dynamic.pipeline.stage2.residue-raw.stage2.residue))
                overloads += int(not raw.reconstruction.correctable)
        assert overloads == 0 and maximum_static_difference == 0
        result.append({"gain_scales": [a1,a2], "conversions": control["points"]*4,
            "maximum_independent_inverse_identity_error_codes": maximum_identity_error,
            "zero_settling_static_difference": maximum_static_difference, "overloads": overloads,
            "backend_quantization_error_gain": 1/(a1*a2)})
    return result


def correction(raw, k1, k2, width):
    a = abs(raw)
    magnitude = k1*a if a < width else k1*width+k2*(a-width)
    return math.copysign(magnitude,raw)


def paper_principle(spec):
    rng = np.random.default_rng(spec["seed"])
    count, d, b = spec["samples"], spec["dither"], spec["slice_width"]
    x = rng.random(count)
    tags = rng.choice(np.array([-1.0,1.0]),size=count)
    u = x+d*tags
    raw = np.where(u < .52,.96*u,.8*u+.084)
    def evaluate(k1,k2):
        target = np.linspace(0,1,4096)
        mse = 0.0
        for sign in (-1,1):
            value = target+sign*d
            plant = np.where(value < .52,.96*value,.8*value+.084)
            mag = np.abs(plant)
            fixed = np.sign(plant)*np.where(mag < b,k1*mag,k1*b+k2*(mag-b))-sign*d
            mse += float(np.mean((fixed-target)**2))/2
        return mse
    initial_mse = evaluate(1,1)
    cfg = GatedLmsConfig(b,tuple(spec["steps"]))
    state = GatedLmsState.unity(2)
    k1=k2=1.0
    mu1,mu2=spec["steps"]
    checkpoints=[]
    clipped=0
    max_reference_error=0.0
    for n,(r,s) in enumerate(zip(raw,tags),1):
        r,s=float(r),float(s)
        local=correction(r,k1,k2,b)-s*d
        gate=abs(local)>=k1*b
        new1=k1-mu1*s*d*local
        new2=k2-mu2*s*d*local if gate else k2
        if n<=spec["reference_kernel_samples"]:
            original=update(state,dither_code=s*d,corrected_output=local,config=cfg)
            state=original.state
            error=max(abs(state.coefficients[0]-new1),abs(state.coefficients[1]-new2))
            max_reference_error=max(max_reference_error,error)
            assert error < 1e-12
        clipped+=int(not 0<=new1<=2)+int(not 0<=new2<=2)
        k1,k2=min(max(new1,0),2),min(max(new2,0),2)
        if n in spec["checkpoints"]:
            checkpoints.append({"samples":n,"coefficients":[k1,k2],"dithered_grid_mse":evaluate(k1,k2)})
            print(f"paper principle n={n}, k={k1:.6f},{k2:.6f}",flush=True)
    final_mse=evaluate(k1,k2)
    passed=final_mse < initial_mse/100 and abs(k1-1/.96)<.02 and abs(k2-1/.8)<.02
    return {"checkpoints":checkpoints,"initial_mse":initial_mse,"final_mse":final_mse,
            "acceptance_passed":passed,"source_literal_jump":.8*.52+.084-.96*.52,
            "raw_above_one_samples":int(np.sum(raw>=1)),"clipped_coefficients":clipped,
            "maximum_reference_kernel_error":max_reference_error,
            "assumed_unquantized_continuous_last_slice_extension":True}


def moment_control(spec):
    rng=np.random.default_rng(spec["seed"])
    amplitude=spec["residue_half_range_codes"]
    step=float(Fraction(spec["base_step"]))
    rows=[]
    for gain in spec["gain_scales"]:
        for method in spec["methods"]:
            n,p=method["selected"],method["multiplier"]
            k=np.ones(spec["ensemble_paths"])
            all_up=all_down=0
            d=spec["dither_codes"]
            for w in range(spec["windows"]):
                x=rng.uniform(-amplitude,amplitude,(len(k),n))
                signs=rng.choice(np.array([-1.0,1.0]),size=x.shape)
                dd=d*signs
                y=k[:,None]*gain*(x+dd)-dd
                new=k-step*p*np.sum(dd*y,axis=1)
                # Independent fresh-record population MSE = (gain*k-1)^2 E[(X+D)^2].
                before=(gain*k-1)**2
                after=(gain*new-1)**2
                all_up+=int(np.sum(after>before))
                all_down+=int(np.sum(after<before))
                k=new
            predicted=scalar_window_moments(gain=gain,dither=d,residue_variance=amplitude**2/3,
                step=step,selected=n,multiplier=p,windows=spec["windows"])
            empirical_mean,empirical_var=float(np.mean(k)),float(np.var(k))
            se=math.sqrt(predicted.coefficient_variance/len(k))
            z=abs(empirical_mean-predicted.mean_coefficient)/se
            ratio=empirical_var/predicted.coefficient_variance
            passed=z<=5 and abs(ratio-1)<=.08
            item={"gain":gain,"method":method["name"],"predicted":asdict(predicted),
                "ensemble_mean":empirical_mean,"ensemble_variance":empirical_var,
                "mean_error_standard_errors":z,"variance_ratio":ratio,"acceptance_passed":passed,
                "population_mse_worsening_step_fraction":all_up/(len(k)*spec["windows"]),
                "population_mse_improving_step_fraction":all_down/(len(k)*spec["windows"])}
            rows.append(item)
            print(f"scalar gain={gain}/{method['name']}: mean z={z:.3f}, variance ratio={ratio:.4f}",flush=True)
    return rows


def run(output):
    output.relative_to(ROOT/"artifacts/runs/EXP_055")
    output.mkdir(parents=True,exist_ok=False)
    protocol_bytes=PROTOCOL.read_bytes()
    protocol=json.loads(protocol_bytes)
    (output/"protocol.json").write_bytes(protocol_bytes)
    paths=[ROOT/"configs/architectures/gu_behavioral_v1.yaml",ROOT/"experiments/exp_050_phase_selection/protocol.json",
           ROOT/"references/local/OJSSCS2026_Gu.pdf",Path(__file__),PROTOCOL,
           ROOT/"src/adc_research/theory/dither_information.py"]
    paths += sorted((ROOT/"src/adc_research/platform").glob("*.py"))
    paths += sorted((ROOT/"src/adc_research/calibration").glob("*.py"))
    fingerprints={str(p):digest(p) for p in paths}
    static=static_audit(protocol)
    print("independent static and zero-settling controls passed",flush=True)
    paper=paper_principle(protocol["paper_principle_control"])
    moments=moment_control(protocol["moment_controls"])
    for path,expected in fingerprints.items():assert digest(Path(path))==expected
    assert PROTOCOL.read_bytes()==protocol_bytes
    summary={"protocol_sha256":digest(PROTOCOL),"source_sha256":fingerprints,
        "static_controls":static,"paper_principle":paper,"scalar_moment_controls":moments,
        "all_controls_passed":paper["acceptance_passed"] and all(m["acceptance_passed"] for m in moments),
        "new_static_adc_conversions":sum(s["conversions"] for s in static)*2,
        "paper_scalar_samples":protocol["paper_principle_control"]["samples"],
        "full_dynamic_chip_fidelity_passed":False,"new_online_algorithm":False,"rtl_changed":False}
    write(output/"summary.json",summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ("source_sha256","scalar_moment_controls")}),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    run(parser.parse_args().output.resolve())
