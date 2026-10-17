"""EXP-076: one offline mean-shadow gate intervention with full feedback.

Only front gate2 is sourced from the prior continuous mean. Actual learning
numbers, other gates, full front state and integer output follow original Gu.
The shadow uses future knowledge: this is a diagnostic, not an online algorithm.
"""
import argparse
from dataclasses import replace
from fractions import Fraction as F
from math import lcm
from pathlib import Path
import shutil
import sys
import traceback
import numpy as np

ROOT = Path(__file__).resolve().parents[2]; sys.path[:0] = [str(ROOT),str(ROOT/'src')]
from experiments.exp_075_front_sampling_intervention import run as old
from experiments.exp_075_front_sampling_intervention.analyze_fixed_mean_statistics import (
    Budget,vector_rear,scalar_rear,basis,
)
from adc_research.theory.static_fixed_contract import pwl

W=2048; N=120*W; PERIOD=30720; SEED=202610625; RATE='quarter'; KEY=(SEED,RATE,'prefix')
FULL=ROOT/'artifacts/runs/EXP_075/front_sampling_v1'
FIXED=ROOT/'artifacts/research/full_front_fixed_mean_statistics_20261014_v1'
QUADRATIC=ROOT/'artifacts/research/full_front_gate_position_quadratic_20261014_v1'
META=[FULL/'results.json',FULL/'verification.json',FULL/'independent_check.json',FULL/'summary.json',
      FIXED/'results.json',FIXED/'verification.json',FIXED/'independent_check.json',
      QUADRATIC/'results.json',QUADRATIC/'summary.json',old.OLD/'source_protocol.json',old.PHASE]
DATA=[old.OLD/f'both_smooth_{SEED}_words.bin',FULL/f'{SEED}_{RATE}_q22.bin',
      FULL/f'{SEED}_{RATE}_outputs.bin',old.BASE/f'{SEED}_{RATE}_outputs.bin',old.OLD/'tone.bin']
DOCS=old.DOCS+['docs/DECISIONS.md','docs/theory/README.md']
load=old.load; write=old.write; digest=old.digest


def controls():
    q=Budget({'scalar_add':128,'scalar_mul':128,'scalar_div':32})
    k=[F(1),F(1)]
    def yy(second): return q.sub(q.add(q.mul(F(128),k[0]),q.mul(F(64),second)),F(64))
    threshold=q.mul(F(128),k[0]); y=yy(k[1])
    assert y==threshold and abs(y)>=threshold
    assert abs(yy(q.sub(k[1],F(1,1024))))<threshold
    assert abs(yy(q.add(k[1],F(1,1024))))>threshold
    assert round(F(1,2))==0 and round(F(3,2))==2 and round(F(-3,2))==-2
    # Fixed shadow mask and own readout can disagree; only coordinate2 changes.
    original=[F(2),F(3),F(5),F(7)]; hybrid=original.copy(); hybrid[1]=F(-1)
    assert [hybrid[j] for j in (0,2,3)]==[original[j] for j in (0,2,3)]
    assert q.sub(q.total(hybrid),q.total(original))==q.sub(F(-1),F(3))
    # One complete-window update; output is before commit and clipping retained.
    a=F(1); u=F(2); ys=[a]; a=q.add(a,u); ys.append(a)
    assert ys==[1,3] and min(5,max(0,7))==5
    # Same-history deletion does not equal feedback propagation.
    a=F(0); path=[]
    for _ in range(2): path.append(a); a=q.add(a,q.add(F(1),a))
    assert path==[0,1] and a==3 and q.sub(a,F(1))!=1
    assert q.div(q.total([F(1),F(-2)]+[F(0)]*28),F(30))==-F(1,30)
    return {'passed':True,'exact_controls':6,'shadow_equality_only_gate2_nearest_even_timing_feedback_normalization':True},q


def row(d): return next(r for r in d['rows'] if (r['seed'],r['rate'],r['initialization'])==KEY)


def prepare(out):
    assert not out.exists(),'Refuse overwrite'
    assert not (Path(__file__).parent/'protocol.json').exists(),'Existing experiment protocol'
    assert not (ROOT/'docs/reports/experiments/EXP_076_FIXED_MEAN_GATE_INTERVENTION_V1.md').exists()
    qualified=0
    for p in META:
        if p.name in ('verification.json','independent_check.json','summary.json'):
            qualified+=p.stat().st_size; assert load(p)['passed'],p
    assert load(QUADRATIC/'summary.json')['deleted_position_negative_certified']
    files=META+DATA
    hashes={str(p):digest(p) for p in files}
    for folder in (FULL,FIXED):
        for name,z in load(folder/'source_hashes.json').items():
            if name in hashes: assert hashes[name]==z,name
    dependencies=list((ROOT/'src/adc_research').rglob('*.py'))
    dependencies += [Path(__file__),ROOT/'experiments/exp_075_front_sampling_intervention/run.py',
        ROOT/'experiments/exp_073_bank_feedback_intervention/run.py',
        ROOT/'experiments/exp_062_same_input_background/verify.py',
        ROOT/'experiments/exp_060_static_auxiliary_preflight/run.py',
        ROOT/'experiments/exp_075_front_sampling_intervention/analyze_fixed_mean_statistics.py']
    dependencies=sorted(set(p.resolve() for p in dependencies))
    historical=load(FULL/'execution_hashes.json')
    for p in dependencies:
        if str(p) in historical:assert digest(p)==historical[str(p)],p
    out.mkdir(parents=True);write(out/'source_hashes.json',hashes)
    write(out/'execution_hashes.json',{str(p):digest(p) for p in dependencies})
    shutil.copyfile(Path(__file__),out/'frozen_run.py')
    for name in DOCS:
        p=out/'documents_before'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
    fixed=row(load(FIXED/'results.json')); ref=row(load(FULL/'results.json'))
    fingerprint=2*(sum(p.stat().st_size for p in files)+sum(p.stat().st_size for p in dependencies))
    common={'fingerprint_bytes':fingerprint,'metadata_json_bytes':sum(p.stat().st_size for p in META),'initial_state_values':8}
    def actual_limits(codes,windows):
        return {'evaluated_codes':codes,'front_Q3_PWL':codes,'rear_Q3_PWL':codes,
                'own_gate_tests':8*codes,'support_tests':8*codes,'original_product_cells':8*codes,
                'gate2_override_product_cells':codes,'request_reduction_inputs':8*codes,
                'candidate_roundings':8*windows,'front_commit_cells':4*windows}
    def shadow_limits(codes):
        return {'shadow_rear_Q3_PWL':codes,'shadow_raw_cells':codes,'shadow_basis_cells':4*codes,
                'shadow_continuous_PWL':codes,'shadow_gate_tests':codes}
    pre={**common,'source_values':2*120*4,**actual_limits(4*120,4),**shadow_limits(2*120),
         'front_learning_observations':240,'front_commits':2,'formal_and_Fraction_readouts_each':480,
         'scalar_shadow_probes':480,'original_formal_bank_probes':4,'scalar_hybrid_commit_probes':2,
         'saved_reference_control_values':2*120,'scalar_add':20000,'scalar_mul':20000,'scalar_div':10000}
    run={**common,'source_values':N*4,**actual_limits(N,W),**shadow_limits(N),
         'front_learning_observations':N,'front_commits':W,'output_bytes':N*2,
         'state_bytes':(W+1)*8*4,'request_bytes':W*8*4,'shadow_bytes':N}
    verify={**common,'source_values':N*4,'saved_state_values':(W+1)*8,'saved_request_values':W*8,
        'saved_output_values':N,'saved_reference_output_values':2*N,'saved_shadow_values':N,
        'export_round_cells':(W+1)*8,'joint_group_inputs':N,'independent_group_readouts':N,
        'independent_rear_Fraction_cells':256,'independent_shadow_Fraction_cells':9216,
        'independent_request_cells':W*4,'independent_reduction_inputs':N*4,'independent_commit_cells':W*4,
        'formal_and_Fraction_readouts_each':360,'scalar_shadow_probes':360,
        'original_formal_bank_probes':3,'scalar_hybrid_commit_probes':3,
        'score_absolute_word_inputs':6*N,'score_pair_word_inputs':6*N,'score_integer_word_products':18*N,
        'score_phase_inputs':12*N,'score_target_products':54*PERIOD,'score_scalar_formula_objects':54,
        'target_table_values':PERIOD,'target_table_square_products':PERIOD,
        'scalar_add':200000,'scalar_mul':200000,'scalar_div':40000,
        'candidate_fingerprint_bytes':2*(N*3+(W+1)*8*4+W*8*4)}
    check={**common,'saved_output_values':3*N,'direct_residual_word_inputs':3*N,
        'direct_bigint_products':6*N,'pair_absolute_word_inputs':3*N,'block_objects':8,
        'target_table_values':PERIOD,'candidate_fingerprint_bytes':verify['candidate_fingerprint_bytes']}
    cr,cq=controls()
    protocol={'date':'2026-10-14','version':'EXP076-one-shadow-gate2-finite-v1','case':KEY,
        'authority':'User continues D136..140. Current STATUS specifies minimal same-initial-state gate-source feedback/MSE test under approved finite-intervention mainline.',
        'question':'Does replacing only front low2 gate2 by the prior continuous mean shadow reduce actual final-integer MSE after full front feedback?',
        'scope':'Exactly one new path625 prefix/quarter,2048 windows/full120/[128,136), original complete8 Q22 initial, old source/order/end. Rear held; front ALL4 requests active, high motion and clipping reported, never screened. No new source/model/horizon/holdout/online algorithm.',
        'initial_Q22':ref['initial_Q22'],'shadow_front_kappa':fixed['continuous_kappa'],
        'shadow_rear_codes':fixed['original_rear_codes'],'shadow_expected_gate_count':fixed['gate2_count'],
        'transition':'Original actual Q3 output and all8 Gu gated products; replace ONLY product coordinate1(second front coordinate) by8*d1*y1_scaled*GF. Full120 sum with FACTORS/(125*4), once nearest-even Q22 request/clip. Commit front4 only, rear held. Output all120 using old state before commit. Other front gates and numeric readout recomputed from own current full state.',
        'shadow':'GF=abs(sum psi_j*kbar_j-64d1)>=128*kbar1, with ORIGINAL held rear Q3 and exact rational non-grid front mean. This is a per-word mask, NOT current y compared to a mean threshold. Source independent of front digital coefficients; precompute same2048x120 mask once, save245760 bytes. No target enters transition.',
        'information_cost':'kbar uses complete future ORIGINAL full120 export history; explicit additional offline knowledge. Extra shadow rear/continuous-front PWL, four bases and gate tests counted. Precomputed mask storage counted; not online information or same-cost algorithm. Actual learning still full120 (30x four-word), extra shadow readout is not free.',
        'prediction':'Primary candidate-minus-original-full final-integer MSE is predicted negative from prior gate/position evidence; certify using ORIGINAL target_radius. Positive or unresolved result rejects/narrows transfer from same-history deletion to feedback. Candidate-minus-held and old-full-minus-held are secondary; all8 blocks kept, no score-driven repairs.',
        'validation':'Six bounded controls, two-window old-full exact replay and candidate scalar Fraction/formal readout and original-bank check (unchanged coords0,2,3), independent hybrid second request/commit. Full candidate path independently rebuilt from scalar digital/export groups with integer front PWL and Fraction shadow cache, every request/after/output/mask matches. Three prescribed windows0,1024,2047 same probes. Main phase-summed exact scores; independent per-block direct bigint residual squares and original target intervals.',
        'scoring':'Original binary64 target2048*(1+tone), original NG39/43 phase radius, final integer MSE. Compare candidate/full/held, center exact dyadic and +/-2*rT*mean|Y-Z|. Original full/held scores and full-held interval must match immutable EXP075 row. No FFT or new target precision.',
        'preflight_limits':pre,'run_limits':run,'verify_limits':verify,'independent_limits':check,'control_limits':cq.limits,
        'units':'Count external old values/metadata and full-file fingerprints separately. Actual evaluate kernels include internals; gate/support/product cells each explicit. Extra gate2 product, eight request reduction inputs/cell and Q22 request/commit kernels counted. Shadow rear/raw/four-basis/continuous/gate kernels include their internals. Independent scalar group kernel includes front PWL offset/local nearest-even, actual gates/products and integer output; Fraction shadow/rear outer binary ops wrapped. Score phase/word products and fixed formula-object kernels counted as EXP075. Controls separately wrapped; index/parse/fixed constants/unary/compare/display excluded. Diagnostic units not chip costs.',
        'stop':'Only one original endpoint and8 blocks. Preserve failed prefixes, all high requests/clips and uncertain intervals; no automatic retries/precision/model/seed/period/policy changes. New online algorithm/hardware/physical/general recovery claims excluded.'}
    write(out/'protocol.json',protocol);write(out/'controls.json',cr);cq.accounting(out,'accounting_controls.json',True)
    write(out/'preparation_accounting.json',{'fingerprint_bytes':fingerprint//2,'qualified_json_bytes':qualified,
        'parameter_metadata_bytes':sum(p.stat().st_size for p in (FIXED/'results.json',FULL/'results.json')),
        'scientific_record_calculations':0})
    shutil.copyfile(out/'protocol.json',Path(__file__).parent/'protocol.json')
    print('Frozen EXP076 one offline shadow gate2 path, same initial state/end.',flush=True)


def guards(out,q,candidate=False):
    assert digest(Path(__file__))==digest(out/'frozen_run.py')
    for manifest in ('source_hashes.json','execution_hashes.json'):
        for name,z in load(out/manifest).items():
            p=Path(name);q.charge('fingerprint_bytes',p.stat().st_size);assert digest(p)==z,p
    if candidate:
        for name,z in load(out/'candidate_hashes.json').items():
            p=Path(name);q.charge('candidate_fingerprint_bytes',p.stat().st_size);assert digest(p)==z,p


def inputs(out,q):
    values={}
    for p in META:q.charge('metadata_json_bytes',p.stat().st_size);values[str(p)]=load(p)
    return load(out/'protocol.json'),row(values[str(FULL/'results.json')]),old.fixed_setup(values[str(old.OLD/'source_protocol.json')])[1],F(values[str(old.PHASE)]['target_radius'])


def initial(q):
    q.charge('initial_state_values',8)
    return np.array(np.memmap(DATA[1],dtype='<i4',mode='r',shape=(W+1,2,8))[0,1],dtype=np.int64)


def words(q,count):
    q.charge('source_values',count*120*4)
    return np.array(old.source(SEED)[:count],dtype=np.int64)


def shadow(ws,p,q):
    num=ws.shape[0]*120
    for key,mult in (('shadow_rear_Q3_PWL',1),('shadow_raw_cells',1),('shadow_basis_cells',4),('shadow_continuous_PWL',1),('shadow_gate_tests',1)):q.charge(key,mult*num)
    q2,sar,bits=(ws[:,:,j] for j in (1,2,3));d,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
    raw=1024*q2+vector_rear(8*sar,p['shadow_rear_codes'])-128*d2
    assert np.all((raw>=-4096)&(raw<4096))
    coeff=list(map(F,p['shadow_front_kappa']));den=lcm(*(k.denominator for k in coeff))
    kn=[k.numerator*(den//k.denominator) for k in coeff];phi=basis(raw)
    y=sum(phi[:,:,j]*kn[j] for j in range(4))-512*den*d
    return abs(y)>=1024*kn[0]


def step(ws,a,gf,q,learn):
    num=ws.shape[0]*120
    for key,mult in (('evaluated_codes',1),('front_Q3_PWL',1),('rear_Q3_PWL',1),('own_gate_tests',8),('support_tests',8),('original_product_cells',8)):q.charge(key,mult*num)
    value=old.evaluate(ws,a)
    products=value[3].copy()
    # None is used only by old-full preflight control; its counted override
    # kernel still obtains the identical original second product.
    q.charge('gate2_override_product_cells',num)
    if gf is not None:
        d=2*(ws[:,:,3]&1)-1;products[:,:,1]=8*d*value[5]*gf
    q.charge('request_reduction_inputs',8*num);q.charge('candidate_roundings',len(a)*8)
    candidate=old.round_ratio(products.sum(axis=1)*old.FACTORS,125*4)
    requested=candidate*np.array([1,1,1,1,0,0,0,0])
    q.charge('front_commit_cells',len(a)*4);raw=a+requested;after=np.clip(raw,0,2047*4096)
    if learn:q.charge('front_learning_observations',num);q.charge('front_commits',len(a))
    return value[0],requested,after,int(np.count_nonzero(raw!=after))


def scalar_shadow(q2,sar,bits,p,q,rear=None):
    d,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
    if rear is None:rear=scalar_rear(sar,p['shadow_rear_codes'],q)
    raw=int(q.sub(q.add(q.mul(F(1024),F(q2)),F(rear)),q.mul(F(128),F(d2))))
    assert -4096<=raw<4096
    psi=[F((1 if raw>=0 else -1)*min(max(abs(raw)-1024*j,0),1024),8) for j in range(4)]
    y=q.sub(q.total(q.mul(psi[j],F(p['shadow_front_kappa'][j])) for j in range(4)),F(64*d))
    return abs(y)>=q.mul(F(128),F(p['shadow_front_kappa'][0]))


def probe(ws,a,after,y,rq,p,cfg,w,q,gf=None):
    codes=old.export(tuple(map(int,a)));ks=tuple(F(z,1024) for z in codes)
    cc=replace(cfg.cascade,stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=codes[:4]),stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=codes[4:]))
    rows=[];values=[];sums=[F(0)]*4
    for j,word in enumerate(ws):
        q.charge('formal_and_Fraction_readouts_each');q.charge('scalar_shadow_probes')
        q1,q2,sar,bits=map(int,word);d,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
        sample=old.DigitalCalibrationSample(q1,q2,sar,d,d2)
        rd=old.readout(q1,q2,F(sar),d,d2,ks,data_q3=True);fm=old.correct_two_stage_fixed_observed(sample,cc)
        assert fm.unclipped_output_scaled==8*rd.output and fm.stage1_raw_scaled==8*rd.raw1
        assert 0<=rd.output<=4095 and old.nearest_even(rd.output)==int(y[j])
        sh=scalar_shadow(q2,sar,bits,p,q)
        if gf is not None:assert sh==bool(gf[j])
        rows.append(old.FourLaneConversion(120*(old.START+w)+j,j%4,sample));values.append((512*d,int(8*rd.y1)))
        for i,g in enumerate(rd.gates[0]):
            if i==1 and gf is not None:g=sh
            if g:sums[i]=q.add(sums[i],q.mul(F(64*d),rd.y1))
    steps=tuple(mu/4 for mu in cfg.stage1_lms.step_sizes)
    bank=old.FixedGatedLmsState(tuple(map(int,a[:4])),(0,)*4,(0,)*4,(0,)*4,120*(old.START+w))
    q.charge('original_formal_bank_probes')
    original=old._bank(bank,replace(cfg.stage1_lms,step_sizes=steps),rows,values,(True,)*120,1)
    requested,post=old.commit(tuple(map(int,a[:4])),tuple(sums),1,steps)
    if gf is not None:
        q.charge('scalar_hybrid_commit_probes')
        assert [requested[i] for i in (0,2,3)]==[original.requested_deltas[i] for i in (0,2,3)]
    else:assert requested==original.requested_deltas
    assert requested==tuple(map(int,rq[:4])) and post==tuple(map(int,after[:4]))
    assert np.array_equal(a[4:],after[4:]) and not np.any(rq[4:])


def run(out):
    assert not (out/'completed.json').exists() and not (out/'preflight.json').exists()
    q=Budget(load(out/'protocol.json')['preflight_limits']);done=False
    try:
        guards(out,q);p,ref,cfg,_=inputs(out,q);ws=words(q,2);a=initial(q);assert a.tolist()==p['initial_Q22']
        gf=shadow(ws,p,q);stock=a.copy();candidate=a.copy()
        q.charge('saved_reference_control_values',240)
        yy=np.memmap(DATA[2],dtype='<i2',mode='r',shape=(W,2,120))[:2,1]
        for w in range(2):
            ys,rq,after,_=step(ws[w:w+1],stock[None,:],None,q,False)
            assert np.array_equal(ys[0],yy[w]);probe(ws[w],stock,after[0],ys[0],rq[0],p,cfg,w,q)
            stock=after[0]
            ys,rq,after,_=step(ws[w:w+1],candidate[None,:],gf[w:w+1],q,True)
            probe(ws[w],candidate,after[0],ys[0],rq[0],p,cfg,w,q,gf[w]);candidate=after[0]
        guards(out,q);write(out/'preflight.json',{'passed':True,'windows':2,'old_full_replay_exact':True,'hybrid_probes_exact':True});done=True
    finally:q.accounting(out,'accounting_preflight.json',done)
    q=Budget(load(out/'protocol.json')['run_limits']);done=False
    try:
        guards(out,q);p,ref,_,_=inputs(out,q);ws=words(q,W);a=initial(q);init=a.copy()
        gf=shadow(ws,p,q);assert int(np.count_nonzero(gf))==p['shadow_expected_gate_count']
        states=np.empty((W+1,8),dtype='<i4');ys=np.empty((W,120),dtype='<i2');req=np.empty((W,8),dtype='<i4');states[0]=a;clips=0;done_windows=0
        for w in range(W):
            y,rq,after,c=step(ws[w:w+1],a[None,:],gf[w:w+1],q,True)
            assert np.array_equal(after[0,4:],init[4:]);ys[w]=y[0];req[w]=rq[0];states[w+1]=after[0];a=after[0];clips+=c
            done_windows=w+1
        for name,v,key in (('outputs.bin',ys,'output_bytes'),('q22.bin',states,'state_bytes'),('requests.bin',req,'request_bytes'),('shadow_gate.bin',gf.astype('u1'),'shadow_bytes')):
            q.charge(key,v.nbytes);v.tofile(out/name)
        guards(out,q);write(out/'candidate_hashes.json',{str(out/n):digest(out/n) for n in ('outputs.bin','q22.bin','requests.bin','shadow_gate.bin')})
        write(out/'completed.json',{'completed':True,'new_paths':1,'new_outputs':N,'front_learning_observations':N,
            'front_commits':W,'shadow_readout_words':N,'state_clipped_components':clips,'rear_learning_commits':0,'new_source_conversions_FFT':0});done=True
        print('Completed one original-endpoint feedback path; clips=',clips,flush=True)
    except Exception:
        if 'done_windows' in locals() and not (out/'outputs.bin').exists():
            for name,v,key in (('partial_outputs.bin',ys[:done_windows],'output_bytes'),
                ('partial_q22.bin',states[:done_windows+1],'state_bytes'),('partial_requests.bin',req[:done_windows],'request_bytes')):
                q.charge(key,v.nbytes);v.tofile(out/name)
            write(out/'failed_prefix.json',{'completed_windows':done_windows,'scientific_failure_preserved':True})
        raise
    finally:q.accounting(out,'accounting_run.json',done)


def even_ratio(n,d):
    quotient,remainder=divmod(int(n),int(d))
    return quotient+int(2*remainder>d or (2*remainder==d and quotient%2!=0))


def reconstruct(ws,states,p,q):
    """Independent scalar readout groups; no accelerated evaluate/PWL used."""
    q.charge('export_round_cells',(W+1)*8)
    kk=np.array([[round(F(int(z),4096)) for z in row] for row in states],dtype=np.int64)
    assert np.all((kk>=0)&(kk<=2047)) and np.all(states[:,4:]==states[0,4:])
    assert kk[0,4:].tolist()==p['shadow_rear_codes']
    joint=np.concatenate((ws.reshape(N,4),np.repeat(kk[:-1,:4],120,axis=0)),axis=1)
    q.charge('joint_group_inputs',N);cells,inv=np.unique(joint,axis=0,return_inverse=True)
    sars=sorted(set(int(c[2]) for c in cells));q.charge('independent_rear_Fraction_cells',len(sars))
    rt={s:scalar_rear(s,p['shadow_rear_codes'],q) for s in sars}
    shadows={};gy=np.empty(len(cells),dtype=np.int64);gp=np.empty((len(cells),4),dtype=np.int64);gs=np.empty(len(cells),dtype='u1')
    for i,cell in enumerate(cells):
        q.charge('independent_group_readouts');q1,q2,sar,bits,*k=map(int,cell)
        key=q2,sar,bits
        if key not in shadows:
            q.charge('independent_shadow_Fraction_cells');shadows[key]=scalar_shadow(q2,sar,bits,p,q,rt[sar])
        gf=shadows[key];d,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
        raw=1024*q2+rt[sar]-128*d2;assert -4096<=raw<4096
        mag=abs(raw);seg=min(mag//1024,3)
        front=(1 if raw>=0 else -1)*(sum(k[:seg])+even_ratio((mag-1024*seg)*k[seg],1024))
        y1=front-512*d;out=16384+4096*q1+y1;assert 0<=out<=4095*8
        gy[i]=even_ratio(out,8);gs[i]=gf
        for j in range(4):gp[i,j]=8*d*y1*(gf if j==1 else abs(y1)>=sum(k[:j]))
    yy=gy[inv].reshape(W,120);products=gp[inv].reshape(W,120,4);gf=gs[inv].reshape(W,120)
    q.charge('independent_reduction_inputs',N*4);sums=products.sum(axis=1,dtype=np.int64)
    q.charge('independent_request_cells',W*4)
    rq=np.array([[even_ratio(int(z)*factor,500) for z,factor in zip(row,(-2,-6,-12,-24))] for row in sums],dtype=np.int64)
    q.charge('independent_commit_cells',W*4);raw_after=states[:-1,:4]+rq;after=np.clip(raw_after,0,2047*4096)
    return yy,rq,after,gf,kk,{'joint_cells':len(cells),'shadow_cells':len(shadows),'rear_Fraction_cells':len(sars),
        'state_clipped_components':int(np.count_nonzero(raw_after!=after))}


def inspect(ys,ti,td,t2,rad,q):
    losses={n:old.pack(old.score(y,ti,td,t2,q)) for n,y in ys.items()}
    pairs={n:old.pair(ys[a],ys[b],ti,td,rad,q) for n,a,b in
        (('candidate_minus_full','candidate','full'),('candidate_minus_held','candidate','held'),('full_minus_held','full','held'))}
    for n,a,b in (('candidate_minus_full','candidate','full'),('candidate_minus_held','candidate','held'),('full_minus_held','full','held')):
        assert F(pairs[n]['exact'])==F(losses[a]['exact'])-F(losses[b]['exact'])
    assert F(pairs['candidate_minus_held']['exact'])==F(pairs['candidate_minus_full']['exact'])+F(pairs['full_minus_held']['exact'])
    return {'losses':losses,'pairs':pairs}


def references(q):
    q.charge('saved_reference_output_values',2*N)
    return {'full':np.array(np.memmap(DATA[2],dtype='<i2',mode='r',shape=(W,2,120))[:,1]),
            'held':np.array(np.memmap(DATA[3],dtype='<i2',mode='r',shape=(W,4,120))[:,3])}


def verify(out):
    assert not (out/'results.json').exists()
    assert load(out/'preflight.json')['passed'] and load(out/'completed.json')['completed']
    q=Budget(load(out/'protocol.json')['verify_limits']);done=False
    try:
        guards(out,q,True);p,ref,cfg,rad=inputs(out,q);ws=words(q,W);init=initial(q)
        q.charge('saved_state_values',(W+1)*8);states=np.fromfile(out/'q22.bin',dtype='<i4').reshape(W+1,8).astype(np.int64)
        q.charge('saved_request_values',W*8);requests=np.fromfile(out/'requests.bin',dtype='<i4').reshape(W,8)
        q.charge('saved_output_values',N);outputs=np.fromfile(out/'outputs.bin',dtype='<i2').reshape(W,120)
        q.charge('saved_shadow_values',N);shadow_saved=np.fromfile(out/'shadow_gate.bin',dtype='u1').reshape(W,120)
        assert np.array_equal(init,states[0]) and init.tolist()==p['initial_Q22'] and not np.any(requests[:,4:])
        yy,rq,after,gf,kk,rebuild=reconstruct(ws,states,p,q)
        assert np.array_equal(yy,outputs) and np.array_equal(rq,requests[:,:4]) and np.array_equal(after,states[1:,:4])
        assert np.array_equal(gf,shadow_saved) and int(np.count_nonzero(gf))==p['shadow_expected_gate_count']
        assert rebuild['state_clipped_components']==load(out/'completed.json')['state_clipped_components']
        for w in (0,1024,2047):probe(ws[w],states[w],states[w+1],outputs[w],requests[w],p,cfg,w,q,gf[w])
        ti,td=old.exact_target(q);q.charge('target_table_square_products',PERIOD)
        t2=F(sum(z*z for z in ti),PERIOD*td*td)
        ys={'candidate':outputs,**references(q)};total=inspect(ys,ti,td,t2,rad,q)
        for name in ('full','held'):assert total['losses'][name]==ref['total']['losses'][name]
        assert total['pairs']['full_minus_held']==ref['total']['pairs']['full_minus_held']
        blocks=[]
        for b in range(8):
            v=inspect({n:y[b*256:(b+1)*256] for n,y in ys.items()},ti,td,t2,rad,q)
            assert v['pairs']['full_minus_held']==ref['blocks'][b]['pairs']['full_minus_held']
            blocks.append({'block':128+b,**v})
        for n in ys:assert F(total['losses'][n]['exact'])==sum(F(b['losses'][n]['exact']) for b in blocks)/8
        r={'seed':SEED,'rate':RATE,'initialization':'prefix','total':total,'blocks':blocks,
           'initial_Q22':states[0].tolist(),'terminal_Q22':states[-1].tolist(),
           'high_requested_components_nonzero':int(np.count_nonzero(requests[:,2:4])),
           'high_export_changed_windows':int(np.count_nonzero(np.any(kk[:-1,2:4]!=kk[0,2:4],axis=1))),
           'coefficient_export_min':kk.min(axis=0).tolist(),'coefficient_export_max':kk.max(axis=0).tolist(),
           'state_clipped_components':rebuild['state_clipped_components'],'shadow_gate_count':int(np.count_nonzero(gf)),
           'independent_rebuild':rebuild}
        guards(out,q,True);write(out/'results.json',{'completed':True,'rows':[r]})
        write(out/'verification.json',{'passed':True,'cases':1,'blocks':8,'all_states_requests_outputs_shadow_scalar_rebuild_exact':True,
            'Fraction_and_formal_readouts_each':360,'original_bank_and_hybrid_probes_each':3,
            'old_full_held_scores_and_intervals_exact':True});done=True
        print('Candidate-full MSE=',total['pairs']['candidate_minus_full']['value'],
              'candidate-held=',total['pairs']['candidate_minus_held']['value'],flush=True)
    finally:q.accounting(out,'accounting_verify.json',done)


def check(out):
    assert not (out/'independent_check.json').exists() and load(out/'verification.json')['passed']
    q=Budget(load(out/'protocol.json')['independent_limits']);done=False
    try:
        guards(out,q,True);p,ref,_,rad=inputs(out,q);initial(q)
        ti,td=old.exact_target(q);target=np.array(ti,dtype=object)
        q.charge('saved_output_values',3*N)
        yy={'candidate':np.memmap(out/'outputs.bin',dtype='<i2',mode='r',shape=(W,120)),
            'full':np.memmap(DATA[2],dtype='<i2',mode='r',shape=(W,2,120))[:,1],
            'held':np.memmap(DATA[3],dtype='<i2',mode='r',shape=(W,4,120))[:,3]}
        r=load(out/'results.json')['rows'][0];losses={n:[] for n in yy};radii={n:[] for n in r['total']['pairs']}
        for b in range(8):
            q.charge('block_objects');vals={n:y[b*256:(b+1)*256].ravel() for n,y in yy.items()}
            for n,y in vals.items():
                q.charge('direct_residual_word_inputs',PERIOD);q.charge('direct_bigint_products',2*PERIOD)
                residual=y.astype(object)*td-target;loss=F(int(np.dot(residual,residual)),PERIOD*td*td)
                assert str(loss)==r['blocks'][b]['losses'][n]['exact'];losses[n].append(loss)
            for name,a,c in (('candidate_minus_full','candidate','full'),('candidate_minus_held','candidate','held'),('full_minus_held','full','held')):
                q.charge('pair_absolute_word_inputs',PERIOD)
                radius=2*rad*F(int(np.sum(abs(vals[a].astype(np.int64)-vals[c]))),PERIOD)
                v=losses[a][-1]-losses[c][-1]
                assert list(map(str,(v-radius,v+radius)))==r['blocks'][b]['pairs'][name]['interval'];radii[name].append(radius)
        for n in yy:assert str(sum(losses[n])/8)==r['total']['losses'][n]['exact']
        for name,a,c in (('candidate_minus_full','candidate','full'),('candidate_minus_held','candidate','held'),('full_minus_held','full','held')):
            v=(sum(losses[a])-sum(losses[c]))/8;radius=sum(radii[name])/8
            assert list(map(str,(v-radius,v+radius)))==r['total']['pairs'][name]['interval']
        guards(out,q,True);write(out/'independent_check.json',{'passed':True,'cases':1,'blocks':8,
            'direct_bigint_residual_losses_and_original_target_intervals_exact':True,'new_learning_or_readouts':0})
        pair=r['total']['pairs']['candidate_minus_full'];lo,hi=map(F,pair['interval'])
        write(out/'summary.json',{'passed':True,'candidate_minus_full':pair,
            'primary_prediction_supported':hi<0,'primary_prediction_rejected':lo>0,'primary_prediction_unresolved':lo<=0<=hi,
            'candidate_minus_held':r['total']['pairs']['candidate_minus_held'],
            'high_request_nonzero':r['high_requested_components_nonzero'],'high_export_changed_windows':r['high_export_changed_windows'],
            'state_clipped_components':r['state_clipped_components'],'all_old20_context_preserved':True,
            'future_holdout_or_new_online_algorithm':False});done=True
        print('Independent direct-block scoring passed; prediction supported=',hi<0,flush=True)
    finally:q.accounting(out,'accounting_independent.json',done)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','run','verify','check']);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    try:globals()[args.mode](args.out)
    except Exception:
        if args.out.exists():write(args.out/f'failure_{args.mode}.json',{'traceback':traceback.format_exc()})
        raise
