"""EXP-073: bank-update interventions and a declared rear-to-front edge cut.

The diagnostic policies read digital words and states only. Targets enter
paired scoring after all trajectories. Existing EXP-072 files are immutable.
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
from experiments.exp_062_same_input_background.verify import round_ratio,pwl_scaled
from experiments.exp_060_static_auxiliary_preflight.run import fixed_setup
from adc_research.theory.static_fixed_contract import readout,export,commit,nearest_even
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.fixed_four_lane_window import _bank,FourLaneConversion
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState
from adc_research.calibration.observation import DigitalCalibrationSample

OLD=ROOT/'artifacts/runs/EXP_062/background_v1'
BASE=ROOT/'artifacts/runs/EXP_072/finite_v1'
PHASE=ROOT/'artifacts/research/normal_future_readout_20261013_v1/phase_certificate.json'
SEEDS=list(range(202610621,202610626));N,W,START=30720,2048,128*256
FACTORS=np.array([-2,-6,-12,-24,-32,-96,-192,-384],dtype=np.int64)
MASK=np.array([[1,1,1,1,0,0,0,0],[0,0,0,0,1,1,1,1]]*2,dtype=np.int64)
NAMES=['actual_front_only','actual_rear_only','prefix_front_only','prefix_rear_only']

def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def guard(manifest):
    for p,h in manifest.items():assert digest(Path(p))==h,p

def evaluate(words,acc):
    q1,q2,be,bits=(words[:,:,i].astype(np.int64) for i in range(4))
    d1,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
    k=round_ratio(acc,4096);assert np.all((k>=0)&(k<=2047))
    p2=pwl_scaled(8*be,k[:,4:],32);y2=p2-128*d2
    raw1=1024*q2+y2;y1=pwl_scaled(raw1,k[:,:4],128)-512*d1
    q3=16384+4096*q1+y1
    assert np.all((q3>=0)&(q3<=4095*8)), 'Q3 output range failed'
    output=round_ratio(q3,8)
    gs=[];bs=[];ps=[]
    for bank,y,raw,width,dd in ((0,y1,raw1,128,512*d1),(1,y2,8*be,32,128*d2)):
        kb=k[:,4*bank:4*bank+4]
        threshold=round_ratio(8*width*np.column_stack((np.zeros(len(acc),dtype=np.int64),np.cumsum(kb[:,:3],axis=1))),1024)
        g=np.abs(y[:,:,None])>=threshold[:,None,:]
        b=np.abs(raw[:,:,None])>8*width*np.arange(4)
        prod=dd*y;assert np.all(prod%64==0)
        gs.append(g);bs.append(b);ps.append((prod//64)[:,:,None]*g)
    return output,np.concatenate(gs,axis=2),np.concatenate(bs,axis=2),np.concatenate(ps,axis=2),raw1,y1,y2

def step(words,acc,den,mask):
    value=evaluate(words,acc)
    candidate=round_ratio(value[3][:,:4].sum(axis=1)*FACTORS*30,125*den)
    requested=candidate*mask
    raw=acc+requested;after=np.clip(raw,0,2047*4096)
    return value,requested,after,candidate,int(np.count_nonzero(raw!=after))

def source(seed):return np.memmap(OLD/f'both_smooth_{seed}_words.bin',dtype='i1',mode='r',shape=(65536,120,4))[START:START+W]
def original(seed,rate):
    stem=f'{seed}_{rate}'
    states=np.fromfile(BASE/f'{stem}_q22.bin',dtype='<i4').reshape(W+1,4,8).astype(np.int64)
    outputs=np.fromfile(BASE/f'{stem}_outputs.bin',dtype='<i2').reshape(W,4,120)
    requests=np.fromfile(BASE/f'{stem}_requests.bin',dtype='<i4').reshape(W,4,8)
    return states,outputs,requests

def exact_controls():
    # A three-output scalar triangular system: rear'=rear+1,
    # front'=front+rear. The same source is used in every intervention.
    trajectories={}
    for u1,u2 in ((0,0),(1,0),(0,1),(1,1)):
        f=r=F(0);ys=[];rs=[]
        for _ in range(3):
            ys.append(f+r);rs.append(r);f,r=f+u1*r,r+u2
        trajectories[u1,u2]=(ys,rs)
    assert trajectories[1,1][1]==trajectories[0,1][1]
    y00,y10,y01,y11=(trajectories[k][0] for k in ((0,0),(1,0),(0,1),(1,1)))
    bridge=y01
    loss=lambda y,t:sum((a-b)**2 for a,b in zip(y,t))/3
    zero=[F(0)]*3
    L=[loss(y,zero) for y in (y00,y10,y01,y11,bridge)]
    assert L==[0,0,F(5,3),F(10,3),F(5,3)]
    assert L[3]-L[4]==F(5,3) and L[4]-L[1]-(L[2]-L[0])==0
    target=[F(0),F(1),F(4)]
    assert loss(y11,target)-loss(bridge,target)==-1
    # Interaction may exist without transmission to the front learner.
    y00=[0,0,0];y10=y01=[0,1,2];y11=bridge=[0,3,8]
    L=[loss(y,zero) for y in (y00,y10,y01,y11,bridge)]
    assert L[3]-L[4]==0 and L[3]-L[1]-L[2]+L[0]==21
    return {'passed':True,'controls':['rear autonomy','positive mediated effect','negative mediated effect',
        'interaction without mediation','exact interaction split'],'source_conversions':0}

def prepare(out):
    assert not out.exists(),'Refuse run directory overwrite'
    assert not (ROOT/'experiments/exp_073_bank_feedback_intervention').exists(),'EXP073 already exists'
    assert load(BASE/'verification.json')['passed']
    out.mkdir(parents=True)
    files=[BASE/'protocol.json',BASE/'verification.json',BASE/'results.json',OLD/'tone.bin',OLD/'protocol.json',OLD/'source_protocol.json',PHASE]
    for seed in SEEDS:
        files.append(OLD/f'both_smooth_{seed}_words.bin')
        for rate in ('base','quarter'):
            files.extend(BASE/f'{seed}_{rate}_{s}.bin' for s in ('q22','outputs','requests'))
    sources=list((ROOT/'src/adc_research').rglob('*.py'))+list((ROOT/'experiments').rglob('*.py'))
    write(out/'source_hashes.json',{str(p):digest(p) for p in files})
    write(out/'execution_hashes.json',{str(p):digest(p) for p in sources})
    shutil.copyfile(Path(__file__),out/'frozen_run.py')
    p={'version':'EXP073-bank-feedback-v1','date':'2026-10-13','authority':'D136 and explicit user: continue low-segment requests; ultimately separate causal stage feedback',
       'scope':'Seen both_smooth, original five seeds202610621..625, rates1 and1/4, actual/prefix starts, point30, same [128,136) 2048 windows. No new long axis or input/source generation.',
       'new_paths':NAMES,'old_paths':'EXP072 both-active and both-held, two initializations, immutable full states/requests/outputs',
       'information':'New updates accept same five digital fields and own legal Q22 only. Original actual/prefix initial states reused exactly. Target/truth/phase certificate only enter after trajectories in offline scoring.',
       'intervention':'Only chosen bank commits original Gu requests; its gates/products and complete future state recomputed. Other bank stays at initial Q22. Same global slots/counter tags; output old-state120 slots before simultaneous masked submission.',
       'edge_cut':'Output uses front-only evolving front state and autonomous moving rear state. Front learner sees held initial rear. Its shadow learner is exactly the separately propagated front-only branch; this is a declared diagnostic edge intervention, not Gu or a deployable algorithm.',
       'causal_targets':'Four total controlled bank effects and interaction. Bridge separates rear direct output effect given front learner edge cut, from rear-to-front-history mediated effect. No unique percentage attribution or natural-world identifiability claim.',
       'low_request_analysis':'Both-active and front-only contexts, all20 cases each. Apply only each saved first2 front Q22 requests to the same current120 digital words, hold other6 coordinates. Score all120 vs selected4, preserve products/gates/support, export crossings, exact local sign, power/cross. Not future causal effect or an online acceptance gate.',
       'predictions':['Rear-only rear state/requests equal both-active for every saved window; failure rejects triangular execution',
           'Front-only first submission equals both-active at common initial state; subsequent differences may arise through rear coupling',
           'M=Lboth-Lbridge>0 supports harmful rear-to-front transmission here; zero/negative/seed dependence restricts that statement',
           'Factorial interaction I splits exactly into M plus current-readout interaction with front-only history',
           'Front-only versus both-held isolates front learning without moving rear; no performance order assumed',
           'Local120/selected4 signs need not agree and local increments cannot be summed as complete future MSE'],
       'budget':{'new_long_axes':0,'new_source_conversions':0,'new_bank_paths':40,'new_path_outputs':9830400,
           'new_path_windows':81920,'new_effective_learning_each_stage':163840,'new_active_bank_submissions_each_stage':40960,
           'preflight_windows_per_pair':2,'preflight_outputs_all_old_and_new':19200,'preflight_new_path_outputs':9600,
           'preflight_new_learning_each_stage':160,'preflight_new_active_bank_submissions_each_stage':40,
           'full_new_replay_codes':9830400,'old_both_replay_codes':4915200,'bridge_readouts':4915200,'low_same_window_readouts':9830400,
           'rational_and_formal_readouts_each':41520,'formal_active_bank_probes':280,'fft':0},
       'verification':'Five exact scalar controls; preflight all10 seed/rate pairs, old4 plus new4 states, all120 rational/formal readouts and active bank probes. Full new integer output/state/request replay; rear autonomy whole history. Final local windows0,1024,2047 all120 new/bridge probes, low-counterfactual slots0,1,2,3,59,119.',
       'stopping':'Stop at existing136 endpoint; no extra seed/model/horizon/parameter repair, score selection or holdout. Preserve failures; no performance gate. Invalid digital domain or arithmetic mismatch stops.',
       'limitations':'Deterministic finite causal interventions in declared static feedforward candidate only; synthetic analog assumptions. No general chip causality, stationarity or new algorithm; source reuse does not mean zero diagnostic learning.'}
    write(out/'protocol.json',p);write(out/'controls.json',exact_controls())
    docs=['docs/STATUS.md','docs/DECISIONS.md','docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md',
          'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md','docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
          'docs/theory/README.md','docs/reports/GU_ALGORITHM_EVALUATION_V1.md','docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
          'docs/reports/experiments/README.md','docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md']
    for name in docs:
        path=out/'documents_before'/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,path)
    print('Frozen EXP073, all20 starting contexts and fixed bank/edge interventions',flush=True)

def probe(words,acc,after,ys,requests,den,mask,window,slots=range(120)):
    _,cfg=fixed_setup(load(OLD/'source_protocol.json'));scalars=banks=0
    for h in range(len(acc)):
        old=tuple(map(int,acc[h]));codes=export(old);ks=tuple(F(k,1024) for k in codes)
        cc=replace(cfg.cascade,stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=codes[:4]),
                   stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=codes[4:]))
        conversions=[];values=[[],[]];sums=[F(0)]*8
        for j in slots:
            q1,q2,be,bits=map(int,words[j]);d1=2*(bits&1)-1;d2=2*((bits>>1)&1)-1
            sample=DigitalCalibrationSample(q1,q2,be,d1,d2)
            rd=readout(q1,q2,F(be),d1,d2,ks,data_q3=True)
            formal=correct_two_stage_fixed_observed(sample,cc)
            assert formal.unclipped_output_scaled==8*rd.output and formal.stage1_raw_scaled==8*rd.raw1
            assert 0<=rd.output<=4095 and nearest_even(rd.output)==int(ys[h,j])
            scalars+=1
            conversions.append(FourLaneConversion(120*window+j,j%4,sample))
            for b,(d,y) in enumerate(((d1,rd.y1),(d2,rd.y2))):
                values[b].append((512*d if b==0 else 128*d,int(8*y)))
                if j<4:
                    for i,g in enumerate(rd.gates[b]):sums[4*b+i]+=(64 if b==0 else 16)*d*y*g
        if after is not None:
            assert len(slots)==120
            steps=tuple(mu/den for mu in cfg.stage1_lms.step_sizes+cfg.stage2_lms.step_sizes)
            rq,_=commit(old,tuple(sums),30,steps)
            wanted=tuple(rq[i]*int(mask[h,i]) for i in range(8))
            assert wanted==tuple(map(int,requests[h]))
            assert tuple(min(2047*4096,max(0,old[i]+wanted[i])) for i in range(8))==tuple(map(int,after[h]))
            for b,bcfg in enumerate((cfg.stage1_lms,cfg.stage2_lms)):
                if mask[h,4*b]:
                    bank=FixedGatedLmsState(old[4*b:4*b+4],(0,)*4,(0,)*4,(0,)*4,120*window)
                    actual=_bank(bank,replace(bcfg,step_sizes=tuple(mu/den for mu in bcfg.step_sizes)),
                                 conversions,values[b],tuple(j<4 for j in range(120)),30)
                    assert actual.requested_deltas==wanted[4*b:4*b+4]
                    assert actual.state.accumulator_codes==tuple(map(int,after[h,4*b:4*b+4]));banks+=1
                else:assert np.array_equal(acc[h,4*b:4*b+4],after[h,4*b:4*b+4])
    return scalars,banks

def run(out):
    assert not (out/'completed.json').exists(),'Refuse complete run overwrite'
    assert digest(Path(__file__))==digest(out/'frozen_run.py')
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    pre_sc=pre_banks=0;pre_oldmask=np.array([[1]*8,[0]*8,[1]*8,[0]*8],dtype=np.int64)
    for seed in SEEDS:
        words=source(seed)
        for rate,den in (('base',1),('quarter',4)):
            old,yold,rold=original(seed,rate)
            acc=np.stack((old[0,0],old[0,0],old[0,2],old[0,2]))
            for w in range(2):
                oval,orq,oaft,_,_=step(np.broadcast_to(words[w],(4,120,4)),old[w],den,pre_oldmask)
                assert np.array_equal(oval[0],yold[w]) and np.array_equal(orq,rold[w]) and np.array_equal(oaft,old[w+1])
                value,rq,after,_,clips=step(np.broadcast_to(words[w],(4,120,4)),acc,den,MASK);assert clips==0
                assert np.array_equal(after[1,4:],old[w+1,0,4:]) and np.array_equal(after[3,4:],old[w+1,2,4:])
                if w==0:assert np.array_equal(rq[[0,2],:4],rold[w,[0,2],:4])
                s,b=probe(words[w],np.concatenate((old[w],acc)),np.concatenate((oaft,after)),
                          np.concatenate((oval[0],value[0])),np.concatenate((orq,rq)),den,
                          np.concatenate((pre_oldmask,MASK)),START+w)
                pre_sc+=s;pre_banks+=b;acc=after
    assert pre_sc==19200 and pre_banks==160
    write(out/'preflight.json',{'passed':True,'rational_and_formal_readouts_each':pre_sc,'formal_active_bank_probes':pre_banks,
        'new_path_outputs':9600,'new_learning_each_stage':160,'new_active_bank_submissions_each_stage':40})
    print('All old/new preflight trajectories and original-bank probes passed',flush=True)
    for seed in SEEDS:
        words=source(seed)
        for rate,den in (('base',1),('quarter',4)):
            old,_,_=original(seed,rate)
            acc=np.stack((old[0,0],old[0,0],old[0,2],old[0,2]))
            states=np.empty((W+1,4,8),dtype='<i4');ys=np.empty((W,4,120),dtype='<i2')
            requests=np.empty((W,4,8),dtype='<i4');candidates=np.empty_like(requests);states[0]=acc
            clips=0
            for w in range(W):
                value,rq,after,cand,c=step(np.broadcast_to(words[w],(4,120,4)),acc,den,MASK)
                clips+=c
                assert np.array_equal(after[1,4:],old[w+1,0,4:]) and np.array_equal(after[3,4:],old[w+1,2,4:])
                ys[w]=value[0];requests[w]=rq;candidates[w]=cand;states[w+1]=after;acc=after
            stem=f'{seed}_{rate}'
            states.tofile(out/f'{stem}_q22.bin');ys.tofile(out/f'{stem}_outputs.bin')
            requests.tofile(out/f'{stem}_requests.bin');candidates.tofile(out/f'{stem}_candidate_requests.bin')
            write(out/f'{stem}_execution.json',{'seed':seed,'rate':rate,'coefficient_clips':clips,'rear_autonomy_all_windows':True})
            assert clips==0
            print('Completed',stem,'four new bank paths; rear autonomy exact',flush=True)
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    write(out/'completed.json',{'completed':True,'new_paths':40,'new_outputs':9830400,'new_learning_each_stage':163840,
        'new_active_bank_submissions_each_stage':40960,'new_source_conversions':0,'fft':0})

def signed(y,z,target,rad):
    y=y.ravel().astype(np.int64);z=z.ravel().astype(np.int64);d=y-z
    ratios=[float(t).as_integer_ratio() for t in target];D=max(b for _,b in ratios);aa=[a*(D//b) for a,b in ratios]
    first=int(np.sum(d*(y+z),dtype=np.int64));perphase=d.reshape(8,N).sum(axis=0)
    num=first*D-2*sum(int(v)*a for v,a in zip(perphase,aa));net=F(num,8*N*D)
    power=F(int(np.sum(d*d)),8*N);cross=net-power
    r=2*rad*F(int(np.sum(np.abs(d))),8*N)
    return {'net':float(net),'net_exact':str(net),'power':float(power),'cross':float(cross),
            'target_halfwidth':float(r),'target_halfwidth_exact':str(r),'target_interval':[float(net-r),float(net+r)],
            'sign_certified':bool(net-r>0 or net+r<0),'changed_codes':int(np.count_nonzero(d)),
            'max_abs_code_change':int(np.max(np.abs(d)))}

def local_low(y,z,target):
    y=y.astype(np.int64);z=z.astype(np.int64);d=y-z
    ratios=[float(t).as_integer_ratio() for t in target];D=max(b for _,b in ratios)
    aa=np.array([a*(D//b) for a,b in ratios],dtype=object)
    targets=np.tile(aa,8).reshape(W,120)
    first=d*(y+z)
    nums=first.astype(object)*D-2*d.astype(object)*targets
    alln=nums.sum(axis=1);seln=nums[:,:4].sum(axis=1)
    all_delta=np.array([float(F(int(n),120*D)) for n in alln]);sel_delta=np.array([float(F(int(n),4*D)) for n in seln])
    power=np.mean(d*d,axis=1);cross=all_delta-power
    stats={'all120_positive':sum(int(n)>0 for n in alln),'all120_negative':sum(int(n)<0 for n in alln),
           'all120_zero':sum(int(n)==0 for n in alln),'selected4_positive':sum(int(n)>0 for n in seln),
           'selected4_negative':sum(int(n)<0 for n in seln),'selected4_zero':sum(int(n)==0 for n in seln),
           'strict_sign_disagreements':sum(int(a)*int(b)<0 for a,b in zip(alln,seln)),
           'mean_all120_change':float(all_delta.mean()),'mean_selected4_change':float(sel_delta.mean()),
           'mean_displacement_power':float(power.mean()),'mean_error_cross':float(cross.mean()),
           'output_changed_windows':int(np.count_nonzero(np.any(d!=0,axis=1)))}
    return stats,np.column_stack((all_delta,sel_delta,power,cross))

def verify_analyze(out):
    assert load(out/'completed.json')['completed'] and load(out/'preflight.json')['passed']
    assert digest(Path(__file__))==digest(out/'frozen_run.py')
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    target=2048*(1+np.fromfile(OLD/'tone.bin',dtype='<f8'));flat=np.tile(target,8)
    rad=F(load(PHASE)['target_radius']);rows=[];lowrows=[];sc=banks=0
    for seed in SEEDS:
        words=source(seed)
        for rate,den in (('base',1),('quarter',4)):
            stem=f'{seed}_{rate}';old,oldy,oldrq=original(seed,rate)
            states=np.fromfile(out/f'{stem}_q22.bin',dtype='<i4').reshape(W+1,4,8).astype(np.int64)
            ys=np.fromfile(out/f'{stem}_outputs.bin',dtype='<i2').reshape(W,4,120)
            rqs=np.fromfile(out/f'{stem}_requests.bin',dtype='<i4').reshape(W,4,8)
            cands=np.fromfile(out/f'{stem}_candidate_requests.bin',dtype='<i4').reshape(W,4,8)
            assert np.array_equal(states[0],np.stack((old[0,0],old[0,0],old[0,2],old[0,2])))
            new_gate_stats=[]
            for h in range(4):
                val,rq,after,cand,clips=step(words,states[:-1,h],den,MASK[h])
                assert clips==0 and np.array_equal(val[0],ys[:,h]) and np.array_equal(rq,rqs[:,h])
                assert np.array_equal(cand,cands[:,h]) and np.array_equal(after,states[1:,h])
                new_gate_stats.append((val[1][:,:4,:2].sum(axis=(0,1)).tolist(),
                    val[2][:,:4,:2].sum(axis=(0,1)).tolist(),
                    np.logical_and(val[1][:,:4,:2],val[2][:,:4,:2]).sum(axis=(0,1)).tolist()))
            for w in (0,1024,2047):
                s,b=probe(words[w],states[w],states[w+1],ys[w],rqs[w],den,MASK,START+w);sc+=s;banks+=b
            bridges=np.empty((W,2,120),dtype='<i2');lowys=np.empty((W,4,120),dtype='<i2')
            diagnostics=np.empty((W,4,4),dtype='<f8')
            for h,name in ((0,'actual'),(2,'prefix')):
                # front-only h, rear-only h+1; old both-active h, held h+1.
                assert np.array_equal(states[:,h+1,4:],old[:,h,4:])
                assert np.array_equal(rqs[:,h+1,4:],oldrq[:,h,4:])
                assert np.all(states[:,h,4:]==old[0,h,4:])
                assert np.all(states[:,h+1,:4]==old[0,h,:4])
                cross=np.column_stack((states[:-1,h,:4],states[:-1,h+1,4:]))
                bridge=evaluate(words,cross)[0];bridges[:,h//2]=bridge
                for w in (0,1024,2047):
                    s,b=probe(words[w],cross[w:w+1],None,bridge[w:w+1],None,den,None,START+w);sc+=s
                y00=oldy[:,h+1];y10=ys[:,h];y01=ys[:,h+1];y11=oldy[:,h]
                effects={key:signed(a,b,target,rad) for key,a,b in (
                    ('front_rear_held',y10,y00),('front_rear_active',y11,y01),
                    ('rear_front_held',y01,y00),('rear_front_active',y11,y10),
                    ('rear_direct_edge_cut',bridge,y10),('rear_to_front_mediated',y11,bridge),
                    ('front_edge_cut_rear_active',bridge,y01))}
                I=F(effects['front_rear_active']['net_exact'])-F(effects['front_rear_held']['net_exact'])
                M=F(effects['rear_to_front_mediated']['net_exact'])
                D=F(effects['rear_direct_edge_cut']['net_exact'])-F(effects['rear_front_held']['net_exact'])
                assert I==M+D
                assert F(effects['rear_front_active']['net_exact'])==M+F(effects['rear_direct_edge_cut']['net_exact'])
                mse={key:float(np.mean((y.ravel().astype(float)-flat)**2)) for key,y in (
                    ('held',y00),('front_only',y10),('rear_only',y01),('both',y11),('bridge',bridge))}
                blocks={key:np.mean((y.ravel().astype(float)-flat).reshape(8,N)**2,axis=1).tolist() for key,y in (
                    ('held',y00),('front_only',y10),('rear_only',y01),('both',y11),('bridge',bridge))}
                front_delta=round_ratio(old[:-1,h,:4],4096)-round_ratio(states[:-1,h,:4],4096)
                row={'seed':seed,'rate':rate,'initialization':name,'mse':mse,'effects':effects,
                    'factorial_interaction':float(I),'factorial_interaction_exact':str(I),
                    'current_readout_interaction':float(D),'current_readout_interaction_exact':str(D),
                    'rear_to_front_mediated':float(M),'rear_to_front_mediated_exact':str(M),'block_mse':blocks,
                    'front_history_changed_windows':int(np.count_nonzero(np.any(front_delta!=0,axis=1))),
                    'front_max_export_history_difference':np.max(np.abs(front_delta),axis=0).tolist(),
                    'rear_history_equal_all_states_requests':True}
                rows.append(row)
                for c,context in ((0,'both_active'),(1,'front_only')):
                    acc=old[:-1,h] if c==0 else states[:-1,h]
                    req=oldrq[:,h] if c==0 else rqs[:,h]
                    before=oldy[:,h] if c==0 else ys[:,h]
                    val=evaluate(words,acc) if c==0 else None
                    if c==0:
                        assert np.array_equal(val[0],before)
                        computed=round_ratio(val[3][:,:4].sum(axis=1)*FACTORS*30,125*den)
                        assert np.array_equal(computed,req)
                        gate_counts=val[1][:,:4,:2].sum(axis=(0,1)).tolist()
                        basis_counts=val[2][:,:4,:2].sum(axis=(0,1)).tolist()
                        joint_counts=np.logical_and(val[1][:,:4,:2],val[2][:,:4,:2]).sum(axis=(0,1)).tolist()
                    else:gate_counts,basis_counts,joint_counts=new_gate_stats[h]
                    post=acc.copy();post[:,:2]+=req[:,:2]
                    assert np.all((post>=0)&(post<=2047*4096))
                    afterlow=evaluate(words,post)[0];lowys[:,h+c]=afterlow
                    low,diag=local_low(afterlow,before,target);diagnostics[:,h+c]=diag
                    k0=round_ratio(acc,4096);k1=round_ratio(post,4096)
                    same=np.all(k0[:,:2]==k1[:,:2],axis=1)
                    assert np.array_equal(afterlow[same],before[same])
                    low.update({'seed':seed,'rate':rate,'initialization':name,'context':context,
                        'low_export_changed_windows':int(np.count_nonzero(~same)),
                        'high_front_nonzero_requested_components':int(np.count_nonzero(req[:,2:4])),
                        'high_front_export_changed_windows':int(np.count_nonzero(np.any(round_ratio(acc[:,:4]+req[:,:4],4096)[:,2:4]!=k0[:,2:4],axis=1))),
                        'low_requested_mean':req[:,:2].mean(axis=0).tolist(),
                        'low_requested_rms':np.sqrt(np.mean(req[:,:2].astype(float)**2,axis=0)).tolist(),
                        'low_requested_zero_components':np.count_nonzero(req[:,:2]==0,axis=0).tolist(),
                        'selected_low_gate_counts':gate_counts,'selected_low_basis_counts':basis_counts,
                        'selected_low_gate_basis_counts':joint_counts})
                    lowrows.append(low)
                    for w in (0,1024,2047):
                        s,b=probe(words[w],post[w:w+1],None,afterlow[w:w+1],None,den,None,START+w,slots=(0,1,2,3,59,119));sc+=s
                print(seed,rate,name,'MSE',mse,'M',float(M),'D',float(D),'I',float(I),flush=True)
            bridges.tofile(out/f'{stem}_bridge_outputs.bin');lowys.tofile(out/f'{stem}_low_post_outputs.bin')
            diagnostics.tofile(out/f'{stem}_low_diagnostics.bin')
    # 19200 preflight +14400 new path+7200 bridge+720 low readouts.
    assert sc==22320 and banks==120
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    write(out/'results.json',{'completed':True,'rows':rows,'low_request_rows':lowrows})
    write(out/'verification.json',{'passed':True,'all_new_paths':40,'new_integer_codes_replayed':9830400,
        'new_state_vectors_replayed':81960,'new_submissions_replayed':81920,'rear_autonomous_history_cases':20,
        'exact_factorial_mediation_splits':20,'exact_local_low_windows':81920,
        'rational_and_formal_readouts_each_including_preflight':41520,'formal_active_bank_probes_including_preflight':280,
        'new_path_outputs_including_preflight':9840000,'new_effective_learning_each_stage_including_preflight':164000,
        'new_active_bank_submissions_each_stage_including_preflight':41000,
        'full_new_integer_replay':9830400,'old_both_integer_replay':4915200,
        'bridge_readouts':4915200,'same_window_low_readouts':9830400,
        'kernel_integer_readouts_all_phases':39340800,'kernel_gate_support_product_components_each':314726400,
        'held_bank_candidate_requests_are_offline_only':True,'source_conversions':0,'fft':0,'new_long_axis':False,
        'normal_holdout_used':False,'new_algorithm':False,'complete_physical_regeneration':False})
    write(out/'delivery_hashes.json',{p.name:digest(p) for p in out.iterdir() if p.is_file() and p.name!='delivery_hashes.json'})
    print('Full intervention replay, exact split and low-request analysis passed',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','run','verify_analyze']);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    try:globals()[args.mode](args.out)
    except Exception:
        if args.out.exists():write(args.out/(args.mode+'_failure.json'),{'traceback':traceback.format_exc()})
        raise
