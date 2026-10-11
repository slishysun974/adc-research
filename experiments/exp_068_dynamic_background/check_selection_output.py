"""Output-weight and effective-export checks on old NG-24 windows only.

No new ADC observations, training path, scheduler, or spectrum computation.
"""
import argparse
from collections import Counter
from dataclasses import asdict
from fractions import Fraction as F
from pathlib import Path
import traceback

import numpy as np

from adc_research.theory.selection_output_response import (
    affine_loss_comparison, finite_output_loss_comparison, output_gram,
    vector_moments, weighted_covariance_difference,
)
from adc_research.theory.static_fixed_contract import basis, commit, export, nearest_even, pwl, readout
from check_lane_statistics import digest, frozen_sources, load, write, DOCUMENTS

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT/'artifacts/runs/EXP_068/background_v1'
OLD = ROOT/'artifacts/research/lane_selection_20261011_v1'
SOURCES = [
    'src/adc_research/theory/selection_output_response.py',
    'tests/test_selection_output_response.py',
    'experiments/exp_068_dynamic_background/check_selection_output.py',
    'experiments/exp_068_dynamic_background/check_lane_statistics.py',
    'src/adc_research/theory/static_fixed_contract.py',
    'src/adc_research/theory/lane_phase_statistics.py',
]
FRONT_STEPS = tuple(F(x,262144000) for x in (1,3,6,12))
REAR_STEPS = tuple(F(x,16384000) for x in (1,3,6,12))


def prepare(folder):
    folder.mkdir(parents=True,exist_ok=False)
    p = load(OLD/'protocol.json')
    write(folder/'protocol.json', {
        'scope':'Plan11 T3/T4 output statistical conditions; fixed old windows and states; no online implementation.',
        **{k:p[k] for k in ('cases','histories','seeds','methods','windows','rows')},
        'theory':'Fixed-rear continuous front output Gram weights; joint bilinear loss requires third/fourth moments and targets. Raw equal means need not survive Q22 saturation/export.',
        'raw_comparison':'Exact independent-minus-shared output-weighted variance; all180 windows, continuous and Q3 learning/evaluation-rear layers. Original front step and120-window scale. Rear frozen in scoring.',
        'effective_comparison':'Q3 learning only. Enumerate all30 ideal uniform COMMON phases. Simultaneous original bank commit computed, but score changed front with OLD rear fixed. Deterministic full120 commit at same old state is reference. Independent nonlinear law NOT enumerated.',
        'score':'All120 same old words, uniform. Continuous FRONT output uses frozen rear Q3 raw; actual Q3/integer front scored separately. These are counterfactual same-window diagnostics, not original two-bank future outputs.',
        'targets':'2048*(1+exact stored double tone), offline only. Independent half-code boxes are mechanism controls, not physical envelopes.',
        'steps_front':[str(x) for x in FRONT_STEPS], 'steps_rear':[str(x) for x in REAR_STEPS],
        'independent_checks':'All21600 old Q3 integer codes; all1440 original next-bank coordinates; common-phase raw covariance matches NG24. Affine expected loss versus direct30-atom squared errors. Integer-only front formula versus rational pwl at phase0/29/full, all120 rows. Tight box endpoints.',
        'controls':'Eight exact unit controls: enumerated affine weights, indefinite output weights, target-box endpoints, export tie, saturation, joint digital target/drift, fourth-moment counterexample, arbitrary integer outputs.',
        'predictions':'No universal sign for output-weighted trace; no guarantee of equal effective means. Any strict sign after physical target uncertainty would be conditional on that uncertainty, not a future gain claim.',
        'new_ADC_conversions':0,'new_training':0,'new_FFT_or_scans':0,
        'prohibited':'No PRNG certification, new scheduler, parameter tuning, closed-loop gain, convergence or chip claim.',
    })
    write(folder/'source_hashes.json',{p:digest(ROOT/p) for p in SOURCES})
    previous = [OLD/'protocol.json',OLD/'analysis.json',OLD/'data_hashes.json',OLD/'source_hashes.json',
                OLD/'validation.json', DATA/'protocol.json',DATA/'source_hashes.json',
                ROOT/'artifacts/research/gated_mean_20261011_v2/data_hashes.json']
    write(folder/'previous_hashes.json',{str(p.relative_to(ROOT)):digest(p) for p in previous})
    for name in DOCUMENTS:
        dest = folder/'before'/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes((ROOT/name).read_bytes())
    write(folder/'before_hashes.json',{p:digest(ROOT/p) for p in DOCUMENTS})
    write(folder/'initial_control_failures.json',{
        'preserved':True,'before_protocol_or_data_calculation':True,
        'first_run':'6/8 passed; two incorrect hand-control fixtures failed.',
        'export_fixture':'Even1024 export tie occurs at hidden offset2048, not2047. Changed fixture offset to2048; formula unchanged.',
        'integer_fixture':'Direct hand sum gives center5/2 and bounds[-3/2,13/2], corrected expected values; formula unchanged.',
        'final_control_run':'8/8 passed before protocol preparation.',
    })
    print('prepared',folder,'original_sources',frozen_sources(),flush=True)


def front_integer(raw, coarse, d1, codes):
    """Independent integer front Q3 formula; rear Q3 raw is an eighth."""
    eighth = 8*raw
    assert eighth.denominator == 1
    x = int(eighth)
    segment = min(abs(x)//1024,3)
    local = abs(x)-1024*segment
    product = nearest_even(F(local*codes[segment],1024))
    sign = 1 if x>0 else -1 if x<0 else 0
    local_output = sign*(sum(codes[:segment])+product)-512*d1
    return nearest_even(F(8*coarse+local_output,8))


def sign_name(x):
    return 'positive' if x>0 else 'negative' if x<0 else 'zero'


def box_check(atoms, ref, target, shift, lower, upper):
    lo_t = tuple(t+F(1,2)*(1 if b>0 else -1 if b<0 else 0) for t,b in zip(target,shift))
    hi_t = tuple(t-F(1,2)*(1 if b>0 else -1 if b<0 else 0) for t,b in zip(target,shift))
    assert finite_output_loss_comparison(atoms,ref,lo_t)[1] == lower
    assert finite_output_loss_comparison(atoms,ref,hi_t)[1] == upper


def run(folder):
    assert not (folder/'analysis.json').exists()
    for manifest in ('source_hashes.json','previous_hashes.json'):
        assert all(digest(ROOT/name)==h for name,h in load(folder/manifest).items())
    assert all(digest(ROOT/name)==h for name,h in load(OLD/'source_hashes.json').items())
    count_sources = frozen_sources()
    p = load(folder/'protocol.json')
    oldrows = {(r['case'],r['history'],r['seed'],r['method'],r['window']):r
               for r in load(OLD/'analysis.json')['windows']}
    n = load(DATA/'protocol.json')['budget']['windows_per_path']
    tone = np.fromfile(DATA/'tone.bin',dtype='<f8')
    used={'protocol.json','tone.bin'}
    expected = load(ROOT/'artifacts/research/gated_mean_20261011_v2/data_hashes.json')
    totals={'weighted_trace':{'continuous':Counter(),'Q3':Counter()},'effective':Counter()}
    details=[]
    for case in p['cases']:
        for history in p['histories']:
            for seed in p['seeds']:
                stem=f'{case}_{history}_{seed}'
                wn,on=stem+'_words.bin',stem+'_outputs.bin'
                used.update((wn,on))
                words=np.memmap(DATA/wn,dtype='i1',mode='r',shape=(n,120,4))
                outputs=np.memmap(DATA/on,dtype='<i2',mode='r',shape=(n,120,3))
                for mi,method in enumerate(p['methods']):
                    sn=stem+'_'+method+'_q22.bin'; used.add(sn)
                    states=np.memmap(DATA/sn,dtype='<f8',mode='r',shape=(n+1,8))
                    for w in p['windows']:
                        acc=tuple(map(int,np.rint(states[w]*(1<<22))))
                        codes=export(acc); k=tuple(F(c,1024) for c in codes)
                        products={'continuous':[],'Q3':[]}; features={'continuous':[],'Q3':[]}
                        raw,coarse,tags=[],[],[]
                        for i,word in enumerate(words[w]):
                            q1,q2,be,bits=map(int,word)
                            d1,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
                            for layer,quantized in [('continuous',False),('Q3',True)]:
                                z=readout(q1,q2,F(be),d1,d2,k,data_q3=quantized)
                                products[layer].append(tuple(d*y*int(g) for d,y,gs in
                                    [(F(16*d2),z.y2,z.gates[1]),(F(64*d1),z.y1,z.gates[0])] for g in gs))
                                features[layer].append(basis(z.raw1,128))
                                if quantized:
                                    assert nearest_even(z.output)==int(outputs[w,i,mi+1])
                                    raw.append(z.raw1); coarse.append(F(2048+512*q1)); tags.append(d1)
                                    assert front_integer(z.raw1,coarse[-1],d1,codes[:4])==int(outputs[w,i,mi+1])
                        old=oldrows[(case,history,seed,method,w)]
                        row={'case':case,'history':history,'seed':seed,'method':method,'window':w,'raw_layers':{}}
                        for layer in ('continuous','Q3'):
                            law=old['layers'][layer]
                            full_mean=tuple(F(x) for x in law['full_mean'])
                            assert full_mean==tuple(sum(v[j] for v in products[layer])/120 for j in range(8))
                            shared=tuple(tuple(F(x) for x in r[4:]) for r in law['shared_covariance'][4:])
                            independent=tuple(tuple(F(x) for x in r[4:]) for r in law['independent_covariance'][4:])
                            phase_mean=[tuple(sum(v[j] for v in products[layer][4*r:4*r+4])/4 for j in range(4,8)) for r in range(30)]
                            assert vector_moments(phase_mean)==(full_mean[4:],shared)
                            gram=output_gram(features[layer])
                            value=weighted_covariance_difference(gram,independent,shared,tuple(120*x for x in FRONT_STEPS))
                            totals['weighted_trace'][layer][sign_name(value)]+=1
                            row['raw_layers'][layer]={'gram':gram,'independent_minus_shared_expected_affine_mse':value}
                        # Commit both banks exactly, then hold the OLD rear fixed for scoring.
                        sums=tuple(sum(v[j] for v in products['Q3']) for j in range(8))
                        _,full_acc=commit(acc,sums[4:]+sums[:4],1,FRONT_STEPS+REAR_STEPS)
                        full_codes=export(full_acc)
                        phase_codes=[]
                        for r in range(30):
                            s=tuple(sum(v[j] for v in products['Q3'][4*r:4*r+4]) for j in range(8))
                            _,a=commit(acc,s[4:]+s[:4],30,FRONT_STEPS+REAR_STEPS)
                            phase_codes.append(export(a))
                            if method=='point30' and r==0:
                                assert a==tuple(map(int,np.rint(states[w+1]*(1<<22))))
                        if method=='full120':
                            assert full_acc==tuple(map(int,np.rint(states[w+1]*(1<<22))))
                        ref_update=tuple(F(a-b,1024) for a,b in zip(full_codes[:4],codes[:4]))
                        updates=[tuple(F(a-b,1024) for a,b in zip(c[:4],codes[:4])) for c in phase_codes]
                        target=tuple(2048*(1+F.from_float(float(tone[(120*w+i)%len(tone)]))) for i in range(120))
                        def continuous(c):
                            return tuple(base-64*d+sum(x*F(a,1024) for x,a in zip(psi,c[:4]))
                                         for base,d,psi in zip(coarse,tags,features['Q3']))
                        ref_cont=continuous(full_codes)
                        cont_atoms=[continuous(c) for c in phase_codes]
                        aff=affine_loss_comparison(features['Q3'],ref_cont,ref_update,updates,target,(F(1,2),)*120)
                        finite=finite_output_loss_comparison(cont_atoms,ref_cont,target,(F(1,2),)*120)
                        assert finite==(aff.mean_output_difference,aff.mse_difference_at_centers,aff.lower,aff.upper)
                        box_check(cont_atoms,ref_cont,target,*[finite[i] for i in (0,2,3)])
                        ref_int=tuple(F(front_integer(x,b,d,full_codes[:4])) for x,b,d in zip(raw,coarse,tags))
                        int_atoms=[tuple(F(front_integer(x,b,d,c[:4])) for x,b,d in zip(raw,coarse,tags)) for c in phase_codes]
                        integer=finite_output_loss_comparison(int_atoms,ref_int,target,(F(1,2),)*120)
                        box_check(int_atoms,ref_int,target,*[integer[i] for i in (0,2,3)])
                        for c,zc,zi in [(full_codes,ref_cont,ref_int),(phase_codes[0],cont_atoms[0],int_atoms[0]),(phase_codes[29],cont_atoms[29],int_atoms[29])]:
                            for x,b,d,continuous_out,integer_out in zip(raw,coarse,tags,zc,zi):
                                coeff=tuple(F(a,1024) for a in c[:4])
                                assert b-64*d+pwl(x,128,coeff,False)==continuous_out
                                assert nearest_even(b-64*d+pwl(x,128,coeff,True))==integer_out
                        totals['effective']['nonzero_front_mean_bias']+=int(any(aff.mean_bias))
                        totals['effective']['nonzero_integer_mean_output_shift']+=int(any(integer[0]))
                        totals['effective']['continuous_center_'+sign_name(aff.mse_difference_at_centers)]+=1
                        totals['effective']['integer_center_'+sign_name(integer[1])]+=1
                        totals['effective']['continuous_box_'+('positive' if aff.lower>0 else 'negative' if aff.upper<0 else 'contains_zero')]+=1
                        totals['effective']['integer_box_'+('positive' if integer[2]>0 else 'negative' if integer[3]<0 else 'contains_zero')]+=1
                        row['effective_shared_vs_full']={'front_affine':asdict(aff),'front_integer':{
                            'mean_output_difference':integer[0],'mse_difference_at_centers':integer[1],
                            'lower':integer[2],'upper':integer[3]},'reference_front_codes':full_codes[:4],
                            'phase_front_codes':[c[:4] for c in phase_codes]}
                        details.append(row)
                print('checked',stem,flush=True)
    assert len(details)==180
    hashes={name:digest(DATA/name) for name in sorted(used)}
    assert all(h==expected[name] for name,h in hashes.items())
    assert frozen_sources()==count_sources
    assert all(digest(ROOT/name)==h for name,h in load(folder/'source_hashes.json').items())
    write(folder/'data_hashes.json',hashes)
    write(folder/'analysis.json',{'windows':details,'counts':totals})
    write(folder/'validation.json',{'passed':True,'windows':180,'old_codes_checked':21600,
        'original_next_bank_coordinates_checked':1440,'weighted_traces':360,
        'effective_common_phase_bank_coordinates':43200,'same_word_continuous_outputs':669600,
        'same_word_integer_outputs':669600,'independent_integer_and_continuous_probe_outputs':64800,
        'loss_box_endpoints_checked':720,'exact_residual':'0','counts':totals,
        'data_files_hashed':len(hashes),'original_source_files_verified':count_sources,
        'new_ADC_conversions':0,'new_training':0,'new_FFT_or_scans':0,
        'nonlinear_independent_selection_enumerated':False,'future_state_or_online_rule_changed':False})
    print(load(folder/'validation.json'),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--folder',type=Path,required=True)
    action=parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare',action='store_true'); action.add_argument('--run',action='store_true')
    args=parser.parse_args()
    if args.prepare: prepare(args.folder)
    else:
        try: run(args.folder)
        except Exception:
            write(args.folder/'failure.json',{'traceback':traceback.format_exc()})
            raise
