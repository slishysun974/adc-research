"""Full independent source/integer replay and frozen original/core probes."""
import argparse
from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
import traceback

import numpy as np

from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.fixed_four_lane_window import _bank,FourLaneConversion
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.evaluation.observations import digital_sample
from adc_research.theory.static_fixed_contract import readout,export,commit,nearest_even
from experiments.exp_060_static_auxiliary_preflight.run import fixed_setup,plant,check_physical
from experiments.exp_062_same_input_background.verify import digital,tags,physical_words,round_ratio
from .check_boundary_contract import raw_q3
from .prepare import ROOT,load,write,digest,check


def states(folder,stem,name,nw):
    file=folder/(stem+'_'+name+'_q22.bin')
    assert file.stat().st_size==(nw+1)*32
    return np.memmap(file,dtype='<i4',mode='r',shape=(nw+1,8))


def verify(folder):
    check(folder);assert (folder/'completed.json').exists()
    p=load(folder/'protocol.json');e=load(folder/'execution_contract_v1.json');plan=load(folder/'runplan.json')
    pre=plan['preflight'];budget=e['preflight' if pre else 'long']
    pipeline,cfg=fixed_setup(load(folder/'architecture_protocol.json'))
    smooth={'name':'both_smooth','stage1':[.975,-.055],'stage2':[.98,-.04],'auxiliary':[.975,-.055]}
    ideal={'name':'ideal','stage1':[1.,0.],'stage2':[1.,0.],'auxiliary':[1.,0.]}
    counts={'source_conversions':0,'unit_outputs':0,'online_outputs':0,'bank_pair_commits':0,
            'learning_observations_per_stage':0,'original_platform_probe_conversions':0,
            'rational_and_formal_readouts_each':0,'formal_single_bank_commits':0,
            'endpoint_fixed_readouts':0,'mixed_fixed_readouts':0}
    old=ROOT/'artifacts/runs/EXP_071/preflight_v2_diagnostic'
    cache={}

    def scalar(w,a,expected):
        q1,q2,be,bits=map(int,w);d1=2*(bits&1)-1;d2=2*((bits>>1)&1)-1
        k=export(tuple(map(int,a)))
        rd=readout(q1,q2,F(be),d1,d2,tuple(F(v,1024) for v in k),data_q3=True)
        cascade=replace(cfg.cascade,stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=k[:4]),
                        stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=k[4:]))
        sample=DigitalCalibrationSample(q1,q2,be,d1,d2);core=correct_two_stage_fixed_observed(sample,cascade)
        assert core.unclipped_output_scaled==8*rd.output and core.stage1_raw_scaled==8*rd.raw1
        assert nearest_even(F(core.output_scaled,8))==int(expected)
        counts['rational_and_formal_readouts_each']+=1
        return rd,sample

    for src in plan['sources']:
        stem=src['stem'];nw=src['windows'];tone=np.fromfile(ROOT/src['tone_file'],dtype='<f8')
        words=np.memmap(folder/(stem+'_words.bin'),dtype='i1',mode='r',shape=(nw,120,4))
        assert (folder/(stem+'_words.bin')).stat().st_size==nw*480
        unit=np.memmap(folder/(stem+'_unit_outputs.bin'),dtype='<i2',mode='r',shape=(nw,120))
        model=ideal if src['ideal'] else smooth
        for start in range(0,nw,256):
            stop=min(nw,start+256);part=words[start:stop]
            ix=np.arange(start*120,stop*120);d1,d2=tags(src['seed'],ix)
            assert np.array_equal(part[:,:,3].ravel(),(d1>0)+2*(d2>0))
            native=physical_words(tone[ix%30720],d1,d2,model)
            for j,v in enumerate(native):assert np.array_equal(v,part[:,:,j].ravel()),(stem,'source',start,j)
            a=np.full((stop-start,8),1<<22,dtype=np.int64)
            y=digital(part,a)[0];level,_=raw_q3(part,a)
            assert np.all((level>=0)&(level<=32760))
            assert np.array_equal(y,unit[start:stop])
        sm=load(folder/(stem+'_source.json'))
        assert sm['SourceConversions']==sm['UnitCodes']==nw*120
        assert sm['UnitQ3Clips']==sm['UnitIntegerClips']==0
        assert sm['MinimumUnit']==int(unit.min()) and sm['MaximumUnit']==int(unit.max())
        if pre:
            assert np.array_equal(words,np.fromfile(old/(src['case']+'_words.bin'),dtype='i1').reshape(nw,120,4))
            assert np.array_equal(unit,np.fromfile(old/(src['case']+'_unit_outputs.bin'),dtype='<i2').reshape(nw,120))
        probes=list(range(nw)) if pre else sorted({w for b in p['long_validation']['probe_blocks'] for w in range(256*b,256*b+4)}|set(range(nw-4,nw)))
        assert len(probes)==(32 if pre else 28)
        for w in probes:
            for j,word in enumerate(words[w]):
                q1,q2,be,bits=map(int,word);d1=2*(bits&1)-1;d2=2*((bits>>1)&1)-1;ix=120*w+j
                tr=plant(float(tone[ix%30720]),d1,d2,model,pipeline,ix);check_physical(tr)
                sample=digital_sample(tr.pipeline)
                assert (q1,q2,be)==(sample.stage1_symbol,sample.stage2_symbol,sample.backend_centered_code)
                scalar(word,(1<<22,)*8,unit[w,j]);counts['original_platform_probe_conversions']+=1
        cache[stem]=(words,unit,probes)
        counts['source_conversions']+=nw*120;counts['unit_outputs']+=nw*120
        print('verified independent source',stem,flush=True)

    for task in plan['tasks']:
        stem=task['stem'];nw=task['windows'];desc=task['paths'];meta=load(folder/(stem+'.json'))
        assert meta['Windows']==nw and meta['Conversions']==120*nw and meta['GlobalStart']==task['global_start']
        words=np.memmap(ROOT/task['word_file'],dtype='i1',mode='r',offset=480*task['word_start'],shape=(nw,120,4))
        output=np.memmap(folder/(stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(nw,120,4))
        assert (folder/(stem+'_outputs.bin')).stat().st_size==nw*120*8
        ss=[states(folder,stem,d['name'],nw) for d in desc]
        for h,d in enumerate(desc):
            initial=states(folder,task['resume_task'],d['name'],16)[-1] if task.get('resume_task') else d['initial']
            assert np.array_equal(ss[h][0],initial) and np.array_equal(meta['Paths'][h]['Initial'],initial)
            for start in range(0,nw,256):
                stop=min(nw,start+256);acc=np.asarray(ss[h][start:stop],dtype=np.int64);after=np.asarray(ss[h][start+1:stop+1],dtype=np.int64)
                y,g,b,products=digital(words[start:stop],acc)
                assert np.array_equal(y,output[start:stop,:,h])
                level,_=raw_q3(words[start:stop],acc)
                assert np.all((level>=0)&(level<=32760)) and np.all((y>=0)&(y<=4095))
                sums=products[:,:d['selected']].sum(axis=1)
                delta=round_ratio(sums*np.array([-2,-6,-12,-24,-32,-96,-192,-384])*d['multiplier']*d['num'],125*d['den'])
                assert np.all((acc+delta>=0)&(acc+delta<=2047*4096))
                assert np.array_equal(acc+delta,after)
                saved=meta['Blocks'][start//256]
                for key,span in (('All',120),('Selected',d['selected'])):
                    for field,v in (('Gates',g[:,:span].sum(axis=(0,1))),('Basis',b[:,:span].sum(axis=(0,1))),
                                    ('Both',(g[:,:span]&b[:,:span]).sum(axis=(0,1))),('Correlations',products[:,:span].sum(axis=(0,1)))):
                        assert np.array_equal(saved[key][h][field],v),(stem,h,start,key,field)
                for key,v in (('ZeroRequest',(delta==0).sum(axis=0)),('NonzeroSumZero',((delta==0)&(sums!=0)).sum(axis=0)),
                              ('HiddenChanged',(acc!=after).sum(axis=0)),('ExportChanged',(round_ratio(acc,4096)!=round_ratio(after,4096)).sum(axis=0))):
                    assert np.array_equal(saved[key][h],v)
            assert meta['CoefficientClips'][h]==meta['OutputClips'][h]==0
            if pre and task['kind']=='main':
                prior=task['case']+'_'+d['rate']+'_'+d['method']
                assert np.array_equal(output[:,:,h],np.fromfile(old/(prior+'_outputs.bin'),dtype='<i2').reshape(nw,120))
                assert np.array_equal(ss[h],np.fromfile(old/(prior+'_q22.bin'),dtype='<i4').reshape(nw+1,8))
        if task.get('resume_task'):
            whole=task['case']+'_'+str(task['seed']);first=task['resume_task']
            oo=np.memmap(folder/(whole+'_outputs.bin'),dtype='<i2',mode='r',shape=(32,120,4))
            first_out=np.memmap(folder/(first+'_outputs.bin'),dtype='<i2',mode='r',shape=(16,120,4))
            assert np.array_equal(first_out,oo[:16]) and np.array_equal(output,oo[16:])
            fm=load(folder/(first+'.json'));wm=load(folder/(whole+'.json'))
            for h,d in enumerate(desc):
                assert np.array_equal(ss[h],states(folder,whole,d['name'],32)[16:])
                assert np.array_equal(states(folder,first,d['name'],16),states(folder,whole,d['name'],32)[:17])
                for key in ('ZeroRequest','NonzeroSumZero','HiddenChanged','ExportChanged'):
                    assert np.array_equal(np.array(fm['Blocks'][0][key][h])+meta['Blocks'][0][key][h],wm['Blocks'][0][key][h])
                for key in ('All','Selected'):
                    for field in ('Gates','Basis','Both','Correlations'):
                        assert np.array_equal(np.array(fm['Blocks'][0][key][h][field])+meta['Blocks'][0][key][h][field],wm['Blocks'][0][key][h][field])
        probes=list(range(nw)) if pre else cache[stem][2]
        for w in probes:
            before=[tuple(map(int,st[w])) for st in ss];local=[[[],[]] for _ in desc];conversions=[]
            for j,word in enumerate(words[w]):
                for h,d in enumerate(desc):
                    rd,sample=scalar(word,before[h],output[w,j,h])
                    if h==0:conversions.append(FourLaneConversion(task['global_start']+120*w+j,j%4,sample))
                    d1=sample.stage1_dither_symbol;d2=sample.stage2_dither_symbol
                    local[h][0].append((512*d1,int(8*rd.y1)));local[h][1].append((128*d2,int(8*rd.y2)))
            for h,d in enumerate(desc):
                for bank,bcfg in enumerate((cfg.stage1_lms,cfg.stage2_lms)):
                    changed=replace(bcfg,step_sizes=tuple(mu*F(d['num'],d['den']) for mu in bcfg.step_sizes))
                    bs=FixedGatedLmsState(before[h][4*bank:4*bank+4],(0,)*4,(0,)*4,(0,)*4,task['global_start']+120*w)
                    updated=_bank(bs,changed,conversions,local[h][bank],tuple(j<d['selected'] for j in range(120)),d['multiplier'])
                    assert updated.state.accumulator_codes==tuple(map(int,ss[h][w+1,4*bank:4*bank+4]))
                    requests,after=commit(before[h][4*bank:4*bank+4],tuple(F(v,64) for v in updated.selected_product_sums),d['multiplier'],changed.step_sizes)
                    assert requests==updated.requested_deltas and after==updated.state.accumulator_codes
                    counts['formal_single_bank_commits']+=1
        counts['online_outputs']+=120*nw*4;counts['bank_pair_commits']+=nw*4
        counts['learning_observations_per_stage']+=nw*sum(d['selected'] for d in desc)
        print('verified all integer codes/states/counters',stem,flush=True)

    for c in plan['fixed_controls']:
        words=np.fromfile(ROOT/c['word_file'],dtype='i1').reshape(-1,4)
        if c['limit']>0:words=words[:c['limit']]
        recorded=np.fromfile(folder/(c['name']+'_fixed.bin'),dtype='<i4').reshape(-1,3)
        assert len(words)==len(recorded)
        for w,row in zip(words,recorded,strict=True):
            rd,_=scalar(w,np.array(c['codes'])*4096,row[2])
            assert (int(8*rd.output),nearest_even(rd.output))==tuple(row[:2])
        if c['kind']=='endpoint':
            assert np.array_equal(recorded[:,1],np.fromfile(old/(c['name']+'_outputs.bin'),dtype='<i2'))
            assert np.array_equal(recorded[:,2],np.fromfile(old/(c['name']+'_saturated_outputs.bin'),dtype='<i2'))
        counts[c['kind']+'_fixed_readouts']+=len(words)
    if pre:assert load(folder/'negative_controls.json')['Rejected']==budget['invalid_source_rejections']
    for name,value in counts.items():
        if name in budget:assert value==budget[name],(name,value,budget[name])
    check(folder)
    result={'passed':True,'preflight':pre,'long_ready':pre,'counts':counts,'all_source_words_independent':True,
            'all_codes_states_gates_counts_replayed':True,'working_q3_clips':0,'working_integer_clips':0,'coefficient_saturations':0,
            'original_endpoint_failed_gate_preserved':True,'confirmation_opened':not pre,'future_reservation_opened':False,
            'full_original_platform_replay':False,'fft':0,'performance_scoring':0}
    write(folder/'verification.json',result)
    write(folder/'delivery_hashes.json',{f.name:digest(f) for f in folder.iterdir() if f.is_file() and f.name!='delivery_hashes.json'})
    print('verification accepted',result,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);a=parser.parse_args()
    try:verify(a.folder.resolve())
    except Exception:
        write(a.folder/'verify_failure.json',{'traceback':traceback.format_exc()});raise
