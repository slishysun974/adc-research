"""Paired full-code scores and fixed finite convergence descriptors."""
import argparse
import json
import math
from pathlib import Path
import traceback
import numpy as np

from experiments.exp_057_static_two_stage_million.common import metrics, write
from experiments.exp_062_same_input_background.analyze import tail_statistics, stability
from .verify import ROOT, load, paths, states_for, round_ratio, sources


def independent_score(y, tone, tone_bin, saved):
    """Direct dot MSE/DC plus uncentered FFT; independent score arithmetic."""
    y=np.asarray(y,dtype=float); error=y-2048*(1+tone); n=len(y)
    mse=float(np.dot(error,error)/n); dc=float(np.sum(error)/n)
    assert abs(mse-saved['mse_codes_squared']) < 1e-9*max(1,mse)
    assert abs(dc-saved['mean_error_codes']) < 1e-10
    spectrum=np.fft.rfft(y)/n
    powers=np.square(spectrum.real)+np.square(spectrum.imag);powers[1:-1]*=2
    signal=float(powers[tone_bin]);powers[[0,tone_bin]]=0
    residual=float(np.sum(powers));spur=float(np.max(powers))
    sndr=10*math.log10(signal/residual);sfdr=10*math.log10(signal/spur)
    assert abs(sndr-saved['sndr_db']) < 1e-9
    assert abs(sfdr-saved['sfdr_dbc']) < 1e-9
    assert abs(residual-saved['residual_power']) < 1e-9*max(1,residual)
    return {'mse':mse,'dc':dc,'signal_power':signal,'residual_power':residual}


def finite_loss(y, reference, tone):
    e=reference-2048*(1+tone);delta=y-reference
    cross=2*float(np.dot(e,delta)/len(y));square=float(np.dot(delta,delta)/len(y))
    direct=float(np.mean((y-2048*(1+tone))**2)-np.mean(e**2))
    assert abs(direct-cross-square) < 1e-9*max(1,abs(direct))
    return {'mse_difference':direct,'reference_error_change_cross':cross,'change_square':square}


def analyze(folder):
    p,src,_=load(folder);assert json.loads((folder/'verification.json').read_text())['passed']
    source=ROOT/p['source_folder'];tone=np.fromfile(folder/'tone.bin',dtype='<f8')
    n=p['input']['samples_per_block'];nw=p['budget']['windows_per_path'];nb=p['budget']['blocks'];tail=p['tail']['first_block']
    prior=json.loads((source/'analysis.json').read_text())
    prior_rows={(r['case'],r['method'],r['seed']):r for r in prior['paths']}
    rows=[];score_checks=0;old_sndr_error=0.0
    for case in p['cases']:
        for seed in p['seeds']:
            stem=f'{case}_{seed}';meta=json.loads((folder/(stem+'.json')).read_text(encoding='utf-8-sig'))
            assert meta['Windows']==nw
            desc=paths(meta,p);states=states_for(folder,stem,meta)
            old_meta=json.loads((source/(stem+'.json')).read_text(encoding='utf-8-sig'))
            original=np.memmap(source/(stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(nw*120,3))
            output=np.memmap(folder/(stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(nw*120,len(desc)))
            unit_scores=[];base_scores=[[],[]];new_scores=[[] for _ in desc]
            for b in range(nb):
                piece=slice(b*n,(b+1)*n);unit=np.asarray(original[piece,0],dtype=float)
                score=metrics(unit,tone,p['input']['tone_bin']);independent_score(unit,tone,p['input']['tone_bin'],score)
                unit_scores.append(score);score_checks+=1
                for m in range(2):
                    y=np.asarray(original[piece,m+1],dtype=float)
                    score=metrics(y,tone,p['input']['tone_bin']);ind=independent_score(y,tone,p['input']['tone_bin'],score);score_checks+=1
                    score.update(gain_sndr_db=score['sndr_db']-unit_scores[-1]['sndr_db'],
                                 gain_sfdr_dbc=score['sfdr_dbc']-unit_scores[-1]['sfdr_dbc'],signal_power=ind['signal_power'])
                    base_scores[m].append(score)
                    old=prior_rows[(case,p['methods'][m]['name'],seed)]['block_scores'][b]
                    old_sndr_error=max(old_sndr_error,abs(score['sndr_db']-old['sndr_db']))
                for h,(name,rate,method) in enumerate(desc):
                    y=np.asarray(output[piece,h],dtype=float);base=np.asarray(original[piece,1+h%2],dtype=float)
                    score=metrics(y,tone,p['input']['tone_bin']);ind=independent_score(y,tone,p['input']['tone_bin'],score);score_checks+=1
                    score.update(gain_sndr_db=score['sndr_db']-unit_scores[-1]['sndr_db'],
                        gain_sfdr_dbc=score['sfdr_dbc']-unit_scores[-1]['sfdr_dbc'],
                        paired_base_sndr_db=score['sndr_db']-base_scores[h%2][-1]['sndr_db'],
                        signal_power=ind['signal_power'],unit_loss=finite_loss(y,unit,tone),base_loss=finite_loss(y,base,tone))
                    new_scores[h].append(score)
            all_desc=list(desc)+[("base_"+m['name'],p['rate_scales'][2],m) for m in p['methods']]
            for h,(name,rate,method) in enumerate(all_desc):
                new=h<len(desc);m=h%2
                if new:
                    hidden=np.asarray(states[h],dtype=float)/(1 << 22); scores=new_scores[h]
                    counts=[b['Selected'][h]['Both'] for b in meta['Blocks']]
                    all_counts=[b['All'][h]['Both'] for b in meta['Blocks']]
                    counters={k:np.sum([b[k][h] for b in meta['Blocks']],axis=0).tolist()
                              for k in ('ZeroRequest','NonzeroSumZero','HiddenChanged','ExportChanged')}
                    clips=meta['CoefficientClips'][h];output_clips=meta['OutputClips'][h]
                else:
                    hidden=np.memmap(source/(stem+'_'+method['name']+'_q22.bin'),dtype='<f8',mode='r',shape=(nw+1,8));scores=base_scores[m]
                    counts=[b['Selected'][m]['Both'] for b in old_meta['Blocks']]
                    all_counts=[b['All'][m]['Both'] for b in old_meta['Blocks']]
                    counters={k:np.sum([b[k][m] for b in old_meta['Blocks']],axis=0).tolist()
                              for k in ('ZeroRequest','HiddenChanged','ExportChanged')}
                    counters['NonzeroSumZero']=None # original metadata did not split this counter
                    clips=old_meta['CoefficientClips'][m];output_clips=old_meta['OutputClips'][m]
                effective=round_ratio(np.rint(hidden*(1 << 22)).astype(np.int64),4096)/1024
                def mean(field, start):return float(np.mean([s[field] for s in scores[start:]]))
                row={'case':case,'seed':seed,'rate':rate['name'],'method':method['name'],
                     'step_ratio':rate['numerator']/rate['denominator'],'new_training':new,
                     'conversion_slots':nw*120,'learning_observations_per_stage':nw*method['selected'],
                     'tail_mean_sndr_db':mean('sndr_db',tail),'tail_mean_gain_db':mean('gain_sndr_db',tail),
                     'tail_mean_sfdr_dbc':mean('sfdr_dbc',tail),'tail_mean_mse':mean('mse_codes_squared',tail),
                     'tail_unit_mse':float(np.mean([s['mse_codes_squared'] for s in unit_scores[tail:]])),
                     'tail_residual_power':mean('residual_power',tail),'tail_dc_error':mean('mean_error_codes',tail),
                     'startup_mean_mse':float(np.mean([s['mse_codes_squared'] for s in scores[:p['startup_blocks']]])),
                     'tail_mean_paired_base_sndr_db':mean('paired_base_sndr_db',tail) if new else 0.0,
                     'tail_effective_state':tail_statistics(effective[:-1],p),
                     'tail_hidden_state':tail_statistics(np.asarray(hidden[:-1]),p),
                     'convergence':stability(scores,hidden,counts,p),
                     'selected_joint_total':np.sum(counts,axis=0).tolist(),'all_joint_total':np.sum(all_counts,axis=0).tolist(),
                     'counters':counters,'coefficient_saturations':clips,'output_out_of_range':output_clips,
                     'block_scores':scores,'checkpoints':{str(b):scores[b-1] for b in p['checkpoints_blocks']}}
                rows.append(row)
            print('scored',stem,'six new + two reused paths',flush=True)
    assert old_sndr_error < 1e-9,old_sndr_error
    groups=[]
    for case in p['cases']:
        for method in p['methods']:
            for rate in p['rate_scales']:
                rr=[r for r in rows if r['case']==case and r['method']==method['name'] and r['rate']==rate['name']]
                assert len(rr)==5
                unit=rr[0]['tail_unit_mse'] # all five may differ: report per-row below
                base=[r for r in rows if r['case']==case and r['method']==method['name'] and r['rate']=='base']
                bases={r['seed']:r for r in base}
                groups.append({'case':case,'method':method['name'],'rate':rate['name'],'step_ratio':rr[0]['step_ratio'],
                    **{key:float(np.mean([r[key] for r in rr])) for key in
                       ('tail_mean_sndr_db','tail_mean_gain_db','tail_mean_sfdr_dbc','tail_mean_mse','tail_unit_mse',
                        'tail_residual_power','startup_mean_mse','tail_mean_paired_base_sndr_db')},
                    'mse_better_than_unit_seeds':sum(r['tail_mean_mse']<r['tail_unit_mse'] for r in rr),
                    'mse_better_than_base_seeds':sum(r['tail_mean_mse']<bases[r['seed']]['tail_mean_mse'] for r in rr),
                    'sndr_better_than_unit_seeds':sum(r['tail_mean_gain_db']>0 for r in rr),
                    'criterion_reached_seeds':sum(r['convergence']['first_satisfying_conversion'] is not None for r in rr),
                    'later_criterion_failures':sum(r['convergence']['later_failing_intervals'] for r in rr),
                    'coefficient_saturations':sum(r['coefficient_saturations'] for r in rr),
                    'output_out_of_range':sum(r['output_out_of_range'] for r in rr),
                    'front_k1_tail_std_mean':float(np.mean([r['tail_effective_state']['standard_deviation'][0] for r in rr])),
                    'rear_k1_tail_std_mean':float(np.mean([r['tail_effective_state']['standard_deviation'][4] for r in rr])),
                    'front_k1_tail_mean':float(np.mean([r['tail_effective_state']['mean'][0] for r in rr])),
                    'rear_k1_tail_mean':float(np.mean([r['tail_effective_state']['mean'][4] for r in rr])),
                    'nonzero_sum_zero_total':None if rate['name']=='base' else int(sum(sum(r['counters']['NonzeroSumZero']) for r in rr)),
                    'selected_joint_total':np.sum([r['selected_joint_total'] for r in rr],axis=0).tolist()})
    sources(folder)
    write(folder/'analysis.json',{'paths':rows,'source':p['source_folder'],'finite_loss_identities_passed':True})
    write(folder/'summary.json',{'groups':groups,'new_paths':90,'reused_base_paths':30,'independent_blocks_checked':score_checks,
        'source_block_sndr_max_error':old_sndr_error,'new_output_codes':p['budget']['new_output_codes'],
        'new_learning_observations_per_stage':p['budget']['new_learning_observations_per_stage'],
        'regenerated_adc_source_conversions':0,'eight_state_stationarity_proved':False,'rate_selected':False})
    plot(folder,rows,p)


def plot(folder,rows,p):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(3,2,figsize=(11,9),sharex=True,constrained_layout=True)
    colors={'quarter':'#1878a4','half':'#35976b','base':'#777777','double':'#c55a3d'}
    x=np.arange(1,p['budget']['blocks']+1)*p['input']['samples_per_block']/1e6
    for i,case in enumerate(p['cases']):
        for j,method in enumerate(p['methods']):
            ax=axes[i,j]
            for rate in p['rate_scales']:
                rr=[r for r in rows if r['case']==case and r['method']==method['name'] and r['rate']==rate['name']]
                curves=np.array([[s['gain_sndr_db'] for s in r['block_scores']] for r in rr])
                ax.plot(x,curves.mean(axis=0),color=colors[rate['name']],label=f"Step x {rr[0]['step_ratio']:g}",lw=1.4)
            ax.axhline(0,color='#222222',lw=.7,ls='--');ax.axvspan(x[127],x[-1],color='#cccccc',alpha=.12,zorder=-1)
            ax.set_title(case+' / '+method['name']);ax.set_ylabel('Net block SNDR (dB)');ax.grid(alpha=.15)
    for ax in axes[-1]:ax.set_xlabel('Conversion slots (million)')
    axes[0,0].legend(fontsize=8,frameon=False)
    fig.suptitle('EXP-069: fixed learning-rate scales, identical full digital source\n'
                 'Five paired seeds; continued Q3 / Q1.10 / Q22 updates; no rate selection',fontsize=12)
    fig.savefig(folder/'learning_rate_sndr.png',dpi=170);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);folder=parser.parse_args().folder.resolve()
    try:analyze(folder)
    except Exception:
        write(folder/'analysis_failure.json',{'traceback':traceback.format_exc()});raise
