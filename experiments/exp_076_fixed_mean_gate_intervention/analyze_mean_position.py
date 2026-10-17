"""Saved mean-shadow path: quadratic mean location and actual-minus-mean.

Uses old scalar H/gradient/capacity witnesses and saved low2 Q22 only.
No word, target table, PWL, learner, new integer output or FFT is evaluated.
"""
import argparse
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import shutil
import traceback
import numpy as np

ROOT=Path(__file__).resolve().parents[2];W=2048
MEAN=ROOT/'artifacts/runs/EXP_076/fixed_mean_gate_v1'
CON=ROOT/'artifacts/research/full_front_mean_learning_20261014_v1'
CAP=ROOT/'artifacts/research/front_gate_migration_capacity_20261014_v2'
ALIGN=ROOT/'artifacts/research/front_fixed_alignment_20261014_v2'
SPACE=ROOT/'artifacts/research/shadow_fixed_witness_space_20261014_v1'
META=[CON/n for n in ('results.json','verification.json','independent_check.json','source_hashes.json')]
META += [CAP/n for n in ('results.json','verification.json')]
META += [ALIGN/n for n in ('results.json','verification.json','independent_check.json')]
META += [MEAN/n for n in ('results.json','verification.json','independent_check.json','candidate_hashes.json','source_hashes.json')]
META += [SPACE/n for n in ('results.json','protocol.json','independent_check.json')]
STATE=MEAN/'q22.bin';FILES=META+[STATE];KEY=(202610625,'quarter','prefix')
DOCS=['docs/STATUS.md','docs/DECISIONS.md','docs/RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md',
      'docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md','docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md',
      'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md','docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
      'docs/reports/experiments/EXP_076_FIXED_MEAN_GATE_INTERVENTION_V1.md',
      'docs/reports/GU_ALGORITHM_EVALUATION_V1.md','docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
      'docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md']
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def row(d,witness=False):return next(r for r in d['rows'] if (r['seed'],r['rate'],r['initialization'])==KEY and (not witness or r['reference']=='witness'))
def paths(d):return {str((Path(n) if Path(n).is_absolute() else ROOT/n).resolve()):z for n,z in d.items()}

class Budget:
    def __init__(self,limits):self.limits=limits;self.used=dict.fromkeys(limits,0)
    def charge(self,k,n=1):
        assert self.used[k]+n<=self.limits[k],(k,self.used[k],n,self.limits[k]);self.used[k]+=n
    def add(self,a,b):self.charge('fraction_add');return a+b
    def sub(self,a,b):self.charge('fraction_add');return a-b
    def mul(self,a,b):self.charge('fraction_mul');return a*b
    def div(self,a,b):self.charge('fraction_div');return a/b
    def total(self,v):
        z=F(0)
        for a in v:z=self.add(z,a)
        return z
    def dot(self,a,b):return self.total(self.mul(x,y) for x,y in zip(a,b))
    def mv(self,h,v):return [self.dot(line,v) for line in h]
    def quad(self,h,v):return self.dot(v,self.mv(h,v))
    def read(self,p):self.charge('metadata_bytes',p.stat().st_size);return load(p)
    def sha(self,p):self.charge('fingerprint_bytes',p.stat().st_size);return hashlib.sha256(p.read_bytes()).hexdigest()
    def save(self,out,stage,done):write(out/f'accounting_{stage}.json',{'completed':done,'used':self.used,'limits':self.limits,'all_limits_met':all(self.used[k]<=v for k,v in self.limits.items())})

def inputs(q):
    d={str(p):q.read(p) for p in META}
    con=row(d[str(CON/'results.json')]);cap=row(d[str(CAP/'results.json')])['capacity'];wit=row(d[str(ALIGN/'results.json')],True);mean=row(d[str(MEAN/'results.json')]);space=d[str(SPACE/'results.json')]
    for folder in (CON,ALIGN,MEAN):
        for name in ('verification.json','independent_check.json'):assert d[str(folder/name)]['passed']
    assert d[str(CAP/'verification.json')]['passed'] and d[str(SPACE/'independent_check.json')]['passed']
    assert wit['codes']==space['witness_codes'] and wit['codes'][:2]==cap['legal_low_Q10_witness']
    assert wit['held_loss']['exact']==mean['total']['losses']['held']['exact']==cap['held_loss']['exact']
    assert wit['total']['integer_loss']['exact']==space['witness_MSE']['exact']
    assert mean['high_requested_components_nonzero']==mean['high_export_changed_windows']==mean['state_clipped_components']==0
    assert mean['coefficient_export_min'][2:]==mean['coefficient_export_max'][2:]==wit['initial_codes'][2:]
    assert str(STATE) in paths(d[str(MEAN/'candidate_hashes.json')])
    # Cached scalar evidence and original-full row are bound to the same source generation.
    assert paths(d[str(CON/'source_hashes.json')])[str(ALIGN/'results.json')]==d[str(SPACE/'protocol.json')]['source_hashes'][str(ALIGN/'results.json')]
    space['qualification_CAP_SHA']=d[str(SPACE/'protocol.json')]['source_hashes'][str(CAP/'results.json')]
    return con,cap,wit,mean,space,paths(d[str(MEAN/'candidate_hashes.json')])[str(STATE)]

def guards(out,p,q):
    for n,z in p['source_hashes'].items():assert q.sha(Path(n))==z,n
    assert q.sha(Path(__file__))==q.sha(out/'frozen_analysis.py')==p['execution_sha256']

def controls(q):
    # Exact bridge from mean continuous difference to actual integer witness.
    a,b,c=F(3),F(2),F(1)
    assert q.add(q.add(q.sub(a,b),q.sub(b,c)),F(0))==q.sub(a,c)
    h=F(2);g=F(-1);v=F(1,4);u=F(1,2)
    f=lambda x:q.add(q.mul(g,x),q.mul(h,q.mul(x,x)))
    assert q.sub(f(u),f(v))==q.add(q.mul(g,q.sub(u,v)),q.mul(h,q.sub(q.mul(u,u),q.mul(v,v))))
    # Coefficient centering does not make the basis-weighted error orthogonal.
    assert q.div(q.add(q.mul(F(1),F(-1)),q.mul(F(2),F(1))),F(2))==F(1,2)
    assert round(F(4096+2048,4096))==2 and round(F(8192+2048,4096))==2
    assert abs(F(-1,10))<F(1) and abs(F(1,20))<F(1)
    assert q.sub(F(1),F(1,10))>F(0) and q.add(F(-1),F(2))>0
    return {'passed':True,'exact_controls':6,'no_ADC_readouts':True,'nonorthogonal_centering_and_quadratic_bridge':True}

def prepare(out):
    assert not out.exists(),'Refuse overwrite'
    meta=sum(p.stat().st_size for p in META);files=sum(p.stat().st_size for p in FILES);code=Path(__file__).stat().st_size
    prior=ROOT/'artifacts/research/mean_shadow_position_bridge_20261015_v2'
    prior_record=load(prior/'preparation_correction.json');prior_used=load(prior/'accounting_preparation.json')['used']
    assert prior_record['new_states_or_bounds_computed']==0
    past_meta=prior_record['actual_cumulative_metadata_bytes']
    q=Budget({'metadata_bytes':past_meta+meta,'fingerprint_bytes':prior_used['fingerprint_bytes']+files+2*code,'fraction_add':128,'fraction_mul':128,'fraction_div':16})
    q.charge('metadata_bytes',past_meta)
    for k in ('fingerprint_bytes','fraction_add','fraction_mul','fraction_div'):q.charge(k,prior_used[k])
    _,_,_,_,space,state_sha=inputs(q);ctrl=controls(q)
    hashes={str(p):q.sha(p) for p in FILES};assert hashes[str(STATE)]==state_sha
    assert hashes[str(CAP/'results.json')]==space['qualification_CAP_SHA']
    own=q.sha(Path(__file__));out.mkdir(parents=True);shutil.copyfile(Path(__file__),out/'frozen_analysis.py');assert q.sha(out/'frozen_analysis.py')==own
    common={'metadata_bytes':meta,'fingerprint_bytes':2*(files+2*code),'state_low_values':2*(W+1),'export_mean_cells':2*W,
            'fraction_add':4000,'fraction_mul':4000,'fraction_div':256}
    p={'version':'EXP076-saved-mean-location-bridge-v3','date':'2026-10-15','case':list(KEY),
       'authority':'User continues D136..140; STATUS asks whether mean-shadow remaining witness gap is average location or continued change.',
       'scope':'Exactly one original mean-shadow trajectory625 prefix/quarter/2048 windows/eight blocks; total-record classification only. Original full scalar mean relation reused. Initial-shadow trajectory not expanded.',
       'reference':'J(d)=MSE(Yheld+psi*d), old fixed-rear/high basis; dF arithmetic mean OUTPUT-BEFORE low2 exports relative initial K0. Non-grid continuous difference, not a legal mean readout or online initializer.',
       'identity':'LF-LW=A+U+E, A=J(dF)-J(dW), U=LF-J(dF), E=J(dW)-LW. U jointly contains actual temporal change and current Q3/final-code remainder; never call U pure variation or variance. Keep curvature and all crosses through exact quadratic J.',
       'reuse':'Old H and J gradient at original-full mean with certified coordinate intervals; old legal W and actual scores. Recover g0=gFull-2H*dFull. Position f(d)=g0*d+dHd; common-target difference uses g0*(dF-dW)+Q(dF)-Q(dW). Independent centered-at-cstar polynomial and direct endpoint-gradient formula.',
       'minimal_missing':'Only new shadow low2 output-before mean; all required whole-record scalar H/gradient/targets/scores exist. Per-window Gram lacks per-window target projection, so separating pure time change from remainder would need new contractions; do not do that unless this combined comparison cannot decide.',
       'prediction':'Remaining mean-location A is positive and exceeds |U|+|E| under old target outer bounds. Otherwise retain mixed/unresolved diagnosis. Also compare full->shadow changes of J mean and U; certify improvement only when endpoints permit.',
       'target':'Reuse original saved dyadic target and existing NG39/43 coordinate and score intervals, no word target/table construction or tighter precision. Common uncertain targets use conservative outer differences, not independent samples.',
       'units':'Old JSON and low2 Q22 values; SHA full-file reads include self/frozen twice per guard and both guards. Export/mean cell kernel contains quotient/remainder rounding, delta and integer accumulation. All scalar rational binary ops wrapped; parse/constructor, fixed-scale denominator, unary/compare/index/display excluded. Generated protocol/results metadata and document/administrative checks separate. No hardware-cost interpretation.',
       'source_hashes':hashes,'execution_sha256':own,'preparation_limits':q.limits,'main_limits':common,'independent_limits':common,
       'prior_failed_preparation':str(prior),'preparation_retry_cumulative_metadata_bytes':past_meta+meta,
       'stop':'One whole-record mean relation/bridge and full-to-shadow split, or preserve failure/missing conditions. No new per-word output/PWL/matrix/policy/target/optimizer/FFT/learning/EXP/NG/holdout. Do not chase small bridge sign or perform extra block decompositions.'}
    write(out/'protocol.json',p);write(out/'controls.json',ctrl);q.save(out,'preparation',True)
    docbytes=0
    for n in DOCS:
        dest=out/'documents_before'/n;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/n,dest);docbytes+=(ROOT/n).stat().st_size
    write(out/'administrative_preparation.json',{'document_snapshot_bytes':docbytes,'files':len(DOCS),'new_scientific_record_calculations_before_freeze':0})
    print('Frozen one saved mean location / actual-minus-mean bridge; no new target/PWL/output.')

def exported_mean(q,mean,wit,independent=False):
    q.charge('state_low_values',2*(W+1));a=np.array(np.memmap(STATE,dtype='<i4',mode='r',shape=(W+1,8))[:,:2],dtype=np.int64)
    assert a[0].tolist()==mean['initial_Q22'][:2]
    q.charge('export_mean_cells',2*W)
    if independent:
        sums=[0,0]
        for row_ in a[:-1]:
            for j,z in enumerate(row_):sums[j]+=round(F(int(z),4096))-wit['initial_codes'][j]
    else:
        quo,rem=np.divmod(a[:-1],4096);k=quo+((rem>2048)|((rem==2048)&(quo%2!=0)))
        assert k[0].tolist()==wit['initial_codes'][:2] and np.all((k>=0)&(k<=2047))
        sums=(k-np.array(wit['initial_codes'][:2])).sum(axis=0).tolist()
    return [F(int(z),W*1024) for z in sums]

def packed(z,bounds=None):
    r={'exact':str(z),'value':float(z)}
    if bounds is not None:r.update(interval=list(map(str,bounds)),sign_certified=bounds[0]>0 or bounds[1]<0)
    return r

def projection(g,box,v,q):
    lo=hi=F(0)
    for z,(a,b) in zip(v,box):
        x,y=q.mul(z,a),q.mul(z,b);lo=q.add(lo,min(x,y));hi=q.add(hi,max(x,y))
    return q.dot(g,v),[lo,hi]

def shift(z,b,x,q):return packed(q.add(z,x),[q.add(t,x) for t in b])
def difference(a,b,q):return packed(q.sub(F(a['exact']),F(b['exact'])),[q.sub(F(a['interval'][0]),F(b['interval'][1])),q.sub(F(a['interval'][1]),F(b['interval'][0]))])
def max_abs(obj):return max(abs(F(z)) for z in obj['interval'])

def analysis(out,independent=False):
    p=load(out/'protocol.json');stage='independent' if independent else 'main';target='independent_check.json' if independent else 'results.json'
    assert not (out/target).exists();q=Budget(p['independent_limits' if independent else 'main_limits']);done=False
    try:
        guards(out,p,q);con,cap,wit,mean,space,_=inputs(q);d=exported_mean(q,mean,wit,independent)
        h=[[F(z) for z in line] for line in con['H']];old_d=list(map(F,con['mean_gap']));dw=[F(wit['codes'][j]-wit['initial_codes'][j],1024) for j in range(2)]
        gf=[F(z['exact']) for z in con['gradient_J']];boxes=[list(map(F,z['interval'])) for z in con['gradient_J']]
        hd=q.mv(h,old_d);g0=[q.sub(gf[j],q.mul(F(2),hd[j])) for j in range(2)]
        b0=[[q.sub(z,q.mul(F(2),hd[j])) for z in line] for j,line in enumerate(boxes)]
        cstar=list(map(F,cap['continuous_minimizer']));hc=q.mv(h,cstar)
        assert g0==[-q.mul(F(2),z) for z in hc]
        held=F(mean['total']['losses']['held']['exact']);lw=F(wit['total']['integer_loss']['exact'])
        def position(v):
            z,b=projection(g0,b0,v,q);power=q.quad(h,v)
            result=shift(z,b,power,q)
            if independent:
                centered=[q.sub(v[j],cstar[j]) for j in range(2)]
                assert F(result['exact'])==q.sub(q.quad(h,centered),q.quad(h,cstar))
            return result
        jf,jw,jo=(position(v) for v in (d,dw,old_d))
        assert jf['sign_certified'] in (True,False)
        assert q.add(held,F(jw['exact']))==F(cap['continuous_witness_loss']['exact'])
        assert jo['exact']==con['position_J']['exact']
        dv=[q.sub(d[j],dw[j]) for j in range(2)];z,b=projection(g0,b0,dv,q)
        a=shift(z,b,q.sub(q.quad(h,d),q.quad(h,dw)),q)
        if independent:
            z2,b2=projection(gf,boxes,dv,q)
            offset=q.sub(q.sub(q.quad(h,d),q.quad(h,dw)),q.mul(F(2),q.dot(old_d,q.mv(h,dv))))
            assert shift(z2,b2,offset,q)==a
        actual=mean['total']['pairs']['candidate_minus_held'];wc=wit['total']['contrasts'][0]['change_from_hold']
        u=difference(actual,jf,q);e=difference(jw,wc,q)
        total=q.total(F(t['exact']) for t in (a,u,e))
        expected=next(r for r in space['rows'] if r['record']=='total' and r['path']=='mean_shadow')
        assert str(total)==expected['gap']['exact']
        full_actual=mean['total']['pairs']['full_minus_held'];uold=difference(full_actual,con['position_J'],q)
        dd=[q.sub(d[j],old_d[j]) for j in range(2)];z,b=projection(g0,b0,dd,q)
        mean_change=shift(z,b,q.sub(q.quad(h,d),q.quad(h,old_d)),q)
        residual_change=difference(mean['total']['pairs']['candidate_minus_full'],mean_change,q)
        assert F(mean_change['exact'])==q.sub(F(jf['exact']),F(jo['exact']))
        assert F(residual_change['exact'])==q.sub(F(u['exact']),F(uold['exact']))
        margin=q.sub(q.sub(F(a['interval'][0]),max_abs(u)),max_abs(e))
        r={'case':list(KEY),'mean_gap':list(map(str,d)),'witness_gap':list(map(str,dw)),
           'mean_J_MSE':packed(q.add(held,F(jf['exact']))),'witness_J_MSE':packed(q.add(held,F(jw['exact']))),
           'mean_position_minus_held':jf,'mean_location_minus_witness_continuous':a,
           'actual_minus_mean_combined':u,'witness_continuous_minus_integer':e,
           'actual_minus_witness':expected,'position_lower_minus_other_absolute_upper':packed(margin),
           'mean_location_dominance_certified':margin>0,
           'full_to_shadow_mean_location_change':mean_change,'full_to_shadow_combined_change':residual_change,
           'old_full_actual_minus_mean_combined':uold,'full_to_shadow_total':mean['total']['pairs']['candidate_minus_full'],
           'pure_time_variation_separated_from_readout_rounding':False}
        guards(out,p,q)
        if independent:
            assert r==load(out/'results.json')
            write(out/target,{'passed':True,'independent_scalar_Fraction_export_and_centered_quadratic_exact':True,
                'direct_old_endpoint_gradient_and_all_interval_bridges_exact':True,'new_scientific_readouts_learning_scores':0})
            write(out/'summary.json',{'passed':True,'mean_location_dominance_certified':margin>0,
                'mean_location_gap':a,'combined_path_term':u,'bridge':e,'full_to_shadow_mean_change':mean_change,
                'full_to_shadow_combined_change':residual_change,'all_original_limits_met':True,
                'no_pure_variance_physical_share_or_online_algorithm_claim':True})
        else:write(out/target,r)
        done=True;print(stage,'position gap=',a['value'],'actual-minus-mean=',u['value'],'dominance=',margin>0)
    finally:q.save(out,stage,done)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('prepare','analyze','check'));ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    try:
        if args.mode=='prepare':prepare(args.out)
        else:analysis(args.out,args.mode=='check')
    except Exception:
        if args.out.exists():write(args.out/f'failure_{args.mode}.json',{'traceback':traceback.format_exc()})
        raise
