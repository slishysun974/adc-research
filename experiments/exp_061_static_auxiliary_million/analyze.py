"""Offline scores, full tone replay and finite crossed-observation diagnostics."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import traceback

import numpy as np

from experiments.exp_057_static_two_stage_million.common import input_tags, metrics, write
from experiments.exp_057_static_two_stage_million.analyze import tail_statistics
from experiments.exp_059_static_fixed_million.analyze import effective, pwl, output, state_diagnostics
from experiments.exp_060_static_auxiliary_preflight.run import plant, fixed_setup, voltage_fields, check_physical
from experiments.exp_060_static_auxiliary_preflight.verify import native
from adc_research.evaluation.observations import digital_sample
from .verify import sources


def protocols(folder):
    return tuple(json.loads((folder/name).read_text(encoding='utf-8-sig')) for name in
                 ('protocol.json','source_protocol.json','auxiliary_protocol.json'))


def prepare(folder):
    p,src,aux=protocols(folder);pipeline,_=fixed_setup(src);t=p['test_record']
    xt=t['amplitude']*np.sin(2*np.pi*t['tone_bin']*np.arange(t['samples'])/t['samples'])
    dt=np.array([input_tags(t['seed'],i)[1] for i in range(len(xt))])
    xv=np.repeat(-.82+(np.arange(p['validation_points'])+.5)*(1.64/p['validation_points']),4)
    dv=np.tile(np.array([[-1,-1],[-1,1],[1,-1],[1,1]]),(p['validation_points'],1))
    data={'tone_x':xt,'tone_tags':dt,'grid_x':xv,'grid_tags':dv};count=0;maximum=0
    for case in aux['cases']:
        for kind,x,tags in (('tone',xt,dt),('grid',xv,dv)):
            raw=[]
            for i,(v,(d1,d2)) in enumerate(zip(x,tags,strict=True)):
                original=plant(float(v),int(d1),int(d2),case,pipeline,i);check_physical(original)
                sample=digital_sample(original.pipeline)
                word,voltage=native(float(v),int(d1),int(d2),case)
                assert word==[sample.stage1_symbol,sample.stage2_symbol,sample.backend_centered_code]
                err=max(abs(a-b) for a,b in zip(voltage,voltage_fields(original),strict=True))
                maximum=max(maximum,err);assert err<2e-12
                raw.append([*word,*voltage]);count+=1
            data[case['name']+'_'+kind]=np.asarray(raw).T
        r=data[case['name']+'_tone']
        np.column_stack((r[0],r[1],r[2],dt)).astype('<i4').tofile(folder/(case['name']+'_tone_input.bin'))
        print('prepared original platform',case['name'],flush=True)
    np.savez(folder/'evaluation_records.npz',**data);sources(folder)
    write(folder/'evaluation_preparation.json',{'passed':True,'original_platform_conversions':count,
        'native_original_words_exact':True,'maximum_voltage_error':maximum,'source_hashes_unchanged':True})


def raw_fields(record):
    # q1,q2,c3,z1,m,a,z2,r2 -> old offline score interface
    return (record[0],record[1],record[4],record[7],128*record[7],record[2])


def local(raw,tags,k):
    p2=pwl(raw[5],k[4:],32,True);r1=128*raw[1]+p2-16*tags[:,1]
    y1=pwl(r1,k[:4],128,True)-64*tags[:,0];y2=p2-16*tags[:,1]
    values=np.column_stack((y1,y2));gates=[];support=[]
    for bank,width in ((0,128),(1,32)):
        thresholds=np.rint(8*np.r_[0,width*np.cumsum(k[bank*4:bank*4+3])])/8
        gates.append(np.abs(values[:,bank,None])>=thresholds)
        support.append(np.abs(r1 if bank==0 else raw[5])[:,None]>width*np.arange(4))
    return 2048+512*raw[0]+y1,values,np.concatenate(gates,axis=1),np.concatenate(support,axis=1),r1


def online_replay(raw,tags,hidden,method):
    acc=np.rint(hidden*(1<<22)).astype(np.int64);values=np.empty(len(tags))
    num=np.array([1,3,6,12,1,3,6,12]);factors=np.array([-2]*4+[-32]*4)
    for start in range(0,len(tags),120):
        # Export ties to even in Q22/4096; every integer is exactly represented.
        k=np.clip(np.rint(acc/4096),0,2047)/1024
        rr=tuple(v[start:start+120] for v in raw);tt=tags[start:start+120]
        y,loc,gates,_,_=local(rr,tt,k);values[start:start+120]=y
        n=method['selected'];products=np.repeat(tt[:n]*np.array([64,16]),4,axis=1)*np.repeat(loc[:n],4,axis=1)*gates[:n]
        sums=products.sum(axis=0);assert np.all(sums==sums.astype(np.int64))
        request=factors*num*method['multiplier']*sums.astype(np.int64)
        mag=np.abs(request);delta=np.sign(request)*(mag//125+(2*(mag%125)>125))
        acc+=delta;assert np.all((acc>=0)&(acc<=2047*4096))
    return values


def crossed(raw0,raw1,record0,record1,tags,x,k0,k1):
    # O_ab: observation a and frozen state b, all four on identical x/tags.
    y00=output(raw0,tags[:,0],tags[:,1],k0,True)
    y10=output(raw1,tags[:,0],tags[:,1],k0,True)
    y01=output(raw0,tags[:,0],tags[:,1],k1,True)
    y11=output(raw1,tags[:,0],tags[:,1],k1,True)
    result={}
    for kind,ys in (('continuous',(y00,y10,y01,y11)),('integer',tuple(np.rint(y) for y in (y00,y10,y01,y11)))):
        o00,o10,o01,o11=ys
        terms=np.array([o10-o00,o01-o00,o11-o10-o01+o00])
        total=o11-o00;assert np.max(np.abs(total-terms.sum(axis=0)))==0
        base=o00-2048*(x+1);components=np.vstack((base,terms));moments=components@components.T/len(x)
        err=o11-2048*(x+1)
        assert abs(np.mean(err**2)-moments.sum())<1e-9*max(1,np.mean(err**2))
        result[kind]={'terms':['same_state_observation','same_observation_state','interaction'],
            'term_mean':terms.mean(axis=1).tolist(),'term_rms':np.sqrt(np.mean(terms**2,axis=1)).tolist(),
            'difference_mse':float(np.mean(total**2)),'component_second_moments_with_reference_error':moments.tolist(),
            'actual_mse':float(np.mean(err**2)),'reference_mse':float(np.mean(base**2))}
    _,l0,g0,b0,r0=local(raw0,tags,k0);_,l1,g1,b1,r1=local(raw1,tags,k0)
    yy0=np.repeat(l0,4,axis=1);yy1=np.repeat(l1,4,axis=1);dd=np.repeat(tags*np.array([64,16]),4,axis=1)
    signal=dd*g0*(yy1-yy0);selection=dd*(g1.astype(int)-g0.astype(int))*yy1
    change=dd*(g1*yy1-g0*yy0);assert np.array_equal(signal+selection,change)
    delta0=l0[:,1]+16*tags[:,1]-128*record0[6]
    delta1=l1[:,1]+16*tags[:,1]-128*record1[6]
    assert np.max(np.abs((r1-r0)-(delta1-delta0)))<2e-12
    result.update(q2_changes=int(np.count_nonzero(raw0[1]!=raw1[1])),
        reference_observed_RA=float(np.max(np.abs(record0[4]-raw0[1]/4))),
        case_observed_RA=float(np.max(np.abs(record1[4]-raw1[1]/4))),
        reference_reconstruction_residual_rms=float(np.sqrt(np.mean(delta0**2))),
        case_same_state_reconstruction_residual_rms=float(np.sqrt(np.mean(delta1**2))),
        same_state_gate_changes=np.count_nonzero(g1!=g0,axis=0).tolist(),
        same_state_reference_joint_support=np.count_nonzero(g0&b0,axis=0).tolist(),
        same_state_case_joint_support=np.count_nonzero(g1&b1,axis=0).tolist(),
        same_state_correlation_change=change.mean(axis=0).tolist(),
        same_state_correlation_readout_term=signal.mean(axis=0).tolist(),
        same_state_correlation_gate_term=selection.mean(axis=0).tolist())
    return result


def analyze(folder):
    p,src,aux=protocols(folder);data=np.load(folder/'evaluation_records.npz')
    x=data['tone_x'];dt=data['tone_tags'];xv=data['grid_x'];dv=data['grid_tags'];rows=[];pairs=[];replayed=0
    cases={c['name']:c for c in aux['cases']}
    for case in aux['cases']:
        raw=raw_fields(data[case['name']+'_tone']);record=data[case['name']+'_grid'];rv=raw_fields(record)
        for method in src['methods']:
            for seed in p['seeds']:
                stem=f"{case['name']}_{method['name']}_{seed}"
                meta=json.loads((folder/(stem+'.json')).read_text(encoding='utf-8-sig'))
                statefile=folder/(stem+'_q22.bin')
                states=np.memmap(statefile,dtype='<f8',mode='r',shape=(method['training_windows']+1,8))
                tones=np.memmap(folder/(stem+'_tones.bin'),dtype='<f8',mode='r',shape=(5,2,len(x)))
                checkpoints=[]
                for ci,w in enumerate(method['checkpoint_windows']):
                    k=effective(states[w],3);scores={}
                    for si,kind in enumerate(('frozen','online')):
                        y=np.asarray(tones[ci,si]);assert np.all((y>=0)&(y<=4095))
                        expected=output(raw,dt[:,0],dt[:,1],k,True) if si==0 else online_replay(raw,dt,states[w],method)
                        assert np.array_equal(expected,y),(stem,w,kind);replayed+=len(x)
                        integer=np.rint(y);err=y-2048*(x+1);rounding=integer-y
                        continuous=metrics(y,x,p['test_record']['tone_bin']);ints=metrics(integer,x,p['test_record']['tone_bin'])
                        cross=2*float(np.mean(err*rounding));power=float(np.mean(rounding**2))
                        assert abs(ints['mse_codes_squared']-continuous['mse_codes_squared']-cross-power)<1e-9
                        scores[kind]={'continuous':continuous,'integer':ints,'integer_cross':cross,'integer_rounding_power':power}
                    grid_y=output(rv,dv[:,0],dv[:,1],k,True);assert np.all((grid_y>=0)&(grid_y<=4095))
                    checkpoints.append({'window':w,'conversion_slots':120*w,'observations_per_bank':w*method['selected'],
                        'effective':k.tolist(),'grid_mse':float(np.mean((grid_y-2048*(xv+1))**2)),**scores})
                # Original EXP-059 fixed-matrix statistics on a 512-midpoint subgrid.
                ix=np.concatenate([np.arange(4)+4*j for j in range(4,len(xv)//4,8)])
                diag,balance=state_diagnostics(states,3,tuple(v[ix] for v in rv),dv[ix],xv[ix])
                rows.append({'case':case['name'],'method':method['name'],'seed':seed,'metadata':meta,
                    'tail_hidden':tail_statistics(states),'tail_effective':tail_statistics(effective(states,3)),
                    'fixed_rear_mean_covariance':diag,'finite_hidden_increment_balance':balance,'checkpoints':checkpoints,
                    'state_sha256':sha256(statefile.read_bytes()).hexdigest()})
                reference=case['paired_reference']
                if reference!=case['name']:
                    refstates=np.memmap(folder/f'{reference}_{method["name"]}_{seed}_q22.bin',dtype='<f8',mode='r',shape=states.shape)
                    record0=data[reference+'_grid'];rv0=raw_fields(record0)
                    pairpoints=[]
                    for w in method['checkpoint_windows']:
                        pairpoints.append({'window':w,**crossed(rv0,rv,record0,record,dv,xv,effective(refstates[w],3),effective(states[w],3))})
                    pairs.append({'case':case['name'],'reference':reference,'method':method['name'],'seed':seed,
                        'checkpoints':pairpoints,'tail_hidden_difference':tail_statistics(states-refstates),
                        'tail_effective_difference':tail_statistics(effective(states,3)-effective(refstates,3))})
                print('analyzed and independently replayed',stem,flush=True)
    sources(folder)
    result={'passed':True,'paths':len(rows),'pairs':len(pairs),'rows':rows,'paired_rows':pairs,
        'generated_static_samples':sum(r['metadata']['GeneratedSamples'] for r in rows),
        'full_frozen_and_online_tone_codes_replayed':replayed,'source_hashes_unchanged':True,
        'full_long_training_transition_replay':False,'chip_certified':False}
    write(folder/'summary.json',result);print(json.dumps({k:v for k,v in result.items() if k not in ('rows','paired_rows')}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);parser.add_argument('--prepare',action='store_true')
    args=parser.parse_args();folder=args.folder.resolve()
    try:(prepare if args.prepare else analyze)(folder)
    except Exception:
        write(folder/('preparation_failure.json' if args.prepare else 'analysis_failure.json'),{'traceback':traceback.format_exc()});raise
