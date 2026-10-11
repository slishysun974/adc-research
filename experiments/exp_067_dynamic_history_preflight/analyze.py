"""Finite support/history/short-MSE diagnostics; no incomplete-record spectrum."""

import argparse
import json
from pathlib import Path

import numpy as np

from experiments.exp_057_static_two_stage_million.common import write
from experiments.exp_065_input_switch_tracking.verify import digital
from experiments.exp_067_dynamic_history_preflight.verify import load_rows, acc


def cross(reference, changed, target):
    error=reference-target;delta=changed-reference
    lhs=float(np.mean((changed-target)**2)-np.mean(error**2))
    power=float(np.mean(delta**2));interaction=float(2*np.mean(error*delta))
    assert abs(lhs-power-interaction)<2e-10
    return {'reference_mse':float(np.mean(error**2)),'changed_mse':float(np.mean((changed-target)**2)),
        'mse_difference':lhs,'output_change_power':power,'twice_error_cross':interaction,
        'identity_error':abs(lhs-power-interaction),'changed_codes':int(np.count_nonzero(delta))}


def analyze(folder):
    assert json.loads((folder/'verification.json').read_text(encoding='utf-8'))['passed']
    p=json.loads((folder/'protocol.json').read_text(encoding='utf-8'))
    result=[];cache={}
    for case in p['cases']:
        for phase in p['phases']:
            name=case['name']+'_'+phase['name'];rows=load_rows(folder/(name+'_records.jsonl.gz'))
            windows=load_rows(folder/(name+'_windows.jsonl.gz'));n=len(rows)
            output=np.array([r['online'] for r in rows]);unit=np.array([r['unit'] for r in rows]);target=2048*(np.array([r['x'] for r in rows])+1)
            words=np.array([r['word']+[(r['d'][0]>0)+2*(r['d'][1]>0)] for r in rows]).reshape(-1,120,4)
            entries=[]
            for m,method in enumerate(p['methods']):
                before=np.array([acc(w['before'][m]) for w in windows]);after=np.array([acc(w['after'][m]) for w in windows])
                _,g,b,prod=digital(words,before);selected=np.arange(120)<4 if method['name']=='point30' else np.ones(120,dtype=bool)
                counts={}
                for label,mask in [('all',np.ones(120,dtype=bool)),('selected',selected)]:
                    counts[label]={'observations':int(len(windows)*np.count_nonzero(mask)),
                        'gate':g[:,mask].sum(axis=(0,1)).tolist(),'basis':b[:,mask].sum(axis=(0,1)).tolist(),
                        'joint':(g[:,mask]&b[:,mask]).sum(axis=(0,1)).tolist(),
                        'correlation_sum_codes_squared':prod[:,mask].sum(axis=(0,1)).tolist()}
                item={'method':method['name'],'counts':counts,
                    'q22_change_counts':np.count_nonzero(after!=before,axis=0).tolist(),
                    'export_change_counts': [sum(w['after'][m][bank]['coefficient_change_counts'][j] for w in windows[-1:]) for bank in ('stage1','stage2') for j in range(4)],
                    'final_q22':after[-1].tolist(),'unit_online_cross':cross(unit,output[:,m],target)}
                if phase['name']!='static':
                    nominal=cache[case['name']]
                    item['static_pair_cross']=cross(nominal['online'][:,m],output[:,m],target)
                entries.append(item)
            item={'case':case['name'],'phase':phase['name'],'conversions':n,'methods':entries,
                  'unit_mse':float(np.mean((unit-target)**2)),
                  'actual_minus_target_mean':(np.array([r['outputs'] for r in rows])-np.array([r['targets'] for r in rows])).mean(axis=0).tolist()}
            if phase['name']=='static':cache[case['name']]={'online':output,'words':words,'unit':unit}
            else:
                nominal=cache[case['name']]
                item['static_word_changes']={key:int(np.count_nonzero(words[:,:,j]!=nominal['words'][:,:,j])) for j,key in enumerate(('q1','q2','backend'))}
                item['unit_static_pair_cross']=cross(nominal['unit'],unit,target)
            result.append(item)
    write(folder/'analysis.json',{'passed':True,'records':result,'identities':36,
        'scope':'3840 startup conversions per stream; finite MSE and support only, no coherent spectrum, stability, optimality or chip inference'})
    print('18 own-unit and18 static-pair finite MSE identities; all selected/full support diagnostics saved',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path)
    analyze(parser.parse_args().folder.resolve())
