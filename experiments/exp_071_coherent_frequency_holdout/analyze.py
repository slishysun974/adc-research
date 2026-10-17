"""Frozen complete-block scores/prediction tests; all seeds and failures."""
import argparse
from pathlib import Path
import traceback

import numpy as np

from adc_research.theory.finite_output_acceptance import benefit,group_scores,intervals
from experiments.exp_057_static_two_stage_million.common import metrics
from experiments.exp_062_same_input_background.analyze import stability
from experiments.exp_070_gu_learning_rate_switch.analyze import independent_score,finite_terms
from experiments.exp_062_same_input_background.verify import round_ratio
from .prepare import load,write,digest,check
from .verify import states


def analyze(folder):
    check(folder);p=load(folder/'protocol.json');plan=load(folder/'runplan.json')
    assert not plan['preflight'] and load(folder/'verification.json')['passed']
    rows=[];units=[];blocks=0;fft=0
    for task in plan['tasks']:
        stem=task['stem'];nw=task['windows'];desc=task['paths'];meta=load(folder/(stem+'.json'))
        tone=np.fromfile(folder/(task['case']+'_tone.bin'),dtype='<f8');n=len(tone)
        output=np.memmap(folder/(stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(nw*120,4))
        unit=np.memmap(folder/(stem+'_unit_outputs.bin'),dtype='<i2',mode='r',shape=(nw*120,))
        scores=[[] for _ in range(4)];us=[]
        for b in range(128):
            sl=slice(n*b,n*(b+1));records=[unit[sl]]+[output[sl,h] for h in range(4)]
            sc=[];spectra=[]
            for y in records:
                score=metrics(y,tone,task['tone_bin']);spec,signal=independent_score(y,tone,task['tone_bin'],score)
                score['signal_power']=signal;sc.append(score);spectra.append(spec);blocks+=1;fft+=2
            us.append(sc[0])
            for h in range(4):
                score=sc[h+1];score['gain_sndr_db']=score['sndr_db']-sc[0]['sndr_db']
                score['gain_sfdr_dbc']=score['sfdr_dbc']-sc[0]['sfdr_dbc']
                score['unit_terms']=finite_terms(records[h+1],records[0],tone,spectra[h+1],spectra[0])
                if desc[h]['rate']=='quarter':
                    base=next(j for j,d in enumerate(desc) if d['rate']=='base' and d['method']==desc[h]['method'])
                    score['base_terms']=finite_terms(records[h+1],records[base+1],tone,spectra[h+1],spectra[base+1])
                scores[h].append(score)
        def statistics(sc,lo,hi):
            fields=('mse_codes_squared','mae_codes','mean_error_codes','sndr_db','sfdr_dbc','signal_power','residual_power')
            value={key:float(np.mean([s[key] for s in sc[lo:hi]])) for key in fields}
            value['pooled_sndr_db']=float(10*np.log10(value['signal_power']/value['residual_power']))
            return value
        units.append({'case':task['case'],'role':task['role'],'tone_bin':task['tone_bin'],'seed':task['seed'],
                      'startup':statistics(us,0,24),'tail':statistics(us,64,128),'block_scores':us})
        for h,d in enumerate(desc):
            ss=states(folder,stem,d['name'],nw);effective=round_ratio(np.asarray(ss[:-1],dtype=np.int64),4096)/1024
            support=[b['Selected'][h]['Both'] for b in meta['Blocks']]
            sc=scores[h]
            acceptance=intervals([bool(benefit(a,u)) for a,u in zip(group_scores(sc),group_scores(us),strict=True)])
            old=stability(sc,np.asarray(ss,dtype=float)/(1<<22),support,
                          {'empirical_convergence':p['empirical_coefficient_stability'],'input':p['input']})
            tail=effective[64*256:]
            rows.append({'case':task['case'],'role':task['role'],'tone_bin':task['tone_bin'],'seed':task['seed'],'method':d['method'],'rate':d['rate'],
                'startup':statistics(sc,0,24),'tail':statistics(sc,64,128),'unit_tail':statistics(us,64,128),
                'finite_output':acceptance,'old_stability':old,'block_scores':sc,
                'tail_coefficient_mean':tail.mean(axis=0).tolist(),'tail_coefficient_std':tail.std(axis=0).tolist(),
                'selected_joint_support':np.sum(support,axis=0).tolist(),
                'counters':{key:np.sum([b[key][h] for b in meta['Blocks']],axis=0).tolist() for key in ('ZeroRequest','NonzeroSumZero','HiddenChanged','ExportChanged')},
                'learning_observations_per_stage':nw*d['selected'],'coefficient_saturations':meta['CoefficientClips'][h],'q3_output_clips':meta['OutputClips'][h]})
        print('scored complete blocks',stem,flush=True)
    assert blocks==p['long_budget']['complete_score_blocks_online_plus_unit'] and fft==p['long_budget']['ordinary_fft_calls']
    pairs=[]
    for quarter in [r for r in rows if r['rate']=='quarter']:
        base=next(r for r in rows if r['case']==quarter['case'] and r['seed']==quarter['seed'] and r['method']==quarter['method'] and r['rate']=='base')
        pairs.append({'case':quarter['case'],'role':quarter['role'],'seed':quarter['seed'],'method':quarter['method'],
            'quarter_tail_mse':quarter['tail']['mse_codes_squared'],'base_tail_mse':base['tail']['mse_codes_squared'],
            'quarter_tail_strictly_lower':quarter['tail']['mse_codes_squared']<base['tail']['mse_codes_squared'],
            'quarter_startup_mse':quarter['startup']['mse_codes_squared'],'base_startup_mse':base['startup']['mse_codes_squared'],
            'quarter_startup_no_lower':quarter['startup']['mse_codes_squared']>=base['startup']['mse_codes_squared']})
    confirmation=[r for r in pairs if r['role']=='gu_confirmation']
    predictions={'tail_all_methods_all_seeds':{'passed':all(r['quarter_tail_strictly_lower'] for r in confirmation),
        'pairs':len(confirmation),'counterexamples':[r for r in confirmation if not r['quarter_tail_strictly_lower']]},
        'full120_startup_all_seeds':{'passed':all(r['quarter_startup_no_lower'] for r in confirmation if r['method']=='full120'),
        'pairs':sum(r['method']=='full120' for r in confirmation),'counterexamples':[r for r in confirmation if r['method']=='full120' and not r['quarter_startup_no_lower']]}}
    summary=[]
    for case in p['cases']:
        for method in p['methods']:
            for rate in p['rate_scales']:
                group=[r for r in rows if r['case']==case['name'] and r['method']==method['name'] and r['rate']==rate['name']]
                assert len(group)==5
                summary.append({'case':case['name'],'role':case['role'],'tone_bin':case['tone_bin'],'method':method['name'],'rate':rate['name'],
                    'tail_mse_mean':float(np.mean([r['tail']['mse_codes_squared'] for r in group])),
                    'tail_mse_range':[min(r['tail']['mse_codes_squared'] for r in group),max(r['tail']['mse_codes_squared'] for r in group)],
                    'unit_tail_mse_mean':float(np.mean([r['unit_tail']['mse_codes_squared'] for r in group])),
                    'startup_mse_mean':float(np.mean([r['startup']['mse_codes_squared'] for r in group])),
                    'tail_block_sndr_mean_db':float(np.mean([r['tail']['sndr_db'] for r in group])),
                    'tail_residual_power_mean':float(np.mean([r['tail']['residual_power'] for r in group])),
                    'unit_mse_improved_seeds':sum(r['tail']['mse_codes_squared']<r['unit_tail']['mse_codes_squared'] for r in group),
                    'finite_output_ever':sum(r['finite_output']['first_pass_block'] is not None for r in group),
                    'finite_output_terminal':sum(r['finite_output']['terminal_pass'] for r in group),
                    'finite_output_later_violations':sum(r['finite_output']['later_violations'] for r in group),
                    'old_stability_ever':sum(r['old_stability']['first_satisfying_block_exclusive'] is not None for r in group),
                    'old_stability_terminal':sum(r['old_stability']['intervals'][-1]['passed'] for r in group)})
    check(folder)
    result={'paths':rows,'units':units,'paired_predictions':pairs,'predictions':predictions,'summary':summary,
            'score_blocks':blocks,'ordinary_fft_calls':fft,'numerically_certified_fft':False,
            'all_seeds_and_blocks_retained':True,'confirmation_consumed':True,'future_reservation_opened':False,
            'confidence_interval_or_failure_probability_claimed':False,'asymptotic_convergence_proved':False}
    write(folder/'analysis.json',result);write(folder/'summary.json',{'summary':summary,'predictions':predictions})
    write(folder/'score_verification.json',{'passed':True,'blocks':blocks,'ordinary_fft_calls':fft,
        'independent_mse_dc_full_complex_spectrum':True,'all_unit_and_base_mse_spectral_cross_identities':True,'numerically_certified_fft':False})
    write(folder/'delivery_hashes.json',{f.name:digest(f) for f in folder.iterdir() if f.is_file() and f.name!='delivery_hashes.json'})
    print('scores and predictions verified',predictions,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);a=parser.parse_args()
    try:analyze(a.folder.resolve())
    except Exception:
        write(a.folder/'analysis_failure.json',{'traceback':traceback.format_exc()});raise
