"""Read-only joint bank/selection output checks on the original 180 windows.

No conversion, training path, selector, random source or FFT is executed.
"""
import argparse
from collections import Counter
from dataclasses import asdict
from fractions import Fraction as F
from pathlib import Path
import traceback

import numpy as np

from adc_research.theory.joint_selection_output import (
    four_grid_loss, output_moments, mix_output_moments, moments_loss_comparison,
)
from adc_research.theory.static_fixed_contract import readout, nearest_even, export, commit
from experiments.exp_065_input_switch_tracking.verify import digital
from check_lane_statistics import digest, frozen_sources, load, write, DOCUMENTS
from check_selection_output import FRONT_STEPS, REAR_STEPS, sign_name

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT/'artifacts/runs/EXP_068/background_v1'
PREVIOUS = ROOT/'artifacts/research/selection_output_20261011_v1'
PROBABILITY = ROOT/'artifacts/research/selection_probability_20261011_v1'
SOURCE_NAMES = [
    'src/adc_research/theory/joint_selection_output.py',
    'tests/test_joint_selection_output.py',
    'experiments/exp_068_dynamic_background/check_joint_selection_output.py',
    'src/adc_research/theory/static_fixed_contract.py',
    'src/adc_research/theory/lane_phase_statistics.py',
    'experiments/exp_065_input_switch_tracking/verify.py',
    'experiments/exp_068_dynamic_background/check_lane_statistics.py',
    'experiments/exp_068_dynamic_background/check_selection_output.py',
]
DOCS = DOCUMENTS+['docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md']
FIELDS = ('front_loss', 'rear_loss', 'front_rear_cross', 'interaction_error_cross',
          'interaction_front_cross', 'interaction_rear_cross', 'interaction_square',
          'loss_interaction', 'joint_loss')
LAWS = {
    'uniform': (F(1), F(0), F(0)),
    'mod5': (F(15,16), F(1,32), F(1,32)),
    'capped4': (F(65535,65536), F(1,65536), F(0)),
}


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=False)
    p = load(PREVIOUS/'protocol.json')
    write(folder/'protocol.json', {
        'scope': 'User continue request; Plan12.1 read-only T3/T4 joint output check. No candidate or new closed-loop budget.',
        **{k:p[k] for k in ('cases','histories','seeds','methods','windows','rows')},
        'states': 'Old hidden Q22 states, old Q1.10 exports; original steps, gates, scale30 for four common-phase words, scale1 for full120.',
        'four_grids': 'old/old, changed front/old rear, old front/changed rear, changed/changed; score all120 same old words AFTER each actual export and Q3/integer operations.',
        'selection_laws': {k:[str(x) for x in v] for k,v in LAWS.items()},
        'probability': 'Three ideal conditional common-phase laws; mixes of uniform, phase0 and phase1. No actual random source or independent lane enumeration.',
        'reference': 'Same old-state full120 commit, with the same four-grid definition. Actual saved next state checked separately against phase0 or full120.',
        'target': '2048*(1+exact stored double tone), offline only; independent half-code boxes are algebraic controls without physical coverage.',
        'theory': 'Exact four-grid square loss including output interaction and front/rear error cross; output mean/variance decomposition; tight target-box endpoints.',
        'acceptance': 'All old codes and next Q22 states match. All phase/full outputs match existing independent vector digital evaluator. Phase0/29/full all four grids also match rational readout. Front-only uniform results match NG25; mod5/capped4 match NG26. Exact direct loss and endpoints.',
        'controls': 'Ten unit controls: legal joint integer example, additive output loss cross of both signs, finite arbitrary grids, nonuniform mixture, box endpoints, output fourth-order effect, deterministic variance, invalid inputs, quantizer interaction, legal segment boundary.',
        'prediction': 'No universal sign. Joint loss need not follow front-only loss; c=0 does not suppress 2xy. Counts do not estimate future failures or select an algorithm.',
        'new_ADC_conversions':0, 'new_training':0, 'new_FFT_or_scans':0,
        'prohibited': 'No new selector, tuning, independent-law superiority, future gain, chip target box or convergence claim.',
    })
    write(folder/'source_hashes.json', {p:digest(ROOT/p) for p in SOURCE_NAMES})
    previous = [PREVIOUS/f for f in ('protocol.json','analysis.json','validation.json','source_hashes.json','data_hashes.json')]
    previous += [PROBABILITY/f for f in ('protocol.json','analysis.json','validation.json','source_hashes.json')]
    write(folder/'previous_hashes.json', {str(p.relative_to(ROOT)):digest(p) for p in previous})
    for name in DOCS:
        dest = folder/'before'/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT/name).read_bytes())
    write(folder/'before_hashes.json', {p:digest(ROOT/p) for p in DOCS})
    print('prepared', folder, 'original sources', frozen_sources(), flush=True)


def round_integer(n, d):
    q, r = divmod(n, d)
    return q+int(2*r>d or (2*r==d and q%2))


def integer_readout(word, codes):
    """Independent scalar Q3/PWL/integer chain, including each offset rounding."""
    q1,q2,backend,bits = map(int, word)
    d1,d2 = 2*(bits&1)-1, 2*((bits>>1)&1)-1
    def corrected(raw_eighth, coeff, width):
        if not -32*width <= raw_eighth < 32*width:
            raise ValueError('illegal raw domain in counterfactual readout')
        mag = abs(raw_eighth)
        s = min(mag//(8*width),3)
        off = round_integer(8*width*sum(coeff[:s]),1024)
        local = round_integer((mag-8*width*s)*coeff[s],1024)
        return (1 if raw_eighth>0 else -1 if raw_eighth<0 else 0)*(off+local)
    p2 = corrected(8*backend,codes[4:],32)
    raw = 1024*q2+p2-128*d2
    p1 = corrected(raw,codes[:4],128)
    return round_integer(16384+4096*q1+p1-512*d1,8), raw


def expected_fields(grids, weights):
    return {name:sum((weight*getattr(grid,name) for weight,grid in zip(weights,grids)),F(0))
            for name in FIELDS}


def direct_loss(z, reference, target):
    return sum(((F(int(a))-t)**2-(F(int(b))-t)**2 for a,b,t in zip(z,reference,target)),F(0))/len(target)


def box_check(moment, ref, target, result):
    shift = result.mean_output_difference
    for direction, endpoint in ((1,result.lower),(-1,result.upper)):
        corner = tuple(t+direction*F(1,2)*(1 if b>0 else -1 if b<0 else 0)
                       for t,b in zip(target,shift))
        assert moments_loss_comparison(moment,ref,corner).center == endpoint


def run(folder):
    assert not (folder/'analysis.json').exists() and not (folder/'outputs.npz').exists()
    for name in ('source_hashes.json','previous_hashes.json'):
        assert all(digest(ROOT/p)==h for p,h in load(folder/name).items())
    for previous in (PREVIOUS,PROBABILITY):
        assert all(digest(ROOT/p)==h for p,h in load(previous/'source_hashes.json').items())
    source_count = frozen_sources()
    p = load(folder/'protocol.json')
    key = lambda r:(r['case'],r['history'],r['seed'],r['method'],r['window'])
    front_rows = {key(r):r for r in load(PREVIOUS/'analysis.json')['windows']}
    prob_rows = {key(r):r for r in load(PROBABILITY/'analysis.json')['windows']}
    n = load(DATA/'protocol.json')['budget']['windows_per_path']
    tone = np.fromfile(DATA/'tone.bin',dtype='<f8')
    used = {'protocol.json','tone.bin'}
    counters = {name:Counter() for name in LAWS}
    details, all_outputs, all_states, all_codes, all_old = [],[],[],[],[]
    checks = Counter()
    for case in p['cases']:
        for history in p['histories']:
            for seed in p['seeds']:
                stem = f'{case}_{history}_{seed}'
                wn,on = stem+'_words.bin',stem+'_outputs.bin'
                used.update((wn,on))
                words = np.memmap(DATA/wn,dtype='i1',mode='r',shape=(n,120,4))
                saved = np.memmap(DATA/on,dtype='<i2',mode='r',shape=(n,120,3))
                for mi,method in enumerate(p['methods']):
                    sn=stem+'_'+method+'_q22.bin'; used.add(sn)
                    states=np.memmap(DATA/sn,dtype='<f8',mode='r',shape=(n+1,8))
                    for w in p['windows']:
                        acc=tuple(map(int,np.rint(states[w]*(1<<22))))
                        codes=export(acc)
                        block=np.array(words[w:w+1])
                        old_vector,_,_,product=digital(block,np.array([acc],dtype=np.int64))
                        old=tuple(map(int,old_vector[0]))
                        assert old==tuple(map(int,saved[w,:,mi+1]))
                        checks['old_integer_codes']+=120
                        # Rational old readout independently checks outputs AND all8 learning contributions.
                        for i,word in enumerate(words[w]):
                            q1,q2,be,bits=map(int,word); d1,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
                            z=readout(q1,q2,F(be),d1,d2,tuple(F(c,1024) for c in codes),data_q3=True)
                            assert nearest_even(z.output)==old[i]
                            pr=tuple(d*y*int(g) for d,y,gs in
                                     [(F(64*d1),z.y1,z.gates[0]),(F(16*d2),z.y2,z.gates[1])] for g in gs)
                            assert pr==tuple(map(int,product[0,i]))
                        checks['old_learning_components']+=960
                        accumulators=[]
                        for s,multiplier in [(product[0].sum(axis=0),1)]+[
                                (product[0,4*r:4*r+4].sum(axis=0),30) for r in range(30)]:
                            _,after=commit(acc,tuple(map(F,map(int,s))),multiplier,FRONT_STEPS+REAR_STEPS)
                            accumulators.append(after)
                        full_codes,phase_codes=export(accumulators[0]),[export(a) for a in accumulators[1:]]
                        prior=front_rows[(case,history,seed,method,w)]['effective_shared_vs_full']
                        assert full_codes[:4]==tuple(prior['reference_front_codes'])
                        assert [c[:4] for c in phase_codes]==[tuple(c) for c in prior['phase_front_codes']]
                        checks['old_front_commit_coordinates']+=124
                        actual_index=1 if method=='point30' else 0
                        assert accumulators[actual_index]==tuple(map(int,np.rint(states[w+1]*(1<<22))))
                        checks['actual_next_Q22_coordinates']+=8
                        mixed_states=[]
                        mixed_codes=[]
                        for a in accumulators:
                            mixed_states.extend((a[:4]+acc[4:],acc[:4]+a[4:],a))
                            c=export(a); mixed_codes.extend((c[:4]+codes[4:],codes[:4]+c[4:],c))
                        repeated=np.repeat(block,len(mixed_states),axis=0)
                        vector=digital(repeated,np.array(mixed_states,dtype=np.int64))[0]
                        out=vector.reshape(31,3,120)
                        raw=np.empty((31,120),dtype=np.int32)
                        old_raw=tuple(integer_readout(word,codes)[1] for word in words[w])
                        for ai,c in enumerate(mixed_codes):
                            for i,word in enumerate(words[w]):
                                actual,raw1=integer_readout(word,c)
                                assert actual==int(vector[ai,i])
                                assert 0<=actual<=4095
                                if ai%3==2: raw[ai//3,i]=raw1
                        checks['independent_scalar_vector_outputs']+=31*3*120
                        for index in (0,1,30):  # full, phase0, phase29: every changed grid, every word
                            for g in range(3):
                                c=mixed_codes[3*index+g]
                                for i,word in enumerate(words[w]):
                                    q1,q2,be,bits=map(int,word)
                                    z=readout(q1,q2,F(be),2*(bits&1)-1,2*((bits>>1)&1)-1,
                                              tuple(F(x,1024) for x in c),data_q3=True)
                                    assert nearest_even(z.output)==int(out[index,g,i])
                        checks['independent_rational_changed_outputs']+=3*3*120
                        target=tuple(2048*(1+F.from_float(float(tone[(120*w+i)%len(tone)]))) for i in range(120))
                        grids=[four_grid_loss(old,*[tuple(map(int,z)) for z in atom],target) for atom in out]
                        for grid,atom in zip(grids,out):
                            assert grid.joint_loss==direct_loss(atom[2],old,target)
                            assert grid.front_loss==direct_loss(atom[0],old,target)
                            assert grid.rear_loss==direct_loss(atom[1],old,target)
                        checks['four_grid_direct_loss_checks']+=31*3
                        moments=[output_moments(out[1:,g].tolist()) for g in range(3)]
                        zero=[output_moments(out[1:2,g].tolist()) for g in range(3)]
                        one=[output_moments(out[2:3,g].tolist()) for g in range(3)]
                        uniform=expected_fields(grids[1:],(F(1,30),)*30)
                        law_results={}
                        for law,weights in LAWS.items():
                            expectation={field:weights[0]*uniform[field]+weights[1]*getattr(grids[1],field)+
                                         weights[2]*getattr(grids[2],field) for field in FIELDS}
                            comparisons=[]
                            for g,field in enumerate(('front_loss','rear_loss','joint_loss')):
                                moment=mix_output_moments((moments[g],zero[g],one[g]),weights)
                                result=moments_loss_comparison(moment,out[0,g].tolist(),target,(F(1,2),)*120)
                                assert result.center==expectation[field]-getattr(grids[0],field)
                                box_check(moment,out[0,g].tolist(),target,result)
                                comparisons.append(result)
                            front,rear,joint=comparisons
                            correction=expectation['loss_interaction']-grids[0].loss_interaction
                            assert joint.center==front.center+rear.center+correction
                            if law=='uniform':
                                previous=prior['front_integer']
                                assert (front.center,front.lower,front.upper)==tuple(F(previous[k]) for k in
                                            ('mse_difference_at_centers','lower','upper'))
                                assert front.mean_output_difference==tuple(F(x) for x in previous['mean_output_difference'])
                            else:
                                previous=prob_rows[(case,history,seed,method,w)]['laws'][law]['integer']
                                assert (front.center,front.lower,front.upper)==tuple(F(previous[k]) for k in
                                            ('loss_difference_vs_full','lower','upper'))
                                assert front.mean_output_difference==tuple(F(x) for x in
                                            previous['mean_output_difference_vs_full'])
                            c=counters[law]
                            c['joint_center_'+sign_name(joint.center)]+=1
                            c['joint_box_'+('positive' if joint.lower>0 else 'negative' if joint.upper<0 else 'contains_zero')]+=1
                            c['joint_sign_differs_front']+=int(sign_name(joint.center)!=sign_name(front.center))
                            c['joint_front_opposite_sign']+=int(joint.center*front.center<0)
                            c['joint_sign_differs_sum_single']+=int(sign_name(joint.center)!=sign_name(front.center+rear.center))
                            c['joint_single_sum_opposite_sign']+=int(joint.center*(front.center+rear.center)<0)
                            c['nonzero_loss_interaction_correction']+=int(correction!=0)
                            c['nonzero_joint_mean_output_difference']+=int(any(joint.mean_output_difference))
                            c['joint_sign_differs_uniform']+=int(law!='uniform' and
                                    sign_name(joint.center)!=sign_name(law_results['uniform']['joint']['center']))
                            law_results[law]={'front':asdict(front),'rear':asdict(rear),'joint':asdict(joint),
                                'expected_grid_loss_terms':expectation,'interaction_correction_vs_full':correction}
                        checks['comparison_direct_centers']+=9
                        checks['target_box_endpoints']+=18
                        boundary=sum(abs(x)%1024==0 and x!=0 for x in old_raw)
                        crossed=sum(min(abs(x)//1024,3)!=min(abs(y)//1024,3)
                                    for row in raw for x,y in zip(old_raw,row))
                        nonzero=sum(int(c!=0) for grid in grids for c in grid.output_interaction)
                        actual=grids[actual_index]
                        details.append({'case':case,'history':history,'seed':seed,'method':method,'window':w,
                            'laws':law_results,'full_grid_terms':asdict(grids[0]),
                            'actual_next_same_old_word_terms':asdict(actual),
                            'old_Q3_front_boundary_words':boundary,'changed_joint_Q3_segment_crossings':crossed,
                            'nonzero_integer_output_interactions':nonzero})
                        all_outputs.append(out.copy()); all_states.append(accumulators)
                        all_codes.append([full_codes]+phase_codes); all_old.append(old)
                        checks['old_Q3_front_boundary_words_retained']+=boundary
                        checks['changed_joint_Q3_segment_crossings_retained']+=crossed
                        checks['nonzero_integer_output_interaction_word_atoms']+=nonzero
                print('checked',stem,'windows',len(details),flush=True)
    assert len(details)==180
    expected=load(PREVIOUS/'data_hashes.json')
    hashes={name:digest(DATA/name) for name in sorted(used)}
    assert all(h==expected[name] for name,h in hashes.items())
    assert frozen_sources()==source_count
    for name in ('source_hashes.json','previous_hashes.json'):
        assert all(digest(ROOT/p)==h for p,h in load(folder/name).items())
    np.savez_compressed(folder/'outputs.npz',old=np.array(all_old,dtype='<i2'),
        outputs=np.array(all_outputs,dtype='<i2'),Q22=np.array(all_states,dtype='<i8'),
        Q1_10=np.array(all_codes,dtype='<i2'))
    write(folder/'data_hashes.json',hashes)
    write(folder/'analysis.json',{'windows':details,'counts':counters,'checks':checks})
    write(folder/'validation.json',{'passed':True,'windows':180,'checks':checks,'counts':counters,
        'original_sources_preserved':source_count,'original_data_files_hashed':len(hashes),
        'exact_residual':'0','new_ADC_conversions':0,'new_training':0,'new_FFT_or_scans':0,
        'original_long_path_replayed':False,'actual_source_or_independent_lane_law_certified':False,
        'outputs_npz_sha256':digest(folder/'outputs.npz')})
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
