"""Offline full-output scores and finite state identities, no online truth feedback."""
import argparse
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from adc_research.theory.static_state_statistics import mean_covariance_loss, finite_increment_balance
from experiments.exp_057_static_two_stage_million.common import basis, plant_arrays, input_tags, metrics, write
from experiments.exp_057_static_two_stage_million.analyze import tail_statistics

ROOT=Path(__file__).resolve().parents[2]
LAYERS=('float','q3','export','q22')


def effective(states,mode):
    values=np.asarray(states)
    return np.clip(np.rint(values*1024),0,2047)/1024 if mode>=2 else values


def pwl(raw,k,width,rounded):
    if np.any((raw< -4*width)|(raw>=4*width)):raise ValueError('PWL domain')
    if not rounded:return basis(raw,width)@k
    mag=np.abs(raw);seg=np.minimum((mag/width).astype(int),3)
    offset=np.concatenate(([0],width*np.cumsum(k[:3])))
    return np.sign(raw)*(np.rint(8*offset[seg])/8+np.rint(8*(mag-seg*width)*k[seg])/8)


def output(raw,d1,d2,k,rounded):
    p2=pwl(raw[5],k[4:],32,rounded)
    r1=128*raw[1]+p2-16*d2
    return 2048+512*raw[0]+pwl(r1,k[:4],128,rounded)-64*d1


def prepare(folder):
    p=json.loads((folder/'source_protocol.json').read_text(encoding='utf-8-sig'));t=p['test_record']
    xt=t['amplitude']*np.sin(2*np.pi*t['tone_bin']*np.arange(t['samples'])/t['samples'])
    dt=np.array([input_tags(t['seed'],i)[1] for i in range(len(xt))])
    for case in p['cases']:
        raw=plant_arrays(xt,dt[:,0],dt[:,1],case)
        np.column_stack((raw[0],raw[1],raw[5],dt)).astype('<i4').tofile(folder/(case['name']+'_tone_input.bin'))
    np.savez(folder/'tone_record.npz',x=xt,tags=dt)


def state_diagnostics(states,mode,raw,dt,x):
    start=len(states)//2;tail=effective(states[start:],mode)
    rear=effective(states[-1],mode)[4:]
    # Rear arithmetic included in fixed matrix; front arithmetic excluded for identity.
    p2=pwl(raw[5],rear,32,mode>0)
    r1=128*raw[1]+p2-16*dt[:,1]
    phi=basis(r1,128);target=2048*x-512*raw[0]+64*dt[:,0]
    identity=mean_covariance_loss(phi,target,tail[:,:4])
    active=np.flatnonzero(np.any(phi!=0,axis=0))
    ref=np.ones(4);ref[active]=np.linalg.lstsq(phi[:,active],target,rcond=None)[0]
    residual=phi@ref-target;mean=np.array(identity['mean'])
    identity.update(rear_anchor=rear.tolist(),projection_residual_mse=float(np.mean(residual**2)),
                    mean_state_excess_mse=float(np.mean((phi@(mean-ref))**2)),
                    projection_cross=2*float(np.mean(residual*(phi@(mean-ref)))))
    # Predeclared 20 equally spaced per block; all-tail result uses all states.
    blocks=np.array_split(np.arange(len(tail)),10)
    ix=np.unique(np.concatenate([b[np.linspace(0,len(b)-1,20,dtype=int)] for b in blocks]))
    selected=tail[ix];sub=mean_covariance_loss(phi,target,selected[:,:4])
    direct=np.array([phi@k[:4]-target for k in selected])
    direct_mean=float(np.mean(direct**2))
    assert abs(direct_mean-sub['average_continuous_mse'])<1e-9*max(1,direct_mean)
    arithmetic=[];joint=[]
    for k in selected:
        actual=pwl(r1,k[:4],128,mode>0)-target
        arithmetic.append(actual)
        joint.append(output(raw,dt[:,0],dt[:,1],k,mode>0)-2048*(x+1))
    arithmetic=np.array(arithmetic);joint=np.array(joint)
    correction=arithmetic-direct
    cross=2*float(np.mean(direct*correction));power=float(np.mean(correction**2))
    actual_mse=float(np.mean(arithmetic**2))
    assert abs(actual_mse-direct_mean-cross-power)<1e-9*max(1,actual_mse)
    mean_output=joint.mean(axis=0);var_output=np.mean((joint-mean_output)**2)
    joint_mse=float(np.mean(joint**2))
    assert abs(joint_mse-np.mean(mean_output**2)-var_output)<1e-9*max(1,joint_mse)
    identity.update(subset_states=len(ix),subset_state_indices=(ix+start).tolist(),subset_direct_mse=direct_mean,
                    subset_identity=sub,subset_front_arithmetic_mse=actual_mse,
                    subset_arithmetic_cross=cross,subset_arithmetic_power=power,
                    subset_joint_output_mse=joint_mse,subset_joint_mean_output_mse=float(np.mean(mean_output**2)),
                    subset_joint_output_variance_mse=float(var_output),
                    subset_identity_difference=direct_mean-sub['average_continuous_mse'])
    balance=finite_increment_balance(states[start:],np.ones(8))
    assert balance['maximum_balance_error']<1e-12
    return identity,balance


def analyze(folder):
    p=json.loads((folder/'source_protocol.json').read_text(encoding='utf-8-sig'))
    protocol=json.loads((folder/'protocol.json').read_text(encoding='utf-8-sig'))
    xt=np.load(folder/'tone_record.npz')['x'];tone=p['test_record']['tone_bin'];n=len(xt)
    nv=protocol['T3']['grid_midpoints']
    xv=np.repeat(-.82+(np.arange(nv)+.5)*1.64/nv,4)
    dv=np.tile(np.array([[-1,-1],[-1,1],[1,-1],[1,1]]),(nv,1))
    rows=[]
    for case in p['cases']:
        raw=plant_arrays(xv,dv[:,0],dv[:,1],case)
        for method in p['methods']:
            for seed in p['seeds']:
                stem=f"{case['name']}_{method['name']}_{seed}"
                meta=json.loads((folder/(stem+'.json')).read_text(encoding='utf-8-sig'))
                tones=np.memmap(folder/(stem+'_tones.bin'),dtype='<f8',mode='r',shape=(len(method['checkpoint_windows']),4,2,n))
                for mode,layer in enumerate(LAYERS):
                    statefile=ROOT/protocol['baseline_run']/(stem+'_sar8.bin') if mode==0 else folder/(stem+'_'+layer+'.bin')
                    states=np.memmap(statefile,dtype='<f8',mode='r',shape=(method['training_windows']+1,8))
                    points=[]
                    for ci,w in enumerate(method['checkpoint_windows']):
                        scores={}
                        for si,kind in enumerate(('frozen','online')):
                            y=np.asarray(tones[ci,mode,si]);assert not np.any((y<0)|(y>4095))
                            integer=np.rint(np.clip(y,0,4095));e=y-2048*(xt+1);r=integer-y
                            continuous=metrics(y,xt,tone);ints=metrics(integer,xt,tone)
                            cross=2*float(np.mean(e*r));power=float(np.mean(r*r))
                            assert abs(ints['mse_codes_squared']-continuous['mse_codes_squared']-cross-power)<1e-9
                            scores[kind]={'continuous':continuous,'integer':ints,'integer_cross':cross,'integer_rounding_power':power}
                        points.append({'window':w,'conversion_slots':120*w,'learning_observations_per_bank':w*method['selected'],
                            'hidden':states[w].tolist(),'effective':effective(states[w],mode).tolist(),**scores})
                    identity,balance=state_diagnostics(states,mode,raw,dv,xv)
                    hidden=tail_statistics(states);visible=tail_statistics(effective(states,mode))
                    rows.append({'case':case['name'],'method':method['name'],'seed':seed,'layer':layer,
                        'observations_per_bank':meta['GeneratedSamples'],'conversion_slots':120*method['training_windows'],
                        'commits':method['training_windows'],'gates':meta['Gates'][mode],
                        'basis':meta['Basis'][mode],'both':meta['Both'][mode],
                        'zero_request':meta['ZeroRequest'][mode],'hidden_changed':meta['HiddenChanged'][mode],
                        'export_changed':meta['ExportChanged'][mode],'coefficient_clips':meta['CoefficientClips'][mode],
                        'selected_output_clips':meta['OutputClips'][mode],'physical_overloads':meta['PhysicalOverloads'],
                        'tail_hidden':hidden,'tail_effective':visible,'fixed_rear_mean_covariance':identity,
                        'finite_hidden_increment_balance':balance,'checkpoints':points,
                        'state_file':str(statefile.relative_to(ROOT)), 'state_sha256':sha256(statefile.read_bytes()).hexdigest()})
                print('analyzed',stem,flush=True)
    hashes=json.loads((folder/'source_hashes.json').read_text(encoding='utf-8-sig'))
    assert all(sha256(Path(h['Path']).read_bytes()).hexdigest().upper()==h['Hash'] for h in hashes)
    result={'passed':True,'paths':len(rows),'new_fixed_paths':150,'rows':rows,'source_hashes_unchanged':True,
            'generated_static_samples_shared':sum(r['observations_per_bank'] for r in rows if r['layer']=='q22'),
            'baseline_values_checked':sum(json.loads((folder/f"{c['name']}_{m['name']}_{s}.json").read_text(encoding='utf-8-sig'))['BaselineStatesChecked'] for c in p['cases'] for m in p['methods'] for s in p['seeds']),
            'new_algorithm':False,'chip_certified':False,'full_fixed_transition_replay':False}
    write(folder/'summary.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);parser.add_argument('--prepare',action='store_true')
    args=parser.parse_args();(prepare if args.prepare else analyze)(args.folder.resolve())
