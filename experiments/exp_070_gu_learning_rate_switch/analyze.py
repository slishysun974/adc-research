"""Complete paired finite output/old criterion scores, every seed retained."""
import argparse
from pathlib import Path
import traceback
import numpy as np

from experiments.exp_057_static_two_stage_million.common import metrics
from experiments.exp_062_same_input_background.analyze import stability, tail_statistics
from experiments.exp_066_input_switch_tracking_long.analyze import recovery as old_recovery
from experiments.exp_062_same_input_background.verify import round_ratio
from adc_research.theory.finite_output_acceptance import benefit, group_scores, intervals, recovery
from .prepare import ROOT, read, write, check
from .verify import state_file


def independent_score(y,x,tone_bin,saved):
    values=np.asarray(y,dtype=np.longdouble);e=values-2048*(1+x.astype(np.longdouble))
    mse=float(np.mean(e*e));dc=float(np.mean(e))
    spec=np.fft.fft(np.asarray(y,dtype=float))/len(y)
    signal=float(abs(spec[tone_bin])**2+abs(spec[-tone_bin])**2)
    spec[[0,tone_bin,len(y)-tone_bin]]=0
    residual=float(np.sum(np.abs(spec)**2))
    ordinary=np.abs(spec[:len(y)//2+1])**2*2;ordinary[-1]/=2
    sndr=10*np.log10(signal/residual);sfdr=10*np.log10(signal/ordinary.max())
    assert abs(mse-saved['mse_codes_squared'])<1e-8*max(1,mse)
    assert abs(dc-saved['mean_error_codes'])<1e-10
    assert abs(sndr-saved['sndr_db'])<1e-8 and abs(sfdr-saved['sfdr_dbc'])<1e-8
    assert abs(residual-saved['residual_power'])<1e-8*max(1,residual)
    return spec,signal


def finite_terms(y,reference,x,sy,sr):
    y,reference=np.asarray(y,dtype=float),np.asarray(reference,dtype=float)
    e=reference-2048*(1+x);d=y-reference
    square=float(np.mean(d*d));cross=float(2*np.mean(e*d))
    direct=float(np.mean((y-2048*(1+x))**2)-np.mean(e*e))
    assert abs(direct-square-cross)<1e-8*max(1,abs(direct))
    sd=sy-sr;ps=float(np.sum(abs(sd)**2));pc=float(2*np.real(np.vdot(sr,sd)))
    pd=float(np.sum(abs(sy)**2)-np.sum(abs(sr)**2))
    assert abs(pd-ps-pc)<1e-8*max(1,abs(pd))
    return {'mse_difference':direct,'change_square':square,'reference_error_cross':cross,
        'residual_difference':pd,'residual_change_square':ps,'residual_cross':pc}


def output_accept(scores,units):
    return intervals([bool(benefit(a,u)) for a,u in zip(group_scores(scores),group_scores(units),strict=True)])


def analyze(folder):
    p=read(folder/'protocol.json');plan=read(folder/'runplan.json')
    assert not plan['preflight'] and read(folder/'verification.json')['passed']
    check(folder)
    x=np.fromfile(folder/'tone.bin',dtype='<f8')*0.5;n=len(x)
    old=ROOT/p['sources']['switch_base']
    prior={(r['case'],r['seed'],r['method'],r['variant']):r for r in read(old/'analysis.json')['paths']}
    rows=[];pairs=[];blocks_checked=0;max_old_error=0.0;fft_count=0
    for task in plan['tasks']:
        stem=task['stem'];nw=task['windows'];desc=task['paths'];meta=read(folder/(stem+'.json'))
        outputs=np.memmap(folder/(stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(nw*120,4))
        originals={v:np.memmap(old/f"{task['case']}_{v}_{task['seed']}_outputs.bin",dtype='<i2',mode='r',shape=(nw*120,3)) for v in p['variants']}
        scores=[[] for _ in range(8)];units=[];pair_terms=[[],[]]
        for b in range(p['budget']['blocks']):
            piece=slice(b*n,(b+1)*n)
            assert np.array_equal(originals['carry'][piece,0],originals['fresh'][piece,0])
            records=[originals['carry'][piece,0]]+[outputs[piece,h] for h in range(4)]+[
                originals[v][piece,m+1] for v in p['variants'] for m in range(2)]
            block_scores=[];spectra=[]
            for y in records:
                score=metrics(y,x,p['input']['tone_bin']);spec,signal=independent_score(y,x,p['input']['tone_bin'],score)
                score['signal_power']=signal;block_scores.append(score);spectra.append(spec)
                blocks_checked+=1;fft_count+=2
            units.append(block_scores[0])
            for h in range(8):
                score=block_scores[h+1]
                score['gain_sndr_db']=score['sndr_db']-block_scores[0]['sndr_db']
                score['gain_sfdr_dbc']=score['sfdr_dbc']-block_scores[0]['sfdr_dbc']
                if h<4:
                    score['unit_terms']=finite_terms(records[h+1],records[0],x,spectra[h+1],spectra[0])
                    score['base_terms']=finite_terms(records[h+1],records[h+5],x,spectra[h+1],spectra[h+5])
                    score['paired_base_sndr_db']=score['sndr_db']-block_scores[h+5]['sndr_db']
                else:
                    d=desc[h-4];old_score=prior[(task['case'],task['seed'],d['method'],d['variant'])]['block_scores'][b]
                    max_old_error=max(max_old_error,abs(score['sndr_db']-old_score['sndr_db']))
                    assert abs(score['mse_codes_squared']-old_score['mse_codes_squared'])<1e-8
                scores[h].append(score)
            for m in range(2):
                pair_terms[m].append(finite_terms(records[m+1],records[m+3],x,spectra[m+1],spectra[m+3]))
        stream_rows=[]
        for h in range(8):
            new=h<4;d=desc[h%4];rate='quarter' if new else 'base'
            if new:
                raw=state_file(folder,stem,d['name'],nw)
                hidden=np.asarray(raw,dtype=float)/(1 << 22)
                support=[v['Selected'][h]['Both'] for v in meta['Blocks']]
                counters={key:np.sum([v[key][h] for v in meta['Blocks']],axis=0).tolist() for key in ('ZeroRequest','NonzeroSumZero','HiddenChanged','ExportChanged')}
                clips=meta['CoefficientClips'][h];oc=meta['OutputClips'][h]
            else:
                s=f"{task['case']}_{d['variant']}_{task['seed']}"
                hidden=np.memmap(old/(s+'_'+d['method']+'_q22.bin'),dtype='<f8',mode='r',shape=(nw+1,8))
                om=read(old/(s+'.json'));mi=h%2
                support=[v['Selected'][mi]['Both'] for v in om['Blocks']]
                counters={key:np.sum([v[key][mi] for v in om['Blocks']],axis=0).tolist() for key in ('ZeroRequest','HiddenChanged','ExportChanged')}
                counters['NonzeroSumZero']=None;clips=om['CoefficientClips'][mi];oc=om['OutputClips'][mi]
            effective=round_ratio(np.rint(hidden*(1 << 22)).astype(np.int64),4096)/1024
            t=p['tail']['first_block'];sc=scores[h]
            def mean(key,begin=64,end=128):return float(np.mean([v[key] for v in sc[begin:end]]))
            row={'case':task['case'],'seed':task['seed'],'method':d['method'],'variant':d['variant'],'rate':rate,
                'tail_mean_mse':mean('mse_codes_squared'),'tail_unit_mse':float(np.mean([v['mse_codes_squared'] for v in units[t:]])),
                'tail_mean_sndr_db':mean('sndr_db'),'tail_mean_gain_db':mean('gain_sndr_db'),
                'tail_mean_sfdr_dbc':mean('sfdr_dbc'),'tail_residual_power':mean('residual_power'),
                'tail_signal_power':mean('signal_power'),'tail_dc_error':mean('mean_error_codes'),
                'startup_mean_mse':mean('mse_codes_squared',0,24),
                'tail_paired_base_sndr_db':mean('paired_base_sndr_db') if new else 0,
                'finite_output':output_accept(sc,units),'separate_stability':stability(sc,hidden,support,p),
                'tail_effective_state':tail_statistics(effective[:-1],p),'tail_hidden_state':tail_statistics(hidden[:-1],p),
                'selected_joint_total':np.sum(support,axis=0).tolist(),'support_blocks':support,
                'counters':counters,'coefficient_saturations':clips,'output_out_of_range':oc,'block_scores':sc,
                'learning_observations_per_stage':nw*d['selected'],'carry_prefix_conversions':3932160 if d['variant']=='carry' else 0,
                'checkpoints':{str(b):sc[b-1] for b in p['checkpoints_blocks']}}
            rows.append(row);stream_rows.append(row)
        for rate in ('quarter','base'):
            for method in p['methods']:
                c=next(r for r in stream_rows if r['rate']==rate and r['method']==method['name'] and r['variant']=='carry')
                f=next(r for r in stream_rows if r['rate']==rate and r['method']==method['name'] and r['variant']=='fresh')
                flags=[bool(recovery(a,b,u)) for a,b,u in zip(group_scores(c['block_scores']),group_scores(f['block_scores']),group_scores(units),strict=True)]
                pairs.append({'case':task['case'],'seed':task['seed'],'method':method['name'],'rate':rate,
                    'finite_output_recovery':intervals(flags),
                    'old_recovery':old_recovery(c['separate_stability'],f['separate_stability'],c['support_blocks'],f['support_blocks'],p),
                    'quarter_pair_loss_terms':pair_terms[0 if method['name']=='point30' else 1] if rate=='quarter' else None})
        print('scored',stem,'4 new +4 reused +unit',flush=True)
    assert blocks_checked==17280 and max_old_error<1e-9 and fft_count==34560
    groups=[]
    for case in p['cases']:
        for method in p['methods']:
            for rate in ('base','quarter'):
                for variant in p['variants']:
                    rr=[r for r in rows if (r['case'],r['method'],r['rate'],r['variant'])==(case,method['name'],rate,variant)]
                    assert len(rr)==5
                    groups.append({'case':case,'method':method['name'],'rate':rate,'variant':variant,
                        **{key:float(np.mean([r[key] for r in rr])) for key in ('tail_mean_mse','tail_unit_mse','tail_mean_gain_db',
                            'tail_mean_sndr_db','tail_mean_sfdr_dbc','tail_residual_power','tail_signal_power','tail_dc_error','startup_mean_mse','tail_paired_base_sndr_db')},
                        'mse_better_than_unit_seeds':sum(r['tail_mean_mse']<r['tail_unit_mse'] for r in rr),
                        'terminal_output_pass_seeds':sum(r['finite_output']['terminal_pass'] for r in rr),
                        'old_stability_ever_seeds':sum(r['separate_stability']['first_satisfying_conversion'] is not None for r in rr),
                        'coefficient_saturations':sum(r['coefficient_saturations'] for r in rr),'output_out_of_range':sum(r['output_out_of_range'] for r in rr),
                        'selected_joint_total':np.sum([r['selected_joint_total'] for r in rr],axis=0).tolist()})
    pair_groups=[]
    for case in p['cases']:
        for method in p['methods']:
            for rate in ('base','quarter'):
                rr=[r for r in pairs if (r['case'],r['method'],r['rate'])==(case,method['name'],rate)]
                pair_groups.append({'case':case,'method':method['name'],'rate':rate,
                    'ever_output_recovery_seeds':sum(r['finite_output_recovery']['first_pass_block'] is not None for r in rr),
                    'terminal_output_recovery_seeds':sum(r['finite_output_recovery']['terminal_pass'] for r in rr),
                    'first_output_recovery_conversions':[r['finite_output_recovery']['first_pass_conversion'] for r in rr],
                    'later_output_violations':[r['finite_output_recovery']['later_violations'] for r in rr],
                    'old_recovery_seeds':sum(r['old_recovery']['first_satisfying_post_conversion'] is not None for r in rr)})
    check(folder)
    write(folder/'analysis.json',{'paths':rows,'pairs':pairs,'finite_loss_and_spectrum_identities_passed':True})
    write(folder/'summary.json',{'groups':groups,'pair_groups':pair_groups,'independent_blocks_checked':blocks_checked,
        'new_fft_calls':fft_count,'original_base_sndr_max_error':max_old_error,'new_paths':60,'reused_base_paths':60,
        'new_online_outputs':p['budget']['new_online_outputs'],'new_learning_observations_per_stage':p['budget']['new_learning_observations_per_stage'],
        'general_convergence_or_chip_or_rate_optimum_proved':False})
    plot(folder,rows,p)


def plot(folder,rows,p):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(3,2,figsize=(11,9),sharex=True,constrained_layout=True)
    x=np.arange(1,129)*30720/1e6
    for i,case in enumerate(p['cases']):
        for j,method in enumerate(p['methods']):
            ax=axes[i,j]
            for rate in ('base','quarter'):
                for variant in p['variants']:
                    rr=[r for r in rows if (r['case'],r['method'],r['rate'],r['variant'])==(case,method['name'],rate,variant)]
                    y=np.array([[s['gain_sndr_db'] for s in r['block_scores']] for r in rr]).mean(axis=0)
                    color='#777777' if rate=='base' else ('#167b96' if variant=='carry' else '#c4773f')
                    ax.plot(x,y,color=color,ls='--' if rate=='base' else '-',lw=1.4 if variant=='carry' else 1,
                            alpha=.8,label=rate+' / '+variant)
            ax.axhline(0,color='#222222',lw=.7);ax.axvspan(x[63],x[-1],alpha=.07,color='#777777')
            ax.set_title(case+' / '+method['name']);ax.set_ylabel('Net block SNDR (dB)');ax.grid(alpha=.15)
    axes[0,0].legend(fontsize=8,frameon=False)
    for ax in axes[-1]:ax.set_xlabel('Post-switch conversion slots (million)')
    fig.suptitle('EXP-070: fixed-rate Gu after amplitude 0.82 to 0.41\nFive paired seen seeds; continued integer output; full120 uses 30x observations',fontsize=12)
    fig.savefig(folder/'switch_rate_sndr.png',dpi=170);plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);folder=parser.parse_args().folder.resolve()
    try:analyze(folder)
    except Exception:write(folder/'analysis_failure.json',{'traceback':traceback.format_exc()});raise
