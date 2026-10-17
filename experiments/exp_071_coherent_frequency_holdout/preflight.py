"""Development-only EXP071 controls; no confirmation/future data access."""
import argparse
from dataclasses import replace
from fractions import Fraction as F
from itertools import product
import json
from pathlib import Path
import platform
import shutil
import traceback

import numpy as np

from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.fixed_four_lane_window import _bank,FourLaneConversion
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState
from adc_research.evaluation.observations import digital_sample
from adc_research.theory.static_fixed_contract import readout,export,nearest_even,commit
from experiments.exp_060_static_auxiliary_preflight.run import fixed_setup,plant,check_physical
from experiments.exp_062_same_input_background.verify import digital,tags,physical_words,round_ratio
from experiments.exp_069_gu_learning_rate.check_normal_loss_limits import ROOT,load,write,digest,relative,verify_hashes,output_only

P=Path(__file__).with_name('protocol.json')
COUNTS={'source_conversions':0,'platform_probes':0,'rational_readouts':0,'core_readouts':0,
        'online_codes':0,'unit_codes':0,'endpoint_codes':0,'commits':0,'bank_commits':0,
        'learning_observations_per_stage':0,'balanced_source_conversions':0,'balanced_fixed_readouts':0}


def source(x,d1,d2,case,pipeline,folder,label,*,verify_platform=True):
    x=np.asarray(x,dtype=float)
    if np.any((x < -1)|(x >= 1)):raise ValueError('source input domain')
    q1,q2,be=physical_words(x,d1,d2,case)
    words=np.column_stack((q1,q2,be,(d1>0)+2*(d2>0))).astype(np.int8)
    if verify_platform:
        for i,(xx,dd1,dd2) in enumerate(zip(x,d1,d2,strict=True)):
            trace=plant(float(xx),int(dd1),int(dd2),case,pipeline,i)
            check_physical(trace);sample=digital_sample(trace.pipeline)
            assert tuple(words[i,:3]) == (sample.stage1_symbol,sample.stage2_symbol,sample.backend_centered_code)
            COUNTS['platform_probes']+=1
        COUNTS['source_conversions']+=len(words)
    else:COUNTS['balanced_source_conversions']+=len(words)
    words.tofile(folder/(label+'_words.bin'))
    return words


def scalar_output(words,acc,expected,cfg,*,require_legal=True):
    ks=tuple(F(k,1024) for k in export(tuple(map(int,acc))))
    cascade=replace(cfg.cascade,
        stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=export(tuple(map(int,acc)))[:4]),
        stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=export(tuple(map(int,acc)))[4:]))
    rows=[];values=[[],[]];products=[F(0)]*8
    for j,(word,y) in enumerate(zip(words,expected,strict=True)):
        q1,q2,be,bits=map(int,word);d1,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
        sample=DigitalCalibrationSample(q1,q2,be,d1,d2)
        rd=readout(q1,q2,F(be),d1,d2,ks,data_q3=True)
        core=correct_two_stage_fixed_observed(sample,cascade)
        assert core.unclipped_output_scaled==8*rd.output and core.stage1_raw_scaled==8*rd.raw1
        assert nearest_even(rd.output)==int(y)
        if require_legal and not 0<=y<=4095:raise ValueError('output clip')
        assert nearest_even(F(core.output_scaled,8))==min(4095,max(0,int(y)))
        COUNTS['rational_readouts']+=1;COUNTS['core_readouts']+=1
        rows.append(sample)
        values[0].append((512*d1,int(8*rd.y1)));values[1].append((128*d2,int(8*rd.y2)))
    return rows,values


def learn(words,rate,method,cfg,folder,label,*,initial=None,global_window=0):
    a=np.full(8,1 << 22,dtype=np.int64) if initial is None else np.array(initial,dtype=np.int64)
    states=[a.copy()];outputs=[];counters=[];selected=method['selected'];mult=method['multiplier']
    for iw,w in enumerate(words.reshape(-1,120,4)):
        y,g,b,prod=digital(w[None,:,:],a[None,:]);s=prod[0,:selected].sum(axis=0)
        delta=round_ratio(s*np.array([-2,-6,-12,-24,-32,-96,-192,-384])*mult*rate['numerator'],125*rate['denominator'])
        after=a+delta
        assert np.all((after>=0)&(after<=2047*4096)),'coefficient saturation'
        samples,values=scalar_output(w,a,y.ravel(),cfg)
        observations=[FourLaneConversion((global_window+iw)*120+j,j%4,sample) for j,sample in enumerate(samples)]
        independent=[]
        for bank in range(2):
            config=cfg.stage1_lms if bank==0 else cfg.stage2_lms
            config=replace(config,step_sizes=tuple(mu*F(rate['numerator'],rate['denominator']) for mu in config.step_sizes))
            state=FixedGatedLmsState(tuple(map(int,a[4*bank:4*bank+4])),(0,)*4,(0,)*4,(0,)*4,(global_window+iw)*120)
            fixed=_bank(state,config,observations,values[bank],tuple(j<selected for j in range(120)),mult)
            assert fixed.requested_deltas==tuple(map(int,delta[4*bank:4*bank+4]))
            assert fixed.state.accumulator_codes==tuple(map(int,after[4*bank:4*bank+4]))
            assert fixed.selected_gate_counts==tuple(map(int,g[0,:selected,4*bank:4*bank+4].sum(axis=0)))
            independent.extend(F(p,64) for p in fixed.selected_product_sums)
            COUNTS['bank_commits']+=1
        steps=tuple(mu*F(rate['numerator'],rate['denominator']) for mu in cfg.stage1_lms.step_sizes+cfg.stage2_lms.step_sizes)
        requests,expected=commit(tuple(map(int,a)),tuple(independent),mult,steps)
        assert requests==tuple(map(int,delta)) and expected==tuple(map(int,after))
        counters.append({'gates':g[0,:selected].sum(axis=0).tolist(),'correlations':s.tolist(),
            'zero_request':(delta==0).astype(int).tolist(),'nonzero_sum_zero':((delta==0)&(s!=0)).astype(int).tolist(),
            'hidden_changed':(a!=after).astype(int).tolist(),'export_changed':(round_ratio(a,4096)!=round_ratio(after,4096)).astype(int).tolist()})
        outputs.append(y.ravel());a=after;states.append(a.copy())
        COUNTS['online_codes']+=120;COUNTS['commits']+=1;COUNTS['learning_observations_per_stage']+=selected
    ys=np.array(outputs,dtype='<i2');ss=np.array(states,dtype='<i4')
    ys.tofile(folder/(label+'_outputs.bin'));ss.tofile(folder/(label+'_q22.bin'))
    write(folder/(label+'_counters.json'),counters)
    return ys,ss,counters


def unit(words,cfg,folder,label,*,endpoint=False):
    a=np.full((1,8),1 << 22,dtype=np.int64)
    if endpoint:
        # Keep the original zero-clipping gate: record its failures, never pass
        # by silently deleting endpoints or changing the source/model/criterion.
        y=digital(words[None,:,:],a)[0].ravel()
    else:y=output_only(words[None,:,:],a).ravel()
    scalar_output(words,a[0],y,cfg,require_legal=not endpoint)
    if endpoint:
        clipped=np.clip(y,0,4095);clipped.astype('<i2').tofile(folder/(label+'_saturated_outputs.bin'))
        bad=np.flatnonzero(y!=clipped)
        write(folder/(label+'_boundary.json'),{'output_clips':len(bad),'minimum_raw':int(y.min()),
            'maximum_raw':int(y.max()),'indices':bad.tolist(),'raw_codes':list(map(int,y[bad])),
            'source_legal':True,'independent_raw_and_saturated_core_equal':True})
    y.astype('<i2').tofile(folder/(label+'_outputs.bin'))
    COUNTS['endpoint_codes' if endpoint else 'unit_codes']+=len(y)


def run(folder):
    folder.mkdir(parents=True,exist_ok=False)
    p=load(P);shutil.copyfile(P,folder/'protocol.json')
    arch=ROOT/p['source_architecture_protocol'];shutil.copyfile(arch,folder/'architecture_protocol.json')
    executable=[relative(Path(__file__)),
        'experiments/exp_062_same_input_background/verify.py',
        'experiments/exp_060_static_auxiliary_preflight/run.py',
        'experiments/exp_057_static_two_stage_million/common.py',
        'experiments/exp_069_gu_learning_rate/check_normal_loss_limits.py',
        'src/adc_research/theory/static_fixed_contract.py']
    executable += [relative(f) for f in (ROOT/'src/adc_research').rglob('*.py')]
    executable.append('configs/architectures/gu_behavioral_v1.yaml')
    manifest={n:digest(ROOT/n) for n in sorted(set(executable))}
    write(folder/'execution_hashes.json',manifest)
    write(folder/'design_hashes.json',{relative(P):digest(P),relative(arch):digest(arch)})
    write(folder/'environment.json',{'python':platform.python_version(),'numpy':np.__version__,'platform':platform.platform()})
    origin=ROOT/p['input']['original_tone_file'];assert digest(origin)==p['input']['original_tone_sha256']
    base=np.fromfile(origin,dtype='<f8');n=len(base)
    input_tables={}
    for c in [v for v in p['cases'] if v['role']=='development']+[{'name':'old127_control','tone_bin':127}]:
        idx=(c['tone_bin']*pow(127,-1,n)*np.arange(n))%n
        input_tables[c['name']]=base[idx]
        input_tables[c['name']].astype('<f8').tofile(folder/(c['name']+'_tone.bin'))
    write(folder/'input_hashes.json',{relative(folder/(name+'_tone.bin')):digest(folder/(name+'_tone.bin')) for name in input_tables})
    pipeline,cfg=fixed_setup(load(arch))
    case={'name':'both_smooth','stage1':[.975,-.055],'stage2':[.98,-.04],'auxiliary':[.975,-.055]}
    ideal={'name':'ideal','stage1':[1.,0.],'stage2':[1.,0.],'auxiliary':[1.,0.]}
    all_cases=[c for c in p['cases'] if c['role']=='development']+[{'name':'old127_control','tone_bin':127}]
    sources={};running=[];indices=np.arange(3840);d1,d2=tags(p['preflight_seed'],indices)
    for c in all_cases:
        tone=input_tables[c['name']]
        w=source(tone[indices],d1,d2,case,pipeline,folder,c['name']);sources[c['name']]=w
        unit(w,cfg,folder,c['name']+'_unit')
        for rate in p['rate_scales']:
            for method in p['methods']:
                name=c['name']+'_'+rate['name']+'_'+method['name']
                result=learn(w,rate,method,cfg,folder,name)
                if c['name']=='dev_509':running.append((rate,method,name,result))
        print('short control passed',c['name'],flush=True)
    ideal_tone=base[(509*pow(127,-1,n)*indices)%n]
    iw=source(ideal_tone,d1,d2,ideal,pipeline,folder,'ideal509');unit(iw,cfg,folder,'ideal509_unit')
    for rate,method,name,(y,s,counters) in running:
        w=sources['dev_509'];restart_label=name+'_restart'
        first=learn(w[:1920],rate,method,cfg,folder,restart_label+'_first')
        write(folder/(restart_label+'_checkpoint.json'),{'q22':list(map(int,first[1][-1])),'global_window':16,'counters':first[2]})
        checkpoint=load(folder/(restart_label+'_checkpoint.json'))
        second=learn(w[1920:],rate,method,cfg,folder,restart_label+'_second',initial=checkpoint['q22'],global_window=checkpoint['global_window'])
        assert np.array_equal(np.concatenate((first[0],second[0])),y)
        assert np.array_equal(np.concatenate((first[1],second[1][1:])),s)
        assert checkpoint['counters']+second[2]==counters
    print('serialized restart passed',flush=True)
    grid=np.concatenate((-1+(2*np.arange(4096)+1)/4096,[-1.,np.nextafter(1.,-np.inf)]))
    grid_x=np.repeat(grid,4);dd=np.tile(np.array(list(product((-1,1),repeat=2))),(len(grid),1))
    rejected=0
    for model in (case,ideal):
        label=model['name']+'_endpoint'
        w=source(grid_x,dd[:,0],dd[:,1],model,pipeline,folder,label);unit(w,cfg,folder,label,endpoint=True)
        for x in (1.,-1-1/2048):
            for pair in product((-1,1),repeat=2):
                try:source([x],np.array([pair[0]]),np.array([pair[1]]),model,pipeline,folder,'invalid')
                except ValueError:rejected+=1
                else:raise AssertionError('invalid source domain accepted')
    print('endpoint/ideal/source controls passed',flush=True)
    # Balanced controls access development frequencies and original127 ONLY.
    balanced=[];pairs=np.tile(np.array(list(product((-1,1),repeat=2))),(n,1))
    for k in (127,509,1009):
        idx=(k*pow(127,-1,n)*np.arange(n))%n
        w=source(np.repeat(base[idx],4),pairs[:,0],pairs[:,1],case,pipeline,folder,'balanced_'+str(k),verify_platform=False)
        outputs=[]
        for coeff in p['balanced_permutation_control_budget']['fixed_coefficient_states_q1_10']:
            a=np.array([coeff],dtype=np.int64)*4096
            yy=output_only(w[None,:,:],a).ravel();outputs.append(yy);COUNTS['balanced_fixed_readouts']+=len(yy)
        if k==127:balanced=[w.copy(),outputs]
        else:
            order=np.argsort(idx)
            assert np.array_equal(w.reshape(n,4,4)[order],balanced[0].reshape(n,4,4))
            for yy,ref in zip(outputs,balanced[1],strict=True):assert np.array_equal(yy.reshape(n,4)[order],ref.reshape(n,4))
    limits=p['preflight_budget']
    assert COUNTS['online_codes']==limits['total_online_codes'] and COUNTS['commits']==limits['total_bank_pair_commits']
    assert COUNTS['source_conversions']==limits['total_valid_source_conversions'] and rejected==limits['endpoint_domain_rejections']
    assert COUNTS['rational_readouts']==limits['rational_readout_probes_online_unit_endpoint']
    assert COUNTS['unit_codes']==limits['unit_codes_main_old127_ideal']
    assert COUNTS['learning_observations_per_stage']==limits['learning_observations_per_stage']
    assert COUNTS['bank_commits']==limits['formal_single_bank_commits']
    assert COUNTS['balanced_fixed_readouts']==p['balanced_permutation_control_budget']['integer_fixed_readouts']
    verify_hashes(manifest);verify_hashes(load(folder/'design_hashes.json'));verify_hashes(load(folder/'input_hashes.json'))
    endpoint_clips=sum(load(folder/(model['name']+'_endpoint_boundary.json'))['output_clips'] for model in (case,ideal))
    result={'passed':endpoint_clips==0,'diagnostic_completed':True,'counts':COUNTS,'domain_rejections':rejected,
        'endpoint_output_clips':endpoint_clips,'implementation_mismatches':0,
        'original_zero_clipping_gate_retained':True,
        'confirmation_opened':False,'future_reservation_opened':False,'fft':0,'performance_scores':0,
        'source_generation':True,'new_online_preflight_paths_only':True,
        'long_ready':False,'long_ready_reason':'Original endpoint zero-clipping gate fails if endpoint_output_clips>0; preserve failure. Long accelerator/storage/complete source freeze also remains required.'}
    write(folder/'verification.json',result)
    write(folder/'delivery_hashes.json',{f.name:digest(f) for f in folder.iterdir() if f.is_file() and f.name!='delivery_hashes.json'})
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);args=parser.parse_args()
    try:run(args.folder.resolve())
    except Exception:
        if args.folder.exists():(args.folder/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
