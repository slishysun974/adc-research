"""EXP-072: finite, paired diagnostic of the unchanged Gu candidate.

The four branches are explanatory interventions, never an online proposal.
Targets enter scoring only. Source data and original experiments are read-only.
"""
import argparse
from dataclasses import replace
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys
import traceback
import numpy as np

ROOT = Path('D:/ADC')
sys.path[:0] = [str(ROOT/'src'), str(ROOT)]
from adc_research.theory.static_fixed_contract import readout, export, commit, nearest_even
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.fixed_four_lane_window import _bank, FourLaneConversion
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState
from adc_research.calibration.observation import DigitalCalibrationSample
from experiments.exp_060_static_auxiliary_preflight.run import fixed_setup, plant, check_physical
from adc_research.evaluation.observations import digital_sample
from experiments.exp_062_same_input_background.verify import digital, round_ratio

OLD = ROOT/'artifacts/runs/EXP_062/background_v1'
NEW = ROOT/'artifacts/runs/EXP_069/background_v1'
EXP = ROOT/'experiments/exp_072_normal_state_intervention'
RUN = ROOT/'artifacts/runs/EXP_072/finite_v1'
N, BW, START, STOP = 30720, 256, 128*256, 136*256
SEEDS = list(range(202610621,202610626))
BRANCHES = ['actual_continue','actual_hold','prefix_continue','prefix_hold']
FACTORS = np.array([-2,-6,-12,-24,-32,-96,-192,-384],dtype=np.int64)

def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,d): p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def digest(p):
    h=sha256()
    with p.open('rb') as f:
        for s in iter(lambda:f.read(4*1024*1024),b''):h.update(s)
    return h.hexdigest()
def relative(p): return p.relative_to(ROOT).as_posix()
def guard(manifest):
    for name,value in manifest.items():assert digest(ROOT/name)==value,name

def exact_source(x,d1=1,d2=1):
    """Rational polynomial source, independent of float platform."""
    thresholds=[F(-7,8)+F(j,4) for j in range(8)]
    quant=lambda v:sum(v>=t for t in thresholds)-4
    q1=quant(x);z1=4*(x-F(q1,4)+F(d1,32))
    m=F(39,40)*z1-F(11,200)*z1**3
    q2=quant(m);z2=4*(m-F(q2,4)+F(d2,32))
    r=F(49,50)*z2-F(1,25)*z2**3
    assert -1<x<1 and abs(z1)<=1 and -1<m<1 and abs(z2)<=1 and -1<r<1
    return (q1,q2,(128*(r+1)).numerator//(128*(r+1)).denominator-128,d1,d2), (z1,m,z2,r)

def capability():
    """Physical current-target ambiguity after an identical arbitrary prefix."""
    xs=[F(1,4096)-F(1,65536),F(1,4096)+F(1,65536)]
    words=[exact_source(x)[0] for x in xs]
    assert words[0]==words[1]==(0,0,76,1,1)
    coeffs=[(1100,1024,1024,1024,1024,1024,1024,1024),
            (1102,1024,1024,1024,1024,1024,1024,1024)]
    outputs=[nearest_even(readout(0,0,F(76),1,1,tuple(F(k,1024) for k in c),data_q3=True).output) for c in coeffs]
    assert outputs==[2048,2049]
    targets=[2048*(1+x) for x in xs]
    losses=[[(F(y)-t)**2 for y in outputs] for t in targets]
    assert losses==[[F(225,1024),F(289,1024)],[F(289,1024),F(225,1024)]]
    assert losses[0][1]-losses[0][0]==losses[1][0]-losses[1][1]==F(1,16)
    # Same prefix including its tags, seed and any causal state; only last x changes.
    # Policy randomness is coupled. The current word is also identical.
    # For arbitrary integer output the two squared losses have average >=257/1024.
    for y in range(2046,2052):
        avg=sum((F(y)-t)**2 for t in targets)/2
        assert avg>=F(257,1024)
    pipeline,cfg=fixed_setup(load(OLD/'source_protocol.json'))
    case=next(c for c in load(OLD/'protocol.json')['cases'] if c['name']=='both_smooth')
    for x in xs:
        original=plant(float(x),1,1,case,pipeline,0);check_physical(original)
        obs=digital_sample(original.pipeline)
        assert (obs.stage1_symbol,obs.stage2_symbol,obs.backend_centered_code)==words[0][:3]
    for c,y in zip(coeffs,outputs):
        cascade=replace(cfg.cascade,stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=c[:4]),
                        stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=c[4:]))
        actual=correct_two_stage_fixed_observed(DigitalCalibrationSample(0,0,76,1,1),cascade)
        assert nearest_even(F(actual.unclipped_output_scaled,8))==y
    return {'x':[str(x) for x in xs],'targets':[str(t) for t in targets],
        'word':words[0],'coefficients_q1_10':coeffs,'outputs':outputs,
        'loss_matrix':[[str(v) for v in row] for row in losses],
        'deterministic_worst_regret':'1/16','randomized_minimax_regret':'1/32',
        'randomized_minimax_mse':'257/1024','clairvoyant_mse':'225/1024',
        'physical_platform_probes':2,'formal_fixed_readouts':2,
        'scope':'Same declared smooth model, noiseless arbitrary causal input in [-0.82,0.82]; prefix identical. Does not claim ambiguity for a known sinusoid/phase or the original tone record.'}

def prepare():
    assert not EXP.exists() and not RUN.exists(),'Refuse overwrite'
    EXP.mkdir(parents=True);RUN.mkdir(parents=True)
    shutil.copyfile(Path(__file__),EXP/'run.py')
    protocol={
        'version':'EXP-072-normal-state-intervention-v1','date':'2026-10-12','authority':'D-136; user asks to continue approved plan',
        'cases':['both_smooth'],'seeds':SEEDS,'rates':{'base':1,'quarter':4},'method':'point30',
        'prefix_blocks':[120,128],'evaluation_blocks':[128,136],'window_start':START,'window_stop':STOP,
        'branches':BRANCHES,'initialization':'actual window-start Q22; or coordinate-wise nearest-even average of EXPORTED Q1.10 over preceding 2048 window starts, embedded as code*4096. Prefix stops before evaluation; no target or future states in initialization.',
        'contract':'Original five fields,Q22,Q1.10,Q3,nearest-even,saturation,4 selected slots*30,120 old-state outputs,simultaneous banks. Baseline continued exactly. Held branches suppress both updates only. Prefix continued recomputes all gates,products,requests and future states.',
        'source_condition':'Static physical words and counter tags independent of digital coefficients; identical old words reused for every branch. Global indices preserved.',
        'target':'Original 2048*(1+tone.bin),binary64 real level,offline only; final output integer. MSE/DC/error power only, no FFT.',
        'predictions':['Baseline outputs and every Q22 transition equal saved EXP062/069',
            'If continuing increases MSE at both initializations in each paired path, it supports harmful continuation over THIS interval; reversed or seed-dependent signs restrict that statement',
            'Prefix-hold versus actual-hold isolates initial-state location under fixed future readout; no preset universal benefit',
            'Continuation effect depending on initialization requires interaction, not additive unique contributions',
            'Physical equal-word control has opposite preference between two legal static states even with identical full causal prefix'],
        'budget':{'long_new_axes':0,'source_words_read':5*2048*120,'prefix_state_vectors_read':10*2048,
            'all_diagnostic_readouts':40*2048*120,'reused_baseline_readouts':10*2048*120,
            'new_intervention_readouts':30*2048*120,'active_diagnostic_windows':20*2048,
            'new_intervention_active_windows':10*2048,'new_intervention_learning_per_stage':10*2048*4,
            'source_adc_conversions':0,'capability_source_probes':2,'preflight_windows_per_pair':2,
            'rational_probe_windows_per_branch':3,'fft':0},
        'verification':'Preflight2 windows/all seeds/rates/branches. Full baseline output/state equality. Replay every saved branch output/request/state. Exact Fraction and formal fixed core at local windows0,1024,2047 (all120 codes); active fixed bank commits separately. Prefix rounding exact rational. No full physical source regeneration.',
        'stopping':'Fixed endpoint136; all seeds reported. No extension,performance-selected initial state,extra rate or parameter repair. Failed runs remain.',
        'capability_family':'Exact same smooth coefficients, but arbitrary causal unknown input in [-.82,.82] and identical prior history. Does NOT establish an online bound for the known coherent sine in the normal diagnostic.',
        'limits':'Seen mechanism conditions; diagnostic reset/hold is not a new algorithm. Causal effect conditional on this intervention,reference,prefix,window; no general convergence or unique total-error attribution. Future6007/8009 untouched.'}
    write(EXP/'protocol.json',protocol);write(RUN/'protocol.json',protocol)
    expected={}
    for folder,names in [(OLD,['tone.bin','protocol.json','source_protocol.json']), (NEW,['protocol.json'])]:
        manifest=load(folder/'delivery_hashes.json')
        for seed in SEEDS:
            stem=f'both_smooth_{seed}'
            if folder==OLD:names += [stem+'_words.bin',stem+'_outputs.bin',stem+'_point30_q22.bin']
            else:names += [stem+'_outputs.bin',stem+'_quarter_point30_q22.bin',stem+'.json']
        for name in names:expected[relative(folder/name)]=manifest[name]
    write(RUN/'original_data_hashes.json',expected);guard(expected)
    sources=list((ROOT/'src/adc_research').rglob('*.py'))+list((ROOT/'experiments').rglob('*.py'))
    write(RUN/'execution_hashes.json',{relative(p):digest(p) for p in sources})
    shutil.copyfile(EXP/'run.py',RUN/'frozen_run.py')
    write(RUN/'verification_execution_hashes.json',load(RUN/'execution_hashes.json'))
    docs=['docs/STATUS.md','docs/DECISIONS.md','docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md',
          'docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md','docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md',
          'docs/theory/README.md','docs/reports/GU_ALGORITHM_EVALUATION_V1.md','docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
          'docs/reports/experiments/README.md','docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md']
    for name in docs:
        dest=RUN/'documents_before'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
    (EXP/'README.md').write_text('# EXP-072：正常状态位置与后续更新的有限干预\n\nD-136授权内的机制诊断；不是新算法。固定平滑场景、原五种子、两倍率、前缀120—127块与评价128—135块。四分支及全部预算见[协议](protocol.json)，推导与结果见[报告](../../docs/reports/experiments/EXP_072_NORMAL_STATE_INTERVENTION_V1.md)。\n\n从仓库根目录运行：`python experiments/exp_072_normal_state_intervention/run.py prepare`，继而`run`与`verify`。目录已存在时prepare拒绝覆盖；run和verify依次要求前一状态验收。\n',encoding='utf-8')
    print('Frozen original files',len(expected),'execution sources',len(sources),flush=True)

def old_data(seed,rate):
    stem=f'both_smooth_{seed}'
    words=np.memmap(OLD/(stem+'_words.bin'),dtype='i1',mode='r',shape=(65536,120,4))
    if rate=='base':
        state=np.memmap(OLD/(stem+'_point30_q22.bin'),dtype='<f8',mode='r',shape=(65537,8))
        states=(state[120*256:STOP+1]*(1<<22)).astype(np.int64)
        outputs=np.memmap(OLD/(stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(65536,120,3))[START:STOP,:,1]
    else:
        state=np.memmap(NEW/(stem+'_quarter_point30_q22.bin'),dtype='<i4',mode='r',shape=(65537,8))
        states=np.asarray(state[120*256:STOP+1],dtype=np.int64)
        outputs=np.memmap(NEW/(stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(65536,120,6))[START:STOP,:,0]
    actual=states[2048].copy();hidden=states[:2048]
    codes=round_ratio(hidden,4096)
    prefix=round_ratio(codes.sum(axis=0),2048)*4096
    assert all(int(v)==nearest_even(sum((F(int(k),2048) for k in codes[:,i]),F(0)))*4096 for i,v in enumerate(prefix))
    return words[START:STOP],states[2048:],outputs,actual,prefix

def transition(words,acc,den):
    y,g,s,products=digital(np.broadcast_to(words,(4,120,4)),acc)
    request=round_ratio(products[:,:4].sum(axis=1)*FACTORS*30,125*den)
    request[[1,3]]=0
    return y,request,np.clip(acc+request,0,2047*4096),g,s

def probe(words,acc,after,y,requests,den,global_window):
    _,cfg=fixed_setup(load(OLD/'source_protocol.json'))
    scalar_counts=0;bank_counts=0
    for h in range(4):
        old=tuple(map(int,acc[h]));ks=tuple(F(k,1024) for k in export(old))
        casc=replace(cfg.cascade,stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=export(old)[:4]),
                     stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=export(old)[4:]))
        conversions=[];values=[[],[]];sums=[F(0)]*8
        for j,row in enumerate(words):
            q1,q2,be,bits=map(int,row);d1=2*(bits&1)-1;d2=2*((bits>>1)&1)-1
            sample=DigitalCalibrationSample(q1,q2,be,d1,d2)
            conversions.append(FourLaneConversion(120*global_window+j,j%4,sample))
            rd=readout(q1,q2,F(be),d1,d2,ks,data_q3=True)
            core=correct_two_stage_fixed_observed(sample,casc)
            assert core.unclipped_output_scaled==8*rd.output
            assert core.stage1_raw_scaled==8*rd.raw1
            assert nearest_even(rd.output)==int(y[h,j])
            assert 0<=rd.output<=4095,'Q3 saturation encountered'
            for b,(dd,yy) in enumerate(((d1,rd.y1),(d2,rd.y2))):
                values[b].append((512*dd if b==0 else 128*dd,int(8*yy)))
                if j<4:
                    for i,gate in enumerate(rd.gates[b]):sums[4*b+i]+=(64 if b==0 else 16)*dd*yy*gate
            scalar_counts+=1
        if h in (0,2):
            steps=tuple(mu/den for mu in cfg.stage1_lms.step_sizes+cfg.stage2_lms.step_sizes)
            rq,aft=commit(old,tuple(sums),30,steps)
            assert rq==tuple(map(int,requests[h])) and aft==tuple(map(int,after[h]))
            for b,bcfg in enumerate((cfg.stage1_lms,cfg.stage2_lms)):
                bs=FixedGatedLmsState(old[4*b:4*b+4],(0,)*4,(0,)*4,(0,)*4,120*global_window)
                out=_bank(bs,replace(bcfg,step_sizes=tuple(mu/den for mu in bcfg.step_sizes)),
                          conversions,values[b],tuple(j<4 for j in range(120)),30)
                assert out.requested_deltas==rq[4*b:4*b+4]
                assert out.state.accumulator_codes==aft[4*b:4*b+4];bank_counts+=1
        else:assert np.array_equal(after[h],acc[h]) and not requests[h].any()
    return scalar_counts,bank_counts

def run():
    assert not (RUN/'results.json').exists(),'Refuse completed run overwrite'
    guard(load(RUN/'original_data_hashes.json'));guard(load(RUN/'execution_hashes.json'))
    cap=capability();write(RUN/'capability.json',cap)
    preflight=[]
    for seed in SEEDS:
        for rate,den in [('base',1),('quarter',4)]:
            words,old,old_y,actual,prefix=old_data(seed,rate)
            acc=np.stack((actual,actual,prefix,prefix))
            for w in range(2):
                y,rq,aft,g,s=transition(words[w],acc,den)
                assert np.array_equal(y[0],old_y[w]) and np.array_equal(aft[0],old[w+1])
                probe(words[w],acc,aft,y,rq,den,START+w);acc=aft
            preflight.append({'seed':seed,'rate':rate,'passed':True})
    write(RUN/'preflight.json',{'passed':True,'pairs':preflight,'rational_and_formal_readouts':9600,
          'formal_bank_commits':80,'active_windows':40,'new_intervention_learning_per_stage':80})
    print('Preflight passed10 pairs,2 windows,4 branches',flush=True)
    tone=np.fromfile(OLD/'tone.bin',dtype='<f8');target=np.tile(2048*(1+tone),8)
    rows=[]
    for seed in SEEDS:
        for rate,den in [('base',1),('quarter',4)]:
            words,old,old_y,actual,prefix=old_data(seed,rate)
            stem=f'{seed}_{rate}'
            acc=np.stack((actual,actual,prefix,prefix))
            states=np.empty((2049,4,8),dtype='<i4');states[0]=acc
            out=np.empty((2048,4,120),dtype='<i2');rq_all=np.empty((2048,4,8),dtype='<i4')
            clips=0;gate_counts=np.zeros((2,8),dtype=np.int64)
            for w in range(2048):
                y,rq,aft,g,s=transition(words[w],acc,den)
                assert np.array_equal(y[0],old_y[w]) and np.array_equal(aft[0],old[w+1]),(stem,w)
                clips+=int(np.count_nonzero((acc+rq<0)|(acc+rq>2047*4096)))
                assert np.all((y>=0)&(y<=4095))
                out[w]=y;rq_all[w]=rq;states[w+1]=aft
                gate_counts+=g[[0,2],:4].sum(axis=1);acc=aft
            out.tofile(RUN/(stem+'_outputs.bin'));states.tofile(RUN/(stem+'_q22.bin'));rq_all.tofile(RUN/(stem+'_requests.bin'))
            losses=[];dc=[];block_losses=[]
            for h in range(4):
                error=out[:,h].ravel().astype(float)-target
                losses.append(float(np.mean(error*error)));dc.append(float(error.mean()))
                block_losses.append(np.mean((error.reshape(8,N))**2,axis=1).tolist())
            a,b,c,d=losses
            rows.append({'seed':seed,'rate':rate,'mse':dict(zip(BRANCHES,losses)),
                'dc':dict(zip(BRANCHES,dc)),'block_mse':dict(zip(BRANCHES,block_losses)),
                'initial_q22':{'actual':actual.tolist(),'prefix':prefix.tolist()},
                'continued_minus_held_actual':a-b,'continued_minus_held_prefix':c-d,
                'prefix_minus_actual_held':d-b,'prefix_minus_actual_continued':c-a,
                'interaction':(c-d)-(a-b),'coefficient_clips':clips,'selected_gate_counts':gate_counts.tolist()})
            print(stem,'MSE',dict(zip(BRANCHES,losses)),flush=True)
    write(RUN/'results.json',{'rows':rows,'capability':cap,'completed':True})
    guard(load(RUN/'original_data_hashes.json'));guard(load(RUN/'execution_hashes.json'))

def verify():
    assert load(RUN/'preflight.json')['passed']
    data=load(RUN/'results.json');tone=np.fromfile(OLD/'tone.bin',dtype='<f8');target=np.tile(2048*(1+tone),8)
    probes=banks=0
    for row in data['rows']:
        seed,rate=row['seed'],row['rate'];den=1 if rate=='base' else 4;stem=f'{seed}_{rate}'
        words,old,old_y,actual,prefix=old_data(seed,rate)
        states=np.fromfile(RUN/(stem+'_q22.bin'),dtype='<i4').reshape(2049,4,8).astype(np.int64)
        out=np.fromfile(RUN/(stem+'_outputs.bin'),dtype='<i2').reshape(2048,4,120)
        requests=np.fromfile(RUN/(stem+'_requests.bin'),dtype='<i4').reshape(2048,4,8)
        assert np.array_equal(states[0],np.stack((actual,actual,prefix,prefix)))
        for h in range(4):
            y,g,s,p=digital(words,states[:-1,h])
            assert np.array_equal(y,out[:,h])
            rq=round_ratio(p[:,:4].sum(axis=1)*FACTORS*30,125*den) if h in (0,2) else np.zeros((2048,8),dtype=np.int64)
            assert np.array_equal(rq,requests[:,h])
            assert np.array_equal(np.clip(states[:-1,h]+rq,0,2047*4096),states[1:,h])
            err=y.ravel().astype(float)-target
            assert abs(float(np.mean(err*err))-row['mse'][BRANCHES[h]])<1e-12
        assert np.array_equal(out[:,0],old_y) and np.array_equal(states[:,0],old)
        for w in (0,1024,2047):
            p,b=probe(words[w],states[w],states[w+1],out[w],requests[w],den,START+w);probes+=p;banks+=b
        a,b,c,d=[row['mse'][name] for name in BRANCHES]
        assert abs((c-a)-(d-b)-row['interaction'])<1e-12
    assert json.loads(json.dumps(capability()))==load(RUN/'capability.json')
    guard(load(RUN/'original_data_hashes.json'));guard(load(RUN/'verification_execution_hashes.json'))
    assert digest(RUN/'frozen_run.py')==load(RUN/'execution_hashes.json')[relative(EXP/'run.py')]
    counts={'all_readouts_replayed':9830400,'baseline_saved_codes_equal':2457600,
        'baseline_state_transitions_equal':20480,'all_state_transitions_replayed':81920,
        'active_request_transitions_replayed':40960,'new_intervention_learning_per_stage':81920,
        'new_intervention_state_transitions':20480,'new_intervention_outputs':7372800,
        'rational_and_formal_probe_readouts':probes,'formal_bank_commits':banks,
        'preflight_probe_readouts':9600,'preflight_formal_bank_commits':80,
        'preflight_new_intervention_learning_per_stage':80,'preflight_output_codes':9600,
        'capability_exact_source_evaluations':2,'capability_platform_probes_total_two_calls':4,
        'capability_formal_readouts_total_two_calls':4,'fft':0,'new_long_axes':0,
        'original_source_files':len(load(RUN/'original_data_hashes.json')),
        'execution_sources':len(load(RUN/'execution_hashes.json'))}
    write(RUN/'verification.json',{'passed':True,'counts':counts,'coefficient_clips':sum(r['coefficient_clips'] for r in data['rows']),
        'future_holdout_used':False,'new_algorithm':False,'full_physical_regeneration':False,
        'scope':'Complete vector digital replay; exact rational/formal core only at prespecified probes. Baseline all states/codes equal old records; no FFT/physical generalization.'})
    write(RUN/'delivery_hashes.json',{p.name:digest(p) for p in RUN.iterdir() if p.is_file() and p.name!='delivery_hashes.json'})
    print(json.dumps(load(RUN/'verification.json')),flush=True)

if __name__=='__main__':
    action=argparse.ArgumentParser();action.add_argument('mode',choices=['prepare','run','verify'])
    mode=action.parse_args().mode
    try:globals()[mode]()
    except Exception:
        if RUN.exists():write(RUN/(mode+'_failure.json'),{'traceback':traceback.format_exc()})
        raise
