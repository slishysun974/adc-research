"""Independent scalar replay and population-integral audit of EXP-056."""

from __future__ import annotations

import argparse
from collections import defaultdict
from fractions import Fraction as F
import json
import math
from pathlib import Path

import numpy as np


def alternate_population(gain,dither,low,high,quantized):
    """Split X at union of BOTH signs' thresholds, then integrate polynomials."""
    ex=(low+high)/2
    ex2=(low*low+low*high+high*high)/3
    fields={key:F(0) for key in ("correlation","product_second_moment","raw_mean",
                                "raw_second_moment","raw_target_cross_moment")}
    cuts={low,high}
    if quantized and low<high:
        for sign in (-1,1):
            for boundary in range(math.floor(gain*(low+sign*dither)),math.ceil(gain*(high+sign*dither))+1):
                x=F(boundary)/gain-sign*dither
                if low<x<high:
                    cuts.add(x)
    cells=[(low,high)] if low==high else list(zip(sorted(cuts)[:-1],sorted(cuts)[1:]))
    for left,right in cells:
        probability=F(1) if low==high else (right-left)/(high-low)
        x=(left+right)/2
        x2=(left*left+left*right+right*right)/3
        for sign in (-1,1):
            dd=sign*dither
            weight=probability/2
            if quantized:
                rr=F(math.floor(gain*(x+dd)))
                er,er2,cross=rr,rr*rr,rr*(x+dd)
            else:
                er=gain*(x+dd)
                er2=gain*gain*(x2+2*x*dd+dd*dd)
                cross=gain*(x2+2*x*dd+dd*dd)
            fields["correlation"]+=weight*dd*er
            fields["product_second_moment"]+=weight*dd*dd*er2
            fields["raw_mean"]+=weight*er
            fields["raw_second_moment"]+=weight*er2
            fields["raw_target_cross_moment"]+=weight*cross
    fields.update(target_second_moment=ex2+dither*dither,input_mean=ex,
                  quantization_error_correlation=fields["correlation"]-gain*dither*dither)
    return fields


def verify(folder):
    protocol=json.loads((folder/"protocol.json").read_text(encoding="utf-8"))
    summary=json.loads((folder/"summary.json").read_text(encoding="utf-8"))
    specs={i["name"]:i for i in protocol["inputs"]}
    methods={m["name"]:m for m in protocol["methods"]}
    maximum_state_error=0.0
    transitions=0
    exact_checks=0
    groups=defaultdict(list)
    test=protocol["test_record"]
    xt=test["amplitude_codes"]*np.sin(2*np.pi*test["fundamental_bin"]*np.arange(test["samples"])/test["samples"])
    dt=protocol["dither_codes"]*(2*np.random.default_rng(test["dither_seed"]).integers(0,2,test["samples"])-1)
    score_checks=0
    max_mse_error=0.0
    max_spectral_db_error=0.0
    near_zero_spectral_records=0
    # Each recorded group is read once; replay every window using a plain loop.
    by_file=defaultdict(list)
    for row in summary["rows"]:
        by_file[row["state_file"]].append(row)
    for filename,rows in by_file.items():
        with np.load(folder/filename) as archive:
            states=archive["states"]
            sums=archive["observed_dither_raw_sums"]
        for row in rows:
            j=row["state_row"]
            method=methods[row["method"]]
            n,p=method["selected"],method["multiplier"]
            alpha=float(F(protocol["base_step"]))*p
            c=alpha*n*protocol["dither_codes"]**2
            k=1.0
            error=0.0
            for value,recorded in zip(sums[j],states[j,1:]):
                k=(1-alpha*float(value))*k+c
                error=max(error,abs(k-float(recorded)))
            transitions+=len(sums[j])
            maximum_state_error=max(maximum_state_error,error)
            assert error<=protocol["acceptance"]["reference_and_replay_error"]
            tail=states[j,protocol["tail_start_window"]+1:]
            assert abs(float(np.mean(tail))-row["tail"]["mean"])<1e-12
            assert abs(float(np.var(tail))-row["tail"]["variance"])<1e-12
            assert len(tail)==row["tail"]["states"]
            for point in row["checkpoints"]:
                assert point["coefficient"]==float(states[j,point["windows"]])
                assert point["learning_observations"]==point["windows"]*n
                assert point["conversion_slots"]==point["windows"]*120
            raw=float(F(row["gain"]))*(xt+dt)
            if row["quantizer"]=="floor10":
                raw=np.floor(raw+512)-512
            rr,dd=raw.reshape(-1,120),dt.reshape(-1,120)
            indices=list(range(120)) if n==120 else method["positions"]
            for point in row["checkpoints"]:
                for online in (False,True):
                    k=point["coefficient"]
                    if online:
                        out=np.empty_like(rr)
                        for window in range(len(rr)):
                            out[window]=k*rr[window]-dd[window]
                            k -= alpha*float(np.dot(dd[window,indices],out[window,indices]))
                        values=out.ravel()
                        score=point["online_tone"]
                    else:
                        values=k*raw-dt
                        score=point["frozen_tone"]
                    mse=float(np.mean((values-xt)**2))
                    max_mse_error=max(max_mse_error,abs(mse-score["mse_codes_squared"]))
                    assert abs(mse-score["mse_codes_squared"])<=1e-8*max(1,mse)
                    assert abs(float(np.mean(values-xt))-score["mean_error_codes"])<=2e-8
                    assert abs(k-score["final_coefficient"])<=protocol["acceptance"]["reference_and_replay_error"]
                    spectrum=np.fft.rfft(values-np.mean(values))/len(values)
                    power=np.abs(spectrum)**2
                    power[1:-1]*=2
                    signal=power[test["fundamental_bin"]]
                    power[[0,test["fundamental_bin"]]]=0
                    residual=float(np.sum(power))
                    # Independent masked sum avoids library cancellation for
                    # nearly exact ideal tones; those dB figures are not exact.
                    if residual>1e-6:
                        sndr=10*math.log10(signal/residual)
                        sfdr=10*math.log10(signal/float(np.max(power)))
                        difference=max(abs(sndr-score["sndr_db"]),abs(sfdr-score["sfdr_dbc"]))
                        max_spectral_db_error=max(max_spectral_db_error,difference)
                        assert difference<=1e-4
                    else:
                        near_zero_spectral_records+=1
                    score_checks+=1
            spec=specs[row["input"]]
            pop=alternate_population(F(row["gain"]),F(protocol["dither_codes"]),
                F(spec["low"]),F(spec["high"]),row["quantizer"]=="floor10")
            assert all(value==F(row["population_exact"][key]) for key,value in pop.items())
            exact_checks+=len(pop)
            groupkey=(row["input"],row["gain"],row["quantizer"],row["method"])
            groups[groupkey].append(row)
        print(f"verified {filename}: {len(rows)*protocol['total_windows']} states",flush=True)
    table=[]
    for key,rows in groups.items():
        means=np.array([r["tail"]["mean"] for r in rows])
        root=rows[0]["law"]["equilibrium"]
        individual_sem=rows[0]["tail"]["predicted_correlated_mean_standard_error"]
        group_sem=individual_sem/math.sqrt(len(rows))
        z=abs(float(np.mean(means))-root)/group_sem if group_sem else None
        observed_sd=float(np.mean([r["tail"]["standard_deviation"] for r in rows]))
        ratio=[r["tail"]["variance_ratio"] for r in rows]
        table.append({"input":key[0],"gain":key[1],"quantizer":key[2],"method":key[3],
            "seeds":len(rows),"mean_root":root,"tail_mean_across_seeds":float(np.mean(means)),
            "tail_standard_deviation_mean":observed_sd,
            "group_mean_standard_errors":z,"group_mean_standard_error":group_sem,
            "variance_ratio_min":min(v for v in ratio if v is not None) if group_sem else None,
            "variance_ratio_max":max(v for v in ratio if v is not None) if group_sem else None,
            "frozen_final_sndr_db":[r["checkpoints"][-1]["frozen_tone"]["sndr_db"] for r in rows],
            "online_final_sndr_db":[r["checkpoints"][-1]["online_tone"]["sndr_db"] for r in rows],
            "frozen_final_sfdr_dbc":[r["checkpoints"][-1]["frozen_tone"]["sfdr_dbc"] for r in rows],
            "online_final_sfdr_dbc":[r["checkpoints"][-1]["online_tone"]["sfdr_dbc"] for r in rows],
            "unit_sndr_db":rows[0]["checkpoints"][0]["frozen_tone"]["sndr_db"],
            "stationary_expected_population_mse":rows[0]["stationary_expected_population_mse"],
            "unit_population_mse":rows[0]["population_mse_at_unit"]})
    # This aggregate is diagnostic, not an extra post-result selection gate.
    result={"passed":True,"direct_scalar_replay_transitions":transitions,
        "maximum_state_replay_error":maximum_state_error,"independent_fraction_moment_checks":exact_checks,
        "independent_fixed_and_online_score_records":score_checks,"maximum_score_mse_error":max_mse_error,
        "maximum_resolved_spectral_db_error":max_spectral_db_error,
        "near_zero_residual_spectral_records_not_db_certified":near_zero_spectral_records,
        "independent_seed_groups":len(groups),"shared_cells_are_independent_repeats":False,
        "largest_individual_mean_z":max(r["tail"]["mean_error_standard_errors"] or 0 for r in summary["rows"]),
        "largest_individual_drift_z":max(r["tail"]["drift_standard_errors"] or 0 for r in summary["rows"]),
        "total_float_floor_learning_differences":sum(r["floating_offset_vs_exact_floor_learning_differences"] for r in summary["rows"]),
        "groups":table}
    (folder/"verification.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="groups"}),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder",type=Path)
    verify(parser.parse_args().folder.resolve())
