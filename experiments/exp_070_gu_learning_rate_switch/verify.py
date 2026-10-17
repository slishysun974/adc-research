"""Independent complete integer replay plus declared scalar/core probes."""
import argparse
from dataclasses import replace
from fractions import Fraction as F
import traceback
import numpy as np

from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.fixed_four_lane_window import (
    _bank, FourLaneConversion, FixedFourLaneWindowConfig, correct_fixed_four_lane_window,
)
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState
from adc_research.calibration.fixed_adaptive_two_stage import FixedTwoStageAdaptiveState
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.theory.static_fixed_contract import readout, export, commit, nearest_even
from adc_research.evaluation.observations import digital_sample
from experiments.exp_060_static_auxiliary_preflight.run import fixed_setup, plant, check_physical
from experiments.exp_062_same_input_background.verify import digital, round_ratio, tags, physical_words
from .prepare import ROOT, read, write, check


def state_file(folder, stem, name, windows):
    return np.memmap(folder/(stem+'_'+name+'_q22.bin'),dtype='<i4',mode='r',shape=(windows+1,8))


def negative_controls(cfg, seed, words):
    setup=FixedFourLaneWindowConfig(cfg)
    bank=FixedGatedLmsState((1 << 22,)*4,(0,)*4,(0,)*4,(0,)*4,0)
    state=FixedTwoStageAdaptiveState(bank,bank)
    rows=[FourLaneConversion(j,j%4,DigitalCalibrationSample(0,0,0,1,1)) for j in range(120)]
    for bad in (rows[:-1], [FourLaneConversion(1,0,rows[0].sample)]+rows[1:]):
        try:correct_fixed_four_lane_window(bad,state,setup)
        except ValueError:pass
        else:raise AssertionError('invalid window accepted')
    a,b=tags(seed,np.arange(120))
    assert np.any(words[0,:,3] != (a>0)+2*(b>0)), 'restarted tags not detected'
    acc=(1 << 22)+2047
    assert export((acc,))[0]==export((acc+1,))[0]
    assert export((acc+1,))[0]!=export((acc+2,))[0]
    return 4


def verify(folder):
    p=read(folder/'protocol.json');plan=read(folder/'runplan.json')
    assert (folder/'completed.json').exists()
    check(folder)
    pipeline,cfg=fixed_setup(read(folder/'architecture_protocol.json'))
    models={case['name']:case for case in read(folder/'model_protocol.json')['cases']}
    tone=np.fromfile(folder/'tone.bin',dtype='<f8');n=p['input']['samples_per_block']
    assert len(tone)==n
    output_count=pair_commits=physical_probes=rational_probes=core_commits=0
    base_codes=nochange_codes=restart_codes=negative=0
    for task in plan['tasks']:
        stem=task['stem'];nw=task['windows'];desc=task['paths'];count=len(desc)
        meta=read(folder/(stem+'.json'))
        assert meta['Windows']==nw and meta['GlobalStart']==task['global_start']
        words=np.memmap(ROOT/task['word_file'],dtype='i1',mode='r',offset=480*task['word_start'],shape=(nw,120,4))
        output=np.memmap(folder/(stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(nw,120,count))
        assert (folder/(stem+'_outputs.bin')).stat().st_size==nw*120*count*2
        states=[state_file(folder,stem,d['name'],nw) for d in desc]
        clip_counts=np.zeros(count,dtype=np.int64)
        for h,d in enumerate(desc):
            initial=d['initial'] if not task.get('resume_task') else state_file(folder,task['resume_task'],d['name'],16)[-1]
            assert np.array_equal(states[h][0],initial)
            assert np.array_equal(meta['Paths'][h]['Initial'],initial)
        for block,start in enumerate(range(0,nw,256)):
            stop=min(start+256,nw);part=words[start:stop]
            indices=task['global_start']+np.arange(start*120,stop*120)
            dd1,dd2=tags(task['seed'],indices)
            assert np.array_equal(part[:,:,3].ravel(),(dd1>0)+2*(dd2>0))
            x=tone[indices%n]*(1.0 if task['kind']=='nochange' else 0.5)
            native=physical_words(x,dd1,dd2,models[task['case']])
            for j,expected in enumerate(native):assert np.array_equal(part[:,:,j].ravel(),expected)
            for h,d in enumerate(desc):
                acc=np.asarray(states[h][start:stop],dtype=np.int64)
                after=np.asarray(states[h][start+1:stop+1],dtype=np.int64)
                y,g,b,products=digital(part,acc)
                assert np.array_equal(y,output[start:stop,:,h]),(stem,d['name'],block)
                sums=products[:,:d['selected']].sum(axis=1)
                delta=round_ratio(sums*np.array([-2,-6,-12,-24,-32,-96,-192,-384])*d['multiplier']*d['num'],125*d['den'])
                unclipped=acc+delta
                clip_counts[h]+=np.count_nonzero((unclipped<0)|(unclipped>2047*4096))
                assert np.array_equal(np.clip(unclipped,0,2047*4096),after)
                for key,span in (('All',120),('Selected',d['selected'])):
                    saved=meta['Blocks'][block][key][h]
                    for field,value in (('Gates',g[:,:span].sum(axis=(0,1))),('Basis',b[:,:span].sum(axis=(0,1))),
                        ('Both',(g[:,:span]&b[:,:span]).sum(axis=(0,1))),('Correlations',products[:,:span].sum(axis=(0,1)))):
                        assert np.array_equal(value,saved[field]),(stem,h,block,field)
                for key,value in (('ZeroRequest',(delta==0).sum(axis=0)),('NonzeroSumZero',((delta==0)&(sums!=0)).sum(axis=0)),
                    ('HiddenChanged',(acc!=after).sum(axis=0)),('ExportChanged',(round_ratio(acc,4096)!=round_ratio(after,4096)).sum(axis=0))):
                    assert np.array_equal(value,meta['Blocks'][block][key][h]),(stem,key)
                output_count+=120*(stop-start);pair_commits+=stop-start
        assert np.array_equal(clip_counts,meta['CoefficientClips'])
        assert np.array_equal(np.count_nonzero((output<0)|(output>4095),axis=(0,1)),meta['OutputClips'])

        if task['kind']=='main' and plan['preflight']:
            old=ROOT/p['sources']['switch_base']
            for h,d in enumerate(desc):
                if d['rate']!='base':continue
                base=f"{task['case']}_{d['variant']}_{task['seed']}"
                oo=np.memmap(old/(base+'_outputs.bin'),dtype='<i2',mode='r',shape=(32768,120,3))
                mi=0 if d['method']=='point30' else 1
                ss=np.memmap(old/(base+'_'+d['method']+'_q22.bin'),dtype='<f8',mode='r',shape=(32769,8))
                assert np.array_equal(output[:,:,h],oo[:nw,:,mi+1])
                assert np.array_equal(states[h],ss[:nw+1]*(1 << 22))
                base_codes+=nw*120
            negative+=negative_controls(cfg,task['seed'],words)
        if task['kind']=='nochange':
            for h,d in enumerate(desc):
                source=ROOT/p['sources']['startup_base' if d['rate']=='base' else 'startup_quarter']
                raw_stem=f"{task['case']}_{task['seed']}";mi=0 if d['method']=='point30' else 1
                oo=np.memmap(source/(raw_stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(65536,120,3 if d['rate']=='base' else 6))
                suffix=('_' if d['rate']=='base' else '_quarter_')+d['method']+'_q22.bin'
                ss=np.memmap(source/(raw_stem+suffix),dtype='<f8' if d['rate']=='base' else '<i4',mode='r',shape=(65537,8))
                start=task['word_start'];factor=(1 << 22) if d['rate']=='base' else 1
                assert np.array_equal(output[:,:,h],oo[start:start+nw,:,mi+1 if d['rate']=='base' else mi])
                assert np.array_equal(states[h],ss[start:start+nw+1]*factor)
                nochange_codes+=nw*120
        if task.get('resume_task'):
            full_stem=f"{task['case']}_{task['seed']}";whole=read(folder/(full_stem+'.json'))
            for h,d in enumerate(desc):
                index=next(j for j,r in enumerate(whole['Paths']) if r['Name']==d['name'])
                whole_out=np.memmap(folder/(full_stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(32,120,len(whole['Paths'])))
                first=np.memmap(folder/(task['resume_task']+'_outputs.bin'),dtype='<i2',mode='r',shape=(16,120,count))
                assert np.array_equal(first[:,:,h],whole_out[:16,:,index])
                assert np.array_equal(output[:,:,h],whole_out[16:,:,index])
                assert np.array_equal(states[h],state_file(folder,full_stem,d['name'],32)[16:])
                assert np.array_equal(state_file(folder,task['resume_task'],d['name'],16),state_file(folder,full_stem,d['name'],32)[:17])
                a=read(folder/(task['resume_task']+'.json'))
                for key in ('ZeroRequest','NonzeroSumZero','HiddenChanged','ExportChanged'):
                    assert np.array_equal(np.array(a['Blocks'][0][key][h])+meta['Blocks'][0][key][h],whole['Blocks'][0][key][index])
                restart_codes+=32*120

        if task['kind']=='restart':
            probes=[]
        elif plan['preflight']:
            probes=range(nw)
        else:
            probes=sorted(set(w for b in p['verification']['long_probe_blocks'] for w in range(b*256,b*256+4))|set(range(nw-4,nw)))
            assert len(probes)==28
        for w in probes:
            before=[tuple(map(int,st[w])) for st in states]
            ks=[tuple(F(v,1024) for v in export(acc)) for acc in before]
            cascades=[replace(cfg.cascade,stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=export(acc)[:4]),
                         stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=export(acc)[4:])) for acc in before]
            conversions=[];local=[[[],[]] for _ in desc];sums=np.zeros((count,8),dtype=np.int64)
            for j,word in enumerate(words[w]):
                q1,q2,be,bits=map(int,word);d1,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
                idx=task['global_start']+120*w+j
                original=plant(float(tone[idx%n])*(1 if task['kind']=='nochange' else 0.5),d1,d2,models[task['case']],pipeline,idx)
                check_physical(original);sample=digital_sample(original.pipeline)
                assert (sample.stage1_symbol,sample.stage2_symbol,sample.backend_centered_code)==(q1,q2,be)
                physical_probes+=1;conversions.append(FourLaneConversion(idx,idx%4,sample))
                for h,d in enumerate(desc):
                    rd=readout(q1,q2,F(be),d1,d2,ks[h],data_q3=True)
                    core=correct_two_stage_fixed_observed(sample,cascades[h])
                    assert core.unclipped_output_scaled==8*rd.output and core.stage1_raw_scaled==8*rd.raw1
                    assert nearest_even(rd.output)==output[w,j,h]
                    for bank,y in enumerate((rd.y1,rd.y2)):
                        local[h][bank].append((512*d1 if bank==0 else 128*d2,int(8*y)))
                        if j<d['selected']:
                            for coord,g in enumerate(rd.gates[bank]):
                                sums[h,4*bank+coord]+=int((64*d1 if bank==0 else 16*d2)*y*g)
                    rational_probes+=1
            for h,d in enumerate(desc):
                ratio=F(d['num'],d['den']);steps=tuple(mu*ratio for mu in cfg.stage1_lms.step_sizes+cfg.stage2_lms.step_sizes)
                requested,expected=commit(before[h],tuple(F(int(v)) for v in sums[h]),d['multiplier'],steps)
                assert expected==tuple(map(int,states[h][w+1]))
                for bank,bcfg in enumerate((cfg.stage1_lms,cfg.stage2_lms)):
                    changed=replace(bcfg,step_sizes=tuple(mu*ratio for mu in bcfg.step_sizes))
                    bs=FixedGatedLmsState(before[h][4*bank:4*bank+4],(0,)*4,(0,)*4,(0,)*4,task['global_start']+120*w)
                    update=_bank(bs,changed,conversions,local[h][bank],tuple(j<d['selected'] for j in range(120)),d['multiplier'])
                    assert update.requested_deltas==requested[4*bank:4*bank+4]
                    assert update.state.accumulator_codes==expected[4*bank:4*bank+4]
                    core_commits+=1
        print('verified',stem,'paths',count,'windows',nw,flush=True)
    expected=p['preflight']['totals'] if plan['preflight'] else p['verification']
    budget=p['preflight']['totals'] if plan['preflight'] else p['budget']
    assert output_count==budget['outputs' if plan['preflight'] else 'new_online_outputs']
    assert pair_commits==budget['bank_pair_commits' if plan['preflight'] else 'new_bank_pair_commits']
    assert physical_probes==expected['original_platform_probe_conversions']
    assert rational_probes==expected['rational_core_readouts'] and core_commits==expected['formal_single_bank_commits']
    if plan['preflight']:
        assert (base_codes,nochange_codes,restart_codes,negative)==(46080,48960,46080,12)
    check(folder)
    write(folder/'verification.json',{'passed':True,'preflight':plan['preflight'],
        'all_output_codes_replayed':output_count,'all_bank_pair_commits_replayed':pair_commits,
        'original_platform_probe_conversions':physical_probes,'rational_core_readouts':rational_probes,
        'formal_single_bank_commits':core_commits,'base_main_exact_codes':base_codes,
        'nochange_exact_codes':nochange_codes,'serialized_restart_exact_codes':restart_codes,
        'negative_controls':negative,'all_source_words_tags_vector_formulas_checked':True,
        'all_counters_checked':True,'source_and_data_unchanged':True,'full_long_original_platform_replay':False})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=lambda x:__import__('pathlib').Path(x).resolve())
    folder=parser.parse_args().folder
    try:verify(folder)
    except Exception:write(folder/'verification_failure.json',{'traceback':traceback.format_exc()});raise
