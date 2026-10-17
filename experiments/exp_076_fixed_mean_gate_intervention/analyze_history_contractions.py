"""EXP076: two needed weighted contractions from immutable bases/GF/history.

No ADC evaluation, PWL, gate construction, actual request generation or scoring.
"""
from pathlib import Path
from fractions import Fraction as F
import argparse
import hashlib
import json
import shutil
import struct
import traceback

ROOT=Path('D:/ADC'); W=2048; N=W*120; START=128*256; DEN=1<<21
KEY=(202610625,'quarter','prefix')
FIX=ROOT/'artifacts/research/full_front_fixed_mean_statistics_20261014_v1'
NOW=ROOT/'artifacts/research/fixed_shadow_statistics_20261015_v1'
HIST=ROOT/'artifacts/research/mean_shadow_history_audit_20261015_v1/run_v3'
RUN=ROOT/'artifacts/runs/EXP_076/fixed_mean_gate_v1'
BASIS=ROOT/'artifacts/research/front_block_migration_20261014_v1/202610625_quarter_prefix_basis.bin'
WORDS=ROOT/'artifacts/runs/EXP_062/background_v1/both_smooth_202610625_words.bin'
MASK=RUN/'shadow_gate.bin'; STATES=RUN/'q22.bin'
META=[FIX/'results.json',FIX/'source_hashes.json',FIX/'verification.json',FIX/'independent_check.json',
      NOW/'results.json',NOW/'protocol.json',NOW/'independent_check.json',
      HIST/'results.json',HIST/'source_hashes.json',HIST/'independent_check.json',
      RUN/'protocol.json',RUN/'candidate_hashes.json',RUN/'source_hashes.json',RUN/'verification.json',RUN/'independent_check.json']
DATA=[BASIS,WORDS,MASK,STATES]

def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def row(d):return next(r for r in d['rows'] if (r['seed'],r['rate'],r['initialization'])==KEY)

class Budget:
    def __init__(self,limits):self.limits=limits;self.used={k:0 for k in limits}
    def charge(self,k,n=1):
        self.used[k]+=n;assert self.used[k]<=self.limits[k],(k,self.used[k],self.limits[k])
    def add(self,a,b):self.charge('fraction_add');return a+b
    def sub(self,a,b):self.charge('fraction_add');return a-b
    def mul(self,a,b):self.charge('fraction_mul');return a*b
    def div(self,a,b):self.charge('fraction_div');return a/b
    def total(self,items):
        z=F(0)
        for a in items:z=self.add(z,a)
        return z

def prepare(out):
    assert not out.exists(),'Refuse overwrite'
    out.mkdir(parents=True)
    files=META+DATA+[Path(__file__).resolve(),ROOT/'experiments/exp_075_front_sampling_intervention/analyze_fixed_mean_statistics.py']
    size=sum(p.stat().st_size for p in files)
    base={'metadata_bytes':sum(p.stat().st_size for p in META),
          'fingerprint_bytes':2*(size+Path(__file__).stat().st_size),
          'binary_read_bytes':BASIS.stat().st_size+N*4+MASK.stat().st_size+STATES.stat().st_size,
          'saved_basis_values':2*N,'source_tag_values':N,'saved_mask_values':N,
          'saved_low_state_values':2*W,'export_cells':2*W,
          'fraction_add':512,'fraction_mul':512,'fraction_div':64}
    main={**base,'direct_word_contraction_kernels':N,'state_mean_integer_kernels':2*W}
    independent={**base,'window_word_moment_kernels':N,'window_contraction_kernels':W,'state_mean_integer_kernels':2*W}
    protocol={'date':'2026-10-15','version':'EXP076-two-centered-history-contractions-v1',
       'authority':'User explicitly continues mainline after sufficient-statistic audit; D136..140 same finite case. This fills only the two contractions whose signs can distinguish finite-time versus state-observation weakening.',
       'case':list(KEY),'scope':'Original one case/full120/2048 windows/eight blocks. Same saved GF, rear Q3/high2. New mean is the already certified mean, no new reference, policy, horizon or input.',
       'prediction':'Time versus centered-state projection dominance is open. A certified positive time term supports time-order weakening; a positive state term supports movement/source association; retain opposite signs. Declare dominance only if one lower absolute bound exceeds both other upper bounds. Q3/Q22 combined request difference is retained and compared with conservative Q22-only bound. No sign-driven changes.',
       'derivation':'Cw(k)=Bw*k+bw with fixed GF. Compute u=mean_words h*d*G*psi*(kbar-kr), z=mean_words h*d*G*psi*(kw-kbar). tF=old_t_r-Lambda*u; tM=tF-Lambda*z. flat=hbar*v(kbar); time=tF-flat; state=tM-tF; quant=tQ-tM. All are exact two-coordinate vectors projected onto SAME existing new-mean true L* gradient/box. No full per-window matrix is saved.',
       'data_contract':'Reuse signed low bases phi=8psi from original basis.bin, whose equality to independently rebuilt fixed-rear geometry was certified. Read only original prefix tag fields for d1; tag decode, saved mask and states charged. GF never recomputed. First gate1=1; low2 source/rear/high unchanged; Q3/Q22 remain in original state history.',
       'main_limits':main,'independent_limits':independent,
       'control_limits':{'fraction_add':128,'fraction_mul':128,'fraction_div':32},
       'preparation_fingerprint_limit':size,
       'kernel_units':'Direct word kernel includes dither decode/domain checks, mask count, four signed-basis totals, two phi-dot-delta/center contractions, h/mask products and four sum updates. Independent word kernel accumulates four signed-basis moments; window kernel contracts current 2x2 temporaries against delta and centered state, then h. State mean kernel includes accumulation/centering. Integer scientific internals counted by these fixed kernel units; Fraction outer arithmetic wrapped. Parse, fixed-denominator construction, unary, comparison, index/display excluded. Full old JSON, binary reads and full SHA including current/frozen code and both guards are separate. Document/delivery reads administrative. Offline units, not chip cost.',
       'validation':'Six exact controls before records. Main direct per-word integer contraction versus independent per-window moment first and contraction second; main modular export versus Fraction round. Both recover old global AF and same new mean, GF count, source/mask/state SHA and total projection identity. Original fixed/moving ADC quantities are not recalculated.',
       'stop':'One time/state/combined-quantization comparison or retain failure/uncertainty. No fresh PWL, gate, output/target table/score, request execution, learning, path, full matrices, new reference/root, twenty-case sweep, tighter phase bounds, future6007/8009 or algorithm. Existing failures and budgets retained.'}
    write(out/'protocol.json',protocol)
    hashes={str(p):digest(p) for p in files}
    write(out/'source_hashes.json',hashes);shutil.copyfile(Path(__file__),out/'frozen_analysis.py')
    write(out/'accounting_preparation.json',{'completed':True,'fingerprint_bytes':size,'limit':size,'all_limits_met':True,'new_scientific_array_calculations':0})
    print('Frozen one two-contraction same-history comparison.')

def controls(out):
    q=Budget(load(out/'protocol.json')['control_limits'])
    # Mean zero state can have a nonzero weighted observation product.
    center=[F(-1),F(1)];h=[F(1),F(0)];b=[F(2),F(3)]
    assert q.total(center)==0
    z=q.div(q.total(q.mul(q.mul(h[i],b[i]),center[i]) for i in range(2)),F(2));assert z==-1
    # Same contraction: distribute state subtraction before or after moments.
    k=[F(2),F(4)];m=F(3);r=F(1)
    direct=q.total(q.mul(q.mul(h[i],b[i]),q.sub(k[i],r)) for i in range(2))
    split=q.add(q.total(q.mul(q.mul(h[i],b[i]),q.sub(k[i],m)) for i in range(2)),q.mul(q.total(q.mul(h[i],b[i]) for i in range(2)),q.sub(m,r)))
    assert direct==split
    # Constant state / zero source displacement / gate zero remove relevant terms.
    assert q.mul(F(5),q.sub(F(3),F(3)))==0
    assert q.mul(F(0),F(900))==0 and q.mul(F(900),F(0))==0
    # Nearest even, signed scale and last precommit weight.
    assert [round(F(z,2)) for z in (1,3,-1,-3)]==[0,2,0,-2]
    assert q.mul(F(0),F(900))==0 and q.div(F(8),F(8))==1
    # Target-box projection is linear for the same fixed gradient.
    assert q.mul(F(2),q.add(F(3),F(-1)))==q.add(q.mul(F(2),F(3)),q.mul(F(2),F(-1)))
    write(out/'controls.json',{'passed':True,'exact_controls':6,'centered_state_distributivity_degenerate_mask_export_timing_shared_gradient':True})
    write(out/'accounting_controls.json',{'completed':True,'used':q.used,'limits':q.limits,'all_limits_met':True})
    print('Six exact bounded controls passed.')

def guard(out,q):
    hashes=load(out/'source_hashes.json')
    for name,z in hashes.items():
        p=Path(name);q.charge('fingerprint_bytes',p.stat().st_size);assert digest(p)==z,name
    frozen=out/'frozen_analysis.py';q.charge('fingerprint_bytes',frozen.stat().st_size)
    key=next(k for k in hashes if k.endswith(Path(__file__).name))
    assert digest(frozen)==hashes[key]

def project(g,box,v,q,ind):
    if ind:
        vals=[q.total(q.mul(box[j][(bits>>j)&1],v[j]) for j in range(2)) for bits in range(4)];lo,hi=min(vals),max(vals)
    else:
        vals=[[q.mul(z,v[j]) for z in box[j]] for j in range(2)]
        lo,hi=q.total(min(z) for z in vals),q.total(max(z) for z in vals)
    c=q.total(q.mul(g[j],v[j]) for j in range(2))
    return {'exact':str(c),'value':float(c),'interval':[str(lo),str(hi)],'display_interval':[float(lo),float(hi)],'sign_certified':lo>0 or hi<0}

def analyze(out,ind=False):
    stage='independent' if ind else 'main';target=out/('independent_check.json' if ind else 'results.json')
    assert not target.exists();p=load(out/'protocol.json');q=Budget(p['independent_limits' if ind else 'main_limits']);done=False
    try:
        assert load(out/'controls.json')['passed'];guard(out,q)
        data={}
        for name in META:q.charge('metadata_bytes',name.stat().st_size);data[str(name)]=load(name)
        get=lambda name:data[str(name)]
        for name in META:
            if name.name in ('verification.json','independent_check.json'):assert get(name)['passed'],name
        assert get(FIX/'verification.json')['saved_low_bases_match']
        stat=row(get(FIX/'results.json'));fresh=get(NOW/'results.json')['rows'][0];hist=get(HIST/'results.json');run=get(RUN/'protocol.json')
        assert fresh['position']=='shadow_actual_mean' and hist['case']==list(KEY)
        assert run['shadow_front_kappa']==stat['continuous_kappa'] and run['shadow_rear_codes']==stat['original_rear_codes']
        assert hist['old_reference_kappa']==stat['continuous_kappa'][:2] and hist['mean_kappa']==fresh['kappa_low2']
        source=load(out/'source_hashes.json');old=get(FIX/'source_hashes.json')
        assert source[str(BASIS)]==old[str(BASIS)]
        assert source[str(WORDS)]==old[str(WORDS)]==get(RUN/'source_hashes.json')[str(WORDS)]==hist['same_word_source_sha256']
        candidate={str((Path(k) if Path(k).is_absolute() else ROOT/k).resolve()):v for k,v in get(RUN/'candidate_hashes.json').items()}
        assert candidate[str(MASK)]==source[str(MASK)] and candidate[str(STATES)]==source[str(STATES)]
        assert get(HIST/'source_hashes.json')[str(STATES)]==source[str(STATES)]
        assert get(NOW/'protocol.json')['source_hashes'][str(FIX/'results.json')]==source[str(FIX/'results.json')]
        assert get(RUN/'verification.json')['all_states_requests_outputs_shadow_scalar_rebuild_exact']
        kr=list(map(F,stat['continuous_kappa'][:2]));km=list(map(F,fresh['kappa_low2']))
        delta=[q.sub(km[j],kr[j]) for j in range(2)]
        assert all(DEN%z.denominator==0 for z in kr+km+delta)
        mn=[int(z*DEN) for z in km];dn=[int(z*DEN) for z in delta]
        q.charge('binary_read_bytes',BASIS.stat().st_size+MASK.stat().st_size+STATES.stat().st_size+N*4)
        bases=BASIS.read_bytes();mask=MASK.read_bytes();states=STATES.read_bytes()
        with WORDS.open('rb') as f:f.seek(START*120*4);words=f.read(N*4)
        assert len(bases)==4*N and len(mask)==N and len(words)==N*4 and len(states)==(W+1)*32
        q.charge('saved_basis_values',2*N);q.charge('source_tag_values',N);q.charge('saved_mask_values',N);q.charge('saved_low_state_values',2*W);q.charge('export_cells',2*W)
        def rn(z):
            a,b=divmod(z,4096);return a+int(b>2048 or (b==2048 and a%2))
        exports=[]
        for w in range(W):
            line=[struct.unpack_from('<i',states,32*w+4*j)[0] for j in range(2)]
            exports.append([round(F(z,4096)) if ind else rn(z) for z in line])
        q.charge('state_mean_integer_kernels',2*W)
        assert [F(sum(line[j] for line in exports),W*1024) for j in range(2)]==km
        total_a=[[0,0],[0,0]];corr_delta=[0,0];corr_state=[0,0];gatecount=0
        if ind:
            for w in range(W):
                aw=[[0,0],[0,0]];center=[exports[w][j]*(DEN//1024)-mn[j] for j in range(2)];hw=W-1-w
                for n in range(w*120,(w+1)*120):
                    q.charge('window_word_moment_kernels');f0,f1=struct.unpack_from('<hh',bases,4*n);tag=words[4*n+3];gf=mask[n]
                    assert 0<=tag<=3 and gf in (0,1) and abs(f0)<=1024 and abs(f1)<=1024
                    d=1 if tag%2 else -1;gatecount+=gf
                    for i,gate in enumerate((1,gf)):
                        aw[i][0]+=d*gate*f0;aw[i][1]+=d*gate*f1
                q.charge('window_contraction_kernels')
                for i in range(2):
                    corr_delta[i]+=hw*(aw[i][0]*dn[0]+aw[i][1]*dn[1])
                    corr_state[i]+=hw*(aw[i][0]*center[0]+aw[i][1]*center[1])
                    for j in range(2):total_a[i][j]+=aw[i][j]
        else:
            for n in range(N):
                q.charge('direct_word_contraction_kernels');w=n//120;hw=W-1-w
                f0,f1=struct.unpack_from('<hh',bases,4*n);gf=mask[n];tag=words[4*n+3]
                assert 0<=tag<=3 and gf in (0,1) and abs(f0)<=1024 and abs(f1)<=1024
                d=2*(tag&1)-1;gatecount+=gf
                center0=exports[w][0]*(DEN//1024)-mn[0];center1=exports[w][1]*(DEN//1024)-mn[1]
                a=hw*d*(f0*dn[0]+f1*dn[1]);b=hw*d*(f0*center0+f1*center1)
                corr_delta[0]+=a;corr_delta[1]+=gf*a;corr_state[0]+=b;corr_state[1]+=gf*b
                total_a[0][0]+=d*f0;total_a[0][1]+=d*f1;total_a[1][0]+=d*gf*f0;total_a[1][1]+=d*gf*f1
        assert gatecount==stat['gate2_count']==run['shadow_expected_gate_count']==103744
        assert [[F(z,8*N) for z in line] for line in total_a]==[list(map(F,line)) for line in stat['A']]
        u=[F(z,8*N*DEN) for z in corr_delta];z=[F(v,8*N*DEN) for v in corr_state]
        lam=F(3,409600);weights=(1,3)
        shift=[-q.mul(q.mul(lam,F(weight)),u[j]) for j,weight in enumerate(weights)]
        association=[-q.mul(q.mul(lam,F(weight)),z[j]) for j,weight in enumerate(weights)]
        tr=list(map(F,hist['vectors']['fixed_triangle_at_kr']));actual=list(map(F,hist['vectors']['actual_weighted_requests']))
        tf=[q.add(tr[j],shift[j]) for j in range(2)];tm=[q.add(tf[j],association[j]) for j in range(2)]
        flat=[q.mul(F(W-1,2),F(v)) for v in fresh['mean_continuous_hidden_direction']]
        time=[q.sub(tf[j],flat[j]) for j in range(2)];quant=[q.sub(actual[j],tm[j]) for j in range(2)]
        weakening=[q.sub(actual[j],flat[j]) for j in range(2)]
        for j in range(2):assert q.total([flat[j],time[j],association[j],quant[j]])==actual[j]
        vectors={'flat_at_new_mean':flat,'reference_shift_of_fixed_triangle':shift,'fixed_triangle_at_new_mean':tf,
                 'time_correction':time,'centered_state_association':association,'moving_continuous_triangle':tm,
                 'current_Q3_Q22_request_difference':quant,'actual_Q22_triangle':actual,'actual_minus_flat':weakening}
        g=list(map(F,fresh['true_continuous_gradient']));box=[list(map(F,line)) for line in fresh['gradient_intervals']]
        projections={name:project(g,box,v,q,ind) for name,v in vectors.items()}
        assert projections['actual_Q22_triangle']['exact']==hist['projections_at_new_mean_L_star']['actual_weighted_requests']['exact']
        eps=q.mul(F(W-1,2),F(1,1<<23));rq=q.total(q.mul(max(abs(a),abs(b)),eps) for a,b in box)
        q3eps=[q.add(q.mul(q.mul(q.mul(F(W-1,2),lam),F(weight)),F(1,8)),eps) for weight in weights]
        assert all(abs(quant[j])<=q3eps[j] for j in range(2))
        quantbox=list(map(F,projections['current_Q3_Q22_request_difference']['interval']))
        q3box=[q.sub(quantbox[0],rq),q.add(quantbox[1],rq)]
        def abs_bounds(name):
            a,b=map(F,projections[name]['interval'])
            return (min(abs(a),abs(b)) if a*b>0 else F(0),max(abs(a),abs(b)))
        terms=['time_correction','centered_state_association','current_Q3_Q22_request_difference']
        dominance={}
        for name in terms:
            lower,_=abs_bounds(name);other=q.total(abs_bounds(n)[1] for n in terms if n!=name)
            dominance[name]=lower>other
        result={'case':list(KEY),'common_denominator':DEN,'new_mean':list(map(str,km)),
             'two_correlation_contractions':{'weighted_sensitivity_times_mean_shift':list(map(str,u)),'weighted_centered_state_observation':list(map(str,z))},
             'vectors':{k:list(map(str,v)) for k,v in vectors.items()},'projections':projections,
             'one_term_absolute_dominance_over_other_two_certified':dominance,
             'Q22_only_projection_absolute_upper':str(rq),'Q3_projection_after_Q22_outer_interval':list(map(str,q3box)),
             'Q3_sign_cannot_be_explained_by_final_Q22_rounding':q3box[0]>0 or q3box[1]<0,
             'global_AF_and_GF_count_and_mean_recovered':True,'saved_mask_count':gatecount,
             'new_PWL_gate_tests_requests_learning_paths_outputs_scoring_target_tables_FFT':0,
             'same_history_descriptive_split_not_policy_or_unique_physical_share':True}
        guard(out,q)
        if ind:
            assert result==load(out/'results.json')
            write(target,{'passed':True,'independent_window_moment_first_contractions_match_direct_words':True,'Fraction_export_four_corner_gradient_boxes_and_old_AF_exact':True})
            write(out/'summary.json',{'passed':True,'prediction_signs_left_open_before_execution':True,
                  'dominance':dominance,'projection_values':{k:v['value'] for k,v in projections.items()},
                  'Q22_only_projection_absolute_upper':float(rq),'Q3_projection_outer_interval':list(map(float,q3box)),
                  'two_missing_contractions_completed_without_new_geometry_or_paths':True})
        else:write(target,result)
        done=True;print(stage,{k:round(v['value'],9) for k,v in projections.items()})
    finally:
        write(out/f'accounting_{stage}.json',{'completed':done,'used':q.used,'limits':q.limits,'all_limits_met':all(q.used[k]<=v for k,v in q.limits.items())})

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('prepare','controls','analyze','check'));ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    try:
        if args.mode=='prepare':prepare(args.out)
        elif args.mode=='controls':controls(args.out)
        else:analyze(args.out,args.mode=='check')
    except Exception:
        if args.out.exists():write(args.out/f'failure_{args.mode}.json',{'traceback':traceback.format_exc()})
        raise
