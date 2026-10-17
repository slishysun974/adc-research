"""Grant ideal Gu target orthogonality; audit one existing output direction.

Scalar reuse only, no data arrays, physical counterfactuals, learners or scores.
"""
from pathlib import Path
from fractions import Fraction as F
import argparse
import hashlib
import json
import shutil
import traceback

ROOT=Path('D:/ADC');BASE=ROOT/'artifacts/research'
DIR=BASE/'mean_shadow_direction_information_20261015_v1'
STAT=BASE/'full_front_fixed_mean_statistics_20261014_v1'
CON=BASE/'full_front_mean_learning_20261014_v1'
FIX=BASE/'fixed_shadow_statistics_20261015_v1'
FILES=[DIR/'results.json',DIR/'protocol.json',DIR/'independent_check.json',
       STAT/'results.json',STAT/'verification.json',STAT/'independent_check.json',
       CON/'results.json',CON/'verification.json',CON/'independent_check.json',FIX/'protocol.json']
KEY=(202610625,'quarter','prefix');N=245760

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def row(d):return next(r for r in d['rows'] if (r['seed'],r['rate'],r['initialization'])==KEY)

class Budget:
    def __init__(self,limits):self.limits=limits;self.used={k:0 for k in limits}
    def charge(self,k,n=1):
        self.used[k]+=n;assert self.used[k]<=self.limits[k],(k,self.used[k],self.limits[k])
    def add(self,a,b):self.charge('fraction_add');return a+b
    def sub(self,a,b):self.charge('fraction_add');return a-b
    def mul(self,a,b):self.charge('fraction_mul');return a*b
    def div(self,a,b):self.charge('fraction_div');return a/b
    def dot(self,a,b):return self.add(self.mul(a[0],b[0]),self.mul(a[1],b[1]))
    def mv(self,m,v):return [self.dot(line,v) for line in m]

def prepare(out):
    assert not out.exists(),'Refuse overwrite';out.mkdir(parents=True)
    files=FILES+[Path(__file__).resolve()];size=sum(p.stat().st_size for p in files)
    limits={'old_json_bytes':sum(p.stat().st_size for p in FILES),
            'fingerprint_bytes':2*(size+Path(__file__).stat().st_size),
            'fraction_add':512,'fraction_mul':512,'fraction_div':64}
    p={'date':'2026-10-15','version':'EXP076-given-direction-instrument-residual-v1','case':list(KEY),
       'authority':'User continues mainline. Latest STATUS requests audit of independence/gates versus missing target projection. Reuse NG01/21 and only same predeclared mean-to-W direction.',
       'scope':'Exactly one old direction, original full120 fixed GF/rear/high/eight blocks. Do not certify actual conditional independence or actual ell=0. This audits what the granted two target-moment equalities can and cannot identify.',
       'formula':'V=(d1,d1*GF); R=E[VV^T]=[[1,p],[p,p]], m=E[V*u]=AF*delta, Q=E[u^2]=delta^T H delta. alpha=R^-1*m; residual r=u-alpha^T V; sigma2=Q-m^T alpha. Grant E[V*tau]=0, then p_delta=E[r*tau]. For arbitrary L2 targets this moment determines p only iff sigma2=0. This specializes existing NG21 span criterion, not a new physical impossibility theorem.',
       'bounded_control':'PWL low-basis support vertices (0,0),(128,0),(128,128), both common signs, give Umax=128*max(abs(delta1),abs(delta1+delta2)). M=Umax+max(abs(alpha1),abs(alpha1+alpha2)) bounds |r|. tau=+-256*r/M lies in independent coarse-q1 box and has E[V*tau]=0; p=+-256*sigma2/M. Compare its loss endpoints with existing B and threshold, but do not assume they straddle threshold. Targets are a moment-level relaxation, not full-history or physically dither-independent worlds.',
       'prediction':'Missing residual is open; zero sigma2 would support these granted moments sufficing for this direction. Positive sigma2 shows residual target information remains. Constructed coarse-moment family may or may not cross the old improvement threshold. No new directions or precision changes if bound is inconclusive.',
       'validation':'Six bounded rational controls. Main 2x2 inverse versus independent disjoint GF0/GF1 conditional projection; verify normal equations, nonnegative residual, old direction curvature, coefficients, residual and coarse-moment witness values exactly. No source arrays or new empirical independence test.',
       'limits':limits,'controls_limits':{'fraction_add':128,'fraction_mul':128,'fraction_div':32},
       'preparation_fingerprint_limit':size,
       'units':'Every old JSON byte and full SHA including current/frozen code and two source guards. Fraction binary add/sub/mul/div wrapped; parse, unary/abs/comparison, fixed-denominator constants and display excluded. Generated protocol/results, documentation and delivery administrative. All prior failures/costs preserved; no chip-cost claim.',
       'stop':'Finish condition audit plus one scalar residual/control, or preserve failure. No new targets/arrays/PWL/gates, other directions, roots, policies, learning, paths/scores, full-history counterexamples, model/horizon, higher target precision, algorithms or holdout.'}
    write(out/'protocol.json',p);write(out/'source_hashes.json',{str(z):sha(z) for z in files})
    shutil.copyfile(Path(__file__),out/'frozen_analysis.py')
    write(out/'accounting_preparation.json',{'completed':True,'fingerprint_bytes':size,'limit':size,'all_limits_met':True,'new_scientific_record_calculations':0})
    print('Frozen one instrument-span audit with signs left open.')

def controls(out):
    q=Budget(read(out/'protocol.json')['controls_limits'])
    # A direction already in instrument span has zero unexplained L2 energy.
    p=F(1,2);m=[F(1),F(1,2)];a=[F(1),F(0)]
    assert q.sub(F(1),q.dot(m,a))==0
    # Orthogonal nonzero direction survives even when instrument target moments vanish.
    v=[F(1),F(-1)];u=[F(1),F(1)]
    assert q.dot(v,u)==0 and q.dot(u,u)==2
    # Disjoint gate projection and inverse give identical energies in a small case.
    m=[F(3,4),F(1,4)];a0=q.div(q.sub(m[0],m[1]),q.sub(F(1),p));a1=q.div(m[1],p)
    captured=q.add(q.mul(q.sub(F(1),p),q.mul(a0,a0)),q.mul(p,q.mul(a1,a1)))
    assert captured==F(5,8)
    # Shared-sign PWL geometry supports the three-vertex bound.
    delta=[F(-1),F(2)];bound=q.mul(F(128),max(abs(delta[0]),abs(q.add(*delta))))
    assert bound==128
    # Bounded moment target family has symmetric projection, not guaranteed sign of cost.
    b=F(10);amp=F(2)
    assert q.sub(b,q.mul(F(2),amp))==6 and q.add(b,q.mul(F(2),amp))==14
    # Balanced labels alone do not make a gated target moment zero.
    assert q.div(q.sub(q.mul(F(2),F(1)),q.mul(F(2),F(0))),F(2))==1
    write(out/'controls.json',{'passed':True,'exact_controls':6,'span_orthogonality_gate_partition_geometry_bounded_targets_gate_balance':True})
    write(out/'accounting_controls.json',{'completed':True,'used':q.used,'limits':q.limits,'all_limits_met':True})
    print('Six exact bounded controls passed.')

def guard(out,q):
    z=read(out/'source_hashes.json')
    for key,v in z.items():
        p=Path(key);q.charge('fingerprint_bytes',p.stat().st_size);assert sha(p)==v,key
    f=out/'frozen_analysis.py';q.charge('fingerprint_bytes',f.stat().st_size)
    key=next(k for k in z if k.endswith(Path(__file__).name));assert sha(f)==z[key]

def pack(z):return {'exact':str(z),'value':float(z)}

def analyze(out,ind=False):
    stage='independent' if ind else 'main';target=out/('independent_check.json' if ind else 'results.json')
    assert not target.exists();q=Budget(read(out/'protocol.json')['limits']);done=False
    try:
        assert read(out/'controls.json')['passed'];guard(out,q)
        data={}
        for name in FILES:q.charge('old_json_bytes',name.stat().st_size);data[str(name)]=read(name)
        get=lambda name:data[str(name)];hashes=read(out/'source_hashes.json')
        for name in FILES:
            if name.name in ('verification.json','independent_check.json'):assert get(name)['passed']
        direction=get(DIR/'results.json');stat=row(get(STAT/'results.json'));con=row(get(CON/'results.json'))
        assert direction['case']==list(KEY)
        assert get(DIR/'protocol.json')['source_sha256'][str(CON/'results.json')]==hashes[str(CON/'results.json')]
        assert get(FIX/'protocol.json')['source_hashes'][str(STAT/'results.json')]==hashes[str(STAT/'results.json')]
        assert get(FIX/'protocol.json')['source_hashes'][str(CON/'results.json')]==hashes[str(CON/'results.json')]
        delta=list(map(F,direction['delta']));a_mat=[list(map(F,line)) for line in stat['A']]
        h=[list(map(F,line)) for line in con['H']]
        p=F(stat['gate2_count'],N);assert 0<p<1
        rmat=[[F(1),p],[p,p]];m=q.mv(a_mat,delta);energy=q.dot(delta,q.mv(h,delta))
        assert energy==F(direction['curvature']['exact'])
        if ind:
            a0=q.div(q.sub(m[0],m[1]),q.sub(F(1),p));a1=q.div(m[1],p)
            alpha=[a0,q.sub(a1,a0)]
            cap=q.add(q.mul(q.sub(F(1),p),q.mul(a0,a0)),q.mul(p,q.mul(a1,a1)))
        else:
            det=q.sub(p,q.mul(p,p));assert det>0
            alpha=[q.div(q.sub(q.mul(p,m[0]),q.mul(p,m[1])),det),q.div(q.sub(m[1],q.mul(p,m[0])),det)]
            cap=q.dot(m,alpha)
        assert q.mv(rmat,alpha)==m
        sigma=q.sub(energy,cap);assert sigma>=0
        # The common-sign low basis geometry is a triangle with these extrema.
        umax=q.mul(F(128),max(abs(delta[0]),abs(q.add(delta[0],delta[1]))))
        maximum=q.add(umax,max(abs(alpha[0]),abs(q.add(alpha[0],alpha[1]))));assert maximum>0
        amp=q.div(q.mul(F(256),sigma),maximum)
        b=F(direction['digital_B']['exact']);threshold=F(direction['strict_improvement_threshold']['exact'])
        assert q.div(b,F(2))==threshold
        cost=[q.sub(b,q.mul(F(2),amp)),q.add(b,q.mul(F(2),amp))]
        zero_moment_cost=b
        # This bound is for moment-constrained coarse targets, not actual worlds.
        outer_squared=q.mul(F(65536),sigma)
        known_p=list(map(F,direction['target_projection_p']['interval']))
        result={'case':list(KEY),'instruments':'(d1,d1*fixed_GF), full120 empirical law',
          'given_direction':list(map(str,delta)),'gate_fraction':str(p),
          'instrument_Gram':[[str(z) for z in line] for line in rmat],
          'direction_instrument_cross':list(map(str,m)),'projection_coefficients':list(map(str,alpha)),
          'direction_energy':pack(energy),'captured_energy':pack(cap),'unobserved_direction_energy':pack(sigma),
          'given_direction_in_two_instrument_span':sigma==0,'pointwise_direction_bound':pack(umax),
          'pointwise_residual_bound':pack(maximum),'coarse_zero_target_moment_projection_amplitude':pack(amp),
          'coarse_moment_family_cost_endpoints':[pack(z) for z in cost],
          'coarse_moment_family_straddles_improvement_threshold':amp>threshold,
          'zero_target_coarse_moment_control_cost':pack(zero_moment_cost),
          'coarse_moment_residual_Cauchy_projection_radius_squared':str(outer_squared),
          'known_sine_target_projection_lower_remains_above_threshold':known_p[0]>threshold,
          'actual_target_instrument_moments_zero_or_dither_independence_proved':False,
          'constructed_targets_are_full_history_compatible_physical_worlds':False,
          'other_Gu_statistics_or_all_digital_information_insufficient_proved':False,
          'new_arrays_PWL_gates_targets_scores_learning_paths_or_holdout':0}
        guard(out,q)
        if ind:
            assert result==read(out/'results.json')
            write(target,{'passed':True,'independent_disjoint_gate_projection_matches_2x2_inverse':True,'old_curvature_normal_equations_and_bounded_target_controls_exact':True})
            write(out/'summary.json',{'passed':True,'missing_direction_energy':float(sigma),'captured_energy':float(cap),
              'two_moment_equalities_determine_given_target_projection':sigma==0,
              'bounded_target_amplitude':float(amp),'old_threshold':float(threshold),
              'constructed_coarse_moment_family_straddles_threshold':amp>threshold,
              'actual_independence_or_physical_nonidentifiability_proved':False})
        else:write(target,result)
        done=True;print(stage,{'missing_energy':float(sigma),'captured_energy':float(cap),'bounded_p_amplitude':float(amp),'threshold':float(threshold),'crosses':amp>threshold})
    finally:write(out/f'accounting_{stage}.json',{'completed':done,'used':q.used,'limits':q.limits,'all_limits_met':all(q.used[k]<=v for k,v in q.limits.items())})

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('prepare','controls','analyze','check'));ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    try:
        if args.mode=='prepare':prepare(args.out)
        elif args.mode=='controls':controls(args.out)
        else:analyze(args.out,args.mode=='check')
    except Exception:
        if args.out.exists():write(args.out/f'failure_{args.mode}.json',{'traceback':traceback.format_exc()})
        raise
