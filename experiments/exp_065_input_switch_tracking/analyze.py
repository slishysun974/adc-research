"""Short switch diagnostics only: no incomplete sine spectra or recovery claim."""
import argparse
import json
from pathlib import Path
import traceback

import numpy as np

from experiments.exp_057_static_two_stage_million.common import write
from experiments.exp_061_static_auxiliary_million.verify import sources
from experiments.exp_062_same_input_background.verify import digital, round_ratio
from .verify import load, check_nominal


def mse_difference(y, reference, target):
    e = reference-target
    d = y-reference
    change = float(np.mean(d*d))
    cross = float(2*np.mean(e*d))
    actual = float(np.mean((y-target)**2)-np.mean(e*e))
    assert abs(actual-change-cross) < 1e-9*max(1, abs(actual))
    return {'mse_difference': actual, 'output_change_power': change, 'reference_error_cross': cross}


def analyze(folder):
    p, _ = load(folder)
    assert json.loads((folder/'verification.json').read_text())['passed']
    check_nominal(folder, folder.parents[3]/p['nominal_folder'])
    prefix=p['preflight']['prefix_windows']; post=p['preflight']['post_windows']; seed=p['seeds'][0]
    n=p['input']['samples_per_block']; start=p['switch']['global_conversion']
    tone=np.fromfile(folder/'tone.bin',dtype='<f8')
    target=2048*(1+p['input']['scale_after']*tone[(start+np.arange(120*post))%n])
    rows=[]
    for case in p['cases']:
        streams={}; states={}
        for variant in ('carry','fresh'):
            stem=f"{case['name']}_{variant}_{seed}"; pre=prefix if variant=='carry' else 0
            words=np.memmap(folder/(stem+'_words.bin'),dtype='i1',mode='r',shape=(pre+post,120,4))[pre:]
            codes=np.memmap(folder/(stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(pre+post,120,3))[pre:].reshape(-1,3)
            streams[variant]=(words,codes)
            states[variant]=[np.memmap(folder/(stem+'_'+m['name']+'_q22.bin'),dtype='<f8',mode='r',shape=(pre+post+1,8))[pre:] for m in p['methods']]
        for m, method in enumerate(p['methods']):
            stats={}
            for variant in ('carry','fresh'):
                words,codes=streams[variant]; st=states[variant][m]
                acc=np.rint(st*(1<<22)).astype(np.int64)
                _,g,b,pr=digital(words,acc[:-1]); selected=method['selected']
                stats[variant]={
                    'initial_Q22':acc[0].tolist(),'initial_Q1_10':round_ratio(acc[0],4096).tolist(),
                    'final_Q22':acc[-1].tolist(),'final_Q1_10':round_ratio(acc[-1],4096).tolist(),
                    'hidden_changed':np.sum(acc[:-1]!=acc[1:],axis=0).tolist(),
                    'export_changed':np.sum(round_ratio(acc[:-1],4096)!=round_ratio(acc[1:],4096),axis=0).tolist(),
                    'selected_gates':g[:,:selected].sum(axis=(0,1)).tolist(),
                    'selected_basis':b[:,:selected].sum(axis=(0,1)).tolist(),
                    'selected_joint':(g[:,:selected]&b[:,:selected]).sum(axis=(0,1)).tolist(),
                    'selected_correlations':pr[:,:selected].sum(axis=(0,1)).tolist(),
                    'all_gates':g.sum(axis=(0,1)).tolist(),'all_basis':b.sum(axis=(0,1)).tolist(),
                    'all_joint':(g&b).sum(axis=(0,1)).tolist()}
            carry=streams['carry'][1][:,m+1].astype(float); fresh=streams['fresh'][1][:,m+1].astype(float)
            unit=streams['fresh'][1][:,0].astype(float)
            row={'case':case['name'],'method':method['name'],'seed':seed,
                 'post_conversions':len(target),'statistics':stats,
                 'first_window_carry_mse':float(np.mean((carry[:120]-target[:120])**2)),
                 'first_window_fresh_mse':float(np.mean((fresh[:120]-target[:120])**2)),
                 'short_carry_mse':float(np.mean((carry-target)**2)),
                 'short_fresh_mse':float(np.mean((fresh-target)**2)),
                 'short_unit_mse':float(np.mean((unit-target)**2)),
                 'paired_mse_identity':mse_difference(carry,fresh,target),
                 'carry_unit_identity':mse_difference(carry,unit,target),
                 'fresh_unit_identity':mse_difference(fresh,unit,target),
                 'post_output_differences':int(np.count_nonzero(carry!=fresh)),
                 'maximum_paired_code_difference':float(np.max(np.abs(carry-fresh)))}
            # First switched window reads its inherited old state throughout:
            # a separate frozen-state digital replay has identical120 outputs.
            initial=np.repeat(np.rint(states['carry'][m][0]*(1<<22)).astype(np.int64)[None,:],post,axis=0)
            frozen=digital(streams['carry'][0],initial)[0].ravel()
            assert np.array_equal(frozen[:120],carry[:120])
            row['first_window_frozen_inherited_codes_identical']=True
            row['later_online_vs_frozen_changed_codes']=int(np.count_nonzero(frozen[120:]!=carry[120:]))
            rows.append(row)
            print('short diagnostic',case['name'],method['name'],'carry/fresh MSE',row['short_carry_mse'],row['short_fresh_mse'],flush=True)
    sources(folder)
    write(folder/'analysis.json',{'paths':rows,'finite_MSE_cross_passed':True,
        'first_window_old_state_readout_verified':True,'sine_spectrum_reported':False,
        'recovery_evaluated':False,'short_performance_ranking_claimed':False})


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('folder',type=Path); folder=parser.parse_args().folder.resolve()
    try: analyze(folder)
    except Exception:
        write(folder/'analysis_failure.json',{'traceback':traceback.format_exc()}); raise
