"""EXP074: causal rear-to-front learner signal/gate channel interventions.

All policies use the same digital words, rear trajectory and initial front.
Only learner input channels differ. Output always uses the moving rear.
This is a diagnostic intervention, not a new calibration algorithm.
"""
import argparse
from dataclasses import replace
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import shutil
import sys
import traceback
import numpy as np

ROOT=Path('D:/ADC');sys.path[:0]=[str(ROOT/'src'),str(ROOT)]
from experiments.exp_073_bank_feedback_intervention.run import evaluate,round_ratio,fixed_setup
from adc_research.theory.static_fixed_contract import readout,export,commit,nearest_even
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.observation import DigitalCalibrationSample
from experiments.exp_073_bank_feedback_intervention.run import signed

OLD=ROOT/'artifacts/runs/EXP_062/background_v1'
BASE=ROOT/'artifacts/runs/EXP_072/finite_v1'
NEW=ROOT/'artifacts/runs/EXP_073/bank_feedback_v1'
PHASE=ROOT/'artifacts/research/normal_future_readout_20261013_v1/phase_certificate.json'
SEEDS=list(range(202610621,202610626));N,W,START=30720,2048,128*256
FACT=np.array([-2,-6,-12,-24],dtype=np.int64)
POLICIES=np.array([[1,0],[0,1],[1,0],[0,1]],dtype=np.int64)
NAMES=['actual_signal_only','actual_gate_only','prefix_signal_only','prefix_gate_only']

def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4194304),b''):h.update(b)
    return h.hexdigest()
def guard(m):
    for p,h in m.items():assert digest(Path(p))==h,p

def maps(words,front,rear,held,den,policy):
    moving=np.column_stack((front,rear));holding=np.column_stack((front,held))
    normal=evaluate(words,moving);shadow=evaluate(words,holding)
    signal=np.where(policy[:,0,None],normal[5],shadow[5])
    gate=np.where(policy[:,1,None,None],normal[1][:,:,:4],shadow[1][:,:,:4])
    d=2*(words[:,:,3].astype(np.int64)&1)-1
    products=(8*d*signal)[:,:,None]*gate
    request=round_ratio(products[:,:4].sum(axis=1)*FACT*30,125*den)
    after=np.clip(front+request,0,2047*4096)
    clips=int(np.count_nonzero(after!=front+request))
    return normal,shadow,request,after,clips

def original(seed,rate):
    stem=f'{seed}_{rate}'
    a=np.fromfile(BASE/f'{stem}_q22.bin',dtype='<i4').reshape(W+1,4,8).astype(np.int64)
    b=np.fromfile(NEW/f'{stem}_q22.bin',dtype='<i4').reshape(W+1,4,8).astype(np.int64)
    ay=np.fromfile(BASE/f'{stem}_outputs.bin',dtype='<i2').reshape(W,4,120)
    by=np.fromfile(NEW/f'{stem}_bridge_outputs.bin',dtype='<i2').reshape(W,2,120)
    ar=np.fromfile(BASE/f'{stem}_requests.bin',dtype='<i4').reshape(W,4,8)
    br=np.fromfile(NEW/f'{stem}_requests.bin',dtype='<i4').reshape(W,4,8)
    return a,b,ay,by,ar,br
def source(seed):return np.memmap(OLD/f'both_smooth_{seed}_words.bin',dtype='i1',mode='r',shape=(65536,120,4))[START:START+W]

def controls():
    # Pure scalar channels need interaction even with no history.
    value=lambda y,g:y*g
    y0,y1,g0,g1=F(1),F(2),0,1
    R00,R10,R01,R11=[value(y,g) for y,g in ((y0,g0),(y1,g0),(y0,g1),(y1,g1))]
    assert R11-R00==(R10-R00)+(R11-R10)
    assert R11-R00==(R01-R00)+(R11-R01)
    assert R11-R10-R01+R00==1
    assert value(y0,g0)==value(y0,g0) and value(y1,1)==value(y0,1)+(y1-y0)
    return {'passed':True,'controls':['two channel orders','nonzero channel interaction','same channel equality','first gate always open'],'source_conversions':0}

def prepare(out,support):
    assert not out.exists(),'Refuse run overwrite'
    assert not (ROOT/'experiments/exp_074_learning_signal_gate_intervention').exists(),'EXP074 already registered'
    assert load(NEW/'verification.json')['passed'] and load(support/'verification.json')['passed']
    out.mkdir(parents=True)
    support_dir=out/'request_analysis_before';support_dir.mkdir()
    for name in ('protocol.json','results.json','verification.json','frozen_analysis.py'):
        shutil.copyfile(support/name,support_dir/name)
    files=[OLD/'tone.bin',OLD/'source_protocol.json',NEW/'results.json',NEW/'verification.json',PHASE]
    for seed in SEEDS:
        files.append(OLD/f'both_smooth_{seed}_words.bin')
        for rate in ('base','quarter'):
            stem=f'{seed}_{rate}'
            files.extend(BASE/f'{stem}_{s}.bin' for s in ('q22','outputs','requests'))
            files.extend(NEW/f'{stem}_{s}.bin' for s in ('q22','bridge_outputs','requests'))
    sources=list((ROOT/'src/adc_research').rglob('*.py'))+list((ROOT/'experiments').rglob('*.py'))
    write(out/'source_hashes.json',{str(p):digest(p) for p in files})
    write(out/'execution_hashes.json',{str(p):digest(p) for p in sources})
    shutil.copyfile(Path(__file__),out/'frozen_run.py')
    protocol={'version':'EXP074-signal-gate-v1','date':'2026-10-13','authority':'D136/D137, current user continue research; necessary finite channel test after frozen existing-history analysis',
       'necessity':'Request analysis found rare second-low gate switches but 3.885..9.505 times larger absolute gate forcing than signal forcing, plus strong history response. This algebra cannot identify each channel causal loss. Two mixed learner policies complete a controlled two-channel square in same original object.',
       'object':'both_smooth; original5 seeds202610621..625; rates1 and1/4; actual/prefix starts; same [128,136) 2048 windows; no new source/model/horizon/holdout',
       'channels':'a chooses learner y1 from moving(1) or initial-held(0) rear; b chooses learner gates from moving(1) or initial-held(0) rear. Both readouts use the policy current front coefficients and original thresholds. Output always moving rear. No target in updates.',
       'new_policies':NAMES,'existing_policies':'(1,1) original both-active front; (0,0) front-only learner with moving-rear bridge output; both already saved in EXP073',
       'rear':'Original autonomous rear trajectory reused, same current-window clock and digital words; no new rear learning or stage2 policy. Its causal equivalence already proved and all20 histories verified in NG40.',
       'contract':'Original eight fields? Only five digital observation fields and legal own front state; original Q22/Q1.10/Q3, products, step sizes, selected4*30, nearest-even and clipping; 120 old-state output then front boundary commit. Extra held-rear readout is explicitly diagnostic resource.',
       'predictions':['Preflight(1,1) and(0,0) requests/states/outputs equal old complete records; new first requests equal at shared initial rear',
           'If changing the gate channel produces large signed effects in both signal contexts it supports a causal role beyond large request impulses',
           'Gate and signal effects can be negative or seed/initialization dependent; retain all signs and channel interaction',
           'Same output and learner inputs at first window and structural first gate always open controls must pass',
           'The two replacement orders sum to previous mediated effect exactly; nonzero interaction precludes a unique channel percentage'],
       'budget':{'new_front_paths':40,'new_outputs':9830400,'new_front_submissions':81920,'new_front_learning_observations':327680,'new_rear_learning':0,
           'preflight_windows_per_seed_rate_pair':2,'preflight_new_outputs':9600,'preflight_new_front_submissions':80,'preflight_new_front_learning_observations':320,
           'kernel_readouts_preflight':38400,'kernel_readouts_new_execution':19660800,'kernel_readouts_new_verification':19660800,
           'kernel_readouts_all_phases':39360000,'kernel_gate_support_product_components_each':314880000,
           'rational_and_formal_readouts_each':67200,'independent_front_candidate_vectors':280,'fft':0,'source_conversions':0,'new_long_axis':0},
       'validation':'Scalar channel controls. Preflight all10 seed/rate pairs, both starts/all4 policies, full120 normal and shadow Fraction/formal readouts plus exact rational commit and independent original fixed-point rounding/clipping. Full new normal output/state/request replay; fixed local windows0,1024,2047 all120 both readouts. Original core bank is not claimed to implement mixed diagnostic gates.',
       'stopping':'Same136 endpoint and all20 cases, no score-selected choice/extension/new rate/model. Source mismatch, invalid readout or state arithmetic mismatch stops and is preserved; performance is not acceptance.',
       'limits':'Controlled causal learner-channel policies in declared digital static candidate; reference-dependent channel effects and interaction, not unique physical percentages or new deployable algorithm; no new global ability bound.'}
    # The contract names the existing observation exactly.
    protocol['contract']=protocol['contract'].replace('Original eight fields? Only','Only')
    write(out/'protocol.json',protocol);write(out/'controls.json',controls())
    for name in ['docs/STATUS.md','docs/DECISIONS.md','docs/RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md',
       'docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md','docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md',
       'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md','docs/theory/README.md','docs/reports/GU_ALGORITHM_EVALUATION_V1.md',
       'docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md','docs/reports/experiments/README.md','docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md']:
        dst=out/'documents_before'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst)
    print('Frozen EXP074, two causal learner channels in all20 original cases',flush=True)

def probe_channels(words,front,rear,held,ys,requests,after,den,policies,window):
    _,cfg=fixed_setup(load(OLD/'source_protocol.json'));scalar=candidate=0
    for h in range(len(front)):
        acc=tuple(map(int,np.r_[front[h],rear[h]]));fixed=tuple(map(int,np.r_[front[h],held[h]]))
        reads=[]
        for state in (acc,fixed):
            codes=export(state);ks=tuple(F(k,1024) for k in codes)
            cc=replace(cfg.cascade,stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=codes[:4]),
                       stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=codes[4:]))
            rr=[]
            for j,row in enumerate(words):
                q1,q2,be,bits=map(int,row);d1=2*(bits&1)-1;d2=2*((bits>>1)&1)-1
                rd=readout(q1,q2,F(be),d1,d2,ks,data_q3=True)
                formal=correct_two_stage_fixed_observed(DigitalCalibrationSample(q1,q2,be,d1,d2),cc)
                assert formal.unclipped_output_scaled==8*rd.output and formal.stage1_raw_scaled==8*rd.raw1
                assert 0<=rd.output<=4095;rr.append(rd);scalar+=1
            reads.append(rr)
        assert all(nearest_even(rd.output)==int(ys[h,j]) for j,rd in enumerate(reads[0]))
        signal=reads[0] if policies[h,0] else reads[1];gates=reads[0] if policies[h,1] else reads[1]
        products=[F(0)]*8;scaled=[0]*4
        for j in range(4):
            d1=2*(int(words[j,3])&1)-1
            for i,g in enumerate(gates[j].gates[0]):
                products[i]+=64*d1*signal[j].y1*g
                scaled[i]+=512*d1*int(8*signal[j].y1)*g
        steps=tuple(mu/den for mu in cfg.stage1_lms.step_sizes+cfg.stage2_lms.step_sizes)
        rq,aft=commit(acc,tuple(products),30,steps)
        fixed_rq=tuple(round_fraction(-mu.numerator*30*p*(1<<22),mu.denominator*64,cfg.stage1_lms.update_rounding)
                        for mu,p in zip(steps[:4],scaled))
        assert rq[:4]==tuple(map(int,requests[h]))==fixed_rq
        assert aft[:4]==tuple(map(int,after[h]))
        assert not any(rq[4:]);candidate+=1
    return scalar,candidate

def run(out):
    assert not (out/'completed.json').exists(),'Refuse completed run overwrite'
    assert digest(Path(__file__))==digest(out/'frozen_run.py')
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    pre_sc=pre_cv=0
    allpol=np.array([[1,1],[0,0],[1,0],[0,1]]*2,dtype=np.int64)
    for seed in SEEDS:
        words=source(seed)
        for rate,den in (('base',1),('quarter',4)):
            a,b,ay,by,ar,br=original(seed,rate)
            front=np.stack([a[0,0,:4]]*4+[a[0,2,:4]]*4)
            held=np.stack([a[0,0,4:]]*4+[a[0,2,4:]]*4)
            for w in range(2):
                rear=np.stack([a[w,0,4:]]*4+[a[w,2,4:]]*4)
                n,s,rq,aft,clips=maps(np.broadcast_to(words[w],(8,120,4)),front,rear,held,den,allpol);assert clips==0
                for z,h in ((0,0),(4,2)):
                    assert np.array_equal(front[z],a[w,h,:4]) and np.array_equal(front[z+1],b[w,h,:4])
                    assert np.array_equal(n[0][z],ay[w,h]) and np.array_equal(n[0][z+1],by[w,h//2])
                    assert np.array_equal(rq[z],ar[w,h,:4]) and np.array_equal(rq[z+1],br[w,h,:4])
                    assert np.array_equal(aft[z],a[w+1,h,:4]) and np.array_equal(aft[z+1],b[w+1,h,:4])
                    if w==0:assert all(np.array_equal(rq[z],rq[z+j]) for j in range(4))
                x,y=probe_channels(words[w],front,rear,held,n[0],rq,aft,den,allpol,START+w)
                pre_sc+=x;pre_cv+=y;front=aft
    assert pre_sc==38400 and pre_cv==160
    write(out/'preflight.json',{'passed':True,'rational_and_formal_readouts_each':pre_sc,'independent_front_candidate_vectors':pre_cv,
        'new_outputs':9600,'new_front_learning':320,'new_front_submissions':80})
    print('All four policies and first-step/old-path preflight controls passed',flush=True)
    for seed in SEEDS:
        words=source(seed)
        for rate,den in (('base',1),('quarter',4)):
            a,_,_,_,_,_=original(seed,rate)
            front=np.stack([a[0,0,:4]]*2+[a[0,2,:4]]*2)
            held=np.stack([a[0,0,4:]]*2+[a[0,2,4:]]*2)
            states=np.empty((W+1,4,4),dtype='<i4');ys=np.empty((W,4,120),dtype='<i2');rqs=np.empty((W,4,4),dtype='<i4')
            states[0]=front;clips=0
            for w in range(W):
                rear=np.stack([a[w,0,4:]]*2+[a[w,2,4:]]*2)
                n,s,rq,aft,c=maps(np.broadcast_to(words[w],(4,120,4)),front,rear,held,den,POLICIES)
                ys[w]=n[0];rqs[w]=rq;states[w+1]=aft;clips+=c;front=aft
            stem=f'{seed}_{rate}';states.tofile(out/f'{stem}_front_q22.bin');ys.tofile(out/f'{stem}_outputs.bin');rqs.tofile(out/f'{stem}_front_requests.bin')
            write(out/f'{stem}_execution.json',{'seed':seed,'rate':rate,'front_coefficient_clips':clips,'rear_autonomous_record_reused':True})
            assert clips==0;print('Completed',stem,'four mixed-channel front paths',flush=True)
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    write(out/'completed.json',{'completed':True,'new_front_paths':40,'new_outputs':9830400,'new_front_submissions':81920,
        'new_front_learning':327680,'new_rear_learning':0,'new_source_conversions':0,'fft':0})

def verify(out):
    assert load(out/'completed.json')['completed'] and load(out/'preflight.json')['passed']
    assert digest(Path(__file__))==digest(out/'frozen_run.py')
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    target=2048*(1+np.fromfile(OLD/'tone.bin',dtype='<f8'));flat=np.tile(target,8);rad=F(load(PHASE)['target_radius'])
    originalrows={(r['seed'],r['rate'],r['initialization']):r for r in load(NEW/'results.json')['rows']}
    rows=[];sc=cv=0
    for seed in SEEDS:
        words=source(seed)
        for rate,den in (('base',1),('quarter',4)):
            stem=f'{seed}_{rate}';a,b,ay,by,ar,br=original(seed,rate)
            states=np.fromfile(out/f'{stem}_front_q22.bin',dtype='<i4').reshape(W+1,4,4).astype(np.int64)
            ys=np.fromfile(out/f'{stem}_outputs.bin',dtype='<i2').reshape(W,4,120)
            rqs=np.fromfile(out/f'{stem}_front_requests.bin',dtype='<i4').reshape(W,4,4)
            assert np.array_equal(states[0],np.stack([a[0,0,:4]]*2+[a[0,2,:4]]*2))
            for k in range(4):
                h=0 if k<2 else 2
                rear=a[:-1,h,4:];held=np.broadcast_to(a[0,h,4:],(W,4))
                policy=np.broadcast_to(POLICIES[k],(W,2))
                n,s,rq,aft,clips=maps(words,states[:-1,k],rear,held,den,policy)
                assert clips==0 and np.array_equal(n[0],ys[:,k]) and np.array_equal(rq,rqs[:,k])
                assert np.array_equal(aft,states[1:,k])
            for w in (0,1024,2047):
                rear=np.stack([a[w,0,4:]]*2+[a[w,2,4:]]*2)
                held=np.stack([a[0,0,4:]]*2+[a[0,2,4:]]*2)
                x,y=probe_channels(words[w],states[w],rear,held,ys[w],rqs[w],states[w+1],den,POLICIES,START+w);sc+=x;cv+=y
            for h,init in ((0,'actual'),(2,'prefix')):
                Y00=by[:,h//2];Y11=ay[:,h];Y10=ys[:,h];Y01=ys[:,h+1]
                effects={key:signed(x,y,target,rad) for key,x,y in (
                   ('signal_gate_held',Y10,Y00),('gate_signal_moving',Y11,Y10),
                   ('gate_signal_held',Y01,Y00),('signal_gate_moving',Y11,Y01),
                   ('total',Y11,Y00))}
                total=F(effects['total']['net_exact']);oldtotal=F(originalrows[seed,rate,init]['effects']['rear_to_front_mediated']['net_exact'])
                assert total==oldtotal
                assert total==F(effects['signal_gate_held']['net_exact'])+F(effects['gate_signal_moving']['net_exact'])
                assert total==F(effects['gate_signal_held']['net_exact'])+F(effects['signal_gate_moving']['net_exact'])
                I=F(effects['gate_signal_moving']['net_exact'])-F(effects['gate_signal_held']['net_exact'])
                mse={k:float(np.mean((y.ravel().astype(float)-flat)**2)) for k,y in (
                    ('all_held',Y00),('signal_only',Y10),('gate_only',Y01),('all_moving',Y11))}
                block={k:np.mean((y.ravel().astype(float)-flat).reshape(8,N)**2,axis=1).tolist() for k,y in (
                    ('all_held',Y00),('signal_only',Y10),('gate_only',Y01),('all_moving',Y11))}
                rows.append({'seed':seed,'rate':rate,'initialization':init,'mse':mse,'effects':effects,
                    'channel_interaction':float(I),'channel_interaction_exact':str(I),'block_mse':block,
                    'mixed_front_high_nonzero_request_components':{'signal_only':int(np.count_nonzero(rqs[:,h,2:])),
                        'gate_only':int(np.count_nonzero(rqs[:,h+1,2:]))},
                    'front_export_gap_to_joint_max':{'signal_only':np.max(np.abs(round_ratio(states[:-1,h],4096)-round_ratio(a[:-1,h,:4],4096)),axis=0).tolist(),
                        'gate_only':np.max(np.abs(round_ratio(states[:-1,h+1],4096)-round_ratio(a[:-1,h,:4],4096)),axis=0).tolist()}})
                print(seed,rate,init,'total',float(total),'signal/gate',[effects[k]['net'] for k in ('signal_gate_held','gate_signal_moving','gate_signal_held','signal_gate_moving')],
                    'I',float(I),flush=True)
    assert sc==28800 and cv==120
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    write(out/'results.json',{'completed':True,'rows':rows})
    write(out/'verification.json',{'passed':True,'new_front_paths':40,'all_new_codes_replayed':9830400,
        'all_new_front_state_vectors_replayed':81960,'all_new_front_submissions_replayed':81920,
        'all20_exact_channel_squares':True,'all20_prior_mediated_effects_unchanged':True,
        'rational_and_formal_readouts_each_including_preflight':67200,'independent_front_candidate_vectors_including_preflight':280,
        'new_outputs_including_preflight':9840000,'new_front_learning_including_preflight':328000,
        'new_front_submissions_including_preflight':82000,'new_rear_learning':0,'source_conversions':0,'fft':0,
        'kernel_readouts_all_phases':39360000,'kernel_gate_support_product_components_each':314880000,
        'original_core_bank_not_claimed_to_implement_mixed_gate_policy':True,'new_algorithm':False,'holdout_used':False})
    print('All40 channel paths and20 causal squares verified',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','run','verify']);ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--support',type=Path)
    args=ap.parse_args()
    try:
        if args.mode=='prepare':assert args.support is not None;prepare(args.out,args.support)
        else:globals()[args.mode](args.out)
    except Exception:
        if args.out.exists():write(args.out/(args.mode+'_failure.json'),{'traceback':traceback.format_exc()})
        raise
