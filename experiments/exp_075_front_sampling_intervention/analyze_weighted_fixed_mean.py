"""Two fixed-mean downhill cases: original triangular time weighting.

Same rational mean, rear Q3, high coefficients and source order. This is
an offline frozen-state request diagnostic, not a propagated policy.
"""
import argparse
from fractions import Fraction as F
from math import lcm
from pathlib import Path
import hashlib
import json
import shutil
import sys
import traceback
import numpy as np

ROOT = Path('D:/ADC'); sys.path.insert(0,str(ROOT))
from experiments.exp_075_front_sampling_intervention.analyze_fixed_mean_statistics import (
    Budget, vector_rear, scalar_rear, basis, pack,
)

W = 2048; N = W*120; START = 128*256
OLD = ROOT/'artifacts/runs/EXP_062/background_v1'
FIXED = ROOT/'artifacts/research/full_front_fixed_mean_statistics_20261014_v1'
MEAN = ROOT/'artifacts/research/full_front_mean_learning_20261014_v1'
DEPENDENCY = ROOT/'experiments/exp_075_front_sampling_intervention/analyze_fixed_mean_statistics.py'
CASES = [(202610625,'base','actual'),(202610625,'quarter','prefix')]
META = [FIXED/'results.json',FIXED/'verification.json',FIXED/'independent_check.json',FIXED/'summary.json',
        MEAN/'results.json',MEAN/'verification.json',MEAN/'independent_check.json']
DOCS = ['docs/STATUS.md','docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md',
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


def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as stream:
        for block in iter(lambda:stream.read(4194304),b''): h.update(block)
    return h.hexdigest()


def controls():
    weights = [3,2,1,0]; c = [F(-2),F(-2),F(3),F(3)]; v = [-z for z in c]
    uniform = sum(v)/4; weighted = sum(w*z for w,z in zip(weights,v))/4
    assert uniform == -F(1,2) and weighted == F(7,4)
    time = weighted-F(3,2)*uniform; assert time == F(5,2)
    assert sum(w*z for w,z in zip(weights,reversed(v)))/4 == -F(13,4)
    assert sum(w*F(-2) for w in weights)/4 == F(3,2)*F(-2)
    changed = v[:]; changed[-1] = F(900)
    assert sum(w*z for w,z in zip(weights,changed))/4 == weighted
    states = [F(0)]
    for z in v: states.append(states[-1]+z)
    assert sum(states[:-1])/4 == weighted and sum(v)/4 != weighted
    # Exact projection identity and bound retain the SAME target gradient.
    actual = F(2); remainder = actual-weighted
    assert actual == F(3,2)*uniform+time+remainder
    assert (F(1)*remainder,F(2)*remainder) == (F(1,4),F(1,2))
    return {'passed':True,'exact_controls':6,
            'weighting_flip_reverse_constant_last_zero_output_before_identity':True,
            'algebra_only_no_new_physical_source':True}


def freeze(out):
    assert not out.exists(),'Refuse overwrite'
    for p in META:
        if p.name in ('verification.json','independent_check.json','summary.json'): assert load(p)['passed']
    assert digest(DEPENDENCY) == digest(FIXED/'frozen_analysis.py')
    files = META+[OLD/'both_smooth_202610625_words.bin',DEPENDENCY]
    hashes = {str(p):digest(p) for p in files}
    historical = load(FIXED/'source_hashes.json')
    for p,z in hashes.items():
        if p in historical: assert historical[p] == z,p
    out.mkdir(parents=True); write(out/'source_hashes.json',hashes)
    shutil.copyfile(Path(__file__),out/'frozen_analysis.py')
    for name in DOCS:
        p = out/'documents_before'/name; p.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(ROOT/name,p)
    shared = {'fingerprint_bytes':2*sum(p.stat().st_size for p in files),
              'metadata_json_bytes':sum(p.stat().st_size for p in META),'case_objects':2,'source_values':N*3}
    main = {**shared,'tag_decode_cells':2*N*2,'rear_Q3_PWL_cells':2*N,
            'front_continuous_cells':2*N,'basis_geometry_cells':2*N*4,'gate_tests':2*N,
            'vector_add':2*N*7,'vector_mul':2*N*13,'reduction_inputs':2*N*4,
            'scalar_add':5000,'scalar_mul':5000,'scalar_div':1000}
    independent = {**shared,'result_json_bytes':150000,'group_word_inputs':N,
                   'group_weight_integer_adds':N,'digital_group_cells':2*9216,
                   'rear_Fraction_PWL_cells':2*256,
                   'scalar_add':1000000,'scalar_mul':1000000,'scalar_div':50000}
    write(out/'protocol.json',{
        'date':'2026-10-14','version':'EXP075-two-triangular-fixed-means-v1',
        'authority':'User continues D136..140; STATUS specifically identifies625 actual/base and prefix/quarter weighting question.',
        'cases':CASES,'scope':'Only two prescribed downhill fixed-mean cases; old20/four-case context kept. Same non-grid mean, rear Q3/high2, source order/eight blocks and original endpoint.',
        'question':'Does original output-before triangular weighting flip the fixed continuous full120 mean direction, before any moving-state/gate/quantization difference is introduced?',
        'state':'Reuse exact continuous_kappa/rear codes from finished four-case analysis. No rounding to Q1.10/Q22. Front y*=sum psi*k-64d1 and own G2>=128*k1; rear Q3 retained. No actual learner or altered policy.',
        'identity':'Cw=mean120 dG*y*; h_w=W-1-w. Ctriangle=E_words[h_w*dG*y*] with original N denominator (not normalized by sum h). delta_fixed=-lambda diag(1,3)Ctriangle. hbar=(W-1)/2; delta_flat=hbar*v_uniform; delta_time=delta_fixed-delta_flat; delta_rest=old_actual_weighted_Q22_gap-delta_fixed. Project all vectors onto SAME true L* mean gradient. flat+time=fixed, fixed+rest=actual, all exact.',
        'target':'Reuse old true mean gradient coordinate intervals under NG39/43; direct remainder-vector projection retains shared target, do not infer all input/physical/future behavior. No new target table or tighter phase bound.',
        'prediction':'Fixed triangle uphill supports finite order/time-weight explanation of a sign flip; fixed triangle downhill with actual uphill requires positive remaining request-history projection. Keep both cases and all crossed-zero intervals.',
        'main_limits':main,'independent_limits':independent,
        'units':'Reuse reviewed Budget/vector rear/basis/scalar rear with dependency SHA frozen. Scientific scalar binary operations explicitly wrapped; outer vector products/adds/reduction INPUTS all charged including masks and time multiplication. Rear/basis/tag kernels include their internals; fixed index/denominator construction, unary/compare/display excluded. Independent DIGITAL groups retain both multiplicity and integer sum of h via add.at (N charged adds); no float weights, main masks or stored bases. Offline units, not chip costs.',
        'validation':'Six rational time-weight controls before records. Recover old full C and down D exactly; integer direct weighted products. Independent scalar digital grouping with sum h per group recovers both C and Ctriangle; independent vector/time/remainder algebra and target ranges. Last weight0/output-before timing fixed.',
        'stop':'Two weighting judgments or preserve failure; no block sweep, new A/roots/Q3 front/Q22 request/reference/learner/source/score/FFT/precision chase or future6007/8009. Do not automatically split remaining state/gate/quantization difference.'})
    write(out/'preparation_accounting.json',{'fingerprint_bytes':sum(p.stat().st_size for p in files),
        'qualified_metadata_bytes':sum(p.stat().st_size for p in META if p.name in ('verification.json','independent_check.json','summary.json')),
        'dependency_source_bytes':DEPENDENCY.stat().st_size,'new_scientific_word_calculations':0})
    write(out/'controls.json',controls()); print('Frozen two same-mean triangular weighting diagnostics.',flush=True)


def guard(out,q):
    assert digest(Path(__file__)) == digest(out/'frozen_analysis.py')
    for name,z in load(out/'source_hashes.json').items():
        p = Path(name); q.charge('fingerprint_bytes',p.stat().st_size); assert digest(p) == z,p


def inputs(q):
    values = {}
    for p in META: q.charge('metadata_json_bytes',p.stat().st_size); values[str(p)] = load(p)
    fixed = {(r['seed'],r['rate'],r['initialization']):r for r in values[str(FIXED/'results.json')]['rows']}
    means = {(r['seed'],r['rate'],r['initialization']):r for r in values[str(MEAN/'results.json')]['rows']}
    assert len(means) == 20 and len(fixed) == 4
    assert {k for k,r in fixed.items() if F(r['D']['exact']) < 0} == set(CASES)
    return fixed,means


def source(q):
    q.charge('source_values',N*3)
    return np.array(np.memmap(OLD/'both_smooth_202610625_words.bin',dtype='i1',mode='r',shape=(65536,120,4))[START:START+W,:,1:],dtype=np.int64)


def projection(gradient,intervals,vector,q):
    products = [[q.mul(z,vector[j]) for z in line] for j,line in enumerate(intervals)]
    bounds = [q.total(min(line) for line in products),q.total(max(line) for line in products)]
    return pack(q.dot(gradient,vector),bounds)


def describe(key,c,ct,prior,mean,q):
    assert list(map(str,c)) == prior['C']
    m = 1 if key[1] == 'base' else 4
    scales = [F(-3072*factor,25*m*(1 << 22)) for factor in (1,3)]
    uniform = [q.mul(scales[j],c[j]) for j in range(2)]
    assert list(map(str,uniform)) == prior['direction']
    g = [F(z['exact']) for z in mean['gradient_L']]
    gi = [list(map(F,z['interval'])) for z in mean['gradient_L']]
    assert projection(g,gi,uniform,q) == prior['D']
    flat = [q.mul(F(W-1,2),z) for z in uniform]
    fixed = [q.mul(scales[j],ct[j]) for j in range(2)]
    time = [q.sub(fixed[j],flat[j]) for j in range(2)]
    actual = list(map(F,mean['history_parts']['weighted_requests']))
    rest = [q.sub(actual[j],fixed[j]) for j in range(2)]
    vectors = {'uniform':uniform,'flat':flat,'time':time,'fixed_triangle':fixed,'remaining_history':rest,'actual_weighted':actual}
    effects = {name:projection(g,gi,vec,q) for name,vec in vectors.items()}
    assert q.add(F(effects['flat']['exact']),F(effects['time']['exact'])) == F(effects['fixed_triangle']['exact'])
    assert q.add(F(effects['fixed_triangle']['exact']),F(effects['remaining_history']['exact'])) == F(effects['actual_weighted']['exact'])
    assert effects['actual_weighted'] == mean['history_projections']['L']['component_projections']['weighted_requests']
    return {'seed':key[0],'rate':key[1],'initialization':key[2],
            'C_uniform':list(map(str,c)),'C_triangle':list(map(str,ct)),
            'vectors':{name:list(map(str,vec)) for name,vec in vectors.items()},'projections':effects,
            'fixed_triangle_uphill':F(effects['fixed_triangle']['exact']) > 0,
            'actual_Q3_Q22_policy_propagated':False}


def analyze(out):
    assert not (out/'results.json').exists()
    q = Budget(load(out/'protocol.json')['main_limits']); done = []
    try:
        guard(out,q); fixed,means = inputs(q); words = source(q)
        q2,sar,bits = (words[:,:,j] for j in range(3)); weights = (W-1-np.arange(W))[:,None]
        for key in CASES:
            q.charge('case_objects'); r = fixed[key]; k = list(map(F,r['continuous_kappa']))
            den = lcm(*(z.denominator for z in k)); kn = [int(z.numerator*(den//z.denominator)) for z in k]
            q.charge('tag_decode_cells',2*N); d,d2 = 2*(bits&1)-1,2*((bits>>1)&1)-1
            q.charge('rear_Q3_PWL_cells',N); rear = vector_rear(q.vm(8,sar),r['original_rear_codes'])
            raw = q.vs(q.va(q.vm(1024,q2),rear),q.vm(128,d2)); assert np.all((raw >= -4096) & (raw < 4096))
            q.charge('basis_geometry_cells',4*N); phi = basis(raw)
            q.charge('front_continuous_cells',N)
            high = q.vs(q.va(q.vm(phi[:,:,2],kn[2]),q.vm(phi[:,:,3],kn[3])),q.vm(d,512*den))
            yn = q.va(q.va(q.vm(phi[:,:,0],kn[0]),q.vm(phi[:,:,1],kn[1])),high)
            q.charge('gate_tests',N); gate = abs(yn) >= 1024*kn[0]
            x = q.vm(d,yn); gated = q.vm(x,gate)
            assert int(np.max(abs(x),initial=0))*(W-1) < 1 << 63
            cc = [q.isum(x),q.isum(gated)]
            ch = [q.isum(q.vm(x,weights)),q.isum(q.vm(gated,weights))]
            c = [F(z,8*den*N) for z in cc]; ct = [F(z,8*den*N) for z in ch]
            item = describe(key,c,ct,r,means[key],q); done.append(item)
            print(key,'triangle=',item['projections']['fixed_triangle']['value'],
                  'remaining=',item['projections']['remaining_history']['value'],flush=True)
        guard(out,q); write(out/'results.json',{'completed':True,'rows':done})
        write(out/'verification.json',{'passed':True,'cases':2,'old_uniform_C_D_and_actual_projection_exact':True,
            'triangular_flat_time_remaining_identities_exact':True,'new_learner_requests_scores_fft':0})
    except Exception: write(out/'partial_results.json',{'completed':False,'rows':done}); raise
    finally: q.accounting(out,'accounting_main.json',len(done) == 2)


def check(out):
    assert not (out/'independent_check.json').exists()
    q = Budget(load(out/'protocol.json')['independent_limits']); done = 0
    try:
        guard(out,q); fixed,means = inputs(q); words = source(q)
        q.charge('result_json_bytes',(out/'results.json').stat().st_size)
        results = {(r['seed'],r['rate'],r['initialization']):r for r in load(out/'results.json')['rows']}
        q.charge('group_word_inputs',N)
        cells,indices,counts = np.unique(words.reshape(N,3),axis=0,return_inverse=True,return_counts=True)
        hcounts = np.zeros(len(cells),dtype=np.int64)
        q.charge('group_weight_integer_adds',N)
        np.add.at(hcounts,indices,np.repeat(W-1-np.arange(W,dtype=np.int64),120))
        assert q.total(F(int(z)) for z in counts) == N
        assert q.total(F(int(z)) for z in hcounts) == F(N*(W-1),2)
        lookups = []
        for key in CASES:
            q.charge('case_objects'); r = fixed[key]; k = list(map(F,r['continuous_kappa']))
            values = sorted(set(int(z[1]) for z in cells)); q.charge('rear_Fraction_PWL_cells',len(values))
            rt = {z:scalar_rear(z,r['original_rear_codes'],q) for z in values}
            sums = [F(0),F(0)]; weighted = [F(0),F(0)]
            for cell,nn,hh in zip(cells,counts,hcounts):
                q.charge('digital_group_cells'); q2,sar,bits = map(int,cell); d,d2 = 2*(bits&1)-1,2*((bits>>1)&1)-1
                raw = int(q.sub(q.add(q.mul(1024,q2),rt[sar]),q.mul(128,d2)))
                assert -4096 <= raw < 4096
                psi = [F((1 if raw >= 0 else -1)*min(max(abs(raw)-1024*j,0),1024),8) for j in range(4)]
                y = q.sub(q.total(q.mul(psi[j],k[j]) for j in range(4)),F(64*d))
                gate = abs(y) >= q.mul(F(128),k[0]); dy = q.mul(F(d),y)
                for j,g in enumerate((True,gate)):
                    if g:
                        sums[j] = q.add(sums[j],q.mul(F(int(nn)),dy))
                        weighted[j] = q.add(weighted[j],q.mul(F(int(hh)),dy))
            c = [q.div(z,F(N)) for z in sums]; ct = [q.div(z,F(N)) for z in weighted]
            old = results[key]
            assert list(map(str,c)) == old['C_uniform'] and list(map(str,ct)) == old['C_triangle']
            # Independent algebra from weighted source moments, with a direct
            # common-gradient remainder interval (not subtraction of two boxes).
            m = 1 if key[1] == 'base' else 4
            uniform = [q.mul(F(-3072*f,25*m*(1 << 22)),c[j]) for j,f in enumerate((1,3))]
            tri = [q.mul(F(-3072*f,25*m*(1 << 22)),ct[j]) for j,f in enumerate((1,3))]
            flat = [q.mul(F(W-1,2),v) for v in uniform]
            time = [q.sub(tri[j],flat[j]) for j in range(2)]
            actual = list(map(F,means[key]['history_parts']['weighted_requests']))
            rest = [q.sub(actual[j],tri[j]) for j in range(2)]
            vectors = {'uniform':uniform,'flat':flat,'time':time,'fixed_triangle':tri,'remaining_history':rest,'actual_weighted':actual}
            g = [F(z['exact']) for z in means[key]['gradient_L']]
            for name,vec in vectors.items():
                assert list(map(str,vec)) == old['vectors'][name]
                value = q.total(q.mul(g[j],vec[j]) for j in range(2))
                bounds = [q.total(q.mul(F(means[key]['gradient_L'][j]['interval'][end if vec[j] >= 0 else 1-end]),vec[j]) for j in range(2)) for end in (0,1)]
                assert pack(value,bounds) == old['projections'][name]
            lookups.append(len(values)); done += 1
        guard(out,q)
        write(out/'independent_check.json',{'passed':True,'cases':done,'digital_cells':len(cells),
            'rear_scalar_lookups_per_case':lookups,'integer_group_weight_sums_and_scalar_correlations_exact':True,
            'independent_vectors_and_common_target_intervals_exact':True,'main_masks_or_basis_words_read':0})
        rows = list(results.values())
        write(out/'summary.json',{'passed':True,'cases':2,
            'triangle_uphill':sum(F(r['projections']['fixed_triangle']['exact']) > 0 for r in rows),
            'triangle_downhill':sum(F(r['projections']['fixed_triangle']['exact']) < 0 for r in rows),
            'triangle_certified':sum(r['projections']['fixed_triangle']['sign_certified'] for r in rows),
            'remaining_positive':sum(F(r['projections']['remaining_history']['exact']) > 0 for r in rows),
            'remaining_certified':sum(r['projections']['remaining_history']['sign_certified'] for r in rows),
            'all20_context_preserved':True,'new_learner_policies_legal_readouts_scores_fft':0})
    finally: q.accounting(out,'accounting_independent.json',done == 2)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('mode',choices=['freeze','analyze','check'])
    parser.add_argument('--out',type=Path,required=True); args = parser.parse_args()
    try: {'freeze':freeze,'analyze':analyze,'check':check}[args.mode](args.out)
    except Exception:
        if args.out.exists(): write(args.out/(args.mode+'_failure.json'),{'traceback':traceback.format_exc()})
        raise
