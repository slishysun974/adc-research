"""One old gate vector and the full quadratic continuous position loss.

Only existing scalar JSON is used. kbar-t is an algebraic continuous position,
not a legal integer readout, alternate learner, or frozen-gate feedback path.
"""
import argparse
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import shutil
import sys
import traceback

ROOT = Path(__file__).resolve().parents[2]; sys.path.insert(0, str(ROOT))
from experiments.exp_075_front_sampling_intervention.analyze_fixed_mean_statistics import Budget, pack

KEY = (202610625, 'quarter', 'prefix')
MEAN = ROOT/'artifacts/research/full_front_mean_learning_20261014_v1'
GATE = ROOT/'artifacts/research/full_front_fixed_gate_history_20261014_v1'
FIXED = ROOT/'artifacts/research/full_front_fixed_mean_statistics_20261014_v1'
DEPENDENCY = ROOT/'experiments/exp_075_front_sampling_intervention/analyze_fixed_mean_statistics.py'
META = [MEAN/'results.json', MEAN/'verification.json', MEAN/'independent_check.json',
        GATE/'results.json', GATE/'verification.json', GATE/'independent_check.json', GATE/'summary.json']
DOCS = ['docs/STATUS.md', 'docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md',
        'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md',
        'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
        'docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md',
        'docs/reports/GU_ALGORITHM_EVALUATION_V1.md',
        'docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
        'docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md',
        'docs/reports/experiments/EXP_075_FRONT_SAMPLING_INTERVENTION_V1.md',
        'experiments/exp_075_front_sampling_intervention/README.md']


def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def quad(h,v,q): return q.dot(v,q.mv(h,v))


def project(g,gi,v,q):
    products = [[q.mul(z,v[j]) for z in gi[j]] for j in range(2)]
    return pack(q.dot(g,v),[q.total(min(line) for line in products),q.total(max(line) for line in products)])


def translated(p,c,q):
    return pack(q.add(F(p['exact']),c),[q.add(F(z),c) for z in p['interval']])


def expanded_quad(h,v,q):
    return q.total([q.mul(h[0][0],q.mul(v[0],v[0])),
                    q.mul(q.mul(F(2),h[0][1]),q.mul(v[0],v[1])),
                    q.mul(h[1][1],q.mul(v[1],v[1]))])


def controls():
    q = Budget({'scalar_add':192,'scalar_mul':192,'scalar_div':16})
    h = [[F(2),F(1)],[F(1),F(3)]]; v = [F(1),F(-1)]
    assert quad(h,v,q) == expanded_quad(h,v,q) == 3
    assert q.add(q.mul(h[0][0],q.mul(v[0],v[0])),q.mul(h[1][1],q.mul(v[1],v[1]))) == 5
    # Positive endpoint projection can still have negative finite addition.
    g,t = F(1),F(2); p = q.mul(g,t); curve = q.mul(t,t)
    assert p > 0 and q.sub(p,curve) == -2
    t = F(1,4); assert q.sub(q.mul(g,t),q.mul(t,t)) == F(3,16)
    # Zero deletion and a nonzero full two-coordinate quadratic identity.
    assert quad(h,[F(0),F(0)],q) == 0
    d = [F(1,2),F(-1,3)]; t = [F(0),F(1,5)]; g = [F(2),F(-3)]
    s = [q.sub(d[j],t[j]) for j in range(2)]
    old = q.sub(q.dot(g,d),quad(h,d,q))
    deleted = q.add(q.sub(q.dot(g,s),quad(h,d,q)),quad(h,t,q))
    effect = q.sub(q.dot(g,t),quad(h,t,q))
    assert q.add(deleted,effect) == old
    g0 = [q.sub(g[j],q.mul(F(2),z)) for j,z in enumerate(q.mv(h,d))]
    assert q.add(q.dot(g0,s),expanded_quad(h,s,q)) == deleted
    # SAME scalar gradient g in [1,2]: direct deletion interval [-2,-1].
    # Treating the two projections as independent would give [-3,0].
    direct = [q.add(z,F(-3)) for z in (F(1),F(2))]
    naive = [q.sub(F(-2),F(1)),q.sub(F(0),F(0))]
    assert direct == [-2,-1] and naive == [-3,0]
    return {'passed':True,'exact_controls':6,
            'cross_term_positive_projection_counterexample_zero_deletion_full_identity_common_target':True},q


def freeze(out):
    assert not out.exists(),'Refuse overwrite'
    qualified = 0
    for p in META:
        if p.name != 'results.json': qualified += p.stat().st_size; assert load(p)['passed'],p
    assert digest(DEPENDENCY) == digest(FIXED/'frozen_analysis.py')
    files = META+[DEPENDENCY]; hashes = {str(p):digest(p) for p in files}
    for name,z in load(GATE/'source_hashes.json').items():
        if name in hashes: assert hashes[name] == z,name
    out.mkdir(parents=True); write(out/'source_hashes.json',hashes)
    shutil.copyfile(Path(__file__),out/'frozen_analysis.py')
    for name in DOCS:
        p = out/'documents_before'/name; p.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(ROOT/name,p)
    common = {'fingerprint_bytes':2*sum(p.stat().st_size for p in files),
              'metadata_json_bytes':sum(p.stat().st_size for p in META),'case_objects':1,
              'scalar_add':384,'scalar_mul':384,'scalar_div':16}
    control_result,cq = controls()
    write(out/'protocol.json',{
        'date':'2026-10-14','version':'EXP075-one-gate-position-full-quadratic-v1',
        'authority':'User continues D136..140; STATUS asks full continuous position after deleting same-history gate-weighted vector.',
        'case':KEY,'scope':'Exactly one existing case, same original continuous L* family with fixed rear Q3/high2/source/target. Only scalar JSON; no digital words, state/request arrays, new target or PWL/gate computation.',
        'question':'Does kdiag=kbar-t, t=old own_gate_change vector, still have positive FULL L*(kdiag)-L*(k0)? Endpoint projection alone is insufficient.',
        'state':'d=kbar-k0 is old actual mean gap including initial-hidden/weighted-request/export remainder. Reconstruct d from those three old parts; preserve them when deleting t. kbar and kdiag checked within continuous coefficient range[1/4,7/4], no rounding to Q1.10 or integer readout.',
        'derivation':'H=E psi_low psi_low^T, g=gL(kbar). Old Delta=g dot d-d H d. t=deltaM-deltaH, t[0]=0. Qgate=t H t; finite gate addition E_gate=g dot t-Qgate. Deleted Delta=g dot(d-t)-d H d+t H t. Evaluate each vector with SAME original gradient box. All are exact continuous quadratic identities; current outputs/scores/policies unchanged.',
        'independent':'Expand H00*v0^2+2H01*v0*v1+H11*v1^2. g0=g-2Hd; Delta_diag=g0 dot(d-t)+(d-t)H(d-t). gdiag=g-2Ht; E_gate=gdiag dot t+tHt. Independent signed endpoints of original shifted gradient intervals; no reading main result as input to reconstruction.',
        'prediction':'Deleted position negative supports gate vector changing a helpful continuous algebraic position into original bad one after full curvature. Deleted positive shows projection necessity alone insufficient to explain bad position. Cross-zero/domain/budget failure remains unresolved and stops.',
        'main_limits':common,'independent_limits':{**common,'result_json_bytes':30000},'control_limits':cq.limits,
        'units':'Reviewed Budget/pack source SHA frozen. Every scientific scalar binary add/sub/mul/div is wrapped, including matrix products/cross terms/history and target interval shifts. Parsing/Fraction construction/fixed constants/unary/compare/display/gcd excluded. Control arithmetic independently charged. Metadata hashes and preparation bytes separate. Offline units, not chip costs.',
        'validation':'Six bounded controls include cross-term requirement, positive endpoint projection but negative finite effect, zero deletion, two-dimensional full identity and common-target interval example. Recover old H positive definiteness/curvature/position interval/gate projection exactly; independent initial-gradient polynomial and shifted-gradient finite addition reconstruct all results/ranges.',
        'stop':'One deleted-position sign and finite gate effect, then return mainline position/variation/remaining representation. No other19, block/mask/target-precision sweep, optimizer, new legal reference, actual learner/commits, continuous or integer scores from records, FFT/new NG/EXP/algorithm/holdout6007/8009.'})
    write(out/'controls.json',control_result); cq.accounting(out,'accounting_controls.json',True)
    write(out/'preparation_accounting.json',{'fingerprint_bytes':sum(p.stat().st_size for p in files),
        'qualified_json_bytes':qualified,'dependency_bytes':DEPENDENCY.stat().st_size,
        'scientific_record_reads_or_calculations':0})
    print('Frozen one same-history gate deletion and full continuous position quadratic.',flush=True)


def guard(out,q):
    assert digest(Path(__file__)) == digest(out/'frozen_analysis.py')
    for name,z in load(out/'source_hashes.json').items():
        p = Path(name); q.charge('fingerprint_bytes',p.stat().st_size); assert digest(p) == z,p


def inputs(q):
    values = {}
    for p in META: q.charge('metadata_json_bytes',p.stat().st_size); values[str(p)] = load(p)
    def row(p): return next(r for r in values[str(p)]['rows'] if (r['seed'],r['rate'],r['initialization']) == KEY)
    q.charge('case_objects'); return row(MEAN/'results.json'),row(GATE/'results.json')


def analyze(out):
    assert not (out/'results.json').exists()
    q = Budget(load(out/'protocol.json')['main_limits']); done = False
    try:
        guard(out,q); mean,gate = inputs(q)
        h = [list(map(F,line)) for line in mean['H']]; d = list(map(F,mean['mean_gap']))
        kbar = list(map(F,mean['mean_kappa'])); t = list(map(F,gate['vectors']['own_gate_change']))
        assert h[0][1] == h[1][0] and h[0][0] > 0
        assert q.sub(q.mul(h[0][0],h[1][1]),q.mul(h[0][1],h[1][0])) > 0
        assert t[0] == 0
        assert [q.total(F(part[j]) for part in mean['history_parts'].values()) for j in range(2)] == d
        s = [q.sub(d[j],t[j]) for j in range(2)]
        k0 = [q.sub(kbar[j],d[j]) for j in range(2)]; kd = [q.sub(kbar[j],t[j]) for j in range(2)]
        assert all(F(1,4) <= z <= F(7,4) for z in kbar+kd+k0)
        g = [F(z['exact']) for z in mean['gradient_L']]; gi = [list(map(F,z['interval'])) for z in mean['gradient_L']]
        qd,qt = quad(h,d,q),quad(h,t,q); assert qd == F(mean['curvature']['exact'])
        old = translated(project(g,gi,d,q),-qd,q); assert old == mean['position_L']
        pg = project(g,gi,t,q); assert pg == gate['projections']['own_gate_change']
        effect = translated(pg,-qt,q)
        deleted = translated(project(g,gi,s,q),q.sub(qt,qd),q)
        assert q.add(F(deleted['exact']),F(effect['exact'])) == F(old['exact'])
        r = {'seed':KEY[0],'rate':KEY[1],'initialization':KEY[2],
             'initial_kappa':list(map(str,k0)),'mean_kappa':list(map(str,kbar)),
             'deleted_kappa':list(map(str,kd)),'mean_gap':list(map(str,d)),
             'gate_vector':list(map(str,t)),'deleted_gap':list(map(str,s)),
             'original_curvature':pack(qd),'gate_curvature':pack(qt),'gate_endpoint_projection':pg,
             'original_position_L':old,'deleted_position_L':deleted,'finite_gate_addition_L':effect,
             'continuous_domain_certified':True,'new_legal_integer_readout_or_policy':False}
        guard(out,q); write(out/'results.json',{'completed':True,'rows':[r]})
        write(out/'verification.json',{'passed':True,'cases':1,'old_curvature_position_interval_gate_projection_exact':True,
            'original_history_gap_and_full_position_identity_exact':True,'new_source_PWL_gate_policy_score_FFT':0})
        done = True
        print('Deleted position=',deleted['value'],'finite gate addition=',effect['value'],'gate curvature=',float(qt),flush=True)
    finally: q.accounting(out,'accounting_main.json',done)


def check(out):
    assert not (out/'independent_check.json').exists()
    q = Budget(load(out/'protocol.json')['independent_limits']); done = False
    try:
        guard(out,q); mean,gate = inputs(q)
        q.charge('result_json_bytes',(out/'results.json').stat().st_size); r = load(out/'results.json')['rows'][0]
        h = [list(map(F,line)) for line in mean['H']]; d = list(map(F,mean['mean_gap']))
        t = list(map(F,gate['vectors']['own_gate_change'])); s = [q.sub(d[j],t[j]) for j in range(2)]
        g = [F(z['exact']) for z in mean['gradient_L']]; gi = [list(map(F,z['interval'])) for z in mean['gradient_L']]
        hd = [q.add(q.mul(h[j][0],d[0]),q.mul(h[j][1],d[1])) for j in range(2)]
        ht = [q.add(q.mul(h[j][0],t[0]),q.mul(h[j][1],t[1])) for j in range(2)]
        shifts_d = [q.mul(F(2),z) for z in hd]; shifts_t = [q.mul(F(2),z) for z in ht]
        g0 = [q.sub(g[j],shifts_d[j]) for j in range(2)]
        gd = [q.sub(g[j],shifts_t[j]) for j in range(2)]
        i0 = [[q.sub(z,shifts_d[j]) for z in gi[j]] for j in range(2)]
        idg = [[q.sub(z,shifts_t[j]) for z in gi[j]] for j in range(2)]
        qold,qnew,qgate = (expanded_quad(h,v,q) for v in (d,s,t))
        assert str(qold) == r['original_curvature']['exact'] and str(qgate) == r['gate_curvature']['exact']
        def polynomial(gradient,intervals,v,curvature):
            z = q.add(q.total(q.mul(gradient[j],v[j]) for j in range(2)),curvature)
            ends = [q.add(q.total(q.mul(intervals[j][end if v[j] >= 0 else 1-end],v[j]) for j in range(2)),curvature) for end in (0,1)]
            return pack(z,ends)
        old = polynomial(g0,i0,d,qold); deleted = polynomial(g0,i0,s,qnew)
        effect = polynomial(gd,idg,t,qgate)
        assert old == r['original_position_L'] and deleted == r['deleted_position_L'] and effect == r['finite_gate_addition_L']
        assert q.sub(F(old['exact']),F(deleted['exact'])) == F(effect['exact'])
        kbar = list(map(F,mean['mean_kappa']))
        assert [str(q.sub(kbar[j],d[j])) for j in range(2)] == r['initial_kappa']
        assert [str(q.sub(kbar[j],t[j])) for j in range(2)] == r['deleted_kappa']
        guard(out,q)
        write(out/'independent_check.json',{'passed':True,'cases':1,
            'expanded_quadratic_initial_gradient_and_deleted_gradient_exact':True,
            'independent_signed_interval_endpoints_exact':True,'main_formula_used':False,
            'original_records_or_new_target_read':0})
        lo,hi = map(F,deleted['interval'])
        write(out/'summary.json',{'passed':True,'cases':1,'deleted_position_negative_certified':hi < 0,
            'deleted_position_positive_certified':lo > 0,'deleted_position_unresolved':lo <= 0 <= hi,
            'finite_gate_addition_positive_certified':F(effect['interval'][0]) > 0,
            'original_bad_position_certified':F(old['interval'][0]) > 0,
            'all20_original_context_preserved':True,'new_policies_legal_readouts_scores_fft':0})
        done = True; print('Independent expanded full-position polynomial and shared-target intervals verified.',flush=True)
    finally: q.accounting(out,'accounting_independent.json',done)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('mode',choices=['freeze','analyze','check']); p.add_argument('--out',type=Path,required=True)
    a = p.parse_args()
    try: {'freeze':freeze,'analyze':analyze,'check':check}[a.mode](a.out)
    except Exception:
        if a.out.exists(): write(a.out/(a.mode+'_failure.json'),{'traceback':traceback.format_exc()})
        raise
