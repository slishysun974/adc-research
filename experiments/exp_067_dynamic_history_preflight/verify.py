"""Full independent physical-history/digital replay and declared limit controls."""

import argparse
from dataclasses import asdict
from fractions import Fraction as F
import gzip
import json
from pathlib import Path
import traceback

import numpy as np

from adc_research.calibration.fixed_adaptive_two_stage import FixedTwoStageAdaptiveState
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState
from adc_research.calibration.fixed_four_lane_window import (
    FourLaneConversion, correct_fixed_four_lane_window, FixedFourLaneWindowConfig,
)
from adc_research.evaluation.observations import digital_sample
from adc_research.platform.dual_path_settling import DualPathSettlingState
from adc_research.platform.two_phase_dual_path import process, TwoPhasePath
from adc_research.platform.backend_sar import convert as sar
from adc_research.theory.dynamic_history import convert, phase, expanded, unroll, scalar_current_correlation
from adc_research.theory.static_fixed_contract import export, readout, commit, nearest_even
from experiments.exp_057_static_two_stage_million.common import truth, write
from experiments.exp_060_static_auxiliary_preflight.run import fixed_setup, check_physical
from experiments.exp_065_input_switch_tracking.verify import digital, tags
from experiments.exp_067_dynamic_history_preflight.run import (
    ROOT, digest, sources, phases_config, integer_code,
)


def load_rows(path):
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        return [json.loads(line) for line in handle]


def restore(row):
    return FixedTwoStageAdaptiveState(*(FixedGatedLmsState(
        tuple(row[bank]['accumulator_codes']), tuple(row[bank]['gate_counts']),
        tuple(row[bank]['nonzero_update_counts']), tuple(row[bank]['coefficient_change_counts']),
        row[bank]['sample_count']) for bank in ('stage1','stage2')))


def acc(row):
    return row['stage1']['accumulator_codes']+row['stage2']['accumulator_codes']


def controls(p, pipeline):
    scalar_count = chain_count = boundaries = 0; maximum = 0.0
    for tracking in map(lambda x:F(str(x)),p['controls']['tracking_controls']):
        a,b = F(1,25),F(1,100)
        exact = F(1,2); native = float(exact); targets=[]
        for n in range(p['controls']['exact_scalar_steps']):
            target=F((7*n)%19-9,20); targets.append(target)
            output=phase(exact,target,a,tracking,b)[1]
            assert output==expanded(exact,target,a,tracking,b)
            assert output==unroll(targets,F(1,2),a,tracking,b)
            native=TwoPhasePath(float(a),float(tracking),float(b)).advance(native,float(target))[1]
            maximum=max(maximum,abs(native-float(output))); exact=output; scalar_count+=1
    mean_controls=[]
    for tracking in (F(0),F(1,10),F(1)):
        gain,rho=F(39,40),F(1,25)
        for inverse in (1/gain,1/(gain*(1-rho))):
            pp=[]
            for x in (F(-1,5),F(1,5)):
                for old in (F(-1,3),F(1,3)):
                    for d in (F(-1,32),F(1,32)):
                        rr=phase(old,gain*(x+d),rho,tracking)[1]
                        pp.append(d*(inverse*rr-d))
            total=sum(pp)/len(pp)
            assert total==scalar_current_correlation(gain,inverse,rho,F(1,1024))
            mean_controls.append({'tracking':str(tracking),'inverse':str(inverse),'correlation':str(total)})
    for case in p['cases']:
        rational={bank:tuple(F(str(v)) for v in case[bank]) for bank in ('stage1','auxiliary','stage2')}
        for ph in p['phases']:
            factors=tuple(F(str(v)) for v in ph['amplification']); tracking=F(str(ph['tracking']))
            exact=(F(0),)*3; native=DualPathSettlingState(); cfg=phases_config(case,ph)
            count=p['controls']['exact_chain_steps_smooth' if case['name']=='both_smooth' else 'exact_chain_steps_linear']
            for n in range(count):
                x=F((37*n)%101-50,71); d1=1 if n%2 else -1;d2=1 if n%3 else -1
                r=convert(x,d1,d2,rational,factors,tracking,exact)
                actual=process(float(x),pipeline,cfg,native,sample_index=n,
                               dither_symbols=(d1,d2),nonidealities=truth(case));check_physical(actual)
                sample=digital_sample(actual.pipeline)
                assert (r.q1,r.q2,r.backend)==(sample.stage1_symbol,sample.stage2_symbol,sample.backend_centered_code)
                vals=actual.tracking_starts+actual.static_targets+actual.next_state.as_tuple()
                refs=r.starts+r.targets+r.outputs
                maximum=max(maximum,max(abs(a-float(b)) for a,b in zip(vals,refs)))
                exact=r.outputs;native=actual.next_state;chain_count+=1
    # Exact one-path flash preimages at all thresholds, with history and neighbors.
    a,k,old=F(1,25),F(1),F(1,2)
    endpoint_records=[]
    for j in range(8):
        threshold=F(2*j-7,8)
        target=(threshold-a*k*old)/(1-a)
        for shift in (-F(1,2**40),F(0),F(1,2**40)):
            output=phase(old,target+shift,a,k)[1]
            native=TwoPhasePath(float(a),float(k)).advance(float(old),float(target+shift))[1]
            # Zero may differ in double if cancellation lands on adjacent side;
            # mathematical equality and native double are recorded separately.
            exact_decision=output>=threshold
            native_decision=native>=float(threshold)
            if shift!=0:
                assert native_decision==exact_decision
            endpoint_records.append({'threshold':str(threshold),'target_shift':str(shift),
                'exact_decision':bool(exact_decision),'native_decision':bool(native_decision),
                'native_minus_exact_voltage':native-float(output)})
            boundaries+=1
    sar_controls=[]
    for j in range(1,256):
        t=F(j,128)-1
        for shift in (-F(1,2**40),F(0),F(1,2**40)):
            x=t+shift; expected=(128*(x+1)).__floor__()-128
            assert sar(float(x),pipeline.backend).centered_code==expected
            sar_controls.append(expected)
    # At reset/zero factors arbitrary past states must disappear at the same input.
    memoryless=0
    for c in p['cases']:
        for ph in p['phases'][:2]:
            cfg=phases_config(c,ph)
            a=process(-1/2048,pipeline,cfg,DualPathSettlingState(),dither_symbols=(1,1),nonidealities=truth(c))
            b=process(-1/2048,pipeline,cfg,DualPathSettlingState(*p['controls']['history_contrast']),
                      dither_symbols=(1,1),nonidealities=truth(c))
            assert a.next_state==b.next_state and digital_sample(a.pipeline)==digital_sample(b.pipeline)
            memoryless+=1
    assert maximum<=p['verification']['voltage_tolerance']
    return {'exact_scalar_steps':scalar_count,'exact_chain_conversions':chain_count,
        'flash_history_boundary_nodes':boundaries,'SAR_boundary_nodes':len(sar_controls),
        'flash_history_endpoints':endpoint_records,
        'flash_exact_equality_native_exceptions':sum(r['exact_decision']!=r['native_decision'] for r in endpoint_records),
        'memoryless_history_pairs':memoryless,'scalar_correlations':mean_controls,
        'maximum_exact_to_native_voltage_difference':maximum}


def verify(folder):
    p=json.loads((folder/'protocol.json').read_text(encoding='utf-8'))
    src=json.loads((folder/'source_protocol.json').read_text(encoding='utf-8-sig'))
    assert sources()==json.loads((folder/'source_hashes.json').read_text(encoding='utf-8'))
    reference_hashes=json.loads((folder/'reference_hashes.json').read_text(encoding='utf-8'))
    for name,h in reference_hashes.items():
        assert digest(folder/'reference'/name)==digest(ROOT/p['static_reference']/name)==h
    tone=np.fromfile(folder/'reference/tone.bin',dtype='<f8');nw=p['budget']['windows']
    pipeline,cfg=fixed_setup(src);steps=cfg.stage1_lms.step_sizes+cfg.stage2_lms.step_sizes
    tally={'physical_conversions':0,'online_codes':0,'unit_codes':0,'two_bank_commits':0,
           'rational_readouts':0,'restart_physical_conversions':0,'restart_online_codes':0,
           'static_reference_online_codes':0,'static_reference_q22_values':0,
           'skip_history_selected_word_changes':0,'wrong_reset_suffix_word_changes':0}
    maxv=0.0
    for c in p['cases']:
        for ph in p['phases']:
            name=c['name']+'_'+ph['name'];rows=load_rows(folder/(name+'_records.jsonl.gz'))
            windows=load_rows(folder/(name+'_windows.jsonl.gz'))
            assert len(rows)==nw*120 and len(windows)==nw
            physical=(0.,0.,0.);wrong_skip=(0.,0.,0.);words=[]
            d1,d2=tags(p['seed'],np.arange(len(rows)))
            for n,row in enumerate(rows):
                assert row['n']==n and row['x']==float(tone[n%len(tone)])
                assert row['d']==[int(d1[n]),int(d2[n])]
                assert tuple(row['before'])==physical
                r=convert(row['x'],*row['d'],c,ph['amplification'],ph['tracking'],physical)
                assert list((r.q1,r.q2,r.backend))==row['word']
                vv=r.starts+r.targets+r.outputs+r.nominal
                saved=tuple(row['starts']+row['targets']+row['outputs']+row['nominal'])
                error=max(abs(a-b) for a,b in zip(vv,saved));maxv=max(maxv,error)
                assert error<=p['verification']['voltage_tolerance']
                physical=r.outputs
                if n%120<4:
                    skip=convert(row['x'],*row['d'],c,ph['amplification'],ph['tracking'],wrong_skip)
                    wrong_skip=skip.outputs
                    changed=list((skip.q1,skip.q2,skip.backend))!=row['word']
                    if ph['name']=='hold':tally['skip_history_selected_word_changes']+=changed
                    else:assert not changed
                bits=(row['d'][0]>0)+2*(row['d'][1]>0)
                words.append(row['word']+[bits]);tally['physical_conversions']+=1
            words=np.array(words,dtype=np.int64).reshape(nw,120,4)
            output=np.array([r['online'] for r in rows]);unit=np.array([r['unit'] for r in rows])
            u=np.full((nw,8),1<<22,dtype=np.int64)
            assert np.array_equal(digital(words,u)[0].ravel(),unit);tally['unit_codes']+=len(unit)
            for m,method in enumerate(p['methods']):
                before=np.array([acc(w['before'][m]) for w in windows],dtype=np.int64)
                after=np.array([acc(w['after'][m]) for w in windows],dtype=np.int64)
                assert np.array_equal(before[0],u[0]) and np.array_equal(before[1:],after[:-1])
                yy,g,sp,prod=digital(words,before)
                assert np.array_equal(yy.ravel(),output[:,m]);tally['online_codes']+=len(rows)
                selected=np.arange(120)<4 if method['name']=='point30' else np.ones(120,dtype=bool)
                for w,win in enumerate(windows):
                    k=export(tuple(map(int,before[w])))
                    sums=prod[w,selected].sum(axis=0)
                    req,new=commit(tuple(map(int,before[w])),tuple(F(int(v)) for v in sums),method['multiplier'],steps)
                    assert tuple(new)==tuple(after[w])
                    assert tuple(new[i]-int(before[w,i]) for i in range(8))==req
                    for bank,bname in enumerate(('stage1','stage2')):
                        indices=slice(4*bank,4*bank+4)
                        update=win['updates'][m][bank]
                        assert update['requested_deltas']==list(req[indices])
                        assert update['applied_deltas']==list(req[indices])
                        assert update['selected_product_sums']==list(map(int,64*sums[indices]))
                        counts=g[w,selected,indices].sum(axis=0)
                        assert update['selected_gate_counts']==list(map(int,counts))
                        for lane in range(4):
                            assert update['lane_gate_counts'][lane]==list(map(int,g[w,lane::4,indices].sum(axis=0)))
                            assert update['lane_product_sums'][lane]==list(map(int,64*prod[w,lane::4,indices].sum(axis=0)))
                        b=win['before'][m][bname];a=win['after'][m][bname]
                        assert a['gate_counts']==[int(v+n) for v,n in zip(b['gate_counts'],counts)]
                        assert a['nonzero_update_counts']==[v+int(d!=0) for v,d in zip(b['nonzero_update_counts'],req[indices])]
                        assert a['coefficient_change_counts']==[v+int(x!=y) for v,x,y in zip(b['coefficient_change_counts'],k[indices],export(new)[indices])]
                        assert a['sample_count']==b['sample_count']+120==120*(w+1)
                    # Independent rational readout at first, restart and last window.
                    if w in (0,p['controls']['checkpoint_window'],nw-1):
                        for slot,row in enumerate(rows[120*w:120*(w+1)]):
                            rr=readout(*row['word'],*row['d'],tuple(F(v,1024) for v in k),data_q3=True)
                            assert nearest_even(rr.output)==int(yy[w,slot])
                            assert rr.gates==tuple(tuple(bool(v) for v in g[w,slot,i:i+4]) for i in (0,4))
                            assert rr.support==tuple(tuple(bool(v) for v in sp[w,slot,i:i+4]) for i in (0,4))
                            tally['rational_readouts']+=1
                    tally['two_bank_commits']+=1
                if ph['name']=='static':
                    old=folder/'reference'/f"{c['name']}_{p['seed']}_{method['name']}_q22.bin"
                    oldstate=np.fromfile(old,dtype='<f8').reshape(nw+1,8)*(1<<22)
                    assert np.array_equal(oldstate,np.vstack((before[0],after)))
                    tally['static_reference_q22_values']+=oldstate.size
            if ph['name']=='static':
                oldwords=np.fromfile(folder/'reference'/f"{c['name']}_{p['seed']}_words.bin",dtype='i1').reshape(nw,120,4)
                oldout=np.fromfile(folder/'reference'/f"{c['name']}_{p['seed']}_outputs.bin",dtype='<i2').reshape(-1,3)
                assert np.array_equal(oldwords,words)
                assert np.array_equal(oldout[:,0],unit) and np.array_equal(oldout[:,1:],output)
                tally['static_reference_online_codes']+=output.size
            checkpoint=json.loads((folder/(name+'_checkpoint.json')).read_text(encoding='utf-8'))
            start=checkpoint['global_conversion'];assert start==120*p['controls']['checkpoint_window']
            assert checkpoint['analog']==rows[start]['before']
            assert checkpoint['digital']==windows[start//120]['before']
            physical=DualPathSettlingState(*checkpoint['analog'])
            dstates=[restore(s) for s in checkpoint['digital']]
            wrong=(0.,0.,0.)
            for w in range(start//120,nw):
                batch=[]
                for row in rows[120*w:120*(w+1)]:
                    actual=process(row['x'],pipeline,phases_config(c,ph),physical,sample_index=row['n'],
                                   dither_symbols=tuple(row['d']),nonidealities=truth(c));check_physical(actual)
                    assert list(actual.next_state.as_tuple())==row['outputs']
                    sample=digital_sample(actual.pipeline)
                    assert [sample.stage1_symbol,sample.stage2_symbol,sample.backend_centered_code]==row['word']
                    physical=actual.next_state;batch.append(FourLaneConversion(row['n'],row['n']%4,sample))
                    bad=convert(row['x'],*row['d'],c,ph['amplification'],ph['tracking'],wrong);wrong=bad.outputs
                    changed=list((bad.q1,bad.q2,bad.backend))!=row['word']
                    if ph['name']=='hold':tally['wrong_reset_suffix_word_changes']+=changed
                    else:assert not changed
                    tally['restart_physical_conversions']+=1
                for m,method in enumerate(p['methods']):
                    result=correct_fixed_four_lane_window(batch,dstates[m],FixedFourLaneWindowConfig(cfg,selection=method['selection']))
                    assert [integer_code(cal) for cal in result.calibrations]==output[120*w:120*(w+1),m].tolist()
                    assert asdict(result.state)==asdict(restore(windows[w]['after'][m]))
                    dstates[m]=result.state;tally['restart_online_codes']+=120
            print(f'{name}: independent whole physical/digital replay and exact suffix restart passed',flush=True)
    assert maxv<=p['verification']['voltage_tolerance']
    assert tally['skip_history_selected_word_changes']>0
    # A finite suffix may quantize away an initial history change; retain actual count,
    # do not require every model to exhibit a digital difference.
    result={'passed':True,**tally,'maximum_physical_replay_voltage_difference':maxv,
        'all_window_counters_replayed':True,'all_sources_and_old_reference_unchanged':True,
        'controls':controls(p,pipeline),'scope':'full34560 physical history equations/full digital output and every commit; original platform generated all records and exactly replayed17280 suffix conversions; rational readout selected declared windows'}
    write(folder/'verification.json',result)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path)
    folder=parser.parse_args().folder.resolve()
    try:verify(folder)
    except Exception:
        write(folder/'verification_failure.json',{'passed':False,'traceback':traceback.format_exc()});raise
