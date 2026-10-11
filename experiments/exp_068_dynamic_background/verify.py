"""Independent full integer replay, expanded history filter and original probes."""
import argparse
from dataclasses import replace
from fractions import Fraction as F
from itertools import product
import json
from pathlib import Path
import traceback

import numpy as np
from scipy.signal import lfilter

from adc_research.calibration.fixed_four_lane_window import FourLaneConversion, _bank
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.evaluation.observations import digital_sample
from adc_research.platform.dual_path_settling import DualPathSettlingState
from adc_research.platform.two_phase_dual_path import process
from adc_research.theory.dynamic_history import convert
from adc_research.theory.static_fixed_contract import export, readout, commit
from experiments.exp_057_static_two_stage_million.common import truth, write
from experiments.exp_060_static_auxiliary_preflight.run import fixed_setup, check_physical
from experiments.exp_061_static_auxiliary_million.verify import sources
from experiments.exp_065_input_switch_tracking.verify import digital, tags
from experiments.exp_066_input_switch_tracking_long.verify import round_ratio, check_nominal
from experiments.exp_067_dynamic_history_preflight.run import ROOT, phases_config
from experiments.exp_067_dynamic_history_preflight.verify import load_rows, acc


def load(folder):
    return tuple(json.loads((folder/f).read_text(encoding='utf-8-sig')) for f in ('protocol.json','source_protocol.json'))


def scalar_control():
    # Enumerate all independent bipolar sequences. This checks finite-horizon
    # moments against direct outputs, then checks the stationary limit algebra.
    c,k,v=F(3,4),F(1,2),F(1); n=8; cu=ss=0; losses=[F(0),F(0)]
    kd=1/c; kn=(1-k*k)/(c*(1-k**(2*n)))
    for sequence in product((-1,1),repeat=n):
        s=F(0)
        for u in sequence:s=c*u+k*s
        cu+=sequence[-1]*s;ss+=s*s
        for j,coef in enumerate((kd,kn)):losses[j]+=(coef*s-sequence[-1])**2
    count=2**n;cu/=count;ss/=count;losses=[x/count for x in losses]
    assert cu==c*v and ss==c*c*v*(1-k**(2*n))/(1-k*k) and kn==cu/ss
    for coef,loss in zip((kd,kn),losses):assert loss==v-2*coef*cu+coef*coef*ss
    optimum=(1-k*k)/c
    assert v-2*c*optimum*v+optimum**2*c*c*v/(1-k*k)==v*k*k
    assert v*k*k/(1-k*k)-v*k*k==v*k**4/(1-k*k)
    return {'enumerated_sequences':count,'finite_horizon':n,'exact_moment_and_loss_checks':True,
            'finite_optimum':str(kn),'stationary_optimum':str(optimum),'dither_root':str(kd),
            'stationary_optimal_loss':str(v*k*k),'stationary_root_loss':str(v*k*k/(1-k*k)),
            'two_stage_mean_root_proved':False}


def physical(x,d1,d2,case,ph,previous):
    """Expanded convolution independently computed; no platform imports used."""
    thresholds=np.arange(-.875,1,.25)
    q1=np.searchsorted(thresholds,x,side='right')-4
    z1=4*(x-q1/4+d1/32)
    a1,b1=case['stage1'];a2,b2=case['stage2']
    t1=a1*z1+b1*np.power(z1,3)
    aa,ba=case['auxiliary'];ta=aa*z1+ba*np.power(z1,3)
    def advance(target,j):
        alpha=ph['amplification'][j];k=alpha*ph['tracking']
        return lfilter([1-alpha],[1,-k],target,zi=[k*previous[j]])[0]
    m=advance(t1,0);aux=advance(ta,1)
    q2=np.searchsorted(thresholds,aux,side='right')-4
    z2=4*(m-q2/4+d2/32);t2=a2*z2+b2*np.power(z2,3);rear=advance(t2,2)
    be=np.floor((rear+1)*128).astype(np.int64)-128
    assert np.all((x>=-1)&(x<1)&(np.abs(z1)<=1)&(m>=-1)&(m<1)&(np.abs(z2)<=1)&(rear>=-1)&(rear<1))
    return np.column_stack((q1,q2,be)),np.column_stack((m,aux,rear)),aux,rear


def verify(folder):
    p,src=load(folder);pipeline,cfg=fixed_setup(src);nominal=ROOT/p['nominal_folder']
    check_nominal(folder,nominal);scalar=scalar_control()
    tone=np.fromfile(folder/'tone.bin',dtype='<f8');n=len(tone);bw=n//120
    short=json.loads((folder/'ideal_static_202610621.json').read_text(encoding='utf-8-sig'))['Windows']==32 if (folder/'ideal_static_202610621.json').exists() else False
    seeds=p['seeds'][:1] if short else p['seeds'];phases=p['phases'] if short else p['phases'][1:]
    streams=codes=commits=units=probes=rational=bank_commits=physics=ambiguous=short_codes=0
    max_history=max_voltage=0.
    for case in p['cases']:
        for seed in seeds:
            for ph in phases:
                stem=f"{case['name']}_{ph['name']}_{seed}";meta=json.loads((folder/(stem+'.json')).read_text(encoding='utf-8-sig'))
                nw=meta['Windows'];count=120*nw;blocks=(count+n-1)//n
                assert nw==(32 if short else p['budget']['windows_per_path'])
                raw=np.memmap(folder/(stem+'_words.bin'),dtype='i1',mode='r',shape=(nw,120,4))
                out=np.memmap(folder/(stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(nw,120,3))
                st=[np.memmap(folder/(stem+'_'+m['name']+'_q22.bin'),dtype='<f8',mode='r',shape=(nw+1,8)) for m in p['methods']]
                hist=np.memmap(folder/(stem+'_history.bin'),dtype='<f8',mode='r',shape=(nw+1,3))
                assert np.array_equal(hist[0],p['initial_analog_outputs']) and all(np.all(s[0]==1) for s in st)
                for b in range(blocks):
                    start=b*bw;stop=min(nw,(b+1)*bw);words=raw[start:stop]
                    idx=np.arange(120*start,120*stop,dtype=np.int64);x=tone[idx%n];d1,d2=tags(seed,idx)
                    assert np.array_equal(words[:,:,3].ravel(),(d1>0)+2*(d2>0))
                    expected,h,aux,rear=physical(x,d1,d2,case,ph,hist[start])
                    # A reordered floating filter can lie across an exact threshold.
                    # Replay each affected whole window in the independently declared
                    # native order, restoring saved prior history. Never waive a word.
                    near=np.any(np.abs(aux[:,None]-np.arange(-.875,1,.25))<p['verification']['voltage_tolerance'],axis=1)
                    near|=np.abs((rear+1)*128-np.rint((rear+1)*128))<128*p['verification']['voltage_tolerance']
                    for wlocal in np.unique(np.flatnonzero(near)//120):
                        prior=tuple(hist[start+wlocal]);off=120*wlocal
                        for j in range(120):
                            r=convert(float(x[off+j]),int(d1[off+j]),int(d2[off+j]),case,ph['amplification'],ph['tracking'],prior)
                            expected[off+j]=(r.q1,r.q2,r.backend);h[off+j]=r.outputs;prior=r.outputs
                        ambiguous+=1
                    assert np.array_equal(expected,words[:,:,:3].reshape(-1,3)),(stem,b,'physical words')
                    diff=float(np.max(np.abs(h[119::120]-hist[start+1:stop+1])))
                    max_history=max(max_history,diff);assert diff<=p['verification']['voltage_tolerance']
                    physics+=len(x)
                    unity=np.full((stop-start,8),1<<22,dtype=np.int64)
                    yu,_,_,_=digital(words,unity);assert np.array_equal(yu,out[start:stop,:,0]);units+=len(x)
                    for m,method in enumerate(p['methods']):
                        before=np.rint(st[m][start:stop]*(1<<22)).astype(np.int64);after=np.rint(st[m][start+1:stop+1]*(1<<22)).astype(np.int64)
                        y,g,bs,products=digital(words,before);assert np.array_equal(y,out[start:stop,:,m+1]);assert np.all((y>=0)&(y<=4095))
                        sel=method['selected'];sums=products[:,:sel].sum(axis=1)
                        delta=round_ratio(np.array([-2,-6,-12,-24,-32,-96,-192,-384])*method['multiplier']*sums,125)
                        assert np.all((before+delta>=0)&(before+delta<=2047*4096));assert np.array_equal(before+delta,after)
                        for key,span in (('All',120),('Selected',sel)):
                            c=meta['Blocks'][b][key][m]
                            for field,value in (('Gates',g[:,:span].sum(axis=(0,1))),('Basis',bs[:,:span].sum(axis=(0,1))),('Both',(g[:,:span]&bs[:,:span]).sum(axis=(0,1))),('Correlations',products[:,:span].sum(axis=(0,1)))):assert np.array_equal(value,c[field])
                        for field,value in (('ZeroRequest',(delta==0).sum(axis=0)),('HiddenChanged',(before!=after).sum(axis=0)),('ExportChanged',(round_ratio(before,4096)!=round_ratio(after,4096)).sum(axis=0))):assert np.array_equal(value,meta['Blocks'][b][field][m])
                        codes+=len(x);commits+=stop-start
                audit=np.fromfile(folder/(stem+'_probes.bin'),dtype='<f8').reshape(-1,2092)
                expected_probes=list(range(nw)) if short else sorted({b*bw+j for b in p['verification']['long_probe_blocks'] for j in range(4)}|set(range(nw-4,nw)))
                assert list(audit[:,0].astype(int))==expected_probes and len(audit)==meta['ProbeWindows']
                for row in audit:
                    w=int(row[0]);analog=DualPathSettlingState(*row[1:4]);before=row[4:20].reshape(2,8)
                    obs=row[20:2060].reshape(120,17);sums=row[2060:2076].reshape(2,8);after=row[2076:].reshape(2,8)
                    assert np.array_equal(row[1:4],hist[w])
                    for m in range(2):assert np.array_equal(before[m],st[m][w]) and np.array_equal(after[m],st[m][w+1])
                    ks=[tuple(F(v,1024) for v in export(tuple(int(v*(1<<22)) for v in before[m]))) for m in range(2)]
                    cascades=[replace(cfg.cascade,stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=tuple(int(v*1024) for v in k[:4])),
                        stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=tuple(int(v*1024) for v in k[4:]))) for k in ks]
                    conversions=[];values=[[],[]];computed=np.zeros((2,8),dtype=np.int64)
                    for j,sample in enumerate(obs):
                        x,dd1,dd2,q1,q2,be=sample[:6];idx=120*w+j
                        dt=tags(seed,np.array([idx]));assert x==tone[idx%n] and (dd1,dd2)==(dt[0][0],dt[1][0])
                        original=process(float(x),pipeline,phases_config(case,ph),analog,sample_index=idx,
                            dither_symbols=(int(dd1),int(dd2)),nonidealities=truth(case));check_physical(original)
                        ds=digital_sample(original.pipeline);analog=original.next_state
                        assert (ds.stage1_symbol,ds.stage2_symbol,ds.backend_centered_code)==(q1,q2,be)
                        expected=(4*original.pipeline.stage1.residue_preamp,4*original.pipeline.stage2.residue_preamp)+original.tracking_starts+original.static_targets+analog.as_tuple()
                        error=max(abs(a-b) for a,b in zip(expected,sample[6:],strict=True));max_voltage=max(max_voltage,error)
                        assert error<=p['verification']['voltage_tolerance'];assert np.array_equal(raw[w,j,:3],(q1,q2,be))
                        conversions.append(FourLaneConversion(idx,j%4,ds))
                        for m,method in enumerate(p['methods']):
                            rd=readout(int(q1),int(q2),F(int(be)),int(dd1),int(dd2),ks[m],data_q3=True)
                            core=correct_two_stage_fixed_observed(ds,cascades[m]);assert core.unclipped_output_scaled==int(8*rd.output)
                            assert core.stage1_raw_scaled==int(8*rd.raw1) and round(float(rd.output))==out[w,j,m+1]
                            values[m].append([(int(512*dd1),int(8*rd.y1)),(int(128*dd2),int(8*rd.y2))])
                            if j<method['selected']:
                                for bank,local in enumerate((rd.y1,rd.y2)):
                                    for seg,gate in enumerate(rd.gates[bank]):computed[m,4*bank+seg]+=int((64*dd1 if bank==0 else 16*dd2)*local*gate)
                            rational+=1
                        probes+=1
                    assert np.array_equal(computed,sums);assert np.allclose(analog.as_tuple(),hist[w+1],atol=p['verification']['voltage_tolerance'],rtol=0)
                    for m,method in enumerate(p['methods']):
                        accumulator=tuple(int(v*(1<<22)) for v in before[m]);steps=cfg.stage1_lms.step_sizes+cfg.stage2_lms.step_sizes
                        requests,expected=commit(accumulator,tuple(F(int(v)) for v in computed[m]),method['multiplier'],steps)
                        assert expected==tuple(int(v*(1<<22)) for v in after[m])
                        for bank,bcfg in enumerate((cfg.stage1_lms,cfg.stage2_lms)):
                            bs=FixedGatedLmsState(accumulator[4*bank:4*bank+4],(0,)*4,(0,)*4,(0,)*4,120*w)
                            update=_bank(bs,bcfg,conversions,[v[bank] for v in values[m]],tuple(j<method['selected'] for j in range(120)),method['multiplier'])
                            assert update.requested_deltas==requests[4*bank:4*bank+4] and update.state.accumulator_codes==expected[4*bank:4*bank+4];bank_commits+=1
                if short:
                    ref=ROOT/p['short_reference'];refname=case['name']+'_'+ph['name']
                    records=load_rows(ref/(refname+'_records.jsonl.gz'));windows=load_rows(ref/(refname+'_windows.jsonl.gz'))
                    assert np.array_equal(out.reshape(-1,3),[[r['unit']]+r['online'] for r in records])
                    assert np.array_equal(raw[:,:,:3].reshape(-1,3),[r['word'] for r in records])
                    for m in range(2):
                        expected=np.array([acc(w['before'][m]) for w in windows]+[acc(windows[-1]['after'][m])])
                        assert np.array_equal(np.rint(st[m]*(1<<22)).astype(np.int64),expected)
                    assert np.allclose(hist[1:],[records[120*w+119]['outputs'] for w in range(nw)],atol=p['verification']['voltage_tolerance'],rtol=0)
                    short_codes+=2*count
                assert meta['CoefficientClips']==meta['OutputClips']==[0,0]
                streams+=1
                print('verified',stem,count,'conversions',flush=True)
    assert streams==(9 if short else p['budget']['physical_streams'])
    sources(folder)
    write(folder/'verification.json',{'passed':True,'streams':streams,'all_online_codes_replayed':codes,
        'all_unit_codes_replayed':units,'all_bank_pair_commits_replayed':commits,'all_physical_words_replayed':physics,
        'threshold_near_native_windows':ambiguous,'max_window_history_error':max_history,
        'original_platform_probe_conversions':probes,'rational_readouts':rational,'original_bank_commits':bank_commits,
        'maximum_original_platform_voltage_error':max_voltage,'full_original_platform_replay':short,
        'short_reference_online_codes':short_codes,'scalar_objective_control':scalar,'source_hashes_unchanged':True})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);folder=parser.parse_args().folder.resolve()
    try:verify(folder)
    except Exception:write(folder/'verification_failure.json',{'traceback':traceback.format_exc()});raise
