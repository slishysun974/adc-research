"""Prespecified lane-staggering hypothesis on saved windows, no training.

The proposed rotating candidate is specified in the protocol, but its state
trajectory is NOT implemented here. Every counterfactual starts at OLD state.
"""
import argparse
from collections import Counter
from dataclasses import asdict
from fractions import Fraction as F
from pathlib import Path
import traceback

import numpy as np

from adc_research.theory.cyclic_lane_selection import FOUR_LANE_OFFSETS, cyclic_lane_moments
from adc_research.theory.joint_selection_output import four_grid_loss, output_moments, moments_loss_comparison
from adc_research.theory.selection_output_response import weighted_covariance_difference
from adc_research.theory.static_fixed_contract import commit, export, nearest_even, readout
from adc_research.theory.target_moment_bounds import affine_target_interval
from experiments.exp_065_input_switch_tracking.verify import digital
from check_joint_selection_output import (
    integer_readout, direct_loss, box_check, FRONT_STEPS, REAR_STEPS, FIELDS,
)
from check_lane_statistics import digest, frozen_sources, load, write, DOCUMENTS
from check_selection_output import sign_name

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'artifacts/runs/EXP_068/background_v1'
JOINT=ROOT/'artifacts/research/joint_selection_20261011_v2'
LANES=ROOT/'artifacts/research/lane_selection_20261011_v1'
OUTPUT=ROOT/'artifacts/research/selection_output_20261011_v1'
CONTROLS=ROOT/'artifacts/research/staggered_phase_controls_20261011_v1'
SOURCES=[
    'src/adc_research/theory/cyclic_lane_selection.py','tests/test_cyclic_lane_selection.py',
    'experiments/exp_068_dynamic_background/check_staggered_phases.py',
    'src/adc_research/theory/joint_selection_output.py',
    'src/adc_research/theory/selection_output_response.py',
    'src/adc_research/theory/target_moment_bounds.py',
    'experiments/exp_068_dynamic_background/check_joint_selection_output.py',
    'experiments/exp_065_input_switch_tracking/verify.py',
]
DOCS=[p for p in DOCUMENTS if not p.startswith('experiments/')]+[
    'docs/theory/FOUR_POINT_PHASE_SELECTION_CONDITIONS_V1.md',
    'docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md',
    'docs/stages/04_new_algorithm/README.md']


def preserve_sources():
    count=frozen_sources()
    for name in ('lane_selection_20261011_v1','selection_output_20261011_v1',
                 'selection_probability_20261011_v1','joint_selection_20261011_v2'):
        assert all(digest(ROOT/p)==h for p,h in load(ROOT/'artifacts/research'/name/'source_hashes.json').items())
    return count


def prepare(folder):
    folder.mkdir(parents=True,exist_ok=False)
    old=load(JOINT/'protocol.json')
    write(folder/'protocol.json',{
        'scope':'Plan12.2 candidate-contract preparation in existing T3/T4; fixed old states/words, no new online implementation or training budget.',
        **{k:old[k] for k in ('cases','histories','seeds','methods','windows','rows')},
        'candidate_offsets':FOUR_LANE_OFFSETS,
        'offset_provenance':'Derived before scores from physical slots(0,61,30,91), circular gaps29/30/30/31. Minimal max gap31 for one sample in each of four lanes; no score/seed tuning.',
        'proposed_actual_rule':'5-bit base r, reset0, advance+1 mod30 only after complete window and simultaneous original bank commit; lane l uses index4*((r+offset[l]) mod30)+l. Both banks use same4 words. No control randomness or dither changes.',
        'actual_rule_diagnostic':'At each OLD state inspect r=w mod30, versus phase0 and common r; this is NOT the candidate state at that time or a new trajectory.',
        'ideal_law':'Uniform common base over30, offsets fixed; conditional mean exactly full; covariance from cross-lag sum, no universal reduction. Deterministic rotation does NOT assume this law.',
        'contract':'120 old-state outputs, every lane exactly1 learning word, original gates/Q3/Q1.10/Q22/steps/scale30/boundary commit. Invalid base30/31 rejected before window admission; deadline and chip timing unverified.',
        'score':'Same120 old words, four grids, complete joint integer output, keep boundary/crossing; compare ideal common uniform and full120 from NG27. Fixed-rear continuous front Gram weights only auxiliary.',
        'target':'Stored tone exact double rational; offline targets, half-code independent algebraic boxes without physical coverage.',
        'control_source':'Deterministic counter; zero random bits. Proposed5 new state bits, three6-bit constant adds/wrap subtracts and four phase enables; no area/timing claim.',
        'prediction':'More temporal spread changes cross-lag terms, possibly increases or reduces output loss. Failure or mixed signs retained; no candidate selected by negative-count or best phase.',
        'acceptance':'Original21600 codes, all old learning components and covariance reused exactly; full commit matches NG27. All candidate grid codes match independent vector and scalar integer chains; phases0/29/declared r rational checked. Moment/square-loss identities and box endpoints exact.',
        'controls':'Ten controls: gap/lane geometry, zero-offset degeneration, full-marginal equality, cross-lag identity, common translation, legal in-phase and cancellation examples, frozen versus time-varying rotation, lane-constant degeneration, invalid inputs.',
        'new_ADC_conversions':0,'new_training':0,'new_FFT_or_scans':0,
        'future_short_budget':'Plan12.3 discussion only;9 shared physical streams/34560 conversions with existing32-window records reusable; candidate updates are new training and are NOT run here.',
    })
    write(folder/'source_hashes.json',{p:digest(ROOT/p) for p in SOURCES})
    files=[f/p for f in (JOINT,LANES,OUTPUT) for p in ('protocol.json','source_hashes.json','analysis.json','validation.json')]
    files += [JOINT/'outputs.npz',JOINT/'data_hashes.json',CONTROLS/'controls.log',CONTROLS/'initial_test_cyclic_lane_selection.py']
    write(folder/'previous_hashes.json',{str(p.relative_to(ROOT)):digest(p) for p in files})
    for name in DOCS:
        dest=folder/'before'/name; dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes((ROOT/name).read_bytes())
    write(folder/'before_hashes.json',{p:digest(ROOT/p) for p in DOCS})
    write(folder/'initial_control_failures.json',{
        'first_run':'9/10 passed; legal cancellation fixture expected positive variance but remained cancelling under offsets.',
        'correction':'Lane alternation signs changed from lane parity to declared offset parity(0,1,1,0). This exactly cancels common phase but aligns staggered phases. Formula and candidate offsets unchanged; before protocol/data calculation.',
        'initial_test_source_sha256':digest(CONTROLS/'initial_test_cyclic_lane_selection.py'),
        'final_controls_passed':10,
    })
    print('prepared',folder,'original sources',preserve_sources(),flush=True)


def compare_laws(first,second,target):
    dm=tuple(a-b for a,b in zip(first.mean,second.mean))
    ds=tuple(a-b for a,b in zip(first.second,second.second))
    bounds=affine_target_interval(ds,tuple(-2*x for x in dm),
                                 tuple(t-F(1,2) for t in target),tuple(t+F(1,2) for t in target))
    for t,value in ((bounds.minimizing_targets,bounds.lower),(bounds.maximizing_targets,bounds.upper)):
        assert sum((s-2*x*b for s,x,b in zip(ds,t,dm)),F(0))/len(target)==value
    return {'mean_output_difference':dm,'second_moment_difference':ds,
            **{k:getattr(bounds,k) for k in ('center','radius','lower','upper')}}


def run(folder):
    assert not (folder/'analysis.json').exists()
    for name in ('source_hashes.json','previous_hashes.json'):
        assert all(digest(ROOT/p)==h for p,h in load(folder/name).items())
    original=preserve_sources()
    p=load(folder/'protocol.json'); key=lambda r:(r['case'],r['history'],r['seed'],r['method'],r['window'])
    oldrows=load(JOINT/'analysis.json')['windows']; oldmap={key(r):(i,r) for i,r in enumerate(oldrows)}
    lanes={key(r):r for r in load(LANES/'analysis.json')['windows']}
    grams={key(r):r for r in load(OUTPUT/'analysis.json')['windows']}
    with np.load(JOINT/'outputs.npz') as z:
        oldout=z['outputs'].copy(); oldcodes=z['old'].copy(); oldacc=z['Q22'].copy()
    n=load(DATA/'protocol.json')['budget']['windows_per_path']; tone=np.fromfile(DATA/'tone.bin',dtype='<f8')
    used={'protocol.json','tone.bin'}; details=[]; checks=Counter(); counts=Counter(); saved=[]; states_out=[]
    for case in p['cases']:
        for history in p['histories']:
            for seed in p['seeds']:
                stem=f'{case}_{history}_{seed}'; wn,on=stem+'_words.bin',stem+'_outputs.bin'
                used.update((wn,on))
                words=np.memmap(DATA/wn,dtype='i1',mode='r',shape=(n,120,4))
                output=np.memmap(DATA/on,dtype='<i2',mode='r',shape=(n,120,3))
                for mi,method in enumerate(p['methods']):
                    sn=stem+'_'+method+'_q22.bin'; used.add(sn)
                    states=np.memmap(DATA/sn,dtype='<f8',mode='r',shape=(n+1,8))
                    for w in p['windows']:
                        identity=(case,history,seed,method,w); oi,prior=oldmap[identity]
                        acc=tuple(map(int,np.rint(states[w]*(1<<22)))); codes=export(acc)
                        block=np.array(words[w:w+1]); z,_,_,pr=digital(block,np.array([acc],dtype=np.int64))
                        old=tuple(map(int,z[0])); products=tuple(tuple(map(int,row)) for row in pr[0])
                        assert old==tuple(map(int,output[w,:,mi+1]))==tuple(map(int,oldcodes[oi]))
                        checks['old_codes']+=120
                        for i,word in enumerate(words[w]):
                            q1,q2,be,bits=map(int,word); d1,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
                            out=readout(q1,q2,F(be),d1,d2,tuple(F(c,1024) for c in codes),data_q3=True)
                            assert nearest_even(out.output)==old[i]
                            values=tuple(d*y*int(g) for d,y,gs in
                                [(F(64*d1),out.y1,out.gates[0]),(F(16*d2),out.y2,out.gates[1])] for g in gs)
                            assert values==products[i]
                        checks['old_learning_components']+=960
                        shifted=cyclic_lane_moments(products)
                        shared=cyclic_lane_moments(products,(0,)*4)
                        assert shifted.selected_mean==shifted.full_mean==shared.selected_mean
                        prior_law=lanes[identity]['layers']['Q3']; order=(4,5,6,7,0,1,2,3)
                        assert tuple(shared.selected_mean[j] for j in order)==tuple(F(x) for x in prior_law['full_mean'])
                        assert tuple(tuple(shared.covariance[j][k] for k in order) for j in order)==tuple(tuple(F(x) for x in row) for row in prior_law['shared_covariance'])
                        checks['old_covariance_components']+=64; checks['shifted_mean_components']+=8
                        # Independent direct raw sums for every declared phase pattern.
                        accum=[]
                        for base,chosen in enumerate(shifted.indices):
                            independent=tuple(4*((base+shift)%30)+lane for lane,shift in enumerate(FOUR_LANE_OFFSETS))
                            assert chosen==independent and len(set(chosen))==4
                            sums=tuple(sum(products[i][j] for i in chosen) for j in range(8))
                            assert tuple(F(s,4) for s in sums)==shifted.phase_means[base]
                            accum.append(commit(acc,tuple(map(F,sums)),30,FRONT_STEPS+REAR_STEPS)[1])
                        checks['selected_phase_raw_components']+=240
                        full=commit(acc,tuple(F(sum(row[j] for row in products)) for j in range(8)),1,FRONT_STEPS+REAR_STEPS)[1]
                        assert full==tuple(map(int,oldacc[oi,0])); checks['old_full_commit_coordinates']+=8
                        mixed=[]; coeff=[]
                        for a in accum:
                            mixed.extend((a[:4]+acc[4:],acc[:4]+a[4:],a))
                            k=export(a); coeff.extend((k[:4]+codes[4:],codes[:4]+k[4:],k))
                        vector=digital(np.repeat(block,90,axis=0),np.array(mixed,dtype=np.int64))[0]
                        out=vector.reshape(30,3,120)
                        for ai,k in enumerate(coeff):
                            for i,word in enumerate(words[w]):
                                zi,_=integer_readout(word,k); assert zi==int(vector[ai,i]) and 0<=zi<=4095
                        checks['scalar_vector_candidate_outputs']+=10800
                        for base in sorted({0,29,w%30}):
                            for g in range(3):
                                k=tuple(F(c,1024) for c in coeff[3*base+g])
                                for i,word in enumerate(words[w]):
                                    q1,q2,be,bits=map(int,word)
                                    zi=readout(q1,q2,F(be),2*(bits&1)-1,2*((bits>>1)&1)-1,k,data_q3=True)
                                    assert nearest_even(zi.output)==int(out[base,g,i])
                            checks['rational_candidate_outputs']+=360
                        target=tuple(2048*(1+F.from_float(float(tone[(120*w+i)%len(tone)]))) for i in range(120))
                        grids=[four_grid_loss(old,*[tuple(map(int,row)) for row in atom],target) for atom in out]
                        for atom,grid in zip(out,grids):
                            assert grid.joint_loss==direct_loss(atom[2],old,target)
                            assert grid.front_loss==direct_loss(atom[0],old,target)
                            assert grid.rear_loss==direct_loss(atom[1],old,target)
                        checks['direct_grid_losses']+=90
                        joint_laws={}; comparisons={}
                        for g,field in enumerate(('front_loss','rear_loss','joint_loss')):
                            moment=output_moments(out[:,g].tolist())
                            common=output_moments(oldout[oi,1:,g].tolist())
                            ref=oldout[oi,0,g].tolist()
                            candidate=moments_loss_comparison(moment,ref,target,(F(1,2),)*120)
                            original_compare=moments_loss_comparison(common,ref,target,(F(1,2),)*120)
                            assert original_compare.center==F(prior['laws']['uniform'][('front','rear','joint')[g]]['center'])
                            assert candidate.center==sum((getattr(grid,field) for grid in grids),F(0))/30-F(prior['full_grid_terms'][field])
                            difference=compare_laws(moment,common,target)
                            assert difference['center']==candidate.center-original_compare.center
                            box_check(moment,ref,target,candidate)
                            comparisons[('front','rear','joint')[g]]=difference
                            joint_laws[('front','rear','joint')[g]]=asdict(candidate)
                        checks['moment_loss_centers']+=6; checks['target_box_endpoints']+=12
                        base=w%30; actual=grids[base]
                        actual_differences={}
                        for name,index in (('fixed0',1),('common_rotate',base+1)):
                            before=oldout[oi,index,2].tolist(); after=out[base,2].tolist()
                            b=compare_laws(output_moments((after,)),output_moments((before,)),target)
                            assert b['center']==direct_loss(after,before,target)
                            actual_differences[name]=b
                        checks['actual_base_centers']+=2; checks['target_box_endpoints']+=4
                        h=tuple(tuple(F(x) for x in row) for row in grams[identity]['raw_layers']['Q3']['gram'])
                        front_cov=lambda m:tuple(tuple(row[:4]) for row in m.covariance[:4])
                        variance=weighted_covariance_difference(h,front_cov(shifted),front_cov(shared),tuple(120*x for x in FRONT_STEPS))
                        joint_delta=comparisons['joint']['center']
                        counts['affine_front_variance_'+sign_name(variance)]+=1
                        counts['ideal_joint_vs_common_'+sign_name(joint_delta)]+=1
                        counts['ideal_joint_vs_full_'+sign_name(joint_laws['joint']['center'])]+=1
                        counts['ideal_joint_box_'+('positive' if comparisons['joint']['lower']>0 else 'negative' if comparisons['joint']['upper']<0 else 'contains_zero')]+=1
                        counts['nonzero_joint_mean_difference_vs_common']+=int(any(comparisons['joint']['mean_output_difference']))
                        counts['affine_variance_joint_opposite_sign']+=int(variance*joint_delta<0)
                        for name,b in actual_differences.items(): counts['declared_base_vs_'+name+'_'+sign_name(b['center'])]+=1
                        avg={field:sum((getattr(grid,field) for grid in grids),F(0))/30 for field in FIELDS}
                        correction=avg['loss_interaction']-sum((F(prior['laws']['uniform']['expected_grid_loss_terms'][field]) for field in ('loss_interaction',)),F(0))
                        assert joint_delta==comparisons['front']['center']+comparisons['rear']['center']+correction
                        details.append({'case':case,'history':history,'seed':seed,'method':method,'window':w,
                            'offsets':FOUR_LANE_OFFSETS,'candidate_raw_mean':shifted.selected_mean,
                            'candidate_raw_covariance':shifted.covariance,'fixed_rear_affine_variance_vs_common':variance,
                            'ideal_vs_common':comparisons,'ideal_vs_full':joint_laws,
                            'ideal_loss_interaction_difference_vs_common':correction,
                            'expected_candidate_grid_terms':avg,'declared_base':base,
                            'declared_base_same_old_state_vs_references':actual_differences})
                        saved.append(out.copy()); states_out.append(accum)
                print('checked',stem,'windows',len(details),flush=True)
    assert len(details)==180
    hashes={name:digest(DATA/name) for name in sorted(used)}
    expected=load(JOINT/'data_hashes.json'); assert all(h==expected[name] for name,h in hashes.items())
    assert preserve_sources()==original
    for name in ('source_hashes.json','previous_hashes.json'):
        assert all(digest(ROOT/p)==h for p,h in load(folder/name).items())
    np.savez_compressed(folder/'outputs.npz',outputs=np.array(saved,dtype='<i2'),Q22=np.array(states_out,dtype='<i8'))
    write(folder/'data_hashes.json',hashes)
    write(folder/'analysis.json',{'windows':details,'counts':counts,'checks':checks})
    write(folder/'validation.json',{'passed':True,'windows':180,'counts':counts,'checks':checks,
        'original_sources_preserved':original,'original_data_files_verified':len(hashes),'exact_residual':'0',
        'outputs_sha256':digest(folder/'outputs.npz'),'new_ADC_conversions':0,'new_training':0,'new_FFT_or_scans':0,
        'candidate_trajectory_executed':False,'actual_rotation_conditionally_uniform':False})
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
            write(args.folder/'failure.json',{'traceback':traceback.format_exc()})
            raise
