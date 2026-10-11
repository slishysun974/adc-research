"""Actual post-switch output, finite paired identities and frozen recovery rule."""
import argparse
import json
from pathlib import Path
import traceback

import numpy as np

from experiments.exp_057_static_two_stage_million.common import metrics, write
from experiments.exp_061_static_auxiliary_million.verify import sources
from experiments.exp_062_same_input_background.analyze import stability, tail_statistics, net_terms
from experiments.exp_062_same_input_background.verify import round_ratio
from .verify import load


def recovery(carry, fresh, supports_c, supports_f, p):
    c=p['tracking']; size=c['group_blocks']; need=c['minimum_groups']
    cm=np.array(carry['group_sndr_means_db']); fm=np.array(fresh['group_sndr_means_db'])
    ck=np.array(carry['group_effective_state_means']); fk=np.array(fresh['group_effective_state_means'])
    joint=np.array(supports_c)+np.array(supports_f)
    joint=np.array([part.sum(axis=0) for part in np.split(joint,len(cm))])
    ci={v['end_block_exclusive']:v['passed'] for v in carry['intervals']}
    fi={v['end_block_exclusive']:v['passed'] for v in fresh['intervals']}
    checks=[]; first=None
    for end in range(need,len(cm)+1):
        begin=end-need; active=np.any(joint[begin:end]>0,axis=0)
        sg=float(np.max(np.abs(cm[begin:end]-fm[begin:end])))
        kg=np.max(np.abs(ck[begin:end]-fk[begin:end]),axis=0)
        ok=ci[end*size] and fi[end*size] and sg<=c['pair_sndr_group_mean_gap_db'] and bool(np.all(kg[active]<=c['pair_coefficient_group_mean_gap']))
        if ok and first is None: first=end*size
        checks.append({'end_post_block_exclusive':end*size,'passed':bool(ok),'both_separately_stable':bool(ci[end*size] and fi[end*size]),
            'maximum_pair_sndr_group_gap_db':sg,'maximum_pair_coefficient_group_gaps':kg.tolist(),
            'unsupported_coordinates':np.flatnonzero(~active).tolist()})
    return {'first_satisfying_post_block_exclusive':first,
        'first_satisfying_post_conversion':None if first is None else first*p['input']['samples_per_block'],
        'passing_intervals':sum(v['passed'] for v in checks),
        'later_failing_intervals':sum(not v['passed'] for v in checks if first is not None and v['end_post_block_exclusive']>first),
        'status':'not reached within frozen budget' if first is None else 'finite criterion reached',
        'intervals':checks,'general_recovery_proved':False}


def independent_score(y, x, tone, expected):
    # Full complex FFT, both frequency signs, separate from common.rfft score.
    y=np.asarray(y,dtype=float); spec=np.fft.fft(y-y.mean())/len(y)
    power=np.abs(spec)**2; signal=power[tone]+power[-tone]
    power[[0,tone,len(y)-tone]]=0
    sndr=10*np.log10(signal/power.sum()); sfdr=10*np.log10(signal/(2*power.max()))
    # Nyquist is unpaired, while ordinary real-signal bins are paired.
    paired=2*power[:len(y)//2+1]; paired[-1]=power[len(y)//2]
    sfdr=10*np.log10(signal/paired.max())
    target=2048*(x+1); e=y.astype(np.longdouble)-target.astype(np.longdouble)
    mse=float(np.sum(e*e)/len(y)); dc=float(np.sum(e)/len(y))
    err=max(abs(sndr-expected['sndr_db']),abs(sfdr-expected['sfdr_dbc']))
    assert err<1e-8 and abs(mse-expected['mse_codes_squared'])<1e-8 and abs(dc-expected['mean_error_codes'])<1e-10
    return float(err)


def analyze(folder):
    p,_=load(folder); assert json.loads((folder/'verification.json').read_text())['passed']
    n=p['input']['samples_per_block']; blocks=p['budget']['blocks']; nw=p['budget']['post_windows_per_path']
    tone=np.fromfile(folder/'tone.bin',dtype='<f8')*p['input']['scale_after']
    t=p['tail']['first_block']; rows=[]; pairs=[]; max_score_error=0.; scored=0
    for case in p['cases']:
        for seed in p['seeds']:
            group={}; outputs={}; supports={}
            for variant in ('carry','fresh'):
                stem=f"{case['name']}_{variant}_{seed}"; meta=json.loads((folder/(stem+'.json')).read_text(encoding='utf-8-sig'))
                assert meta['Windows']==nw and meta['StartIndex']==p['switch']['global_conversion']
                out=np.memmap(folder/(stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(nw*120,3)); outputs[variant]=out
                unit_scores=[]
                for b in range(blocks):
                    y=out[b*n:(b+1)*n,0]; score=metrics(y,tone,p['input']['tone_bin']); unit_scores.append(score)
                    max_score_error=max(max_score_error,independent_score(y,tone,p['input']['tone_bin'],score)); scored+=1
                for m,method in enumerate(p['methods']):
                    st=np.memmap(folder/(stem+'_'+method['name']+'_q22.bin'),dtype='<f8',mode='r',shape=(nw+1,8))
                    scores=[]; support=[v['Selected'][m]['Both'] for v in meta['Blocks']]; supports[(variant,m)]=support
                    for b in range(blocks):
                        y=out[b*n:(b+1)*n,m+1]; unit=out[b*n:(b+1)*n,0]
                        score=metrics(y,tone,p['input']['tone_bin'])
                        max_score_error=max(max_score_error,independent_score(y,tone,p['input']['tone_bin'],score)); scored+=1
                        score['gain_sndr_db']=score['sndr_db']-unit_scores[b]['sndr_db']
                        score['unit_net_terms']=net_terms(y.astype(float),unit.astype(float),tone,p['input']['tone_bin']); scores.append(score)
                    effective=round_ratio(np.rint(st*(1<<22)).astype(np.int64),4096)/1024
                    row={'case':case['name'],'method':method['name'],'variant':variant,'seed':seed,
                        'block_scores':scores,'unit_block_scores':unit_scores,'first_block':scores[0],
                        'separate_stability':stability(scores,st,support,p),
                        'tail_mean_sndr_db':float(np.mean([s['sndr_db'] for s in scores[t:]])),
                        'tail_mean_gain_db':float(np.mean([s['gain_sndr_db'] for s in scores[t:]])),
                        'tail_mean_mse':float(np.mean([s['mse_codes_squared'] for s in scores[t:]])),
                        'tail_unit_mse':float(np.mean([s['mse_codes_squared'] for s in unit_scores[t:]])),
                        'tail_mean_residual_power':float(np.mean([s['residual_power'] for s in scores[t:]])),
                        'tail_unit_residual_power':float(np.mean([s['residual_power'] for s in unit_scores[t:]])),
                        'tail_mean_sfdr_dbc':float(np.mean([s['sfdr_dbc'] for s in scores[t:]])),
                        'tail_state':tail_statistics(effective[:-1],p),
                        'tail_effective_covariance':np.cov(effective[t*(n//120):-1].T,bias=True).tolist(),
                        'initial_Q22':np.rint(st[0]*(1<<22)).astype(np.int64).tolist(),
                        'final_Q22':np.rint(st[-1]*(1<<22)).astype(np.int64).tolist(),
                        'selected_joint_total':np.sum(support,axis=0).tolist(),
                        'selected_gate_total':np.sum([v['Selected'][m]['Gates'] for v in meta['Blocks']],axis=0).tolist(),
                        'all_joint_total':np.sum([v['All'][m]['Both'] for v in meta['Blocks']],axis=0).tolist(),
                        'hidden_changed_total':np.sum([v['HiddenChanged'][m] for v in meta['Blocks']],axis=0).tolist(),
                        'export_changed_total':np.sum([v['ExportChanged'][m] for v in meta['Blocks']],axis=0).tolist()}
                    rows.append(row); group[(variant,m)]=row
            for m,method in enumerate(p['methods']):
                carry=group[('carry',m)]; fresh=group[('fresh',m)]; terms=[]
                for b in range(blocks):
                    y=outputs['carry'][b*n:(b+1)*n,m+1].astype(float); ref=outputs['fresh'][b*n:(b+1)*n,m+1].astype(float)
                    terms.append(net_terms(y,ref,tone,p['input']['tone_bin']))
                pairs.append({'case':case['name'],'method':method['name'],'seed':seed,
                    'recovery':recovery(carry['separate_stability'],fresh['separate_stability'],supports[('carry',m)],supports[('fresh',m)],p),
                    'tail_carry_minus_fresh_sndr_db':carry['tail_mean_sndr_db']-fresh['tail_mean_sndr_db'],
                    'tail_carry_minus_fresh_mse':carry['tail_mean_mse']-fresh['tail_mean_mse'],
                    'block_paired_terms':terms})
            print('analyzed',case['name'],seed,flush=True)
    summaries=[]
    for case in p['cases']:
        for method in p['methods']:
            ss={v:[r for r in rows if r['case']==case['name'] and r['method']==method['name'] and r['variant']==v] for v in ('carry','fresh')}
            pp=[r for r in pairs if r['case']==case['name'] and r['method']==method['name']]
            variants={}
            for v,sub in ss.items():
                keys=('tail_mean_sndr_db','tail_mean_gain_db','tail_mean_mse','tail_unit_mse','tail_mean_residual_power','tail_unit_residual_power','tail_mean_sfdr_dbc')
                variants[v]={key:float(np.mean([r[key] for r in sub])) for key in keys}
                variants[v].update(positive_gain_seeds=sum(r['tail_mean_gain_db']>0 for r in sub),mse_improved_seeds=sum(r['tail_mean_mse']<r['tail_unit_mse'] for r in sub),
                    separate_stability_reached_seeds=sum(r['separate_stability']['first_satisfying_conversion'] is not None for r in sub),
                    selected_joint_total=np.sum([r['selected_joint_total'] for r in sub],axis=0).tolist())
            summaries.append({'case':case['name'],'method':method['name'],'variants':variants,
                'tail_carry_minus_fresh_sndr_db':float(np.mean([r['tail_carry_minus_fresh_sndr_db'] for r in pp])),
                'carry_better_sndr_seeds':sum(r['tail_carry_minus_fresh_sndr_db']>0 for r in pp),
                'carry_better_mse_seeds':sum(r['tail_carry_minus_fresh_mse']<0 for r in pp),
                'recovery_reached_seeds':sum(r['recovery']['first_satisfying_post_conversion'] is not None for r in pp),
                'recovery_post_conversions':[r['recovery']['first_satisfying_post_conversion'] for r in pp],
                'recovery_later_failures':[r['recovery']['later_failing_intervals'] for r in pp]})
    sources(folder)
    write(folder/'analysis.json',{'paths':rows,'pairs':pairs,'finite_MSE_and_residual_spectrum_cross_passed':True,'general_recovery_proved':False})
    write(folder/'summary.json',{'summary':summaries,'actual_online_post_codes':235929600,'actual_post_physical_conversions':117964800,'long_runs':1,'chip_certified':False})
    write(folder/'independent_score_validation.json',{'passed':True,'all_unit_and_online_block_scores_checked':scored,'maximum_db_error':max_score_error,'full_complex_FFT_and_extended_precision_MSE':True})
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
            for v,color,label in (('carry','#165680','Inherited'),('fresh','#c76b32','Unit start')):
                sub=[r for r in rows if r['case']==case['name'] and r['method']==method['name'] and r['variant']==v]
                y=np.array([[s['sndr_db'] for s in r['block_scores']] for r in sub])
                for trace in y: ax.plot(x,trace,color=color,alpha=.18,linewidth=.6)
                ax.plot(x,y.mean(axis=0),color=color,linewidth=1.5,label=label+' (5 seeds)')
            ax.plot(x,np.mean([[s['sndr_db'] for s in r['unit_block_scores']] for r in sub],axis=0),color='#60696c',linewidth=1,label='Unit, no updates')
            ax.set_title(case['name']+' / '+method['name']); ax.set_ylabel('Block SNDR (dB)'); ax.grid(alpha=.15)
    for ax in axes[-1]: ax.set_xlabel('Actual post-switch conversions (million)')
    axes[0,0].legend(fontsize=8)
    fig.suptitle('Amplitude 0.82 to 0.41: continuous post-switch output\nInherited Q22 state vs unit start, same global tags; nominal static paths',fontsize=13)
    fig.tight_layout(rect=(0,0,1,.94)); fig.savefig(folder/'switch_sndr.png',dpi=170); plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('folder',type=Path); folder=parser.parse_args().folder.resolve()
    try: analyze(folder)
    except Exception:
        write(folder/'analysis_failure.json',{'traceback':traceback.format_exc()}); raise
