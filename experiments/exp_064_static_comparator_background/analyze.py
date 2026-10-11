"""Offline paired outputs, finite cross terms, support and state statistics."""
import argparse
import json
from pathlib import Path
import traceback

import numpy as np

from experiments.exp_057_static_two_stage_million.common import metrics, write
from experiments.exp_061_static_auxiliary_million.verify import sources
from experiments.exp_062_same_input_background.analyze import tail_statistics, stability, net_terms
from experiments.exp_062_same_input_background.verify import digital, round_ratio, load
from .verify import nominal_check


def four_grid(words, base_words, acc, base_acc, y, base_y, tone):
    """All four integer readouts; entire changed observation retained."""
    obs = digital(words, base_acc)[0].astype(np.int64)
    state = digital(base_words, acc)[0].astype(np.int64)
    v = obs-base_y
    w = state-base_y
    interaction = y-obs-state+base_y
    parts = np.stack((v,w,interaction),axis=-1).reshape(-1,3)
    delta = (y-base_y).ravel()
    assert np.array_equal(parts.sum(axis=1),delta)
    gram = parts.T@parts/len(delta)
    error = base_y.ravel()-np.tile(2048*(tone+1),len(y)*120//len(tone))
    cross = 2*np.mean(error[:,None]*parts,axis=0)
    dmse = float(np.mean((error+delta)**2)-np.mean(error**2))
    assert abs(dmse-gram.sum()-cross.sum()) < 1e-9*max(1,abs(dmse))
    return {'part_order':['observation','state','interaction'],
        'part_mean_codes':parts.mean(axis=0).tolist(),
        'part_mean_square_codes':np.diag(gram).tolist(),
        'part_gram':gram.tolist(),'nominal_error_part_cross':cross.tolist(),
        'paired_mse_difference':dmse,'sum_identity_passed':True}


def average_scores(scores):
    signal=np.array([s['residual_power']*10**(s['sndr_db']/10) for s in scores])
    return {'mean_sndr_db':float(np.mean([s['sndr_db'] for s in scores])),
        'mean_mse':float(np.mean([s['mse_codes_squared'] for s in scores])),
        'mean_residual_power':float(np.mean([s['residual_power'] for s in scores])),
        'mean_signal_power':float(signal.mean()),
        'ratio_of_mean_powers_sndr_db':float(10*np.log10(signal.mean()/np.mean([s['residual_power'] for s in scores])))}


def analyze(folder):
    p,_=load(folder)
    assert json.loads((folder/'verification.json').read_text())['passed']
    assert not (folder/'analysis.json').exists(), 'Refusing analysis overwrite'
    sources(folder); nominal=nominal_check(folder,p)
    n=p['input']['samples_per_block']; bw=n//120
    tone=np.fromfile(folder/'tone.bin',dtype='<f8'); rows=[]
    nominal_analysis=json.loads((nominal/'analysis.json').read_text(encoding='utf-8'))
    nominal_rows={(r['case'],r['seed'],r['method']):r for r in nominal_analysis['paths']}
    for case in p['cases']:
        for seed in p['seeds']:
            stem=f"{case['name']}_{seed}"; base_stem=f"{case['model']}_{seed}"
            meta=json.loads((folder/(stem+'.json')).read_text(encoding='utf-8-sig'))
            count=meta['Conversions']; nw=meta['Windows']
            assert count==p['budget']['conversions_per_path']
            output=np.memmap(folder/(stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(count,3))
            base_output=np.memmap(nominal/(base_stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(count,3))
            words=np.memmap(folder/(stem+'_words.bin'),dtype='i1',mode='r',shape=(nw,120,4))
            base_words=np.memmap(nominal/(base_stem+'_words.bin'),dtype='i1',mode='r',shape=(nw,120,4))
            unit_scores=[metrics(output[b*n:(b+1)*n,0],tone,p['input']['tone_bin']) for b in range(p['budget']['blocks'])]
            for m,method in enumerate(p['methods']):
                name=method['name']; reference=nominal_rows[(case['model'],seed,name)]
                state=np.memmap(folder/(stem+'_'+name+'_q22.bin'),dtype='<f8',mode='r',shape=(nw+1,8))
                base_state=np.memmap(nominal/(base_stem+'_'+name+'_q22.bin'),dtype='<f8',mode='r',shape=(nw+1,8))
                scores=[]; supports=[]; cross_blocks=[]; changes=0; max_change=0
                for b in range(p['budget']['blocks']):
                    y=np.asarray(output[b*n:(b+1)*n,m+1],dtype=np.int64)
                    y0=np.asarray(base_output[b*n:(b+1)*n,m+1],dtype=np.int64)
                    unit=np.asarray(output[b*n:(b+1)*n,0],dtype=np.int64)
                    base_score=reference['block_scores'][b]
                    score=metrics(y,tone,p['input']['tone_bin'])
                    score.update(gain_sndr_db=score['sndr_db']-unit_scores[b]['sndr_db'],
                        paired_sndr_difference_db=score['sndr_db']-base_score['sndr_db'],
                        net_identity=net_terms(y,unit,tone,p['input']['tone_bin']),
                        nominal_identity=net_terms(y,y0,tone,p['input']['tone_bin']))
                    start=b*bw; stop=start+bw
                    acc=np.rint(state[start:stop]*(1<<22)).astype(np.int64)
                    base_acc=np.rint(base_state[start:stop]*(1<<22)).astype(np.int64)
                    cross=four_grid(words[start:stop],base_words[start:stop],acc,base_acc,
                        y.reshape(bw,120),y0.reshape(bw,120),tone)
                    if case['variant']=='stage1_only' and m==0:
                        assert cross['part_mean_square_codes'][1:]==[0,0]
                    cross_blocks.append(cross); scores.append(score)
                    supports.append(meta['Blocks'][b]['Selected'][m]['Both'])
                    changes+=int(np.count_nonzero(y!=y0)); max_change=max(max_change,int(np.max(np.abs(y-y0))))
                effective=round_ratio(np.rint(state*(1<<22)).astype(np.int64),4096)/1024
                t=p['tail']['first_block']; tail=average_scores(scores[t:]); unit_tail=average_scores(unit_scores[t:])
                base_tail=average_scores(reference['block_scores'][t:])
                aggregates={key:{field:np.sum([b[key][m][field] for b in meta['Blocks']],axis=0).tolist()
                    for field in ('Gates','Basis','Both','Correlations')} for key in ('All','Selected')}
                row={'case':case['name'],'model':case['model'],'variant':case['variant'],'seed':seed,'method':name,
                    'actual_conversions':count,'actual_observations_per_stage':nw*method['selected'],
                    'tail':tail,'unit_tail':unit_tail,'nominal_tail':base_tail,
                    'tail_gain_sndr_db':tail['mean_sndr_db']-unit_tail['mean_sndr_db'],
                    'tail_paired_sndr_difference_db':tail['mean_sndr_db']-base_tail['mean_sndr_db'],
                    'tail_mse_difference_vs_unit':tail['mean_mse']-unit_tail['mean_mse'],
                    'tail_mse_difference_vs_nominal':tail['mean_mse']-base_tail['mean_mse'],
                    'convergence':stability(scores,state,supports,p),'tail_effective_state':tail_statistics(effective[:-1],p),
                    'tail_effective_covariance':np.cov(effective[t*bw:-1].T,bias=True).tolist(),
                    'all_states_equal_nominal':bool(np.array_equal(state,base_state)),
                    'different_hidden_state_windows':int(np.count_nonzero(np.any(state!=base_state,axis=1))),
                    'different_output_codes':changes,'maximum_integer_output_difference':max_change,
                    'q_changes_all':np.sum([b['AllQChanges'] for b in meta['Blocks']],axis=0).tolist(),
                    'q_changes_selected':np.sum([b['SelectedPointQChanges'] if m==0 else b['AllQChanges'] for b in meta['Blocks']],axis=0).tolist(),
                    'support':aggregates,'update_counts':{key:np.sum([b[key][m] for b in meta['Blocks']],axis=0).tolist()
                        for key in ('ZeroRequest','HiddenChanged','ExportChanged')},
                    'block_scores':scores,'unit_block_scores':unit_scores,'four_grid_block_cross':cross_blocks,
                    'four_grid_tail_gram':np.mean([v['part_gram'] for v in cross_blocks[t:]],axis=0).tolist(),
                    'four_grid_tail_nominal_error_cross':np.mean([v['nominal_error_part_cross'] for v in cross_blocks[t:]],axis=0).tolist()}
                rows.append(row)
                print('analyzed',stem,name,'own unit gain',row['tail_gain_sndr_db'],'nominal change',row['tail_paired_sndr_difference_db'],flush=True)
    summaries=[]
    for case in p['cases']:
        for method in p['methods']:
            sub=[r for r in rows if r['case']==case['name'] and r['method']==method['name']]
            summaries.append({'case':case['name'],'model':case['model'],'variant':case['variant'],'method':method['name'],'seeds':len(sub),
                'tail_mean_sndr_db':float(np.mean([r['tail']['mean_sndr_db'] for r in sub])),
                'tail_mean_gain_db':float(np.mean([r['tail_gain_sndr_db'] for r in sub])),
                'tail_mean_paired_sndr_difference_db':float(np.mean([r['tail_paired_sndr_difference_db'] for r in sub])),
                'tail_mean_mse':float(np.mean([r['tail']['mean_mse'] for r in sub])),
                'tail_mean_unit_mse':float(np.mean([r['unit_tail']['mean_mse'] for r in sub])),
                'tail_mean_nominal_mse':float(np.mean([r['nominal_tail']['mean_mse'] for r in sub])),
                'tail_mean_residual_power':float(np.mean([r['tail']['mean_residual_power'] for r in sub])),
                'tail_mean_unit_residual_power':float(np.mean([r['unit_tail']['mean_residual_power'] for r in sub])),
                'tail_ratio_of_mean_powers_sndr_db':float(10*np.log10(np.mean([r['tail']['mean_signal_power'] for r in sub])/np.mean([r['tail']['mean_residual_power'] for r in sub]))),
                'positive_gain_seed_means':sum(r['tail_gain_sndr_db']>0 for r in sub),
                'positive_paired_sndr_seed_means':sum(r['tail_paired_sndr_difference_db']>0 for r in sub),
                'mse_better_than_unit_seeds':sum(r['tail_mse_difference_vs_unit']<0 for r in sub),
                'mse_better_than_nominal_seeds':sum(r['tail_mse_difference_vs_nominal']<0 for r in sub),
                'criterion_reached_seeds':sum(r['convergence']['first_satisfying_conversion'] is not None for r in sub),
                'first_criterion_conversions':[r['convergence']['first_satisfying_conversion'] for r in sub],
                'later_failing_intervals':[r['convergence']['later_failing_intervals'] for r in sub],
                'selected_joint_total':np.sum([r['support']['Selected']['Both'] for r in sub],axis=0).tolist(),
                'selected_gate_total':np.sum([r['support']['Selected']['Gates'] for r in sub],axis=0).tolist(),
                'all_joint_total':np.sum([r['support']['All']['Both'] for r in sub],axis=0).tolist(),
                'selected_hidden_changes':np.sum([r['update_counts']['HiddenChanged'] for r in sub],axis=0).tolist(),
                'selected_export_changes':np.sum([r['update_counts']['ExportChanged'] for r in sub],axis=0).tolist(),
                'all_states_equal_nominal':all(r['all_states_equal_nominal'] for r in sub),
                'paired_sndr_seed_means':[r['tail_paired_sndr_difference_db'] for r in sub],
                'output_changes':[r['different_output_codes'] for r in sub]})
    sources(folder); nominal_check(folder,p)
    write(folder/'analysis.json',{'paths':rows,'all_integer_four_grid_identities_passed':True,'all_mse_spectral_identities_passed':True})
    write(folder/'summary.json',{'summary':summaries,'actual_online_output_codes':sum(r['actual_conversions'] for r in rows),
        'generated_physical_conversions':p['budget']['generated_physical_conversions'],'stationarity_proved':False,'causal_attribution_claimed':False})
    plot(folder,rows,p)


def plot(folder,rows,p):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(3,2,figsize=(11,9),sharex=True)
    x=np.arange(1,p['budget']['blocks']+1)*p['input']['samples_per_block']/1e6
    for i,model in enumerate(('ideal','both_linear','both_smooth')):
        for m,method in enumerate(p['methods']):
            ax=axes[i,m]
            for variant,color in (('stage1_only','#246d9b'),('stage2_only','#c46a31')):
                sub=[r for r in rows if r['model']==model and r['method']==method['name'] and r['variant']==variant]
                data=np.array([[v['paired_sndr_difference_db'] for v in r['block_scores']] for r in sub])
                for line in data: ax.plot(x,line,color=color,alpha=.14,linewidth=.6)
                ax.plot(x,data.mean(axis=0),color=color,linewidth=1.5,label=variant+' (5 seeds)')
            ax.axhline(0,color='#777777',linewidth=.7); ax.set_title(model+' / '+method['name'])
            ax.set_ylabel('SNDR change vs nominal (dB)'); ax.grid(alpha=.15)
    axes[0,0].legend(fontsize=8)
    for ax in axes[-1]: ax.set_xlabel('Actual conversions (million)')
    fig.suptitle('Fixed comparator offsets: paired uninterrupted output\nOriginal vectors, algorithms and horizon; full method uses 30x observations',fontsize=13)
    fig.tight_layout(rect=(0,0,1,.94)); fig.savefig(folder/'comparator_paired_sndr.png',dpi=170); plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('folder',type=Path); folder=parser.parse_args().folder.resolve()
    try: analyze(folder)
    except Exception:
        write(folder/'analysis_failure.json',{'traceback':traceback.format_exc()}); raise
