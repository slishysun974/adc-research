"""Metadata-only fixed shadow-gate statistics at two predeclared positions.

No ADC/PWL/learner, source words, target tables, output score or new policy.
"""
import argparse
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import shutil
import traceback

ROOT=Path(__file__).resolve().parents[2]
STAT=ROOT/'artifacts/research/full_front_fixed_mean_statistics_20261014_v1'
CON=ROOT/'artifacts/research/full_front_mean_learning_20261014_v1'
POS=ROOT/'artifacts/research/mean_shadow_position_bridge_20261015_v3'
ALIGN=ROOT/'artifacts/research/front_fixed_alignment_20261014_v2'
MEAN=ROOT/'artifacts/runs/EXP_076/fixed_mean_gate_v1'
META=[STAT/n for n in ('results.json','protocol.json','verification.json','independent_check.json','source_hashes.json')]
META += [CON/n for n in ('results.json','verification.json','independent_check.json')]
META += [POS/n for n in ('results.json','protocol.json','independent_check.json')]
META += [ALIGN/n for n in ('results.json','verification.json','independent_check.json')]
META += [MEAN/n for n in ('protocol.json','verification.json','independent_check.json','source_hashes.json')]
DOCS=['docs/STATUS.md','docs/DECISIONS.md','docs/RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md',
      'docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md','docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md',
      'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md','docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
      'docs/reports/experiments/EXP_076_FIXED_MEAN_GATE_INTERVENTION_V1.md',
      'docs/reports/GU_ALGORITHM_EVALUATION_V1.md','docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
      'docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md']
KEY=(202610625,'quarter','prefix');N=245760;LAM=F(3072,25*4*(1<<22))
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def row(d,witness=False):return next(r for r in d['rows'] if (r['seed'],r['rate'],r['initialization'])==KEY and (not witness or r['reference']=='witness'))
def pathmap(d):return {str((Path(n) if Path(n).is_absolute() else ROOT/n).resolve()):z for n,z in d.items()}

class Budget:
    def __init__(self,limits):self.limits=limits;self.used=dict.fromkeys(limits,0)
    def charge(self,k,n=1):
        assert self.used[k]+n<=self.limits[k],(k,self.used[k],n,self.limits[k]);self.used[k]+=n
    def add(self,a,b):self.charge('fraction_add');return a+b
    def sub(self,a,b):self.charge('fraction_add');return a-b
    def mul(self,a,b):self.charge('fraction_mul');return a*b
    def div(self,a,b):self.charge('fraction_div');return a/b
    def total(self,values):
        z=F(0)
        for v in values:z=self.add(z,v)
        return z
    def dot(self,a,b):return self.total(self.mul(x,y) for x,y in zip(a,b))
    def mv(self,a,v):return [self.dot(line,v) for line in a]
    def sha(self,p):self.charge('fingerprint_bytes',p.stat().st_size);return hashlib.sha256(p.read_bytes()).hexdigest()
    def read(self,p):self.charge('metadata_bytes',p.stat().st_size);return load(p)
    def save(self,out,stage,done):write(out/f'accounting_{stage}.json',{'completed':done,'used':self.used,'limits':self.limits,'all_limits_met':all(self.used[k]<=v for k,v in self.limits.items())})

def inputs(q):
    data={str(p):q.read(p) for p in META}
    stat=row(data[str(STAT/'results.json')]);con=row(data[str(CON/'results.json')]);wit=row(data[str(ALIGN/'results.json')],True)
    pos=data[str(POS/'results.json')];policy=data[str(MEAN/'protocol.json')]
    for folder in (STAT,CON,ALIGN,MEAN):
        for name in ('verification.json','independent_check.json'):assert data[str(folder/name)]['passed']
    assert data[str(POS/'independent_check.json')]['passed']
    assert stat['continuous_kappa']==policy['shadow_front_kappa']
    assert stat['original_rear_codes']==policy['shadow_rear_codes']==wit['codes'][4:]
    assert stat['continuous_kappa'][2:]==['1','1'] and wit['codes'][2:4]==[1024,1024]
    assert stat['continuous_kappa'][:2]==con['mean_kappa']
    assert stat['gate2_count']==policy['shadow_expected_gate_count']==103744
    assert wit['total']['high_request_nonzero']['full']==0
    assert pos['case']==list(KEY) and policy['case']==list(KEY)
    old=pathmap(data[str(STAT/'source_hashes.json')]);bound=data[str(POS/'protocol.json')]['source_hashes']
    for name in (str(CON/'results.json'),str(ALIGN/'results.json')):assert old[name]==bound[name]
    expected=pathmap(data[str(MEAN/'source_hashes.json')])[str(STAT/'results.json')]
    return stat,con,wit,pos,expected

def guards(out,p,q):
    for n,z in p['source_hashes'].items():assert q.sha(Path(n))==z,n
    assert q.sha(Path(__file__))==q.sha(out/'frozen_analysis.py')==p['execution_sha256']

def controls(q):
    a=[[F(2),F(1)],[F(0),F(3)]];b=[F(-3),F(1)];k0=[F(1),F(1)];k=[F(2),F(3)]
    c0=[q.add(x,y) for x,y in zip(q.mv(a,k0),b)]
    shifted=[q.add(x,y) for x,y in zip(c0,q.mv(a,[q.sub(k[j],k0[j]) for j in range(2)]))]
    assert shifted==[q.add(x,y) for x,y in zip(q.mv(a,k),b)]
    assert q.add(F(1),q.mul(F(-2),F(1)))<0 # A coefficient-dependent gate cannot be frozen silently.
    assert q.add(F(1,16),F(1,16))==F(1,8)
    assert round(F(1,2))==0 and round(F(3,2))==2
    assert q.mul(F(1,8),F(1,4))==F(1,32)
    assert q.add(q.mul(F(-1),F(1,4)),q.mul(F(1),F(-1,4)))<0
    return {'passed':True,'controls':6,'fixed_mask_affine_transfer_quantization_and_projection_controls':True,'new_ADC_readouts':0}

def prepare(out):
    assert not out.exists(),'Refuse overwrite'
    size=sum(p.stat().st_size for p in META);code=Path(__file__).stat().st_size
    q=Budget({'metadata_bytes':size,'fingerprint_bytes':size+2*code,'fraction_add':128,'fraction_mul':128,'fraction_div':16})
    *_,expected=inputs(q);ctrl=controls(q)
    hashes={str(p):q.sha(p) for p in META};assert hashes[str(STAT/'results.json')]==expected
    own=q.sha(Path(__file__));out.mkdir(parents=True);shutil.copyfile(Path(__file__),out/'frozen_analysis.py');assert q.sha(out/'frozen_analysis.py')==own
    common={'metadata_bytes':size,'fingerprint_bytes':2*(size+2*code),'fraction_add':4000,'fraction_mul':4000,'fraction_div':256,'positions':2}
    p={'version':'EXP076-fixed-shadow-affine-target-v1','date':'2026-10-15','case':list(KEY),
       'authority':'User asks continue mainline; D136..140/current STATUS specifies at most new mean and prior witness, scalar fixed-shadow statistic transfer.',
       'scope':'Exactly new mean low2 and original legal witness, original rear/high/source/eight blocks/full120/rate1/4. Whole-record conditional directions only; no third point, root or policy.',
       'derivation':'GF is the frozen per-word shadow at old reference kr, not evaluated-coefficient own gate. First gate1=1. Hence low2 continuous C_GF(k)=C(kr)+A(kr)(k-kr)=A(kr)k+b for all k with same rear/high. No old dynamic-gate rho required; this is not global-affine original Gu.',
       'target':'True continuous-front fixed-rear loss L*, gradient at k = gL(kr)+2H(k-kr). Keep J mean-position family separate; compare gL dot v using original gradient boxes.',
       'direction':'v=-lambda diag(1,3)C, lambda=3072/(25*4*2^22). This is average unrounded hidden coefficient request with continuous front data over SAME full record. D=gL dot v and finite continuous mean increment D+vHv; neither actual final-integer MSE nor future feedback.',
       'prediction':'New mean is expected locally downhill with fixed GF, as motivated by old reference descent; test at prior witness without assumed sign. Uphill supports local target mismatch; two downhill positions exclude that explanation ONLY there, not all fixed-gate targets or future dynamics.',
       'witness_quantization':'At legal witness only, front Q3 error conservatively <=1/8 code, so C errors <=(1,GF_count/N)/8. Mean Q22 request error adds halfLSB2^-23 per coordinate. Bound the gL projection with max gradient endpoints. Prove no low2 clipping from |yQ3|<=512 max(k)+64+1/8 and lambda weights before using bound. High Q22 requests remain old zero since only gate2 product replaced. This is a hidden-request projection, not Q1.10 export/actual integer loss change.',
       'validation':'Six bounded controls first. Main C-reference transfer and gradient shift; independent direct A*k+b and initial-gradient expansion. Both exact gradients at witness match prior directly scored continuous witness. Independent scalar coordinate and interval arithmetic, quantization error box bound. Preserve uncertain signs.',
       'units':'All old JSON full-file bytes; all SHA including self/frozen/both guards. Rational add/sub/mul/div wrapped; fixed-scale Fraction construction, parse/unary/compare/index/display excluded. Generated local protocol/result reads and document/delivery operations administrative, separately retained. No source words, saved mask/states/output arrays, target tables, PWL/gates/score/learning or FPGA/chip costs.',
       'source_hashes':hashes,'execution_sha256':own,'preparation_limits':q.limits,'main_limits':common,'independent_limits':common,
       'stop':'Complete two conditional positions and witness request bound or explicit failed qualification. No target refinement, matrix/readout expansion, new roots, feedback policy, online algorithm, model/horizon/FFT or holdout. All prior failures/budgets retained.'}
    write(out/'protocol.json',p);write(out/'controls.json',ctrl);q.save(out,'preparation',True)
    docbytes=0
    for n in DOCS:
        target=out/'documents_before'/n;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,target);docbytes+=(ROOT/n).stat().st_size
    write(out/'administrative_preparation.json',{'document_snapshot_bytes':docbytes,'files':len(DOCS),'record_calculations_before_freeze':0})
    print('Frozen two fixed-shadow conditional positions; no new record readouts.')

def pack(x,interval=None):
    r={'exact':str(x),'value':float(x)}
    if interval is not None:r.update(interval=list(map(str,interval)),sign_certified=interval[0]>0 or interval[1]<0)
    return r

def project(g,box,v,q,independent=False):
    if independent:
        products=[[q.mul(a,v[j]),q.mul(b,v[j])] for j,(a,b) in enumerate(box)]
        interval=[q.total(min(z) for z in products),q.total(max(z) for z in products)]
        center=q.add(q.mul(g[0],v[0]),q.mul(g[1],v[1]))
    else:
        lo=hi=F(0)
        for z,(a,b) in zip(v,box):
            x,y=q.mul(z,a),q.mul(z,b);lo=q.add(lo,min(x,y));hi=q.add(hi,max(x,y))
        interval=[lo,hi];center=q.dot(g,v)
    return pack(center,interval)

def quantized_witness(k,g,box,c,v,d,q,independent):
    prob=F(103744,N);epsC=[F(1,8),q.mul(F(1,8),prob)];round_eps=F(1,1<<23)
    epsv=[q.add(q.mul(q.mul(LAM,F(w)),epsC[j]),round_eps) for j,w in enumerate((1,3))]
    y_bound=q.add(q.add(q.mul(F(512),max(k+[F(1),F(1)])),F(64)),F(1,8))
    max_update=[q.add(q.mul(q.mul(LAM,F(w)),y_bound),round_eps) for w in (1,3)]
    distances=[min(z,q.sub(F(2047,1024),z)) for z in k]
    assert all(max_update[j]<distances[j] for j in range(2))
    # C error box transported through fixed lambda, then projection error box.
    radius=q.total(q.mul(max(abs(a),abs(b)),epsv[j]) for j,(a,b) in enumerate(box))
    outer=[q.sub(F(d['interval'][0]),radius),q.add(F(d['interval'][1]),radius)]
    if independent:
        cbox=[[q.sub(c[j],epsC[j]),q.add(c[j],epsC[j])] for j in range(2)]
        vbox=[[q.sub(-q.mul(q.mul(LAM,F(w)),cbox[j][1]),round_eps),q.add(-q.mul(q.mul(LAM,F(w)),cbox[j][0]),round_eps)] for j,w in enumerate((1,3))]
        assert all([q.sub(v[j],epsv[j]),q.add(v[j],epsv[j])]==vbox[j] for j in range(2))
    return {'C_error_upper':list(map(str,epsC)),'hidden_mean_step_error_upper':list(map(str,epsv)),
            'front_Q3_y_absolute_bound':str(y_bound),'maximum_hidden_increment':list(map(str,max_update)),
            'low2_no_clip_certified':True,'old_high_Q22_requests_unchanged_zero':True,
            'mean_Q3_Q22_hidden_request_derivative_interval':list(map(str,outer)),
            'projection_sign_certified':outer[0]>0 or outer[1]<0,
            'actual_Q1_10_integer_output_or_future_benefit_proved':False}

def analyze(out,independent=False):
    p=load(out/'protocol.json');stage='independent' if independent else 'main';target='independent_check.json' if independent else 'results.json'
    assert not (out/target).exists();q=Budget(p['independent_limits' if independent else 'main_limits']);done=False
    try:
        guards(out,p,q);stat,con,wit,pos,_=inputs(q)
        a=[[F(z) for z in line] for line in stat['A']];b=list(map(F,stat['b']));cr=list(map(F,stat['C']));kr=list(map(F,stat['continuous_kappa'][:2]))
        h=[[F(z) for z in line] for line in con['H']];gr=[F(z['exact']) for z in con['gradient_L']];boxes=[list(map(F,z['interval'])) for z in con['gradient_L']]
        assert [q.add(x,y) for x,y in zip(q.mv(a,kr),b)]==cr
        kmean=[q.add(F(wit['initial_codes'][j],1024),F(pos['mean_gap'][j])) for j in range(2)]
        locations=[('shadow_actual_mean',kmean),('prior_legal_witness',[F(z,1024) for z in wit['codes'][:2]])];rows=[]
        for tag,k in locations:
            q.charge('positions');delta=[q.sub(k[j],kr[j]) for j in range(2)]
            if independent:
                c=[q.add(x,y) for x,y in zip(q.mv(a,k),b)]
                base=q.mv(h,kr);hk=q.mv(h,k)
                shift=[q.sub(q.mul(F(2),hk[j]),q.mul(F(2),base[j])) for j in range(2)]
            else:
                c=[q.add(x,y) for x,y in zip(cr,q.mv(a,delta))]
                shift=[q.mul(F(2),z) for z in q.mv(h,delta)]
            g=[q.add(gr[j],shift[j]) for j in range(2)];box=[[q.add(z,shift[j]) for z in line] for j,line in enumerate(boxes)]
            if tag=='prior_legal_witness':
                assert list(map(str,g))==[z['exact'] for z in wit['total']['gradient']]
                assert [list(map(str,line)) for line in box]==[z['interval'] for z in wit['total']['gradient']]
            v=[-q.mul(q.mul(LAM,F(w)),c[j]) for j,w in enumerate((1,3))]
            d=project(g,box,v,q,independent);curve=q.dot(v,q.mv(h,v));finite=pack(q.add(F(d['exact']),curve),[q.add(F(z),curve) for z in d['interval']])
            result={'position':tag,'kappa_low2':list(map(str,k)),'C_fixed_GF':list(map(str,c)),
                    'C_nonzero':any(c),'true_continuous_gradient':list(map(str,g)),'gradient_intervals':[list(map(str,line)) for line in box],
                    'mean_continuous_hidden_direction':list(map(str,v)),'D':d,'curvature':str(curve),'finite_continuous_mean_increment':finite}
            if tag=='prior_legal_witness':result['quantization_bound']=quantized_witness(k,g,box,c,v,d,q,independent)
            rows.append(result)
        r={'case':list(KEY),'fixed_shadow_gate_count':stat['gate2_count'],'lambda':str(LAM),'rows':rows,
           'source_mask_fixed_not_original_Gu_global_affine':True,'new_readouts_learning_scores_paths_FFT':0}
        guards(out,p,q)
        if independent:
            assert r==load(out/'results.json')
            write(out/target,{'passed':True,'direct_Ak_plus_b_and_initial_gradient_expand_match':True,
                             'prior_direct_witness_gradient_and_quantization_boxes_exact':True,'two_positions':True})
            write(out/'summary.json',{'passed':True,'new_mean_downhill_certified':F(rows[0]['D']['interval'][1])<0,
                'both_continuous_directions_downhill_certified':all(F(z['D']['interval'][1])<0 for z in rows),
                'both_finite_continuous_mean_increments_downhill_certified':all(F(z['finite_continuous_mean_increment']['interval'][1])<0 for z in rows),
                'witness_hidden_Q3_Q22_projection_interval':rows[1]['quantization_bound']['mean_Q3_Q22_hidden_request_derivative_interval'],
                'new_mean_is_a_fixed_continuous_correlation_root':not rows[0]['C_nonzero'],
                'global_mismatch_or_long_term_reachability_proved':False})
        else:write(out/target,r)
        done=True;print(stage,[(z['position'],z['D']['value'],z['D']['sign_certified']) for z in rows])
    finally:q.save(out,stage,done)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('prepare','analyze','check'));ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    try:
        if args.mode=='prepare':prepare(args.out)
        else:analyze(args.out,args.mode=='check')
    except Exception:
        if args.out.exists():write(args.out/f'failure_{args.mode}.json',{'traceback':traceback.format_exc()})
        raise
