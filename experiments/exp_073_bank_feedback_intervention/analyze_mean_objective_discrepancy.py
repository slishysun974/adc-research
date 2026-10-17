"""Existing-moment metric/target decomposition; no ADC readouts or scores.

The canonical transform H A^-1 is an offline diagnostic, not an updater.
All arithmetic is rational; counters wrap every declared binary operation.
"""
import argparse
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import shutil
import traceback
import numpy as np

ROOT=Path('D:/ADC');W=2048
ALIGN=ROOT/'artifacts/research/front_fixed_alignment_20261014_v2'
PARAM=ROOT/'artifacts/research/front_low_parameter_statistics_20261014_v1'
HISTORY=ROOT/'artifacts/research/front_forcing_response_20261013_v2'
BASE=ROOT/'artifacts/runs/EXP_072/finite_v1'
NEW=ROOT/'artifacts/runs/EXP_073/bank_feedback_v1'
KINDS=('continuous_front','Q3','rounded_Q22')
DOCS=['docs/STATUS.md','docs/DECISIONS.md','docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md',
      'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md','docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md',
      'docs/reports/GU_ALGORITHM_EVALUATION_V1.md','docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
      'docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md',
      'docs/reports/experiments/EXP_073_BANK_FEEDBACK_INTERVENTION_V1.md',
      'experiments/exp_073_bank_feedback_intervention/README.md']

def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def digest(p):
    h=sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(4*1024*1024),b''):h.update(chunk)
    return h.hexdigest()

class Budget:
    def __init__(self,limits):self.limits=limits;self.used=dict.fromkeys(limits,0)
    def charge(self,k,n=1):
        assert self.used[k]+n<=self.limits[k],(k,self.used[k],n,self.limits[k])
        self.used[k]+=n
    def add(self,a,b):self.charge('fraction_add');return a+b
    def sub(self,a,b):self.charge('fraction_add');return a-b
    def mul(self,a,b):self.charge('fraction_mul');return a*b
    def div(self,a,b):self.charge('fraction_div');return a/b
    def ia(self,a,b):self.charge('history_integer_add');return a+b
    def isu(self,a,b):self.charge('history_integer_add');return a-b
    def im(self,a,b):self.charge('history_integer_mul');return a*b

def dot(a,b,q):return q.add(q.mul(a[0],b[0]),q.mul(a[1],b[1]))
def mv(a,v,q):return [dot(row,v,q) for row in a]
def mm(a,b,q):return [[dot(a[i],[b[0][j],b[1][j]],q) for j in range(2)] for i in range(2)]
def inv(a,q):
    det=q.sub(q.mul(a[0][0],a[1][1]),q.mul(a[0][1],a[1][0]));assert det
    return [[q.div(a[1][1],det),q.div(-a[0][1],det)],
            [q.div(-a[1][0],det),q.div(a[0][0],det)]]
def pack(z):return {'exact':str(z),'value':float(z)}
def ranged(z,lo,hi):return {**pack(z),'interval':[str(lo),str(hi)],'sign_certified':lo>0 or hi<0}
def shifted_interval(ref,shift,q):
    return ranged(q.sub(F(ref['exact']),shift),q.sub(F(ref['interval'][0]),shift),q.sub(F(ref['interval'][1]),shift))

def controls():
    q=Budget({'fraction_add':256,'fraction_mul':256,'fraction_div':256})
    ident=[[F(1),F(0)],[F(0),F(1)]];c=[F(1),F(0)];v=[F(-1),F(0)]
    m=mm(ident,inv(ident,q),q);w=mv(m,c,q);g=[F(-1),F(0)]
    r=[q.sub(q.div(g[i],F(2)),w[i]) for i in range(2)]
    dm=q.mul(F(2),dot(w,v,q));dr=q.mul(F(2),dot(r,v,q))
    assert dm==-2 and dr==3 and q.add(dm,dr)==dot(g,v,q)==1
    g0=[F(2),F(0)];assert dot(g0,v,q)==-2
    # Invertible statistics and H>0 do not alone force a descent metric.
    a=[[F(1),F(4)],[F(0),F(1)]];m=mm(ident,inv(a,q),q)
    c=[F(2),F(1)];v=[F(-2),F(-3)];w=mv(m,c,q)
    assert q.mul(F(2),dot(w,v,q))==2
    # A known metric component shifts the target interval without widening it.
    z=shifted_interval({'exact':'1','interval':['9/10','11/10']},F(-2),q)
    assert z['interval']==['29/10','31/10']
    # Endpoint gradient and exact quadratic position loss agree.
    assert q.sub(q.mul(F(10),F(3)),q.mul(F(2),F(9)))==12
    # Output-before-update and nearest-even mean-grid controls.
    u=[1,2,-1,99];states=[sum(u[:j]) for j in range(4)]
    assert F(sum(states),4)==F(sum((3-j)*u[j] for j in range(4)),4)==F(3,2)
    assert round(F(3,2))==2 and round(F(5,2))==2
    return {'passed':True,'exact_controls':7,'arithmetic':q.used,'new_readouts_or_source':0}

def freeze(out):
    assert not out.exists(),'Refuse overwrite';out.mkdir(parents=True)
    qualification=load(PARAM/'delivery_verification.json')
    assert qualification['passed'] and qualification['original_operation_budget_met'] is False
    assert load(ALIGN/'independent_check.json')['passed'] and load(PARAM/'independent_check.json')['passed']
    files=[ALIGN/'results.json',PARAM/'results.json',ALIGN/'independent_check.json',PARAM/'independent_check.json',
           PARAM/'delivery_verification.json',PARAM/'accounting_reconciliation.json',PARAM/'source_correction.json']
    for seed in range(202610621,202610626):
        for rate in ('base','quarter'):
            files.extend([BASE/f'{seed}_{rate}_q22.bin',NEW/f'{seed}_{rate}_q22.bin'])
            for init in ('actual','prefix'):files.append(HISTORY/f'{seed}_{rate}_{init}_front_moments.bin')
    prior=load(ALIGN/'source_hashes.json')
    manifest={}
    for p in files:
        sha=digest(p)
        if str(p) in prior:assert sha==prior[str(p)],p
        manifest[str(p)]=sha
    write(out/'source_hashes.json',manifest)
    sources=list((ROOT/'src/adc_research').rglob('*.py'))+list((ROOT/'experiments').rglob('*.py'))
    write(out/'execution_hashes.json',{str(p):digest(p) for p in sources})
    shutil.copyfile(Path(__file__),out/'frozen_analysis.py')
    for name in DOCS:
        dest=out/'documents_before'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,dest)
    metadata_bytes=(ALIGN/'results.json').stat().st_size+(PARAM/'results.json').stat().st_size
    fingerprint_bytes=2*sum(Path(p).stat().st_size for p in manifest)+2*sum(Path(p).stat().st_size for p in load(out/'execution_hashes.json'))
    limits={'metadata_json_bytes':metadata_bytes,'moment_values':20*W*4,'initial_Q22_values':20*8,'terminal_Q22_values':20*2,
            'positions':40,'matrix_objects':80,'direction_objects':240,'history_objects':20,
            'fraction_add':16000,'fraction_mul':16000,'fraction_div':2000,
            'history_integer_mul':20*(4*W+6),'history_integer_add':20*(10*W+6),'history_export_round_checks':20*W*2,
            'fingerprint_bytes':fingerprint_bytes}
    independent=dict(limits);independent.update({'initial_Q22_values':20*2,
        'history_integer_mul':20*W*2,'history_integer_add':20*(10*W+6),'history_export_round_checks':20*W*2})
    write(out/'protocol.json',{
        'version':'EXP073-existing-moment-metric-target-and-position-history-v1','date':'2026-10-14',
        'authority':'User continues approved D136..140 mainline; STATUS fixed40 A/H/C/gradient decomposition.',
        'scope':'Same40 positions, full/selected2 low statistics:80 transforms and240 already-stored continuous/Q3/Q22 directions;20 mean-position weighted histories. No block extension, extra position, root, optimization or learner.',
        'theory':'M=H*A^-1; w=M*C_cont; r=g/2-w. D=g dot v=2w dot v+2r dot v for each stored direction. S0=sym(M^T*diag(1,3)) classifies target-free metric for the continuous Gu direction. No assumption of positivity, component sign or physical independent shares.',
        'target':'g and its intervals are old true continuous-front/fixed Q3-rear output loss, saved real nominal target with NG39/43 conditions. Metric part uses digital A/H/C only; r still needs offline target, and includes fixed high/readout/input effects, not solely unknown analog nonlinearity.',
        'history':'Actual output-before Q22 A_s and requests u_s, exported K_s: K_mean_legal-K0 split into initial hidden export residual, triangular-weighted actual requests, mean actual export residual, and final mean-to-grid rounding; exact Q22 normalization2^22. Position loss L*(Kmean)-L*(K0)=g_at_mean dot delta-delta^T H delta. Endpoint M*C/r projection is an algebraic reference, not causal historical share; masks need not be preserved along history for quadratic output identity.',
        'predictions':['M*A=H and r+w=g/2 exactly; all240 derivatives and mean-step polynomials recover stored values.',
            'If S0>0, continuous metric direction is strictly downhill for nonzero C; certified uphill cases then require residual projection to exceed that descent.',
            'Indefinite S0 or an actual uphill metric term retains weighting as an explanation independent of target mismatch.',
            'All20 request-weighted histories and legal mean states reproduce, including hidden/mean-grid residuals; endpoint position identity and current integer contrast differ only by a recorded readout-quantization correction.',
            'No shared root or future benefit inferred even if r is nonzero or one component is large.'],
        'budget_units':'All binary Fraction add/sub/mul/div use counted wrappers; word-history integer data products/reductions and nearest-even export checks likewise. Fraction construction/parsing, unary signs/abs, comparisons, constant/loop/index arithmetic, serialization and display conversions are excluded, with finite40/80/240/20 object caps. Hash I/O bytes recorded separately. No simulated conversions/PWL/gates/request recomputation/output or MSE scoring/FFT.',
        'limits':limits,'independent_limits':independent,
        'independent':'Solve A*x=C and M*A=H by independent two-equation rational elimination (no inverse helper). Reconstruct state means by direct prefix averaging rather than request triangular weights; exact component/position/interval identities. Sources and prior budget failure retained.',
        'stop':'Finish same80/240/20 or reject arithmetic/source/normalization/budget mismatch. Preserve failure; no automatic new run, point, precision, long axis, future6007/8009, new algorithm or hardware.'})
    write(out/'controls.json',controls())

def guard(out,q):
    for f in ('source_hashes.json','execution_hashes.json'):
        for path,sha in load(out/f).items():
            p=Path(path);q.charge('fingerprint_bytes',p.stat().st_size);assert digest(p)==sha,path

def input_rows(q):
    rows=[]
    for p in (ALIGN/'results.json',PARAM/'results.json'):
        q.charge('metadata_json_bytes',p.stat().st_size);rows.append(load(p)['rows'])
    param={(r['seed'],r['rate'],r['initialization'],r['reference']):r for r in rows[1]}
    return rows[0],param

def history(row,q):
    seed,rate,init=row['seed'],row['rate'],row['initialization'];idx=0 if init=='actual' else 2
    name=f'{seed}_{rate}_{init}';q.charge('moment_values',W*4)
    mom=np.memmap(HISTORY/f'{name}_front_moments.bin',dtype='<i8',mode='r',shape=(W,24))
    u=np.array(mom[:,:2],dtype=np.int64);k=np.array(mom[:,10:12],dtype=np.int64)
    q.charge('initial_Q22_values',8)
    a0=list(map(int,np.memmap(BASE/f'{seed}_{rate}_q22.bin',dtype='<i4',mode='r',shape=(W+1,4,8))[0,idx]))
    current=a0[:2].copy();tri=[0,0];er=[0,0];ks=[0,0]
    for w in range(W):
        for j in range(2):
            uj,kj=int(u[w,j]),int(k[w,j]);q.charge('history_export_round_checks')
            assert round(F(current[j],4096))==kj and 0<=current[j]<=2047*4096
            tri[j]=q.ia(tri[j],q.im(W-1-w,uj))
            er[j]=q.ia(er[j],q.isu(q.im(4096,kj),current[j]))
            ks[j]=q.ia(ks[j],kj);current[j]=q.ia(current[j],uj)
    q.charge('terminal_Q22_values',2)
    terminal=list(map(int,np.memmap(NEW/f'{seed}_{rate}_q22.bin',dtype='<i4',mode='r',shape=(W+1,4,8))[W,idx,:2]))
    assert current==terminal
    initial=[F(q.isu(a0[j],q.im(4096,row['initial_codes'][j])),1<<22) for j in range(2)]
    weighted=[F(tri[j],W*(1<<22)) for j in range(2)]
    export=[F(er[j],W*(1<<22)) for j in range(2)]
    finalgrid=[F(q.im(4096,q.isu(q.im(W,row['codes'][j]),ks[j])),W*(1<<22)) for j in range(2)]
    delta=[F(q.isu(row['codes'][j],row['initial_codes'][j]),1024) for j in range(2)]
    assert row['codes'][:2]==[round(F(z,W)) for z in ks]
    parts=[initial,weighted,export,finalgrid]
    for j in range(2):
        total=q.add(q.add(parts[0][j],parts[1][j]),q.add(parts[2][j],parts[3][j]));assert total==delta[j]
    q.charge('history_objects')
    return {'delta':list(map(str,delta)),'parts':{t:list(map(str,v)) for t,v in zip(('initial_hidden','weighted_requests','mean_export','mean_grid'),parts)}}

def analyze(out):
    assert not (out/'results.json').exists();assert digest(Path(__file__))==digest(out/'frozen_analysis.py')
    protocol=load(out/'protocol.json');q=Budget(protocol['limits']);done=[];positions=[]
    try:
        guard(out,q);assert load(out/'controls.json')['passed'];rows,params=input_rows(q)
        for row in rows:
            q.charge('positions');key=(row['seed'],row['rate'],row['initialization'],row['reference']);param=params[key]
            assert row['codes']==param['codes']
            h=[[F(z) for z in r] for r in row['total']['H']];g=[F(z['exact']) for z in row['total']['gradient']]
            hist=history(row,q) if row['reference']=='mean' else None
            pdata=[]
            for method in ('selected','full'):
                q.charge('matrix_objects');a=[[F(z) for z in line] for line in param['total']['matrices'][method+'_continuous_mask']['A']]
                m=mm(h,inv(a,q),q);assert mm(m,a,q)==h
                rate=1 if row['rate']=='base' else 4;lam=[F(3072*z,25*rate*(1<<22)) for z in (1,3)]
                primary=row['total']['directions'][method+'_continuous_front']
                cv=[q.div(-F(v),l) for v,l in zip(primary['mean_step_low2'],lam)]
                w=mv(m,cv,q);r=[q.sub(q.div(g[j],F(2)),w[j]) for j in range(2)]
                rbox=[[q.sub(q.div(F(z),F(2)),w[j]) for z in row['total']['gradient'][j]['interval']] for j in range(2)]
                s0=[[m[0][0],q.div(q.add(m[0][1],q.mul(F(3),m[1][0])),F(2))],
                    [F(0),q.mul(F(3),m[1][1])]];s0[1][0]=s0[0][1]
                determinant=q.sub(q.mul(s0[0][0],s0[1][1]),q.mul(s0[0][1],s0[1][0]))
                item={'method':method,'A':[[str(z) for z in line] for line in a],
                      'M':[[str(z) for z in line] for line in m],'C':list(map(str,cv)),
                      'metric_half_gradient':list(map(str,w)), 'residual_half_gradient':list(map(str,r)),
                      'residual_component_intervals':[[str(z) for z in line] for line in rbox],
                      'residual_nonzero_certified':any(lo>0 or hi<0 for lo,hi in rbox),
                      'S0':[[str(z) for z in line] for line in s0],'S0_determinant':str(determinant),
                      'S0_positive_definite':s0[0][0]>0 and determinant>0,'directions':{}}
                for kind in KINDS:
                    q.charge('direction_objects');old=row['total']['directions'][method+'_'+kind]
                    v=list(map(F,old['mean_step_low2']));dm=q.mul(F(2),dot(w,v,q));dr=q.mul(F(2),dot(r,v,q))
                    total=q.add(dm,dr);assert total==dot(g,v,q)==F(old['derivative']['exact'])
                    curvature=dot(v,mv(h,v,q),q)
                    assert q.add(total,curvature)==F(old['mean_step_continuous_loss_change']['exact'])
                    residual=shifted_interval(old['derivative'],dm,q);assert F(residual['exact'])==dr
                    item['directions'][kind]={'metric':pack(dm),'residual':residual,'total':old['derivative'],
                                              'curvature':pack(curvature),'finite_mean_step_change':old['mean_step_continuous_loss_change']}
                if hist:
                    delta=list(map(F,hist['delta']));dc=dot(delta,mv(h,delta,q),q)
                    metric=q.mul(F(2),dot(w,delta,q));residual=q.mul(F(2),dot(r,delta,q))
                    gl=dot(g,delta,q);change=q.sub(gl,dc);assert q.sub(q.add(metric,residual),dc)==change
                    lo=q.add(min(q.mul(F(row['total']['gradient'][0]['interval'][0]),delta[0]),q.mul(F(row['total']['gradient'][0]['interval'][1]),delta[0])),
                             min(q.mul(F(row['total']['gradient'][1]['interval'][0]),delta[1]),q.mul(F(row['total']['gradient'][1]['interval'][1]),delta[1])))
                    hi=q.add(max(q.mul(F(row['total']['gradient'][0]['interval'][0]),delta[0]),q.mul(F(row['total']['gradient'][0]['interval'][1]),delta[0])),
                             max(q.mul(F(row['total']['gradient'][1]['interval'][0]),delta[1]),q.mul(F(row['total']['gradient'][1]['interval'][1]),delta[1])))
                    contributions={}
                    for tag,vs in hist['parts'].items():
                        vector=list(map(F,vs));contributions[tag]={'metric_projection':pack(q.mul(F(2),dot(w,vector,q))),
                            'residual_projection':pack(q.mul(F(2),dot(r,vector,q)))}
                    item['position']={'metric_projection':pack(metric),'residual_projection':ranged(residual,q.sub(lo,metric),q.sub(hi,metric)),
                                      'curvature_subtracted':pack(dc),'continuous_change':ranged(change,q.sub(lo,dc),q.sub(hi,dc)),
                                      'integer_change':row['total']['contrasts'][0]['change_from_hold'],
                                      'integer_readout_correction':pack(q.sub(F(row['total']['contrasts'][0]['change_from_hold']['exact']),change)),
                                      'history_component_projections':contributions}
                    pdata.append(item['position'])
                done.append({'seed':row['seed'],'rate':row['rate'],'initialization':row['initialization'],
                             'reference':row['reference'],'codes':row['codes'],'gradient':row['total']['gradient'],**item})
            if hist:
                assert pdata[0]['continuous_change']==pdata[1]['continuous_change']
                positions.append({'seed':row['seed'],'rate':row['rate'],'initialization':row['initialization'],'history':hist})
        assert len(done)==80 and len(positions)==20
        guard(out,q);write(out/'results.json',{'completed':True,'rows':done,'positions':positions})
        write(out/'verification.json',{'passed':True,'transforms':80,'directions':240,'histories':20,
                                        'all_old_direction_polynomials_exact':True,'new_record_readouts_requests_scores_fft':0})
    finally:write(out/'accounting_main.json',{'limits':q.limits,'used':q.used,'all_limits_met':all(q.used[k]<=q.limits[k] for k in q.limits),'completed':len(done)==80 and len(positions)==20})

def check(out):
    assert not (out/'independent_check.json').exists();p=load(out/'protocol.json');q=Budget(p['independent_limits']);count=0
    try:
        guard(out,q);source,param=input_rows(q);old={(r['seed'],r['rate'],r['initialization'],r['reference']):r for r in source}
        result=load(out/'results.json');positions={(r['seed'],r['rate'],r['initialization']):r for r in result['positions']}
        def solve(a,y):
            # Independent row elimination. All current A00 are nonzero; swap
            # locally if needed, without changing the main inverse calculation.
            a=[z.copy() for z in a];y=y.copy()
            if not a[0][0]:a.reverse();y.reverse()
            factor=q.div(a[1][0],a[0][0]);pivot=q.sub(a[1][1],q.mul(factor,a[0][1]))
            rhs=q.sub(y[1],q.mul(factor,y[0]));x1=q.div(rhs,pivot)
            x0=q.div(q.sub(y[0],q.mul(a[0][1],x1)),a[0][0]);return [x0,x1]
        for r in result['rows']:
            key=(r['seed'],r['rate'],r['initialization'],r['reference']);original=old[key]
            q.charge('matrix_objects');a=[[F(z) for z in line] for line in r['A']];c=list(map(F,r['C']))
            h=[[F(z) for z in line] for line in original['total']['H']];x=solve(a,c)
            w=[q.add(q.mul(row[0],x[0]),q.mul(row[1],x[1])) for row in h]
            assert list(map(str,w))==r['metric_half_gradient']
            m=[[F(z) for z in line] for line in r['M']]
            for i in range(2):
                for j in range(2):assert q.add(q.mul(m[i][0],a[0][j]),q.mul(m[i][1],a[1][j]))==h[i][j]
            gg=list(map(lambda z:F(z['exact']),original['total']['gradient']))
            residual=[q.sub(q.div(gg[j],F(2)),w[j]) for j in range(2)]
            assert list(map(str,residual))==r['residual_half_gradient']
            for j in range(2):
                for z in (0,1):
                    assert q.sub(q.div(F(original['total']['gradient'][j]['interval'][z]),F(2)),w[j])==F(r['residual_component_intervals'][j][z])
            # Symmetrize diag(1,3)*M independently, then verify the metric form.
            l=[[m[0][0],m[0][1]],[q.mul(F(3),m[1][0]),q.mul(F(3),m[1][1])]]
            sym=[[q.div(q.add(l[i][j],l[j][i]),F(2)) for j in range(2)] for i in range(2)]
            assert [[str(z) for z in line] for line in sym]==r['S0']
            sd=q.sub(q.mul(sym[0][0],sym[1][1]),q.mul(sym[0][1],sym[1][0]))
            assert str(sd)==r['S0_determinant'] and (sym[0][0]>0 and sd>0)==r['S0_positive_definite']
            rate=1 if r['rate']=='base' else 4
            for j,mult in enumerate((1,3)):
                expected=q.mul(-F(3072*mult,25*rate*(1<<22)),c[j])
                assert expected==F(original['total']['directions'][r['method']+'_continuous_front']['mean_step_low2'][j])
            for kind in KINDS:
                q.charge('direction_objects');vv=list(map(F,original['total']['directions'][r['method']+'_'+kind]['mean_step_low2']))
                vpart=q.add(q.mul(w[0],vv[0]),q.mul(w[1],vv[1]));targetpart=q.add(q.mul(residual[0],vv[0]),q.mul(residual[1],vv[1]))
                stored=r['directions'][kind]
                assert q.mul(F(2),vpart)==F(stored['metric']['exact'])
                assert q.mul(F(2),targetpart)==F(stored['residual']['exact'])
                assert q.mul(F(2),q.add(vpart,targetpart))==F(stored['total']['exact'])
                for j in (0,1):assert q.sub(F(stored['total']['interval'][j]),F(stored['metric']['exact']))==F(stored['residual']['interval'][j])
            count+=1
        for item in result['positions']:
            q.charge('history_objects');seed,rate,init=item['seed'],item['rate'],item['initialization'];idx=0 if init=='actual' else 2
            rr=old[seed,rate,init,'mean'];q.charge('moment_values',W*4)
            mom=np.memmap(HISTORY/f'{seed}_{rate}_{init}_front_moments.bin',dtype='<i8',mode='r',shape=(W,24))
            q.charge('initial_Q22_values',2);a0=list(map(int,np.memmap(BASE/f'{seed}_{rate}_q22.bin',dtype='<i4',mode='r',shape=(W+1,4,8))[0,idx,:2]))
            current=a0.copy();state_sum=[0,0];export_sum=[0,0];k_sum=[0,0]
            for w in range(W):
                for j in range(2):
                    uj,kj=int(mom[w,j]),int(mom[w,10+j]);q.charge('history_export_round_checks')
                    assert round(F(current[j],4096))==kj
                    state_sum[j]=q.ia(state_sum[j],current[j]);k_sum[j]=q.ia(k_sum[j],kj)
                    export_sum[j]=q.ia(export_sum[j],q.isu(q.im(4096,kj),current[j]))
                    current[j]=q.ia(current[j],uj)
            q.charge('terminal_Q22_values',2)
            assert current==list(map(int,np.memmap(NEW/f'{seed}_{rate}_q22.bin',dtype='<i4',mode='r',shape=(W+1,4,8))[W,idx,:2]))
            weighted=[q.sub(F(state_sum[j],W*(1<<22)),F(a0[j],1<<22)) for j in range(2)]
            assert list(map(str,weighted))==item['history']['parts']['weighted_requests']
            assert [str(F(v,W*(1<<22))) for v in export_sum]==item['history']['parts']['mean_export']
            assert [str(q.sub(F(a0[j],1<<22),F(rr['initial_codes'][j],1024))) for j in range(2)]==item['history']['parts']['initial_hidden']
            assert [str(q.sub(F(rr['codes'][j],1024),F(k_sum[j],W*1024))) for j in range(2)]==item['history']['parts']['mean_grid']
            assert rr['codes'][:2]==[round(F(v,W)) for v in k_sum]
            delta=list(map(F,item['history']['delta']));h=[[F(z) for z in line] for line in rr['total']['H']]
            g=list(map(lambda z:F(z['exact']),rr['total']['gradient']))
            # Independent output polynomial using gradient at initial position.
            hd=[q.add(q.mul(h[j][0],delta[0]),q.mul(h[j][1],delta[1])) for j in range(2)]
            g0=[q.sub(g[j],q.mul(F(2),hd[j])) for j in range(2)]
            change=q.add(q.add(q.mul(g0[0],delta[0]),q.mul(g0[1],delta[1])),
                         q.add(q.mul(hd[0],delta[0]),q.mul(hd[1],delta[1])))
            for rr2 in [z for z in result['rows'] if (z['seed'],z['rate'],z['initialization'],z['reference'])==(seed,rate,init,'mean')]:
                assert change==F(rr2['position']['continuous_change']['exact'])
                assert q.add(change,F(rr2['position']['integer_readout_correction']['exact']))==F(rr2['position']['integer_change']['exact'])
                ww=list(map(F,rr2['metric_half_gradient']));rv=list(map(F,rr2['residual_half_gradient']))
                metric_sum=target_sum=F(0)
                for name,vec in item['history']['parts'].items():
                    vec=list(map(F,vec))
                    mp=q.mul(F(2),q.add(q.mul(ww[0],vec[0]),q.mul(ww[1],vec[1])))
                    tp=q.mul(F(2),q.add(q.mul(rv[0],vec[0]),q.mul(rv[1],vec[1])))
                    cp=rr2['position']['history_component_projections'][name]
                    assert mp==F(cp['metric_projection']['exact']) and tp==F(cp['residual_projection']['exact'])
                    metric_sum=q.add(metric_sum,mp);target_sum=q.add(target_sum,tp)
                assert metric_sum==F(rr2['position']['metric_projection']['exact'])
                assert target_sum==F(rr2['position']['residual_projection']['exact'])
        assert count==80;guard(out,q)
        write(out/'independent_check.json',{'passed':True,'transforms':80,'directions':240,'histories':20,
                                           'independent_elimination_and_prefix_means_exact':True,'new_readouts_scores_or_paths':0})
    finally:write(out/'accounting_independent.json',{'limits':q.limits,'used':q.used,'all_limits_met':all(q.used[k]<=q.limits[k] for k in q.limits),'completed':count==80})

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['freeze','analyze','check']);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    try:{'freeze':freeze,'analyze':analyze,'check':check}[a.mode](a.out)
    except Exception:
        if a.out.exists():write(a.out/(a.mode+'_failure.json'),{'traceback':traceback.format_exc()})
        raise
