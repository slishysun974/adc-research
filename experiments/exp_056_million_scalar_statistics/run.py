"""Frozen million-observation static scalar audit (offline controls only)."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import time

import numpy as np

from adc_research.calibration.gated_lms import GatedLmsConfig, GatedLmsState, update_block_mean
from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.platform.backend_sar import SarConfig, convert
from adc_research.theory.scalar_quantized_dither import scalar_population, scalar_window_law

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = Path(__file__).with_name("protocol.json")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")


def safe_metric(value):
    value = float(value)
    return value if math.isfinite(value) else ("+inf" if value > 0 else "-inf")


def affine_scan(initial, product_sums, alpha, selected, dither):
    """Offline acceleration using ONLY observed R*D sums and known D^2.

    The generator's X and a, and all oracle/theory values, are absent here.
    No clipping is approximated: unsupported factors/states cause failure.
    """
    factors = 1-alpha*product_sums
    if np.any(factors <= 0):
        raise ValueError("positive affine factors required by declared acceleration")
    prefix = np.cumprod(factors, axis=-1)
    if np.min(prefix) < 1e-8:
        raise ValueError("chunk is too long for numerically conditioned prefix scan")
    constant = alpha*selected*dither*dither
    return prefix*(np.asarray(initial)[..., None]+constant*np.cumsum(1/prefix, axis=-1))


def population_rows(protocol, input_spec, method):
    rows = []
    for gain_text in protocol["gains"]:
        for quantizer in protocol["quantizers"]:
            pop = scalar_population(gain=F(gain_text),dither=F(protocol["dither_codes"]),
                low=F(input_spec["low"]),high=F(input_spec["high"]),quantized=quantizer=="floor10")
            law = scalar_window_law(pop,dither=protocol["dither_codes"],
                step=float(F(protocol["base_step"])),selected=method["selected"],multiplier=method["multiplier"])
            rows.append((gain_text,quantizer,pop,law))
    return rows


def scalar_raw(x, dd, gain, quantizer):
    value = gain*(x+dd)
    if np.any(value < -512) or np.any(value >= 512):
        raise ValueError("backend physical overload")
    return np.floor(value+512)-512 if quantizer=="floor10" else value


def preflight(protocol):
    """Cross-check bins/endpoints, affine scan and original block-LMS."""
    sar = SarConfig(bits=10,input_range=(-512,512))
    boundaries = np.arange(-512,513,dtype=float)
    probes = np.concatenate([boundaries,np.nextafter(boundaries,-np.inf),np.nextafter(boundaries,np.inf)])
    floor_discrepancies = 0
    for value in probes:
        got = convert(float(value),sar)
        accelerated = int(np.clip(np.floor(value+512)-512,-512,511))
        assert got.centered_code == accelerated
        floor_discrepancies += int(accelerated != int(np.clip(np.floor(value),-512,511)))
        assert got.overload_low == (value < -512)
        assert got.overload_high == (value >= 512)
    rng = np.random.default_rng(202610560)
    maximum_error = 0.0
    reference_windows = protocol["reference_windows"]
    for inp in protocol["inputs"]:
        low,high = float(F(inp["low"])),float(F(inp["high"]))
        for method in protocol["methods"]:
            n,p = method["selected"],method["multiplier"]
            x = rng.uniform(low,high,(reference_windows,n)) if low < high else np.full((reference_windows,n),low)
            dd = protocol["dither_codes"]*(2*rng.integers(0,2,size=x.shape)-1)
            alpha = float(F(protocol["base_step"]))*p
            for gain_text,quantizer,pop,law in population_rows(protocol,inp,method):
                raw = scalar_raw(x,dd,float(F(gain_text)),quantizer)
                sums = np.sum(dd*raw,axis=-1)
                trace = np.empty(reference_windows+1)
                trace[0] = 1
                chunk = protocol["implementation_chunk_windows"]
                for start in range(0,reference_windows,chunk):
                    end=min(start+chunk,reference_windows)
                    trace[start+1:end+1] = affine_scan(trace[start],sums[start:end],alpha,n,protocol["dither_codes"])
                state = GatedLmsState.unity(1)
                cfg = GatedLmsConfig(512,(alpha*n,))  # mean times n equals declared sum
                direct = 1.0
                for window in range(reference_windows):
                    # Original helper consumes observed raw/dither only.
                    observations = tuple((float(d),state.coefficients[0]*float(r)-float(d))
                                         for d,r in zip(dd[window],raw[window]))
                    state = update_block_mean(state,observations=observations,config=cfg).state
                    direct -= alpha*sum(float(d)*(direct*float(r)-float(d))
                                        for d,r in zip(dd[window],raw[window]))
                    maximum_error = max(maximum_error,abs(trace[window+1]-state.coefficients[0]),
                                        abs(trace[window+1]-direct))
                assert state.sample_count == reference_windows*n
    assert maximum_error <= protocol["kernel_acceptance_max_error"]
    return {"sar_bin_endpoint_probes":len(probes),"floating_offset_vs_exact_floor_probe_differences":floor_discrepancies,
            "original_lms_windows":reference_windows*24,
            "maximum_reference_coefficient_error":maximum_error,"passed":True,
            "higher_gates_and_fixed_point_included":False}


def test_score(raw,dd,x,k,protocol,method,online):
    n,p=method["selected"],method["multiplier"]
    windows = len(x)//120
    rr,ds = raw.reshape(windows,120),dd.reshape(windows,120)
    if online:
        indices = np.arange(120) if n==120 else np.array(method["positions"])
        sums = np.sum(rr[:,indices]*ds[:,indices],axis=-1)
        after = affine_scan(k,sums,float(F(protocol["base_step"]))*p,n,protocol["dither_codes"])
        if np.any(after<0) or np.any(after>2):
            raise ValueError("test online coefficient bounds failure")
        before=np.concatenate(([k],after[:-1]))
        values=(before[:,None]*rr-ds).ravel()
        final=float(after[-1])
    else:
        values=k*raw-dd
        final=float(k)
    metrics=analyze_coherent_tone(values,sample_rate_hz=protocol["test_record"]["sample_rate_hz"],
        fundamental_bin=protocol["test_record"]["fundamental_bin"],full_scale_peak=512).metrics
    return {"mse_codes_squared":float(np.mean((values-x)**2)),
            "mean_error_codes":float(np.mean(values-x)),
            "sndr_db":safe_metric(metrics.sndr_db),"sfdr_dbc":safe_metric(metrics.sfdr_dbc),
            "final_coefficient":final}


def tail_statistics(states,law,protocol):
    tail=states[protocol["tail_start_window"]+1:]
    blocks=tail.reshape(protocol["tail_blocks"],-1)
    mean,var=float(np.mean(tail)),float(np.var(tail))
    sem=math.sqrt(law.stationary_mean_variance(len(tail)))
    drift=float(np.mean(tail[len(tail)//2:])-np.mean(tail[:len(tail)//2]))
    drift_sd=math.sqrt(max(law.adjacent_half_drift_variance(len(tail)//2),0))
    zero=law.stationary_variance==0
    tol=protocol["acceptance"]["zero_variance_absolute_tolerance"]
    z=abs(mean-law.equilibrium)/sem if sem else None
    dz=abs(drift)/drift_sd if drift_sd else None
    ratio=var/law.stationary_variance if not zero else None
    checks={
        "mean": abs(mean-law.equilibrium)<=tol if zero else z<=protocol["acceptance"]["tail_mean_max_predicted_standard_errors"],
        "variance": var<=tol*tol if zero else protocol["acceptance"]["tail_variance_ratio_range"][0]<=ratio<=protocol["acceptance"]["tail_variance_ratio_range"][1],
        "drift":abs(drift)<=tol if zero else dz<=protocol["acceptance"]["tail_drift_max_standard_errors"]}
    centered=tail-mean
    den=float(np.dot(centered,centered))
    acf={str(lag):float(np.dot(centered[:-lag],centered[lag:])/den) if den else None
         for lag in (1,100,1000)}
    return {"states":len(tail),"mean":mean,"variance":var,"standard_deviation":math.sqrt(var),
            "predicted_correlated_mean_standard_error":sem,"mean_error_standard_errors":z,
            "iid_effective_state_count":law.stationary_variance/sem**2 if sem else None,
            "variance_ratio":ratio,"second_half_minus_first_half":drift,"drift_standard_errors":dz,
            "block_means":[float(v) for v in np.mean(blocks,axis=1)],
            "block_variances":[float(v) for v in np.var(blocks,axis=1)],
            "autocorrelation":acf,"checks":checks,"passed":all(checks.values())}


def run_group(protocol,inp,method,seed,input_index,method_index,output):
    stream=np.random.SeedSequence([seed,input_index,method_index]).spawn(2)
    rx,rd=(np.random.default_rng(v) for v in stream)
    models=population_rows(protocol,inp,method)
    total=protocol["total_windows"]
    states=np.empty((len(models),total+1)); states[:,0]=1
    sums=np.empty((len(models),total))
    low,high=float(F(inp["low"])),float(F(inp["high"]))
    n,p=method["selected"],method["multiplier"]
    alpha=float(F(protocol["base_step"]))*p
    chunk=protocol["implementation_chunk_windows"]
    floating_floor_discrepancies = [0]*len(models)
    for start in range(0,total,chunk):
        end=min(start+chunk,total)
        x=rx.uniform(low,high,(end-start,n)) if low<high else np.full((end-start,n),low)
        dd=protocol["dither_codes"]*(2*rd.integers(0,2,size=x.shape)-1)
        for j,(gain,quantizer,pop,law) in enumerate(models):
            raw=scalar_raw(x,dd,float(F(gain)),quantizer)
            if quantizer=="floor10":
                floating_floor_discrepancies[j] += int(np.count_nonzero(raw!=np.floor(float(F(gain))*(x+dd))))
            sums[j,start:end]=np.sum(raw*dd,axis=-1)
        states[:,start+1:end+1]=affine_scan(states[:,start],sums[:,start:end],alpha,n,protocol["dither_codes"])
    if not np.all(np.isfinite(states)) or np.min(states)<0 or np.max(states)>2:
        raise ValueError("coefficient bounds failure; saturation is not silently dropped")
    replay=(1-alpha*sums)*states[:,:-1]+alpha*n*protocol["dither_codes"]**2
    replay_error=float(np.max(np.abs(replay-states[:,1:])))
    assert replay_error <= protocol["acceptance"]["reference_and_replay_error"]
    group_id=f"{inp['name']}_{method['name']}_{seed}"
    np.savez(output/f"{group_id}.npz",states=states,observed_dither_raw_sums=sums)
    test=protocol["test_record"]
    x_test=test["amplitude_codes"]*np.sin(2*np.pi*test["fundamental_bin"]*np.arange(test["samples"])/test["samples"])
    d_test=protocol["dither_codes"]*(2*np.random.default_rng(test["dither_seed"]).integers(0,2,test["samples"])-1)
    rows=[]
    for j,(gain,quantizer,pop,law) in enumerate(models):
        raw_test=scalar_raw(x_test,d_test,float(F(gain)),quantizer)
        checkpoint=[]
        for w in protocol["checkpoint_windows"]:
            k=float(states[j,w])
            checkpoint.append({"windows":w,"conversion_slots":120*w,"learning_observations":n*w,
                "coefficient":k,"predicted_ensemble_mean":law.mean(w),
                "frozen_tone":test_score(raw_test,d_test,x_test,k,protocol,method,False),
                "online_tone":test_score(raw_test,d_test,x_test,k,protocol,method,True)})
        equilibrium=law.equilibrium
        mse_at_root=max(pop.mse(equilibrium),0.0)
        expected_mse=mse_at_root+law.stationary_variance*float(pop.raw_second_moment)
        row={"id":f"{group_id}_{gain.replace('/','-')}_{quantizer}","input":inp["name"],
             "gain":gain,"quantizer":quantizer,"method":method["name"],"seed":seed,
             "conversion_slots":120*total,"learning_observations":n*total,"commits":total,
             "active_single_coefficient_observations":n*total,"higher_gate_observations":None,
             "backend_overloads":0,"coefficient_clips":0,"minimum_coefficient":float(states[j].min()),
             "floating_offset_vs_exact_floor_learning_differences":floating_floor_discrepancies[j],
             "maximum_coefficient":float(states[j].max()),"replay_error":replay_error,
             "population_exact":{key:str(value) for key,value in asdict(pop).items()},
             "law":asdict(law),"inverse_gain":1/float(F(gain)),"inverse_gain_offset":equilibrium-1/float(F(gain)),
             "population_mse_minimizer":float(pop.mse_minimizer),
             "population_mse_at_mean_root":mse_at_root,
             "population_mse_at_unit":max(pop.mse(1),0.0),
             "stationary_expected_population_mse":expected_mse,
             "stationary_learning_noise_mse":law.stationary_variance*float(pop.raw_second_moment),
             "tail":tail_statistics(states[j],law,protocol),"checkpoints":checkpoint,
             "root_frozen_tone":test_score(raw_test,d_test,x_test,equilibrium,protocol,method,False),
             "inverse_frozen_tone":test_score(raw_test,d_test,x_test,1/float(F(gain)),protocol,method,False),
             "state_file":f"{group_id}.npz","state_row":j}
        rows.append(row)
    write(output/f"{group_id}.json",rows)
    print(f"{group_id}: 4 paths, learning/path={n*total}, checks={sum(r['tail']['passed'] for r in rows)}/4, replay={replay_error:.2g}",flush=True)
    return rows


def run(output,only_preflight=False):
    output.relative_to(ROOT/"artifacts/runs/EXP_056")
    output.mkdir(parents=True,exist_ok=False)
    protocol_bytes=PROTOCOL.read_bytes()
    (output/"protocol.json").write_bytes(protocol_bytes)
    protocol=json.loads(protocol_bytes)
    files=[PROTOCOL,Path(__file__),ROOT/"src/adc_research/theory/scalar_quantized_dither.py",
           ROOT/"configs/architectures/gu_behavioral_v1.yaml"]
    for folder in ("calibration","platform"):
        files+=sorted((ROOT/f"src/adc_research/{folder}").glob("*.py"))
    files+=sorted((ROOT/"rtl").rglob("*.v"))
    frozen={str(p.relative_to(ROOT)):digest(p) for p in files}
    write(output/"source_sha256.json",frozen)
    start=time.perf_counter()
    pre=preflight(protocol)
    write(output/"preflight.json",pre)
    print(f"preflight passed, original LMS max error={pre['maximum_reference_coefficient_error']:.3g}",flush=True)
    if only_preflight:
        return
    rows=[]
    for ii,inp in enumerate(protocol["inputs"]):
        for mi,method in enumerate(protocol["methods"]):
            for seed in protocol["seeds"]:
                rows+=run_group(protocol,inp,method,seed,ii,mi,output)
    assert PROTOCOL.read_bytes()==protocol_bytes
    for path,sha in frozen.items():
        assert digest(ROOT/path)==sha,path
    summary={"version":protocol["version"],"protocol_sha256":digest(PROTOCOL),"preflight":pre,
             "paths":len(rows),"rows":rows,"all_statistical_checks_passed":all(r["tail"]["passed"] for r in rows),
             "learning_observation_evaluations":sum(r["learning_observations"] for r in rows),
             "independent_latent_scalar_observations_generated":sum(r["learning_observations"] for r in rows)//4,
             "inferred_conversion_slots_all_paths":sum(r["conversion_slots"] for r in rows),
             "window_commits_all_paths":sum(r["commits"] for r in rows),
             "new_two_stage_adc_platform_conversions":0,"chip_fidelity_certified":False,
             "new_online_algorithm":False,"rtl_changed":False,"source_hashes_unchanged":True,
             "elapsed_seconds":time.perf_counter()-start}
    write(output/"summary.json",summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ("rows","preflight")}),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output",type=Path)
    parser.add_argument("--preflight-only",action="store_true")
    args=parser.parse_args()
    run(args.output.resolve(),args.preflight_only)
