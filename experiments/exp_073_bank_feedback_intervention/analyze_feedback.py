"""Read-only follow-up to EXP073: requests, gates, history and signed loss.

No new trajectory or learning is executed. Four current-window evaluations
decompose the existing two front histories at moving/held rear states.
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
from experiments.exp_073_bank_feedback_intervention.run import evaluate,probe,fixed_setup,round_ratio,pwl_scaled
from adc_research.theory.static_fixed_contract import readout,export,nearest_even
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.observation import DigitalCalibrationSample
OLD=ROOT/'artifacts/runs/EXP_062/background_v1'
BASE=ROOT/'artifacts/runs/EXP_072/finite_v1'
NEW=ROOT/'artifacts/runs/EXP_073/bank_feedback_v1'
PHASE=ROOT/'artifacts/research/normal_future_readout_20261013_v1/phase_certificate.json'
N,W,START=30720,2048,128*256;SEEDS=list(range(202610621,202610626))
FACT=np.array([-2,-6,-12,-24],dtype=np.int64)

def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4194304),b''):h.update(b)
    return h.hexdigest()
def guard(m):
    for p,h in m.items():assert digest(Path(p))==h,p

def controls():
    # A gate toggle is not interchangeable with a small continuous signal step.
    assert (2-1)*0+2*(1-0)==2*1-1*0
    assert (2-1)*1+1*(1-0)==2*1-1*0
    # Current low request denominators reduce to25; the 24/25 bound is attained
    # by two integer numerators. These are arithmetic controls, not source data.
    a,b=F(-288,25),F(-2112,25)
    assert (nearest_even(b)-nearest_even(a))-(b-a)==F(24,25)
    _,cfg=fixed_setup(load(OLD/'source_protocol.json'));details=[]
    for be,q2,coeffs in [(80,0,[(1047,)+(1024,)*7,(1033,)+(1024,)*7]),
                         (80,1,[(1024,)*8,(1024,)*4+(992,1024,1024,1024)])]:
        outputs=[];ys=[];gates=[]
        for codes in coeffs:
            rd=readout(0,q2,F(be),1,1,tuple(F(k,1024) for k in codes),data_q3=True)
            cc=replace(cfg.cascade,stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=codes[:4]),
                       stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=codes[4:]))
            formal=correct_two_stage_fixed_observed(DigitalCalibrationSample(0,q2,be,1,1),cc)
            assert formal.unclipped_output_scaled==8*rd.output
            outputs.append(nearest_even(rd.output));ys.append(str(rd.y1));gates.append(list(rd.gates[0]))
        details.append({'word':[0,q2,be,1,1],'codes':coeffs,'outputs':outputs,'learning_y1':ys,'front_gates':gates})
    assert details[0]['outputs']==[2050,2048]
    assert F(2050-2048)-F(64*(1047-1033),1024)==F(9,8)
    assert details[1]['learning_y1']==['128','127']
    assert details[1]['front_gates'][0][1] and not details[1]['front_gates'][1][1]
    assert nearest_even(F(-6*30*4*64*128,125))==-47186
    return {'passed':True,'request_rounding_difference_sharp_bound':'24/25',
            'final_code_gap_remainder_sharp_bound':'9/8','legal_digital_controls':details,
            'formal_and_rational_readouts_each':4,'physical_source_probes':0,
            'scope':'Controls of digital arithmetic; not new physical source evidence or trajectories.'}

def prepare(out):
    assert not out.exists(),'Refuse analysis overwrite'
    assert load(NEW/'verification.json')['passed']
    out.mkdir(parents=True)
    files=[OLD/'tone.bin',OLD/'source_protocol.json',NEW/'protocol.json',NEW/'results.json',NEW/'verification.json',PHASE]
    for seed in SEEDS:
        files.append(OLD/f'both_smooth_{seed}_words.bin')
        for rate in ('base','quarter'):
            stem=f'{seed}_{rate}'
            files.extend(BASE/f'{stem}_{s}.bin' for s in ('q22','outputs','requests'))
            files.extend(NEW/f'{stem}_{s}.bin' for s in ('q22','outputs','requests','candidate_requests','bridge_outputs'))
    write(out/'source_hashes.json',{str(p):digest(p) for p in files})
    sources=list((ROOT/'src/adc_research').rglob('*.py'))+list((ROOT/'experiments').rglob('*.py'))
    write(out/'execution_hashes.json',{str(p):digest(p) for p in sources})
    shutil.copyfile(Path(__file__),out/'frozen_analysis.py')
    protocol={'date':'2026-10-13','authority':'D136/D137; current STATUS next and user continue research',
       'object':'All5 original seeds, rates1 and1/4, actual/prefix initializations, unchanged [128,136), 20 cases40960 windows; EXP072/073 immutable trajectories',
       'corners':['A joint front/moving rear','B front-only front/held rear','C front-only front/moving rear','D joint front/held rear'],
       'question':'Separate rear forcing at fixed front from response of already different front states; identify signal/gate/request-rounding channels and connect history gap to signed mediated MSE.',
       'method':'Current selected4 candidate requests for four corners; no submission. A/B matched existing requests, C matched existing bridge codes. D evaluated over all120 solely to certify digital domain and alternative request order. Complete common-moving-rear basis for actual-vs-bridge final-code gap.',
       'target':'Original binary64 target only in offline exact scoring. Online Gu, branches and original score/holdout unchanged.',
       'predictions':['Exact request forcing+response equals saved request difference and its cumulative sum equals every saved Q22 state gap',
          'The first low gate is always open, so only the second/higher gate can transmit gate-switch forcing',
          'Rare switches can contribute large second-low requests, but per-step components do not by themselves give causal MSE percentages',
          'Larger absolute coefficient/code gaps do not determine loss sign; reference-error cross can dominate nonnegative displacement power',
          'If the continuous parameter-gap reference changes loss sign or rounding residual is substantial, do not claim current output rounding is secondary',
          'Alternative forcing/response and product orders are preserved; nonzero interaction restricts uniqueness'],
       'budget':{'new_trajectories_learning_submissions_source_conversions_fft':0,
          'corners_front_request_vectors':163840,'A_B_C_selected_integer_readouts':491520,
          'D_full_integer_readouts':4915200,'additional_full_probe_integer_readouts':21600,
          'all_kernel_integer_readouts':5428320,'kernel_gate_support_product_components_each':43426560,
          'common_rear_pwl_evaluations':4915200,'continuous_gap_evaluations':4915200,
          'formal_and_rational_readouts_each_including_controls':28804,'formal_front_candidate_request_probes':240},
       'validation':'Arithmetic endpoint/gate controls; every A/B selected code/request and C selected bridge code matched. All saved state gaps and request cumulative sums exact. Fixed local windows0,1024,2047 all120/four-corner independent Fraction+formal readout and front-bank candidate probes. Exact dyadic loss/basis/residual decompositions all20, both request/product orders.',
       'stop':'No new horizon,seed,model,optimization,branch or algorithm. All20 reported, source/hash mismatch or invalid corner domain stops and remains archived.',
       'limits':'Forcing/response and signal/gate are same-window algebra conditional to existing histories, not independent causal gate interventions. Continuous parameter-gap score is an offline difference reference, not a legal integer optimizer or removal of learning-history quantization.'}
    write(out/'protocol.json',protocol);write(out/'controls.json',controls())
    for name in ['docs/STATUS.md','docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md',
                 'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md','docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
                 'docs/theory/README.md','docs/reports/GU_ALGORITHM_EVALUATION_V1.md',
                 'docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md','docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md',
                 'docs/reports/experiments/EXP_073_BANK_FEEDBACK_INTERVENTION_V1.md','experiments/exp_073_bank_feedback_intervention/README.md']:
        dst=out/'documents_before'/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dst)
    print('Frozen all20 request/history cases; exact digital endpoint and gate controls passed',flush=True)

def scaled_sum(values):
    values=np.asarray(values,dtype=np.int64)
    # Guard each integer reduction before using NumPy's signed accumulator.
    assert int(np.max(np.abs(values),initial=0))*values.size < (1<<63)
    return int(np.sum(values,dtype=np.int64))
def reference_score(num,y,targetints,D):
    num=num.ravel().astype(np.int64);y=y.ravel().astype(np.int64);count=len(num);scale=8192
    power=F(scaled_sum(num*num),count*scale*scale)
    phase=num.reshape(8,N).sum(axis=0)
    cross=F(2*scaled_sum(y*num),count*scale)-F(2*sum(int(s)*int(a) for s,a in zip(phase,targetints)),count*scale*D)
    return power,cross
def moment(v,D=1):
    v=np.asarray(v,dtype=np.int64)
    return {'mean':float(F(scaled_sum(v),len(v)*D)),
            'abs_mean':float(F(scaled_sum(np.abs(v)),len(v)*D)),
            'rms':float(np.sqrt(np.mean(v.astype(float)**2))/D),
            'sum_exact':str(F(scaled_sum(v),D)),'max_abs':float(F(int(np.max(np.abs(v),initial=0)),D))}

def analyze(out):
    assert not (out/'results.json').exists(),'Refuse completed analysis overwrite'
    assert digest(Path(__file__))==digest(out/'frozen_analysis.py')
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    target=2048*(1+np.fromfile(OLD/'tone.bin',dtype='<f8'))
    ratios=[float(v).as_integer_ratio() for v in target];TD=max(b for _,b in ratios)
    ti=[a*(TD//b) for a,b in ratios];rad=F(load(PHASE)['target_radius'])
    oldrows={(r['seed'],r['rate'],r['initialization']):r for r in load(NEW/'results.json')['rows']}
    rows=[];sc=4;bank=0
    for seed in SEEDS:
        words=np.memmap(OLD/f'both_smooth_{seed}_words.bin',dtype='i1',mode='r',shape=(65536,120,4))[START:START+W]
        for rate,den in (('base',1),('quarter',4)):
            stem=f'{seed}_{rate}'
            ast=np.fromfile(BASE/f'{stem}_q22.bin',dtype='<i4').reshape(W+1,4,8).astype(np.int64)
            bst=np.fromfile(NEW/f'{stem}_q22.bin',dtype='<i4').reshape(W+1,4,8).astype(np.int64)
            ay=np.fromfile(BASE/f'{stem}_outputs.bin',dtype='<i2').reshape(W,4,120)
            by=np.fromfile(NEW/f'{stem}_outputs.bin',dtype='<i2').reshape(W,4,120)
            cy=np.fromfile(NEW/f'{stem}_bridge_outputs.bin',dtype='<i2').reshape(W,2,120)
            ar=np.fromfile(BASE/f'{stem}_requests.bin',dtype='<i4').reshape(W,4,8)
            br=np.fromfile(NEW/f'{stem}_requests.bin',dtype='<i4').reshape(W,4,8)
            for h,init in ((0,'actual'),(2,'prefix')):
                A=ast[:-1,h];B=bst[:-1,h]
                C=np.column_stack((B[:,:4],A[:,4:]));DD=np.column_stack((A[:,:4],B[:,4:]))
                av=evaluate(words[:,:4],A);bv=evaluate(words[:,:4],B);cv=evaluate(words[:,:4],C);dv=evaluate(words,DD)
                vals=[av,bv,cv,dv];corners=[A,B,C,DD]
                assert np.array_equal(av[0],ay[:,h,:4]) and np.array_equal(bv[0],by[:,h,:4])
                assert np.array_equal(cv[0],cy[:,h//2,:4])
                sums=[v[3][:,:4,:4].sum(axis=1) for v in vals]
                rq=[round_ratio(s*FACT*30,125*den) for s in sums]
                ra,rb,rc,rd=rq
                assert np.array_equal(ra,ar[:,h,:4]) and np.array_equal(rb,br[:,h,:4])
                state_gap=ast[:,h,:4]-bst[:,h,:4]
                assert not state_gap[0].any() and np.array_equal(np.diff(state_gap,axis=0),ra-rb)
                E,S=rc-rb,ra-rc;Ea,Sa=ra-rd,rd-rb;J=ra-rd-rc+rb
                assert np.array_equal(E+S,ra-rb) and np.array_equal(Ea+Sa,ra-rb)
                assert np.array_equal(np.cumsum(E+S,axis=0),state_gap[1:])
                assert np.array_equal(Ea-E,J) and np.array_equal(S-Sa,J)
                bits=words[:,:4,3].astype(np.int64);d=2*(bits&1)-1
                yb,yc,yA,yD=[v[5][:,:4] for v in (bv,cv,av,dv)]
                gb,gc,gA,gD=[v[1][:,:4,:4].astype(np.int64) for v in (bv,cv,av,dv)]
                read=(8*d[:,:,None]*(yc-yb)[:,:,None]*gb).sum(axis=1)
                gate=(8*d[:,:,None]*yc[:,:,None]*(gc-gb)).sum(axis=1)
                read_alt=(8*d[:,:,None]*(yA-yD)[:,:,None]*gD).sum(axis=1)
                gate_alt=(8*d[:,:,None]*yA[:,:,None]*(gA-gD)).sum(axis=1)
                assert np.array_equal(read+gate,sums[2]-sums[1])
                assert np.array_equal(read_alt+gate_alt,sums[0]-sums[3])
                assert not (gc-gb)[:,:,0].any() and not (gA-gD)[:,:,0].any()
                Q=125*den;signal_num=read*FACT*30;gate_num=gate*FACT*30
                round_num=E*Q-signal_num-gate_num
                signal_alt_num=read_alt*FACT*30;gate_alt_num=gate_alt*FACT*30
                round_alt_num=Ea*Q-signal_alt_num-gate_alt_num
                assert np.all(np.abs(round_num)*25<=24*Q) and np.all(np.abs(round_alt_num)*25<=24*Q)
                for w in (0,1024,2047):
                    vfull=evaluate(np.broadcast_to(words[w],(3,120,4)),np.stack((A[w],B[w],C[w])))
                    full_y=np.concatenate((vfull[0],dv[0][w:w+1]))
                    front_mask=np.array([[1,1,1,1,0,0,0,0]]*4,dtype=np.int64)
                    requested=np.column_stack((np.stack([r[w] for r in rq]),np.zeros((4,4),dtype=np.int64)))
                    acc=np.stack([a[w] for a in corners]);after=np.clip(acc+requested,0,2047*4096)
                    ss,bb=probe(words[w],acc,after,full_y,requested,den,front_mask,START+w);sc+=ss;bank+=bb
                K=round_ratio(A[:,:4],4096)-round_ratio(B[:,:4],4096)
                assert not K[:,2:].any()
                assert np.all(np.abs(K.astype(float)-state_gap[:-1]/4096)<=1)
                q2=words[:,:,1].astype(np.int64);be=words[:,:,2].astype(np.int64);db=words[:,:,3].astype(np.int64)
                rear=pwl_scaled(8*be,round_ratio(A[:,4:],4096),32)
                raw=1024*q2+rear-128*(2*((db>>1)&1)-1)
                assert np.all((raw>=-4096)&(raw<4096))
                mag=np.abs(raw);sign=np.sign(raw)
                phi=np.stack((sign*np.minimum(mag,1024),sign*np.minimum(np.maximum(mag-1024,0),1024)),axis=2)
                parts=phi*K[:,:2,None].transpose(0,2,1)
                num=parts.sum(axis=2);delta=ay[:,h].astype(np.int64)-cy[:,h//2].astype(np.int64)
                rem=delta*8192-num;assert np.all(np.abs(rem)<=9216)
                refpow,refcross=reference_score(num,cy[:,h//2],ti,TD);ref=refpow+refcross
                rr=oldrows[seed,rate,init];actual=F(rr['effects']['rear_to_front_mediated']['net_exact'])
                rp,rcross=reference_score(rem,cy[:,h//2],ti,TD)
                rcross+=F(2*scaled_sum(num*rem),W*120*8192*8192)
                residual=rp+rcross
                assert actual==ref+residual
                parts_loss=[]
                for i in range(2):
                    p,c=reference_score(parts[:,:,i],cy[:,h//2],ti,TD)
                    parts_loss.append({'power':float(p),'error_cross':float(c),'net':float(p+c),'net_exact':str(p+c)})
                interaction=F(2*scaled_sum(parts[:,:,0]*parts[:,:,1]),W*120*8192*8192)
                assert ref==sum((F(r['net_exact']) for r in parts_loss),F(0))+interaction
                uncertainty=2*rad*F(scaled_sum(np.abs(num)),W*120*8192)
                requeststats=[]
                for i in range(4):
                    item={'coordinate':i+1,'rear_forcing':moment(E[:,i]),'front_history_response':moment(S[:,i]),
                        'alternative_rear_forcing':moment(Ea[:,i]),'alternative_front_response':moment(Sa[:,i]),
                        'request_interaction':moment(J[:,i]),'held_gate_readout':moment(signal_num[:,i],Q),
                        'changed_gate':moment(gate_num[:,i],Q),'rounding_difference':moment(round_num[:,i],Q),
                        'alternate_held_gate_readout':moment(signal_alt_num[:,i],Q),
                        'alternate_changed_gate':moment(gate_alt_num[:,i],Q),
                        'gate_flip_samples':int(np.count_nonzero(gc[:,:,i]!=gb[:,:,i])),
                        'gate_flip_windows':int(np.count_nonzero(np.any(gc[:,:,i]!=gb[:,:,i],axis=1))),
                        'alternate_gate_flip_samples':int(np.count_nonzero(gA[:,:,i]!=gD[:,:,i])),
                        'final_hidden_gap_q22':int(state_gap[-1,i]),'max_hidden_gap_q22':int(np.max(np.abs(state_gap[:,i]))),
                        'export_gap_mean':float(K[:,i].mean()),'export_gap_abs_mean':float(np.abs(K[:,i]).mean())}
                    assert F(item['rear_forcing']['sum_exact'])+F(item['front_history_response']['sum_exact'])==state_gap[-1,i]
                    assert F(item['rear_forcing']['sum_exact'])==sum((F(item[k]['sum_exact']) for k in ('held_gate_readout','changed_gate','rounding_difference')),F(0))
                    requeststats.append(item)
                row={'seed':seed,'rate':rate,'initialization':init,'requests':requeststats,
                    'mediated_loss':float(actual),'mediated_loss_power':rr['effects']['rear_to_front_mediated']['power'],
                    'mediated_loss_cross':rr['effects']['rear_to_front_mediated']['cross'],
                    'continuous_gap_loss':float(ref),'continuous_gap_loss_exact':str(ref),
                    'continuous_gap_power':float(refpow),'continuous_gap_cross':float(refcross),
                    'readout_rounding_remainder_loss':float(residual),'readout_rounding_remainder_loss_exact':str(residual),
                    'readout_rounding_remainder_power':float(rp),'readout_rounding_remainder_cross':float(rcross),
                    'max_code_gap_remainder':float(F(int(np.max(np.abs(rem))),8192)),
                    'low_coordinate_reference_losses':parts_loss,'low_coordinate_interaction':float(interaction),
                    'continuous_reference_target_interval':[float(ref-uncertainty),float(ref+uncertainty)],
                    'continuous_reference_sign_certified':bool(ref-uncertainty>0 or ref+uncertainty<0),
                    'nominal_sign_matches_without_current_gap_rounding':bool(actual*ref>0),
                    'counterfactual_high_requests':{'C':int(np.count_nonzero(rc[:,2:])),'D':int(np.count_nonzero(rd[:,2:]))},
                    'block_loss':[]}
                for b in range(8):
                    sl=slice(256*b,256*(b+1));dlt=delta[sl].ravel().astype(float);e=cy[sl,h//2].ravel().astype(float)-target
                    row['block_loss'].append({'block':128+b,'power':float(np.mean(dlt*dlt)),
                        'error_cross':float(2*np.mean(e*dlt)),'net':float(np.mean(dlt*dlt)+2*np.mean(e*dlt))})
                rows.append(row)
                record=np.stack((ra,rb,rc,rd,E,S,Ea,Sa,J,signal_num,gate_num,round_num,signal_alt_num,gate_alt_num,round_alt_num),axis=1)
                record.astype('<i8').tofile(out/f'{stem}_{init}_request_decomposition.bin')
                np.column_stack((state_gap[:-1],K)).astype('<i4').tofile(out/f'{stem}_{init}_history_gaps.bin')
                print(seed,rate,init,'M',float(actual),'power/cross',row['mediated_loss_power'],row['mediated_loss_cross'],
                    'reference',float(ref),'rounding',float(residual),'gate2',requeststats[1]['gate_flip_samples'],
                    'signal/gate abs',requeststats[1]['held_gate_readout']['abs_mean'],requeststats[1]['changed_gate']['abs_mean'],flush=True)
    assert sc==28804 and bank==240
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    write(out/'results.json',{'completed':True,'rows':rows})
    write(out/'verification.json',{'passed':True,'cases':20,'request_window_pairs':40960,
        'four_corner_front_request_vectors':163840,'all_saved_front_hidden_gaps_exact':True,
        'all_request_forcing_response_orders_exact':True,'all_product_gate_orders_exact':True,
        'all20_exact_integer_dyadic_loss_reference_splits':True,'all_final_code_gap_remainders_le_9_8':True,
        'all_request_rounding_differences_le_24_25':True,
        'rational_and_formal_readouts_each':sc,'formal_front_candidate_request_probes':bank,
        'kernel_integer_readouts':5428320,'kernel_gate_support_product_components_each':43426560,
        'rear_pwl_and_continuous_gap_evaluations_each':4915200,
        'source_files_preserved':len(load(out/'source_hashes.json')),'old_execution_sources_preserved':len(load(out/'execution_hashes.json')),
        'new_state_submissions_or_learning_or_trajectories':0,'new_source_conversions':0,'fft':0,'holdout_used':False,
        'scope':'Read-only existing histories and current-window request corners, exact finite reference scores; no gate-channel causal ablation or whole-learning quantization removal.'})
    print('All20 forcing/response histories and signed-loss chains verified',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','analyze']);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    try:globals()[args.mode](args.out)
    except Exception:
        if args.out.exists():write(args.out/(args.mode+'_failure.json'),{'traceback':traceback.format_exc()})
        raise
