"""Read-only probability-law sensitivity of previously scored old windows.

No random source, online selector, conversions, training or FFT is executed.
"""
import argparse
from collections import Counter
from dataclasses import asdict
from fractions import Fraction as F
from pathlib import Path
import traceback

import numpy as np

from adc_research.theory.selection_probability_contract import (
    bounded_rejection_law, conditional_lane_mean, expectation_shift_bound,
    modulo_law, total_variation, weighted_moments,
)
from adc_research.theory.selection_output_response import output_gram
from adc_research.theory.static_fixed_contract import basis, export, nearest_even, pwl, readout
from check_lane_statistics import digest, frozen_sources, load, write, DOCUMENTS
from check_selection_output import front_integer

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'artifacts/runs/EXP_068/background_v1'
OLD=ROOT/'artifacts/research/selection_output_20261011_v1'
LANE=ROOT/'artifacts/research/lane_selection_20261011_v1'
UNIFORM=(F(1,30),)*30
EPSILON=F(1,65536)
LAWS={'mod5':modulo_law(5),'capped4':bounded_rejection_law().probabilities}
SOURCES=[
    'src/adc_research/theory/selection_probability_contract.py',
    'tests/test_selection_probability_contract.py',
    'experiments/exp_068_dynamic_background/check_selection_probabilities.py',
    'experiments/exp_068_dynamic_background/check_selection_output.py',
    'experiments/exp_068_dynamic_background/check_lane_statistics.py',
    'src/adc_research/theory/selection_output_response.py',
    'src/adc_research/theory/static_fixed_contract.py',
    'src/adc_research/calibration/window_phase_selection.py',
]


def prepare(folder):
    folder.mkdir(parents=True,exist_ok=False)
    p=load(OLD/'protocol.json')
    write(folder/'protocol.json',{
        'scope':'D109/plan11 T3/T4 causal probability and deadline preparation. No online sampler or new algorithm.',
        **{k:p[k] for k in ('cases','histories','seeds','methods','windows','rows')},
        'source_assumption':'New binary words ideal uniform and mutually independent conditional on complete frozen window/history. Not certified for old xorshift, SplitMix, distinct seeds or chip sources.',
        'probability_controls':['ideal common uniform phase','uniform5-bit word modulo30','at most4 independent5-bit attempts, reject30/31, then fallback0'],
        'causal_control':'30 equiprobable histories choose a known phase before its legal digital word arrives; global phase counts uniform yet conditional rear first product464 versus full0.',
        'reused_results':'NG25 all30 exported front states and ideal common phase output moments, fixed old rear. Reconstruct only phase0/1/full score atoms needed for law mixtures; do not rerun30-atom evaluation.',
        'analyses':'Exact raw bias versus uniform and TV*range bounds, effective exported mean changes, continuous and integer loss mixtures and independent half-code target boxes.',
        'mapping_checks':'Exact32-state modulo enumeration and1024 two-attempt words in ten unit tests; exact uniform-nonzero32bit residue counts, GF2 rank32 of existing xorshift transition. No period/independence certification.',
        'targets':p['targets'], 'score':p['score'],
        'acceptance':'Saved21600 old integer codes,11520 Q3 shared covariance entries and NG25 fixed-rear Gram/means agree. Reconstructed64800 outputs per layer agree with independent rational readouts. Mixture/weighted affine loss agree; all TV bounds and target box endpoints exact; source/data hashes preserved.',
        'costs':'Ideal capped4: per phase<=20 fresh bits, expected21845/4096 bits; four separate lane draws<=80 bits, expected21845/1024 bits. Random source, state/control, failure handling and deadline clocks not implemented.',
        'new_ADC_conversions':0,'new_training':0,'new_FFT_or_parameter_scans':0,
        'prohibited':'No actual PRNG law, chip entropy source, deadline timing, output improvement or future state claim; no scheduler, tuning, seeds or dither changed.',
    })
    write(folder/'source_hashes.json',{name:digest(ROOT/name) for name in SOURCES})
    previous=[OLD/name for name in ('protocol.json','analysis.json','validation.json','source_hashes.json','data_hashes.json','delivery_summary.json')]
    previous += [LANE/name for name in ('analysis.json','source_hashes.json')]
    write(folder/'previous_hashes.json',{str(path.relative_to(ROOT)):digest(path) for path in previous})
    for name in DOCUMENTS:
        dest=folder/'before'/name; dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes((ROOT/name).read_bytes())
    write(folder/'before_hashes.json',{name:digest(ROOT/name) for name in DOCUMENTS})
    print('prepared',folder,'original sources',frozen_sources(),flush=True)


def sign(x): return 'positive' if x>0 else 'negative' if x<0 else 'zero'
def box_class(center,radius):
    return 'positive' if center-radius>0 else 'negative' if center+radius<0 else 'contains_zero'
def dot(a,b): return sum((x*y for x,y in zip(a,b)),F(0))


def run(folder):
    assert not (folder/'analysis.json').exists()
    for name in ('source_hashes.json','previous_hashes.json'):
        assert all(digest(ROOT/path)==h for path,h in load(folder/name).items())
    assert all(digest(ROOT/path)==h for path,h in load(OLD/'source_hashes.json').items())
    count_sources=frozen_sources()
    p=load(folder/'protocol.json')
    oldrows=load(OLD/'analysis.json')['windows']
    lanerows={(r['case'],r['history'],r['seed'],r['method'],r['window']):r for r in load(LANE/'analysis.json')['windows']}
    n=load(DATA/'protocol.json')['budget']['windows_per_path']
    tone=np.fromfile(DATA/'tone.bin',dtype='<f8')
    used={'tone.bin','protocol.json'}; maps={}; details=[]
    counts={name:Counter() for name in LAWS}
    extrema={name:{'maximum_abs_raw_bias':F(0),'maximum_abs_export_mean_shift':F(0),
                   'maximum_abs_integer_loss_shift':F(0),'maximum_abs_continuous_loss_shift':F(0)} for name in LAWS}
    for old in oldrows:
        case,history,seed,method,w=(old[k] for k in ('case','history','seed','method','window'))
        stem=f'{case}_{history}_{seed}'
        names=(stem+'_words.bin',stem+'_outputs.bin',stem+'_'+method+'_q22.bin')
        used.update(names)
        for name,typ,shape in zip(names,('i1','<i2','<f8'),((n,120,4),(n,120,3),(n+1,8))):
            if name not in maps: maps[name]=np.memmap(DATA/name,dtype=typ,mode='r',shape=shape)
        words,outputs,states=(maps[name] for name in names)
        acc=tuple(map(int,np.rint(states[w]*(1<<22))))
        k=tuple(F(x,1024) for x in export(acc)); mi=0 if method=='point30' else 1
        products=[]; features=[]; raw=[]; coarse=[]; tags=[]
        for i,word in enumerate(words[w]):
            q1,q2,be,bits=map(int,word); d1,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
            z=readout(q1,q2,F(be),d1,d2,k,data_q3=True)
            assert nearest_even(z.output)==int(outputs[w,i,mi+1])
            products.append(tuple(d*y*int(g) for d,y,gs in
                [(F(16*d2),z.y2,z.gates[1]),(F(64*d1),z.y1,z.gates[0])] for g in gs))
            raw.append(z.raw1); coarse.append(F(2048+512*q1)); tags.append(d1); features.append(basis(z.raw1,128))
        phase_products=[tuple(sum(v[j] for v in products[4*r:4*r+4])/4 for j in range(8)) for r in range(30)]
        mu,cv=weighted_moments(phase_products,UNIFORM)
        lane=lanerows[(case,history,seed,method,w)]['layers']['Q3']
        assert mu==tuple(F(x) for x in lane['full_mean'])
        assert cv==tuple(tuple(F(x) for x in row) for row in lane['shared_covariance'])
        gram=output_gram(features)
        assert gram==tuple(tuple(F(x) for x in row) for row in old['raw_layers']['Q3']['gram'])
        prior=old['effective_shared_vs_full']; ref_codes=tuple(prior['reference_front_codes'])
        phase_codes=[tuple(c) for c in prior['phase_front_codes']]
        front_coeffs=[tuple(F(c,1024) for c in row) for row in phase_codes]
        mean_u,cov_u=weighted_moments(front_coeffs,UNIFORM)
        prior_bias=tuple(F(x) for x in prior['front_affine']['mean_bias'])
        assert tuple(a-F(c,1024) for a,c in zip(mean_u,ref_codes))==prior_bias
        def score(codes):
            coeff=tuple(F(c,1024) for c in codes)
            cont=tuple(b-64*d+dot(psi,coeff) for b,d,psi in zip(coarse,tags,features))
            ints=tuple(F(front_integer(x,b,d,codes)) for x,b,d in zip(raw,coarse,tags))
            for x,b,d,zc,zi in zip(raw,coarse,tags,cont,ints):
                assert b-64*d+pwl(x,128,coeff,False)==zc
                assert nearest_even(b-64*d+pwl(x,128,coeff,True))==zi
            return cont,ints
        ref_cont,ref_int=score(ref_codes)
        atom0=score(phase_codes[0]); atom1=score(phase_codes[1])
        target=tuple(2048*(1+F.from_float(float(tone[(120*w+i)%len(tone)]))) for i in range(120))
        d0=[sum(((z-t)**2-(v-t)**2 for z,v,t in zip(atom0[j],ref,target)),F(0))/120 for j,ref in enumerate((ref_cont,ref_int))]
        d1=[sum(((z-t)**2-(v-t)**2 for z,v,t in zip(atom1[j],ref,target)),F(0))/120 for j,ref in enumerate((ref_cont,ref_int))]
        uniform_loss=(F(prior['front_affine']['mse_difference_at_centers']),F(prior['front_integer']['mse_difference_at_centers']))
        uniform_shift=(tuple(F(x) for x in prior['front_affine']['mean_output_difference']),
                       tuple(F(x) for x in prior['front_integer']['mean_output_difference']))
        result={'case':case,'history':history,'seed':seed,'method':method,'window':w,'laws':{}}
        for name,q in LAWS.items():
            raw_mean,_=weighted_moments(phase_products,q)
            # Same q at each lane is a common phase law, not lane independence.
            assert conditional_lane_mean(products,(q,)*4)==raw_mean
            bias=tuple(a-b for a,b in zip(raw_mean,mu))
            bounds=[]
            for j in range(8):
                shift,bound=expectation_shift_bound(tuple(row[j] for row in phase_products),q,UNIFORM)
                assert shift==bias[j] and abs(shift)<=bound; bounds.append(bound)
            mean_q,cov_q=weighted_moments(front_coeffs,q)
            export_shift=tuple(a-b for a,b in zip(mean_q,mean_u))
            if name=='mod5':
                weights=(F(15,16),F(1,32),F(1,32))
            else: weights=(1-EPSILON,EPSILON,F(0))
            scores=[]
            for j,ref in enumerate((ref_cont,ref_int)):
                center=weights[0]*uniform_loss[j]+weights[1]*d0[j]+weights[2]*d1[j]
                shifts=tuple(weights[0]*s+weights[1]*(z0-zr)+weights[2]*(z1-zr)
                             for s,z0,z1,zr in zip(uniform_shift[j],atom0[j],atom1[j],ref))
                radius=sum((abs(x) for x in shifts),F(0))/120
                # Box endpoint changes are direct loss differences between
                # each target and the center, for every mixture component.
                for orientation,endpoint in ((1,center-radius),(-1,center+radius)):
                    t=tuple(a+orientation*F(1,2)*(1 if s>0 else -1 if s<0 else 0) for a,s in zip(target,shifts))
                    du=uniform_loss[j]-2*dot(tuple(a-b for a,b in zip(t,target)),uniform_shift[j])/120
                    da=[sum(((z-v)**2-(r-v)**2 for z,r,v in zip(atom[j],ref,t)),F(0))/120 for atom in (atom0,atom1)]
                    assert weights[0]*du+weights[1]*da[0]+weights[2]*da[1]==endpoint
                if j==0:
                    b=tuple(a-F(c,1024) for a,c in zip(mean_q,ref_codes))
                    output_shift=tuple(dot(psi,b) for psi in features)
                    assert output_shift==shifts
                    affine=2*sum(((z-t)*s for z,t,s in zip(ref,target,shifts)),F(0))/120
                    affine+=sum((x*x for x in shifts),F(0))/120
                    affine+=sum((gram[a][b]*cov_q[a][b] for a in range(4) for b in range(4)),F(0))
                    assert affine==center
                layer='continuous' if j==0 else 'integer'
                loss_shift=center-uniform_loss[j]
                counts[name][layer+'_loss_change_'+sign(loss_shift)]+=1
                counts[name][layer+'_full_reference_'+sign(center)]+=1
                counts[name][layer+'_full_reference_box_'+box_class(center,radius)]+=1
                counts[name][layer+'_sign_changed_from_uniform']+=int(center*uniform_loss[j]<0)
                extrema[name]['maximum_abs_'+layer+'_loss_shift']=max(extrema[name]['maximum_abs_'+layer+'_loss_shift'],abs(loss_shift))
                scores.append({'loss_difference_vs_full':center,'loss_shift_vs_uniform':loss_shift,
                               'mean_output_difference_vs_full':shifts,'lower':center-radius,'upper':center+radius})
            counts[name]['nonzero_raw_mean_bias']+=int(any(bias))
            counts[name]['nonzero_export_mean_change']+=int(any(export_shift))
            extrema[name]['maximum_abs_raw_bias']=max(extrema[name]['maximum_abs_raw_bias'],max(map(abs,bias)))
            extrema[name]['maximum_abs_export_mean_shift']=max(extrema[name]['maximum_abs_export_mean_shift'],max(map(abs,export_shift)))
            result['laws'][name]={'conditional_probabilities':q,'raw_mean_bias_vs_uniform':bias,
                                 'raw_bias_TV_bounds':bounds,'export_mean_change_vs_uniform':export_shift,
                                 'continuous':scores[0],'integer':scores[1]}
        details.append(result)
        if len(details)%6==0: print('checked windows',len(details),flush=True)
    assert len(details)==180
    hashes={name:digest(DATA/name) for name in sorted(used)}
    assert hashes==load(OLD/'data_hashes.json')
    assert frozen_sources()==count_sources
    assert all(digest(ROOT/name)==h for name,h in load(folder/'source_hashes.json').items())
    write(folder/'data_hashes.json',hashes)
    write(folder/'analysis.json',{'windows':details,'counts':counts,'extrema':extrema,
                                 'laws':{name:{'probabilities':q,'TV_vs_uniform':total_variation(q,UNIFORM)} for name,q in LAWS.items()},
                                 'capped4_resource_law':asdict(bounded_rejection_law()),
                                 'nonzero32bit_state_mod30_law':modulo_law(32,exclude_zero=True)})
    write(folder/'validation.json',{'passed':True,'windows':180,'old_integer_codes':21600,
        'old_Q3_covariance_components':11520,'old_export_mean_components':720,
        'reconstructed_continuous_outputs':64800,'reconstructed_integer_outputs':64800,
        'raw_bias_range_checks':2880,'mixture_affine_loss_checks':360,'box_endpoints':1440,
        'exact_residual':'0','counts':counts,'extrema':extrema,'data_files_hashed':len(hashes),
        'original_sources_preserved':count_sources,'new_ADC_conversions':0,'new_training':0,
        'new_FFT_or_parameter_scans':0,'online_sampler_or_random_source_implemented':False})
    print(load(folder/'validation.json'),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--folder',type=Path,required=True)
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare',action='store_true'); action.add_argument('--run',action='store_true')
    args=parser.parse_args()
    if args.prepare: prepare(args.folder)
    else:
        try: run(args.folder)
        except Exception:
            write(args.folder/'failure.json',{'traceback':traceback.format_exc()}); raise
