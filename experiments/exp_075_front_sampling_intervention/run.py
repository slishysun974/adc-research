"""Finite full120 versus existing point30 front-bank Gu intervention.

The rear bank stays at the original initial state. All four front requests
are computed; no target or future coefficient is read by the transition.
"""
import argparse
from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
import json
import shutil
import sys
import traceback
import numpy as np

ROOT = Path('D:/ADC'); sys.path[:0] = [str(ROOT), str(ROOT/'src')]
from experiments.exp_073_bank_feedback_intervention.run import (
    OLD, BASE, PHASE, SEEDS, W, START, FACTORS, source, evaluate,
    round_ratio, load, write, digest, guard, fixed_setup, export,
    readout, nearest_even, commit, correct_two_stage_fixed_observed,
    DigitalCalibrationSample, FixedGatedLmsState, FourLaneConversion, _bank,
)
POINT = ROOT/'artifacts/runs/EXP_073/bank_feedback_v1'
N, PERIOD = W*120, 30720
MASK = np.array([1,1,1,1,0,0,0,0], dtype=np.int64)
DOCS = ['docs/STATUS.md','docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md',
        'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md',
        'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
        'docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md',
        'docs/reports/GU_ALGORITHM_EVALUATION_V1.md',
        'docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
        'docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md',
        'docs/reports/experiments/README.md']

class Budget:
    def __init__(self, limits):
        self.limits, self.used = limits, dict.fromkeys(limits,0)
    def charge(self, key, n=1):
        assert self.used[key]+n <= self.limits[key], (key,self.used[key],n,self.limits[key])
        self.used[key] += n
    def report(self, out, name, complete):
        write(out/name, {'used':self.used,'limits':self.limits,'completed':complete,
                         'all_limits_met':all(self.used[k] <= z for k,z in self.limits.items())})

def exact_controls():
    # Normalization keeps the step gain: full sum is the average of all30
    # four-word groups, not30 times their individual normalized requests.
    groups = [F(1),F(-2)]+[F(0)]*28
    assert sum(groups)/30 == -F(1,30)
    assert groups[0]>0 and sum(groups)<0
    assert round(F(12,25))==0 and round(F(13,25))==1
    assert round(F(-12,25))==0 and round(F(-13,25))==-1
    assert min(2047*4096,max(0,-1))==0
    assert (F(1)-F(3))**2-(F(2)-F(3))**2==3
    return {'passed':True,'exact_controls':6,'new_physical_source':False}

def prepare(out):
    assert not out.exists(), 'Refuse overwrite'
    assert not (ROOT/'docs/reports/experiments/EXP_075_FRONT_SAMPLING_INTERVENTION_V1.md').exists()
    for folder in (BASE,POINT):
        assert load(folder/'verification.json')['passed']
    files=[OLD/'tone.bin',OLD/'source_protocol.json',PHASE,
           BASE/'results.json',BASE/'verification.json',POINT/'results.json',POINT/'verification.json']
    for seed in SEEDS:
        files.append(OLD/f'both_smooth_{seed}_words.bin')
        for rate in ('base','quarter'):
            files.extend(BASE/f'{seed}_{rate}_{x}.bin' for x in ('q22','outputs'))
            files.extend(POINT/f'{seed}_{rate}_{x}.bin' for x in ('q22','outputs','requests'))
    expected=load(POINT/'source_hashes.json')
    manifest={}
    for p in files:
        z=digest(p)
        if str(p) in expected: assert z==expected[str(p)],p
        manifest[str(p)]=z
    out.mkdir(parents=True)
    write(out/'source_hashes.json',manifest)
    paths=list((ROOT/'src/adc_research').rglob('*.py'))+list((ROOT/'experiments').rglob('*.py'))
    write(out/'execution_hashes.json',{str(p):digest(p) for p in paths})
    shutil.copyfile(Path(__file__),out/'frozen_run.py')
    for name in DOCS:
        p=out/'documents_before'/name;p.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,p)
    fingerprint=2*sum(p.stat().st_size for p in files)+2*sum(p.stat().st_size for p in paths)
    # Each transition counts all evaluated banks, including the held rear's
    # diagnostic products. Effective learning/commits count the front only.
    unit={'source_values':5*N*4,'fingerprint_bytes':fingerprint,
          'initial_state_values':20*8}
    pre={**unit,'source_values':5*2*120*4,'evaluated_codes':40*120,
         'front_PWL':40*120,'rear_PWL':40*120,'gate_tests':40*120*8,
         'product_components':40*120*8,'candidate_roundings':40*8,
         'front_learning_observations':40*120,'front_commits':40,
         'formal_and_Fraction_readouts_each':40*120,'formal_front_bank_probes':40}
    run={**unit,'evaluated_codes':20*N,'front_PWL':20*N,'rear_PWL':20*N,
         'gate_tests':20*N*8,'product_components':20*N*8,'candidate_roundings':20*W*8,
         'front_learning_observations':20*N,'front_commits':20*W,
         'output_bytes':20*N*2,'state_bytes':20*(W+1)*8*4,'request_bytes':20*W*8*4}
    verify={**unit,'evaluated_codes':20*N,'front_PWL':20*N,'rear_PWL':20*N,
            'gate_tests':20*N*8,'product_components':20*N*8,'candidate_roundings':20*W*8,
            'formal_and_Fraction_readouts_each':20*3*120,'formal_front_bank_probes':20*3,
            'saved_new_output_values':20*N,'saved_new_state_values':20*(W+1)*8,
            'saved_new_request_values':20*W*8,'saved_reference_output_values':20*N*2,
            'score_absolute_word_inputs':20*N*3*2,'score_pair_word_inputs':20*N*3*2,
            'score_integer_word_products':20*N*9*2,'score_phase_inputs':20*N*6*2,
            'score_target_products':20*9*PERIOD*6,'score_scalar_formula_objects':20*9*6,
            'target_table_values':PERIOD,'target_table_square_products':PERIOD}
    independent={'source_manifest_bytes':sum(p.stat().st_size for p in files),
                 'saved_output_values':20*N*3,'direct_residual_word_inputs':20*N*3,
                 'direct_bigint_products':20*N*3*2,'pair_absolute_word_inputs':20*N*3,
                 'block_objects':20*8,'target_table_values':PERIOD}
    protocol={'date':'2026-10-14','version':'EXP075-front-full120-finite-v1',
        'authority':'User continues D136..140 mainline; necessary same-initial-state finite future intervention under mainline actual-history method.',
        'question':'Is the original four-word selection necessary for front-only added MSE in these20 cases, and does fuller observation remove it under the same finite endpoint?',
        'why_needed':'Existing frozen-request and fixed-position full120 analyses do not propagate full120 own response/moving gates. Their additive component effects cannot substitute a closed-loop intervention.',
        'scope':'Original both_smooth5 seeds202610621..625, base/quarter step, actual/prefix initial Q22, [128,136),2048 windows. Exactly20 new full120-front-only paths. Rear is held at each original complete Q22; all four front coordinates remain active. No new source/model/horizon or new algorithm.',
        'transition':'Same digital fields,Q22/Q1.10/Q3,>=gates,separate rounding/saturation,120 output-before-update and one commit per window. Full120 uses all120 products and multiplier1; original point30 uses first4 with multiplier30. FACTORS/125m common. All8 candidate deltas evaluated; only front4 committed. No target or future reference enters transition.',
        'controls':'Compare with immutable original point30-front-only and both-held per case. Same initial full8 Q22, same clock/counter/source and endpoint. Formal `_bank` uses all120 selected/multiplier1; rear commits disabled.',
        'information_cost':'Same conversion duration and front commits; full120 has30 times front observations,4915200 rather than163840 main observations. Rear effective learning/commits0. Diagnostic readouts/PWL of rear are counted. No same-cost superiority claim.',
        'predictions':['If full120-front minus held remains certified positive, four-word selection is not necessary for added MSE in that case; retain objective/response/quantization explanations.',
            'If it becomes certified nonpositive while point30 is positive, changed observation has a controlled finite benefit. No proof that all original error came from selection or future general benefit.',
            'Full-minus-point can have either sign. All20 and all8 blocks reported; no score-based endpoint/parameter choice.',
            'Any high-coordinate request/export motion is reported; do not silently freeze it or attribute a full-bank effect solely to low2.',
            'A frozen same-position downhill direction does not guarantee finite trajectory improvement.'],
        'scoring':'Final integers against original binary64 target. Exact dyadic MSE and three pair differences: full-held,full-point,point-held. Original NG39 target_radius gives interval center +/-2*r_T*E|d|; no precision escalation or assumed joint endpoint attainability. All8 blocks and total; no FFT.',
        'validation':'Six exact controls, all20 two-window preflight with full120 scalar Fraction and formal readout/_bank checks; full output/state/request replay; all20 windows0,1024,2047 same probes. Independent saved-output direct bigint residual squares for every block (no phase-summed score kernel), full/point/held losses and pair ranges agree exactly.',
        'budget_units':'Read/value counts, vector readout/PWL/gate/product components, candidate roundings, effective front observations and commits, byte outputs, score word inputs/phase inputs/target products and finite scalar formulas counted before execution. Fixed-scale/index/export/helper integer operations included in respective vector kernels, not individually estimated as hardware gates. Fingerprint I/O separate; independent all-block bigint squares use explicit word/product units. No source regeneration, FFT, root, optimizer or future6007/8009.',
        'preflight_limits':pre,'run_limits':run,'verify_limits':verify,'independent_limits':independent,
        'stop':'Existing endpoint only. Reject domain/normalization/source/budget/validation mismatch; preserve failed prefixes and do not automatically repair performance or expand. State saturation reported; no new algorithm/hardware/physical claims.'}
    write(out/'protocol.json',protocol);write(out/'controls.json',exact_controls())
    exp=Path(__file__).parent
    shutil.copyfile(out/'protocol.json',exp/'protocol.json')
    (exp/'README.md').write_text('# EXP-075：前级四字／全槽观测的有限闭环干预\n\n原五种子、两倍率、两起点、[128,136)终点及完整Q22保持，后级保持，前级四坐标完整重算。仅新增20条原Gu full120路径，point30及双保持复用，不是同成本新算法。\n\n具体模型、可否定预测、信息／学习成本、预检与独立核对、预算／停止见[冻结协议](protocol.json)。从根目录依次运行`python experiments/exp_075_front_sampling_intervention/run.py prepare --out <新目录>`、`run`、`verify`、`check --out <同目录>`。prepare／后续阶段拒绝覆盖，冻结数据及失败保留；禁止追加种子、期限、源或未来留出。\n',encoding='utf-8')
    print('Frozen EXP075:20 full120 front paths; fixed endpoint136',flush=True)

def guards(out,q):
    assert digest(Path(__file__))==digest(out/'frozen_run.py')
    for name in ('source_hashes.json','execution_hashes.json'):
        for p,z in load(out/name).items():
            q.charge('fingerprint_bytes',Path(p).stat().st_size);assert digest(Path(p))==z,p

def transition(words,acc,den,q,learn):
    num=words.shape[0]*120
    for key,factor in (('evaluated_codes',1),('front_PWL',1),('rear_PWL',1),('gate_tests',8),('product_components',8)):
        q.charge(key,num*factor)
    value=evaluate(words,acc);q.charge('candidate_roundings',len(acc)*8)
    cand=round_ratio(value[3].sum(axis=1)*FACTORS,125*den)
    request=cand*MASK;unclipped=acc+request;after=np.clip(unclipped,0,2047*4096)
    if learn:
        q.charge('front_learning_observations',num);q.charge('front_commits',len(acc))
    return value[0],request,after,int(np.count_nonzero(unclipped!=after))

def initial(seed,rate,q):
    q.charge('initial_state_values',16)
    return np.array(np.memmap(BASE/f'{seed}_{rate}_q22.bin',dtype='<i4',mode='r',shape=(W+1,4,8))[0,[0,2]],dtype=np.int64)

def probe(words,acc,after,ys,rq,den,window,q):
    _,cfg=fixed_setup(load(OLD/'source_protocol.json'))
    for h in range(len(acc)):
        old=tuple(map(int,acc[h]));codes=export(old);ks=tuple(F(z,1024) for z in codes)
        cc=replace(cfg.cascade,stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=codes[:4]),
                   stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=codes[4:]))
        conversions=[];values=[];sums=[F(0)]*4
        for j,word in enumerate(words):
            q.charge('formal_and_Fraction_readouts_each')
            q1,q2,sar,bits=map(int,word);d1,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
            sample=DigitalCalibrationSample(q1,q2,sar,d1,d2)
            rd=readout(q1,q2,F(sar),d1,d2,ks,data_q3=True)
            formal=correct_two_stage_fixed_observed(sample,cc)
            assert formal.unclipped_output_scaled==8*rd.output
            assert formal.stage1_raw_scaled==8*rd.raw1
            assert nearest_even(rd.output)==int(ys[h,j]) and 0<=rd.output<=4095
            conversions.append(FourLaneConversion(120*window+j,j%4,sample))
            values.append((512*d1,int(8*rd.y1)))
            for i,g in enumerate(rd.gates[0]):sums[i]+=64*d1*rd.y1*g
        steps=tuple(mu/den for mu in cfg.stage1_lms.step_sizes)
        req,post=commit(old[:4],tuple(sums),1,steps)
        assert req==tuple(map(int,rq[h,:4])) and post==tuple(map(int,after[h,:4]))
        q.charge('formal_front_bank_probes')
        bank=FixedGatedLmsState(old[:4],(0,)*4,(0,)*4,(0,)*4,120*window)
        actual=_bank(bank,replace(cfg.stage1_lms,step_sizes=steps),conversions,values,(True,)*120,1)
        assert actual.requested_deltas==req and actual.state.accumulator_codes==post
        assert np.array_equal(acc[h,4:],after[h,4:]) and not rq[h,4:].any()

def run(out):
    assert not (out/'completed.json').exists()
    p=load(out/'protocol.json');q=Budget(p['preflight_limits']);done=False
    try:
        guards(out,q);assert load(out/'controls.json')['passed']
        for seed in SEEDS:
            q.charge('source_values',2*120*4);words=source(seed)[:2]
            for rate,den in (('base',1),('quarter',4)):
                acc=initial(seed,rate,q)
                for w in range(2):
                    y,rq,after,_=transition(np.broadcast_to(words[w],(2,120,4)),acc,den,q,True)
                    probe(words[w],acc,after,y,rq,den,START+w,q);acc=after
        guards(out,q);done=True
        write(out/'preflight.json',{'passed':True,'new_codes':4800,'front_learning_observations':4800,
                                    'front_commits':40,'Fraction_and_formal_readouts_each':4800})
    finally:q.report(out,'accounting_preflight.json',done)
    q=Budget(p['run_limits']);done=False;counts=[]
    try:
        guards(out,q)
        for seed in SEEDS:
            q.charge('source_values',N*4);words=source(seed)
            for rate,den in (('base',1),('quarter',4)):
                acc=initial(seed,rate,q);init=acc.copy()
                states=np.empty((W+1,2,8),dtype='<i4');outputs=np.empty((W,2,120),dtype='<i2')
                requests=np.empty((W,2,8),dtype='<i4');states[0]=acc;clips=0
                for w in range(W):
                    y,rq,after,c=transition(np.broadcast_to(words[w],(2,120,4)),acc,den,q,True)
                    assert np.array_equal(after[:,4:],init[:,4:]);clips+=c
                    outputs[w]=y;requests[w]=rq;states[w+1]=after;acc=after
                stem=f'{seed}_{rate}'
                for suffix,array,key in (('q22',states,'state_bytes'),('outputs',outputs,'output_bytes'),('requests',requests,'request_bytes')):
                    q.charge(key,array.nbytes);array.tofile(out/f'{stem}_{suffix}.bin')
                counts.append({'seed':seed,'rate':rate,'state_clipped_components':clips})
                print('Completed',stem,'full120 actual/prefix', 'clips',clips,flush=True)
        guards(out,q);done=True
        write(out/'completed.json',{'completed':True,'new_paths':20,'new_codes':20*N,
             'front_learning_observations':20*N,'front_commits':20*W,'rear_learning_and_commits':0,
             'state_clips':counts,'new_source_conversions':0,'FFT':0})
    finally:q.report(out,'accounting_run.json',done)

def exact_target(q):
    q.charge('target_table_values',PERIOD)
    t=2048*(1+np.fromfile(OLD/'tone.bin',dtype='<f8'))
    ratios=[float(z).as_integer_ratio() for z in t];den=max(b for a,b in ratios)
    return [a*(den//b) for a,b in ratios],den

def pack(z):return {'exact':str(z),'value':float(z)}

def score(y,ti,den,t2,q):
    n=y.size;q.charge('score_absolute_word_inputs',n);q.charge('score_integer_word_products',n)
    q.charge('score_phase_inputs',n);q.charge('score_target_products',PERIOD);q.charge('score_scalar_formula_objects')
    yy=y.astype(np.int64).ravel();ph=yy.reshape(-1,PERIOD).sum(axis=0)
    td=sum(int(a)*b for a,b in zip(ph,ti))
    return F(int(np.sum(yy*yy)),n)-F(2*td,n*den)+t2

def pair(y,z,ti,den,rad,q):
    n=y.size;q.charge('score_pair_word_inputs',n);q.charge('score_integer_word_products',2*n)
    q.charge('score_phase_inputs',n);q.charge('score_target_products',PERIOD);q.charge('score_scalar_formula_objects')
    yy,zz=y.astype(np.int64).ravel(),z.astype(np.int64).ravel();d=yy-zz
    ph=d.reshape(-1,PERIOD).sum(axis=0)
    net=F(int(np.sum(d*(yy+zz))),n)-F(2*sum(int(a)*b for a,b in zip(ph,ti)),n*den)
    radius=2*rad*F(int(np.sum(abs(d))),n);power=F(int(np.sum(d*d)),n)
    return {**pack(net),'interval':list(map(str,(net-radius,net+radius))),
            'sign_certified':abs(net)>radius,'radius':str(radius),'power':str(power),'error_cross':str(net-power)}

def inspect(ys,ti,den,t2,rad,q):
    losses={k:pack(score(y,ti,den,t2,q)) for k,y in ys.items()}
    pairs={name:pair(ys[a],ys[b],ti,den,rad,q) for name,a,b in
           (('full_minus_held','full','held'),('full_minus_point','full','point'),('point_minus_held','point','held'))}
    for name,a,b in (('full_minus_held','full','held'),('full_minus_point','full','point'),('point_minus_held','point','held')):
        assert F(pairs[name]['exact'])==F(losses[a]['exact'])-F(losses[b]['exact'])
    assert F(pairs['full_minus_held']['exact'])==F(pairs['full_minus_point']['exact'])+F(pairs['point_minus_held']['exact'])
    return {'losses':losses,'pairs':pairs}

def verify(out):
    assert not (out/'results.json').exists()
    assert load(out/'completed.json')['completed'] and load(out/'preflight.json')['passed']
    q=Budget(load(out/'protocol.json')['verify_limits']);done=[]
    try:
        guards(out,q);ti,td=exact_target(q);rad=F(load(PHASE)['target_radius'])
        q.charge('target_table_square_products',PERIOD)
        t2=F(sum(z*z for z in ti),PERIOD*td*td)
        oldrows={(r['seed'],r['rate'],r['initialization']):r for r in load(POINT/'results.json')['rows']}
        for seed in SEEDS:
            q.charge('source_values',N*4);words=source(seed)
            for rate,den in (('base',1),('quarter',4)):
                stem=f'{seed}_{rate}';init=initial(seed,rate,q)
                q.charge('saved_new_output_values',2*N);outputs=np.fromfile(out/f'{stem}_outputs.bin',dtype='<i2').reshape(W,2,120)
                q.charge('saved_new_state_values',2*(W+1)*8);states=np.fromfile(out/f'{stem}_q22.bin',dtype='<i4').reshape(W+1,2,8).astype(np.int64)
                q.charge('saved_new_request_values',2*W*8);requests=np.fromfile(out/f'{stem}_requests.bin',dtype='<i4').reshape(W,2,8)
                assert np.array_equal(states[0],init)
                q.charge('saved_reference_output_values',4*N)
                point=np.memmap(POINT/f'{stem}_outputs.bin',dtype='<i2',mode='r',shape=(W,4,120))
                held=np.memmap(BASE/f'{stem}_outputs.bin',dtype='<i2',mode='r',shape=(W,4,120))
                for h,idx,name in ((0,0,'actual'),(1,2,'prefix')):
                    y,rq,after,c=transition(words,states[:-1,h],den,q,False)
                    assert np.array_equal(y,outputs[:,h]) and np.array_equal(rq,requests[:,h])
                    assert np.array_equal(after,states[1:,h]) and np.all(states[:,h,4:]==init[h,4:])
                    for w in (0,1024,2047):probe(words[w],states[w,h:h+1],states[w+1,h:h+1],outputs[w,h:h+1],requests[w,h:h+1],den,START+w,q)
                    ys={'full':outputs[:,h],'point':point[:,idx],'held':held[:,idx+1]}
                    total=inspect(ys,ti,td,t2,rad,q)
                    assert F(total['pairs']['point_minus_held']['exact'])==F(oldrows[seed,rate,name]['effects']['front_rear_held']['net_exact'])
                    blocks=[{'block':128+b,**inspect({k:v[b*256:(b+1)*256] for k,v in ys.items()},ti,td,t2,rad,q)} for b in range(8)]
                    for k in ys:assert F(total['losses'][k]['exact'])==sum(F(b['losses'][k]['exact']) for b in blocks)/8
                    for k in total['pairs']:assert F(total['pairs'][k]['exact'])==sum(F(b['pairs'][k]['exact']) for b in blocks)/8
                    kk=round_ratio(states[:,h],4096)
                    done.append({'seed':seed,'rate':rate,'initialization':name,'total':total,'blocks':blocks,
                         'initial_Q22':init[h].tolist(),'terminal_Q22':states[-1,h].tolist(),
                         'high_requested_components_nonzero':int(np.count_nonzero(requests[:,h,2:4])),
                         'high_export_changed_windows':int(np.count_nonzero(np.any(kk[:-1,2:4]!=kk[0,2:4],axis=1))),
                         'coefficient_export_min':kk.min(axis=0).tolist(),'coefficient_export_max':kk.max(axis=0).tolist(),
                         'state_clipped_components':c})
                    print(seed,rate,name,'full-held',total['pairs']['full_minus_held']['value'],
                          'full-point',total['pairs']['full_minus_point']['value'],flush=True)
        guards(out,q)
        write(out/'results.json',{'completed':True,'rows':done})
        write(out/'verification.json',{'passed':True,'cases':20,'blocks':160,'full_state_output_request_replay':True,
            'Fraction_and_formal_readouts_each':7200,'formal_front_bank_probes':60,'old_point_differences_exact':True,
            'new_generated_source_or_fft':0})
    finally:q.report(out,'accounting_verify.json',len(done)==20)

def check(out):
    assert not (out/'independent_check.json').exists()
    assert load(out/'verification.json')['passed']
    q=Budget(load(out/'protocol.json')['independent_limits']);count=0
    try:
        for path,z in load(out/'source_hashes.json').items():
            q.charge('source_manifest_bytes',Path(path).stat().st_size);assert digest(Path(path))==z,path
        ti,td=exact_target(q);tv=np.array(ti,dtype=object);rad=F(load(PHASE)['target_radius'])
        rows=load(out/'results.json')['rows']
        for r in rows:
            stem=f"{r['seed']}_{r['rate']}";h=0 if r['initialization']=='actual' else 1;idx=2*h
            q.charge('saved_output_values',3*N)
            yy={'full':np.memmap(out/f'{stem}_outputs.bin',dtype='<i2',mode='r',shape=(W,2,120))[:,h],
                'point':np.memmap(POINT/f'{stem}_outputs.bin',dtype='<i2',mode='r',shape=(W,4,120))[:,idx],
                'held':np.memmap(BASE/f'{stem}_outputs.bin',dtype='<i2',mode='r',shape=(W,4,120))[:,idx+1]}
            losses={k:[] for k in yy};radii={k:[] for k in r['total']['pairs']}
            for b in r['blocks']:
                q.charge('block_objects');j=b['block']-128
                vals={k:v[j*256:(j+1)*256].ravel() for k,v in yy.items()}
                for k,y in vals.items():
                    q.charge('direct_residual_word_inputs',PERIOD);q.charge('direct_bigint_products',2*PERIOD)
                    residual=y.astype(object)*td-tv
                    val=F(int(np.dot(residual,residual)),PERIOD*td*td)
                    assert str(val)==b['losses'][k]['exact'];losses[k].append(val)
                for name,a,c in (('full_minus_held','full','held'),('full_minus_point','full','point'),('point_minus_held','point','held')):
                    q.charge('pair_absolute_word_inputs',PERIOD)
                    rr=2*rad*F(int(np.sum(abs(vals[a].astype(np.int64)-vals[c]))),PERIOD)
                    val=losses[a][-1]-losses[c][-1]
                    assert list(map(str,(val-rr,val+rr)))==b['pairs'][name]['interval'];radii[name].append(rr)
                count+=1
            for k in yy:assert str(sum(losses[k])/8)==r['total']['losses'][k]['exact']
            for name,a,c in (('full_minus_held','full','held'),('full_minus_point','full','point'),('point_minus_held','point','held')):
                val=(sum(losses[a])-sum(losses[c]))/8;rr=sum(radii[name])/8
                assert list(map(str,(val-rr,val+rr)))==r['total']['pairs'][name]['interval']
        write(out/'independent_check.json',{'passed':True,'cases':20,'blocks':count,
              'direct_bigint_residual_squares_and_intervals_exact':True,'new_readouts_or_learning':0})
        summary={}
        for key in ('full_minus_held','full_minus_point','point_minus_held'):
            vals=[r['total']['pairs'][key] for r in rows]
            summary[key]={'positive':sum(F(z['exact'])>0 for z in vals),'negative':sum(F(z['exact'])<0 for z in vals),
                          'certified':sum(z['sign_certified'] for z in vals)}
        write(out/'summary.json',{'passed':True,'effects':summary,
              'high_request_nonzero_total':sum(r['high_requested_components_nonzero'] for r in rows),
              'high_export_changed_windows_total':sum(r['high_export_changed_windows'] for r in rows),
              'state_clipped_components_total':sum(r['state_clipped_components'] for r in rows)})
        print(json.dumps(load(out/'summary.json')),flush=True)
    finally:q.report(out,'accounting_independent.json',count==160)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','run','verify','check']);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    try:globals()[args.mode](args.out)
    except Exception:
        if args.out.exists():write(args.out/f'failure_{args.mode}.json',{'traceback':traceback.format_exc()})
        raise
