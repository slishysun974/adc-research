"""Finite dynamic benefit, old-state four-grid and frozen empirical criterion."""
import argparse
import json
from pathlib import Path
import traceback

import numpy as np

from experiments.exp_057_static_two_stage_million.common import metrics, write
from experiments.exp_061_static_auxiliary_million.verify import sources
from experiments.exp_062_same_input_background.analyze import stability, tail_statistics, net_terms
from experiments.exp_065_input_switch_tracking.verify import digital
from experiments.exp_066_input_switch_tracking_long.analyze import independent_score
from .verify import load, ROOT, round_ratio


def four_terms(f00,f10,f01,f11,x,tone_bin):
    f00,f10,f01,f11=(np.asarray(v,dtype=float).ravel() for v in (f00,f10,f01,f11))
    u=f10-f00;w=f01-f00;i=f11-f10-f01+f00;delta=f11-f00
    assert np.array_equal(delta,u+w+i)
    e=f00-2048*(x+1)
    terms=[np.mean(u*u),np.mean(w*w),np.mean(i*i),2*np.mean(u*w),2*np.mean(u*i),2*np.mean(w*i),2*np.mean(e*u),2*np.mean(e*w),2*np.mean(e*i)]
    net=net_terms(f11,f00,x,tone_bin)
    assert abs(sum(terms)-net['mse_difference'])<1e-9*max(1,abs(net['mse_difference']))
    return {'observation_square':float(terms[0]),'state_square':float(terms[1]),'interaction_square':float(terms[2]),
        'observation_state_cross':float(terms[3]),'observation_interaction_cross':float(terms[4]),'state_interaction_cross':float(terms[5]),
        'original_error_observation_cross':float(terms[6]),'original_error_state_cross':float(terms[7]),'original_error_interaction_cross':float(terms[8]),
        'total':net,'integer_interaction_nonzero_codes':int(np.count_nonzero(i))}


def analyze(folder):
    p,_=load(folder);assert json.loads((folder/'verification.json').read_text())['passed']
    n=p['input']['samples_per_block'];bw=n//120;blocks=p['budget']['blocks'];nw=p['budget']['windows_per_path'];tail=p['tail']['first_block']
    tone=np.fromfile(folder/'tone.bin',dtype='<f8');nominal=ROOT/p['nominal_folder']
    rows=[];pairs=[];scored=cross_codes=0;maximum_score=0.
    for case in p['cases']:
        for seed in p['seeds']:
            base=f"{case['name']}_{seed}"
            refwords=np.memmap(nominal/(base+'_words.bin'),dtype='i1',mode='r',shape=(65536,120,4))[:nw]
            refout=np.memmap(nominal/(base+'_outputs.bin'),dtype='<i2',mode='r',shape=(65536,120,3))[:nw]
            refstates=[np.memmap(nominal/(base+'_'+m['name']+'_q22.bin'),dtype='<f8',mode='r',shape=(65537,8))[:nw+1] for m in p['methods']]
            history_outputs={};byhistory={}
            for ph in p['phases'][1:]:
                name=ph['name'];stem=f"{case['name']}_{name}_{seed}"
                meta=json.loads((folder/(stem+'.json')).read_text(encoding='utf-8-sig'))
                words=np.memmap(folder/(stem+'_words.bin'),dtype='i1',mode='r',shape=(nw,120,4))
                out=np.memmap(folder/(stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(nw,120,3));history_outputs[name]=out
                unit_scores=[];static_unit=[]
                for b in range(blocks):
                    sl=slice(b*bw,(b+1)*bw);y=out[sl,:,0].ravel();score=metrics(y,tone,p['input']['tone_bin'])
                    maximum_score=max(maximum_score,independent_score(y,tone,p['input']['tone_bin'],score));scored+=1
                    score['static_unit_terms']=net_terms(y,refout[sl,:,0].ravel(),tone,p['input']['tone_bin'])
                    unit_scores.append(score);static_unit.append(metrics(refout[sl,:,0].ravel(),tone,p['input']['tone_bin']))
                for m,method in enumerate(p['methods']):
                    st=np.memmap(folder/(stem+'_'+method['name']+'_q22.bin'),dtype='<f8',mode='r',shape=(nw+1,8))
                    scores=[];four=[];supports=[block['Selected'][m]['Both'] for block in meta['Blocks']]
                    static_scores=[];physical_changes=[]
                    for b in range(blocks):
                        sl=slice(b*bw,(b+1)*bw);y=out[sl,:,m+1].ravel();unit=out[sl,:,0].ravel()
                        score=metrics(y,tone,p['input']['tone_bin']);maximum_score=max(maximum_score,independent_score(y,tone,p['input']['tone_bin'],score));scored+=1
                        base_score=metrics(refout[sl,:,m+1].ravel(),tone,p['input']['tone_bin']);static_scores.append(base_score)
                        score['gain_sndr_db']=score['sndr_db']-unit_scores[b]['sndr_db'];score['static_sndr_difference_db']=score['sndr_db']-base_score['sndr_db']
                        score['unit_net_terms']=net_terms(y,unit,tone,p['input']['tone_bin']);scores.append(score)
                        actual=np.rint(st[sl]*(1<<22)).astype(np.int64);nom=np.rint(refstates[m][sl]*(1<<22)).astype(np.int64)
                        f10,*_=digital(words[sl],nom);f01,*_=digital(refwords[sl],actual)
                        assert np.all((f10>=0)&(f10<=4095)&(f01>=0)&(f01<=4095))
                        four.append(four_terms(refout[sl,:,m+1],f10,f01,out[sl,:,m+1],tone,p['input']['tone_bin']));cross_codes+=2*n
                        change=words[sl,:,:3]!=refwords[sl,:,:3]
                        physical_changes.append({'all_word_components':change.sum(axis=(0,1)).tolist(),'selected_word_components':change[:,:method['selected']].sum(axis=(0,1)).tolist()})
                    effective=round_ratio(np.rint(st*(1<<22)).astype(np.int64),4096)/1024
                    row={'case':case['name'],'history':name,'seed':seed,'method':method['name'],'block_scores':scores,'unit_block_scores':unit_scores,
                        'static_unit_block_scores':static_unit,'static_online_block_scores':static_scores,'four_grid_block_terms':four,'physical_changes_by_block':physical_changes,
                        'convergence':stability(scores,st,supports,p),'tail_effective_state':tail_statistics(effective[:-1],p),
                        'tail_effective_covariance':np.cov(effective[tail*bw:-1].T,bias=True).tolist(),
                        'tail_mean_sndr_db':float(np.mean([s['sndr_db'] for s in scores[tail:]])),
                        'tail_mean_sfdr_dbc':float(np.mean([s['sfdr_dbc'] for s in scores[tail:]])),
                        'tail_mean_gain_db':float(np.mean([s['gain_sndr_db'] for s in scores[tail:]])),
                        'tail_mean_static_sndr_difference_db':float(np.mean([s['static_sndr_difference_db'] for s in scores[tail:]])),
                        'tail_mean_mse':float(np.mean([s['mse_codes_squared'] for s in scores[tail:]])),
                        'tail_unit_mse':float(np.mean([s['mse_codes_squared'] for s in unit_scores[tail:]])),
                        'tail_mean_residual_power':float(np.mean([s['residual_power'] for s in scores[tail:]])),
                        'tail_unit_residual_power':float(np.mean([s['residual_power'] for s in unit_scores[tail:]])),
                        'initial_Q22':np.rint(st[0]*(1<<22)).astype(np.int64).tolist(),'final_Q22':np.rint(st[-1]*(1<<22)).astype(np.int64).tolist()}
                    for field in ('Gates','Basis','Both','Correlations'):
                        for scope in ('All','Selected'):row[scope.lower()+'_'+field.lower()+'_total']=np.sum([v[scope][m][field] for v in meta['Blocks']],axis=0).tolist()
                    for field in ('ZeroRequest','HiddenChanged','ExportChanged'):row[field+'_total']=np.sum([v[field][m] for v in meta['Blocks']],axis=0).tolist()
                    rows.append(row);byhistory[(name,m)]=row
            for m,method in enumerate(p['methods']):
                terms=[net_terms(history_outputs['hold'][b*bw:(b+1)*bw,:,m+1].ravel(),history_outputs['reset'][b*bw:(b+1)*bw,:,m+1].ravel(),tone,p['input']['tone_bin']) for b in range(blocks)]
                a=byhistory[('hold',m)];b=byhistory[('reset',m)]
                pairs.append({'case':case['name'],'seed':seed,'method':method['name'],'hold_minus_reset_sndr_db':a['tail_mean_sndr_db']-b['tail_mean_sndr_db'],
                    'hold_minus_reset_mse':a['tail_mean_mse']-b['tail_mean_mse'],'block_terms':terms})
            print('analyzed',case['name'],seed,flush=True)
    summaries=[]
    keys=('tail_mean_sndr_db','tail_mean_sfdr_dbc','tail_mean_gain_db','tail_mean_static_sndr_difference_db','tail_mean_mse','tail_unit_mse','tail_mean_residual_power','tail_unit_residual_power')
    for case in p['cases']:
        for method in p['methods']:
            for ph in p['phases'][1:]:
                sub=[r for r in rows if r['case']==case['name'] and r['method']==method['name'] and r['history']==ph['name']]
                summary={'case':case['name'],'method':method['name'],'history':ph['name'],**{key:float(np.mean([r[key] for r in sub])) for key in keys},
                    'positive_net_sndr_seeds':sum(r['tail_mean_gain_db']>0 for r in sub),'net_mse_improved_seeds':sum(r['tail_mean_mse']<r['tail_unit_mse'] for r in sub),
                    'better_than_static_sndr_seeds':sum(r['tail_mean_static_sndr_difference_db']>0 for r in sub),
                    'criterion_reached_seeds':sum(r['convergence']['first_satisfying_conversion'] is not None for r in sub),
                    'first_criterion_conversions':[r['convergence']['first_satisfying_conversion'] for r in sub],
                    'later_failing_intervals':[r['convergence']['later_failing_intervals'] for r in sub]}
                for key in ('selected_gates_total','selected_basis_total','selected_both_total','all_gates_total','all_basis_total','all_both_total','HiddenChanged_total','ExportChanged_total'):summary[key]=np.sum([r[key] for r in sub],axis=0).tolist()
                summaries.append(summary)
    sources(folder)
    write(folder/'analysis.json',{'paths':rows,'history_pairs':pairs,'finite_cross_identities_passed':True,'causal_decomposition_claimed':False})
    write(folder/'summary.json',{'summary':summaries,'actual_online_codes':p['budget']['actual_online_output_codes'],'actual_physical_conversions':p['budget']['generated_physical_conversions'],
        'additional_cross_readout_codes_checked':cross_codes,'four_grid_blocks_checked':len(rows)*blocks,'history_pair_blocks_checked':len(pairs)*blocks,'long_runs':1,'chip_certified':False})
    write(folder/'independent_score_validation.json',{'passed':True,'all_dynamic_unit_and_online_blocks_checked':scored,'maximum_db_error':maximum_score,'full_complex_FFT_and_extended_precision_MSE':True})
    plot(folder,rows,p)


def plot(folder,rows,p):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(3,2,figsize=(11,9),sharex=True)
    x=(np.arange(p['budget']['blocks'])+1)*p['input']['samples_per_block']/1e6
    for i,case in enumerate(p['cases']):
        for m,method in enumerate(p['methods']):
            ax=axes[i,m]
            for name,color in (('reset','#176d8e'),('hold','#ca713a')):
                sub=[r for r in rows if r['case']==case['name'] and r['method']==method['name'] and r['history']==name]
                y=np.array([[s['sndr_db'] for s in r['block_scores']] for r in sub])
                for trace in y:ax.plot(x,trace,color=color,alpha=.16,lw=.6)
                ax.plot(x,y.mean(axis=0),color=color,lw=1.5,label=name+' online')
                ax.plot(x,np.mean([[s['sndr_db'] for s in r['unit_block_scores']] for r in sub],axis=0),color=color,ls=':',lw=.8,label=name+' unit')
            ax.plot(x,np.mean([[s['sndr_db'] for s in r['static_online_block_scores']] for r in sub],axis=0),color='#555e65',lw=1,label='static online')
            ax.set_title(case['name']+' / '+method['name']);ax.set_ylabel('Block SNDR (dB)');ax.grid(alpha=.15)
    for ax in axes[-1]:ax.set_xlabel('Actual conversions (million)')
    axes[0,0].legend(fontsize=8);fig.suptitle('Continuous dynamic background: reset vs hold\nOriginal curves/tags, 5 seeds; static first128 blocks reused',fontsize=13)
    fig.tight_layout(rect=(0,0,1,.94));fig.savefig(folder/'dynamic_sndr.png',dpi=170);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);folder=parser.parse_args().folder.resolve()
    try:analyze(folder)
    except Exception:write(folder/'analysis_failure.json',{'traceback':traceback.format_exc()});raise
