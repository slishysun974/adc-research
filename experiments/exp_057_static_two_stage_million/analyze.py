"""Offline full-chain scoring, gate-support audit and projection diagnostics."""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from experiments.exp_057_static_two_stage_million.common import (
    basis,corrected_arrays,input_tags,metrics,plant_arrays,write,window_original_products)


def least_squares(raw,target,width):
    phi=basis(raw,width)
    active=np.flatnonzero(np.any(phi!=0,axis=0))
    k=np.ones(4)
    fit=np.linalg.lstsq(phi[:,active],target,rcond=None)
    k[active]=fit[0]
    residual=phi@k-target
    return k,phi,residual,{"active_columns":active.tolist(),"rank":int(fit[2]),
        "coefficients":k.tolist(),"mse_codes_squared":float(np.mean(residual**2)),
        "within_candidate_bounds":bool(np.all((k>=0)&(k<=2))),
        "normal_equation_max_residual":float(np.max(np.abs(phi.T@residual)))}


def projection(k,q1,q2,backend,d1,d2,x):
    p2=basis(backend,32)@k[4:]
    raw1=128*q2+p2-16*d2
    target=2048*x-512*q1+64*d1
    ref,phi,residual,info=least_squares(raw1,target,128)
    movement=phi@(k[:4]-ref)
    actual=float(np.mean((phi@k[:4]-target)**2))
    ref_mse=float(np.mean(residual**2))
    excess=float(np.mean(movement**2))
    cross=2*float(np.mean(residual*movement))
    assert abs(actual-ref_mse-excess-cross)<=1e-8*max(1,actual)
    return {"actual_validation_mse":actual,"fixed_rear_front_projection_mse":ref_mse,
            "front_coefficient_excess_mse":excess,"projection_cross_term":cross,"front_projection":info}


def online_score(q1,q2,backend,d1,d2,x,k,method,protocol):
    k=k.copy();outputs=[];clips=0;gates=np.zeros(8,dtype=np.int64)
    selected=method["selected"]
    steps=np.array([n/protocol["steps"][key] for key in ("stage1_denominator","stage2_denominator")
                    for n in protocol["steps"]["numerators"]])
    for start in range(0,len(x),120):
        end=start+120
        output=corrected_arrays(q1[start:end],q2[start:end],backend[start:end],d1[start:end],d2[start:end],k)[0]
        outputs.extend(output)
        stop=start+selected
        _,sums,count=window_original_products(q1[start:stop],q2[start:stop],backend[start:stop],d1[start:stop],d2[start:stop],k)
        requested=k-steps*method["multiplier"]*sums
        clips+=int(np.count_nonzero((requested<0)|(requested>2)))
        k=np.clip(requested,0,2);gates+=count
    score=metrics(np.array(outputs),x,protocol["test_record"]["tone_bin"])
    score.update(final_coefficients=k.tolist(),coefficient_clips=clips,gate_counts=gates.tolist(),
                 learning_observations_per_stage=len(x)//120*selected)
    return score


def tail_statistics(states):
    tail=np.asarray(states[len(states)//2:],dtype=float)
    blocks=np.array_split(tail,10)
    mean=np.mean(tail,axis=0);variance=np.var(tail,axis=0)
    bm=np.array([np.mean(b,axis=0) for b in blocks])
    bv=np.array([np.var(b,axis=0) for b in blocks])
    correlations={}
    for lag in (1,100,1000):
        if lag>=len(tail):continue
        centered=tail-mean
        denominator=np.sum(centered*centered,axis=0)
        numerator=np.sum(centered[:-lag]*centered[lag:],axis=0)
        correlations[str(lag)]=[float(n/d) if d>0 else None for n,d in zip(numerator,denominator)]
    return {"state_count":len(tail),"mean":mean.tolist(),"standard_deviation":np.sqrt(variance).tolist(),
            "block_means":bm.tolist(),"block_standard_deviations":np.sqrt(bv).tolist(),
            "block_mean_range":(np.max(bm,axis=0)-np.min(bm,axis=0)).tolist(),
            "second_half_minus_first_half":(np.mean(tail[len(tail)//2:],axis=0)-np.mean(tail[:len(tail)//2],axis=0)).tolist(),
            "autocorrelation":correlations,"confidence_interval_claimed":False}


def analyze(folder):
    protocol=json.loads((folder/"protocol.json").read_text(encoding="utf-8-sig"))
    test=protocol["test_record"]
    xt=test["amplitude"]*np.sin(2*np.pi*test["tone_bin"]*np.arange(test["samples"])/test["samples"])
    tag=np.array([input_tags(test["seed"],n)[1] for n in range(test["samples"])])
    count=protocol["validation_points"]
    xv=np.repeat(-.82+(np.arange(count)+.5)*(1.64/count),4)
    dv=np.tile(np.array([[-1,-1],[-1,1],[1,-1],[1,1]]),(count,1))
    rows=[];references=[]
    for case in protocol["cases"]:
        rawv=plant_arrays(xv,dv[:,0],dv[:,1],case)
        rawt=plant_arrays(xt,tag[:,0],tag[:,1],case)
        for mode,backendindex in (("continuous_reference",4),("sar8",5)):
            q1,q2=rawv[:2];backend=rawv[backendindex]
            # Hierarchical offline reference: rear fit first, then front fit;
            # not a global joint optimum or a new learning algorithm.
            target2=128*4*(rawv[2]-q2/4+dv[:,1]/32)
            rear,_,_,rearinfo=least_squares(backend,target2,32)
            raw1=128*q2+basis(backend,32)@rear-16*dv[:,1]
            target1=2048*xv-512*q1+64*dv[:,0]
            front,_,_,frontinfo=least_squares(raw1,target1,128)
            ref=np.concatenate((front,rear))
            rt=corrected_arrays(rawt[0],rawt[1],rawt[backendindex],tag[:,0],tag[:,1],ref)[0]
            reference={"case":case["name"],"backend":mode,"kind":"offline hierarchical least-squares PWL, not global minimum",
                "rear_projection":rearinfo,"front_projection":frontinfo,"tone":metrics(rt,xt,test["tone_bin"]),
                "coefficients":ref.tolist(),"not_fed_to_learner":True}
            if case["stage1"][1]==case["stage2"][1]==0:
                inverse=np.array([1/case["stage1"][0]]*4+[1/case["stage2"][0]]*4)
                rt=corrected_arrays(rawt[0],rawt[1],rawt[backendindex],tag[:,0],tag[:,1],inverse)[0]
                reference["exact_linear_inverse_tone"]=metrics(rt,xt,test["tone_bin"])
                reference["inverse_coefficients"]=inverse.tolist()
            references.append(reference)
            for method in protocol["methods"]:
                for seed in protocol["seeds"]:
                    stem=f"{case['name']}_{method['name']}_{seed}"
                    meta=json.loads((folder/(stem+".json")).read_text(encoding="utf-8-sig"))
                    modeindex=0 if mode=="continuous_reference" else 1
                    state_file=folder/(stem+("_continuous.bin" if modeindex==0 else "_sar8.bin"))
                    states=np.memmap(state_file,dtype="<f8",mode="r",shape=(method["training_windows"]+1,8))
                    points=[]
                    for w in method["checkpoint_windows"]:
                        k=np.asarray(states[w]).copy()
                        vals=corrected_arrays(rawt[0],rawt[1],rawt[backendindex],tag[:,0],tag[:,1],k)[0]
                        points.append({"windows":w,"conversion_slots":120*w,"learning_observations_per_stage":method["selected"]*w,
                            "coefficients":k.tolist(),"frozen_tone":metrics(vals,xt,test["tone_bin"]),
                            "online_tone":online_score(rawt[0],rawt[1],rawt[backendindex],tag[:,0],tag[:,1],xt,k,method,protocol),
                            "validation_projection":projection(k,q1,q2,backend,dv[:,0],dv[:,1],xv)})
                    fields=("Continuous","Quantized")
                    suffix=fields[modeindex]
                    row={"case":case["name"],"backend":mode,"method":method["name"],"seed":seed,
                        "learning_observations_per_stage":method["selected"]*method["training_windows"],
                        "conversion_slots":120*method["training_windows"],"commits":method["training_windows"],
                        "generated_static_samples":meta["GeneratedSamples"],"gate_counts":meta["GateCounts"+suffix],
                        "nonzero_basis_counts":meta["Basis"+suffix],"gate_and_nonzero_basis_counts":meta["Both"+suffix],
                        "coefficient_clips":meta[suffix+"CoefficientClips"],"selected_output_clips":meta[suffix+"OutputClips"],
                        "physical_overloads":meta["PhysicalOverloads"],"tail":tail_statistics(states),
                        "minimum_coefficients":np.min(states,axis=0).tolist(),"maximum_coefficients":np.max(states,axis=0).tolist(),
                        "checkpoints":points,"state_file":state_file.name,"state_sha256":hashlib.sha256(state_file.read_bytes()).hexdigest()}
                    rows.append(row)
            print(f"scored {case['name']}/{mode}: 10 paths, reference SNDR={reference['tone']['sndr_db']:.4f}",flush=True)
    frozen=json.loads((folder/"source_hashes.json").read_text(encoding="utf-8-sig"))
    assert all(hashlib.sha256(Path(h["Path"]).read_bytes()).hexdigest().upper()==h["Hash"] for h in frozen)
    result={"protocol":protocol["version"],"paths":len(rows),"rows":rows,"offline_references":references,
        "source_hashes_unchanged":True,"chip_fidelity_certified":False,"new_algorithm":False,
        "training_observations_all_path_banks":sum(r["learning_observations_per_stage"] for r in rows)*2,
        "native_static_samples_generated":sum(r["generated_static_samples"] for r in rows)//2,
        "window_commits_all_paths":sum(r["commits"] for r in rows),
        "all_implementation_count_gates_passed":all(r["physical_overloads"]==r["coefficient_clips"]==r["selected_output_clips"]==0 for r in rows),
        "scoring_samples_all_checkpoint_tones":sum(len(r["checkpoints"])*test["samples"]*2 for r in rows)}
    write(folder/"summary.json",result)
    print(json.dumps({k:v for k,v in result.items() if k not in ("rows","offline_references")}),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("folder",type=Path)
    analyze(p.parse_args().folder.resolve())
