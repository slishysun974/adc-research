"""One original moving history with the mean's continuous gate held fixed.

This evaluates the first order in (35.7) only, without propagating any policy.
The other19 cases, all actual paths and all previously frozen sources stay intact.
"""
import argparse
from fractions import Fraction as F
from math import lcm
from pathlib import Path
import sys
import shutil
import traceback
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.exp_075_front_sampling_intervention import analyze_moving_continuous as previous
from experiments.exp_075_front_sampling_intervention.analyze_fixed_mean_statistics import (
    Budget, basis, vector_rear, scalar_rear, pack,
)

W = 2048; N = 120*W; START = 128*256; KEY = (202610625, 'quarter', 'prefix')
MOVING = ROOT/'artifacts/research/full_front_moving_continuous_20261014_v1'
FIXED = previous.FIXED; WEIGHTED = previous.WEIGHTED; MEAN = previous.MEAN
META = [MOVING/'results.json', MOVING/'verification.json', MOVING/'independent_check.json', MOVING/'summary.json',
        FIXED/'results.json', FIXED/'verification.json', FIXED/'independent_check.json',
        WEIGHTED/'results.json', WEIGHTED/'verification.json', WEIGHTED/'independent_check.json',
        MEAN/'results.json', MEAN/'verification.json', MEAN/'independent_check.json']
DATA = previous.DATA[:2]
DEPENDENCIES = [Path(previous.__file__).resolve(), previous.DEPENDENCY]
load = previous.load; write = previous.write; digest = previous.digest


def controls():
    q = Budget({'scalar_add': 192, 'scalar_mul': 128, 'scalar_div': 64,
                'export_cells': 3, 'rear_Q3_PWL_cells': 12, 'rear_Fraction_PWL_cells': 12,
                'vector_mul': 12})
    a = np.array([1024*4096+2048, 1025*4096+2048, 1024*4096-2048])
    q.charge('export_cells', 3)
    assert previous.export(a).tolist() == [round(F(int(z), 4096)) for z in a] == [1024, 1026, 1024]
    sar = np.array([-128, -96, -64, -32, -1, 0, 1, 31, 32, 64, 96, 127])
    codes = [1089, 1103, 1024, 1024]
    q.charge('rear_Q3_PWL_cells', 12); q.charge('rear_Fraction_PWL_cells', 12)
    assert vector_rear(q.vm(8, sar), codes).tolist() == [scalar_rear(int(z), codes, q) for z in sar]
    # Legal two-basis geometry at raw1536. The equality gate is >=.
    def y(k): return q.sub(q.dot([F(128), F(64)], k), F(64))
    kbar = [F(1), F(1)]; yf = y(kbar); tf = q.mul(F(128), kbar[0])
    assert yf == tf and abs(yf) >= tf
    low = [kbar[0], q.sub(kbar[1], F(1, 1024))]
    high = [kbar[0], q.add(kbar[1], F(1, 1024))]
    assert abs(y(low)) < tf < abs(y(high))
    # Fixed mask and own mask differ for the lower moving readout.
    gf = abs(yf) >= tf; gm = abs(y(low)) >= q.mul(F(128), low[0])
    assert gf and not gm
    held = q.mul(F(int(gf)), y(low)); moving = q.mul(F(int(gm)), y(low))
    assert q.sub(moving, held) == -held
    # No mask change gives zero gate term, regardless of numeric motion.
    ym = y(high)
    assert q.sub(q.mul(F(int(gf)), ym), q.mul(F(int(gf)), ym)) == 0
    assert q.sub(q.mul(F(int(gf)), ym), q.mul(F(int(gf)), yf)) == q.mul(F(int(gf)), q.sub(ym, yf))
    # Zero state mean cannot cancel a time-weighted state/source product.
    gap = [F(-1), F(-1), F(1), F(1)]; h = [3, 2, 1, 0]
    assert q.total(gap) == 0
    assert q.div(q.total(q.mul(F(hw), z) for hw, z in zip(h, gap)), F(4)) == -1
    # Positive numeric difference need not cross zero; the last weight is zero.
    assert q.add(F(-2), F(1)) == -1 and q.add(F(-2), F(3)) == 1
    assert q.total(q.mul(F(hw), z) for hw, z in zip(h, [F(1), F(2), F(3), F(900)])) == 10
    return {'passed': True, 'exact_controls': 6, 'rear_probes': 12,
            'legal_export_equality_mask_change_no_change_zero_mean_last_zero': True}, q


def freeze(out):
    assert not out.exists(), 'Refuse overwrite'
    qualified_bytes = 0
    for p in META:
        if p.name in ('verification.json', 'independent_check.json', 'summary.json'):
            qualified_bytes += p.stat().st_size; assert load(p)['passed'], p
    assert digest(DEPENDENCIES[0]) == digest(MOVING/'frozen_analysis.py')
    assert digest(DEPENDENCIES[1]) == digest(FIXED/'frozen_analysis.py')
    files = META+DATA+DEPENDENCIES
    hashes = {str(p): digest(p) for p in files}
    for folder in (MOVING, FIXED, WEIGHTED, MEAN):
        for name, z in load(folder/'source_hashes.json').items():
            if name in hashes: assert hashes[name] == z, name
    out.mkdir(parents=True)
    write(out/'source_hashes.json', hashes)
    shutil.copyfile(Path(__file__), out/'frozen_analysis.py')
    for name in previous.DOCS:
        target = out/'documents_before'/name
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT/name, target)
    common = {'fingerprint_bytes': 2*sum(p.stat().st_size for p in files),
              'metadata_json_bytes': sum(p.stat().st_size for p in META), 'case_objects': 1,
              'source_values': 3*N, 'state_values': 2*W+6, 'export_cells': 2*W+6}
    main = {**common, 'tag_decode_cells': 2*N, 'rear_Q3_PWL_cells': N,
            'front_continuous_cells': 2*N, 'basis_geometry_cells': 4*N, 'fixed_gate_tests': N,
            'vector_add': 10*N, 'vector_mul': 20*N, 'reduction_inputs': 8*N+2*W,
            'scalar_add': 256, 'scalar_mul': 256, 'scalar_div': 32}
    independent = {**common, 'result_json_bytes': 30000, 'group_word_inputs': N,
                   'group_weight_integer_adds': N, 'digital_state_groups': N, 'rear_Fraction_PWL_cells': 256,
                   'scalar_add': 32*N+4*W, 'scalar_mul': 24*N, 'scalar_div': 2000}
    controls_result, control_q = controls()
    write(out/'protocol.json', {
        'date': '2026-10-14', 'version': 'EXP075-one-mean-gate-held-history-v1',
        'authority': 'User continues D136..140. Latest STATUS identifies whether fixed mean gate suffices for625 prefix/quarter continuous flip.',
        'case': KEY, 'scope': 'One old original export history and source order/eight blocks/2048 windows/full120. Other19 cases and all original paths/results remain. No new model/target/holdout/score/policy.',
        'question': 'Does moving continuous readout with the fixed mean continuous gate already have a positive cumulative projection? This decides gate-change necessity for this specified same-history comparison.',
        'state': 'Output-before actual low2 K=nearest_even(A/4096), k=K/1024. High2/rear retain original codes; read only4096 old low Q22 values plus6 original high/rear fields. Old source SHA and previous full8 recurrence/high constancy verification reused. No requests read/generated or state evolution.',
        'readout': 'Same rear Q3 separately rounded offset/product. yF=sum psi*kbar-64d1; yM=sum psi*k[w]-64d1. GF1=1; GF2=abs(yF)>=128*kbar1. HELD correlation uses GF*yM (it does NOT compare yM to a mean threshold). No own moving mask or Q3 front is newly calculated.',
        'identity': 'CH=E_words[h*d1*GF*yM], CF=old fixed mean h correlation, CM=old moving own-gate h correlation, h=W-1-w, original denominator N=120W. deltaH=-Lambda CH; delta_state=deltaH-deltaF; delta_gate=deltaM-deltaH. This is the fixed-gate-first order of (35.7). delta_state+delta_gate=old moving-minus-fixed exactly; gate coordinate1(first low coordinate)=0. No reverse order/unique fraction is inferred.',
        'target': 'Project each VECTOR onto the old same L* mean gradient and original NG39/43 coordinate interval box. No interval subtraction treating targets as independent. These are request projections, not MSE deltas.',
        'prediction': 'Certified PH>0 supports state/source/time association sufficient under this fixed-gate reference, so moving own gate is not necessary for the continuous flip. PH<0 with old PM>0 requires positive gate-change projection sufficient to flip in this comparison. If PH crosses0, retain uncertainty and stop.',
        'main_limits': main, 'independent_limits': independent, 'control_limits': control_q.limits,
        'units': 'Dependency SHA for prior module and reviewed Budget/geometry/rear kernel frozen. All scientific outer vector add/sub/mul and reduction INPUTS charged, including both fixed/moving signed products, masks and h. Scalar binary scientific operations use wrappers. Export/tag/basis/PWL/gate kernels include fixed internals/counts; independent Fraction control arithmetic is also wrapped. Index/fixed-scale/denominator/parsing/unary/compare/display/gcd excluded. Joint digital/export groups retain integer sum h through N charged adds; group input unit covers assembly/sort/copy. Offline cost units, not chip gates.',
        'validation': 'Six bounded algebra controls/12 rear probes before records. Exact GF count/equalities and old CFh recovered, old mean restored. Independent Fraction export and digital/export grouping recover held and fixed weighted moments, independent signs/endpoint intervals and vector identity, without main bases/masks. Existing first-coordinate CM equals CH exactly.',
        'stop': 'Only one PH sign and specified-order effects; stop at supported/negative/unresolved gate necessity. No all20/block sweep, reverse order, mask-transition classification, actual learner/commits, Q3/request/target/FFT/score/reference/roots, or future6007/8009.'})
    write(out/'controls.json', controls_result); control_q.accounting(out, 'accounting_controls.json', True)
    write(out/'preparation_accounting.json', {'fingerprint_bytes': sum(p.stat().st_size for p in files),
        'qualified_json_bytes': qualified_bytes,
        'dependency_bytes': sum(p.stat().st_size for p in DEPENDENCIES), 'scientific_record_reads_or_calculations': 0})
    print('Frozen one original history with its mean continuous gate held fixed.', flush=True)


def guard(out, q):
    assert digest(Path(__file__)) == digest(out/'frozen_analysis.py')
    for name, z in load(out/'source_hashes.json').items():
        p = Path(name); q.charge('fingerprint_bytes', p.stat().st_size); assert digest(p) == z, p


def inputs(q):
    values = {}
    for p in META: q.charge('metadata_json_bytes', p.stat().st_size); values[str(p)] = load(p)
    def row(p): return next(r for r in values[str(p)]['rows'] if (r['seed'], r['rate'], r['initialization']) == KEY)
    return row(MOVING/'results.json'), row(FIXED/'results.json'), row(WEIGHTED/'results.json'), row(MEAN/'results.json')


def arrays(q):
    q.charge('case_objects'); q.charge('source_values', 3*N)
    words = np.array(np.memmap(DATA[0], dtype='i1', mode='r', shape=(65536,120,4))[START:START+W,:,1:], dtype=np.int64)
    q.charge('state_values', 2*W+6)
    states = np.memmap(DATA[1], dtype='<i4', mode='r', shape=(W+1,2,8))
    low = np.array(states[:W,1,:2], dtype=np.int64)
    highrear = np.array(states[0,1,2:], dtype=np.int64)
    return words, low, highrear


def describe(ch, moving, weighted, mean, q):
    frozen = list(map(F, weighted['vectors']['fixed_triangle']))
    own = list(map(F, moving['vectors']['moving_continuous']))
    assert ch[0] == F(moving['moving_C_triangle'][0])
    held = [q.mul(F(-3072*f,25*4*(1 << 22)), ch[j]) for j,f in enumerate((1,3))]
    state = [q.sub(held[j], frozen[j]) for j in range(2)]
    gate = [q.sub(own[j], held[j]) for j in range(2)]
    assert gate[0] == 0
    for j in range(2):
        assert q.add(state[j], gate[j]) == F(moving['vectors']['moving_minus_fixed'][j])
    vectors = {'fixed_triangle': frozen, 'mean_gate_moving': held,
               'state_with_mean_gate': state, 'own_gate_change': gate, 'moving_own_gate': own}
    g = [F(z['exact']) for z in mean['gradient_L']]; gi = [list(map(F,z['interval'])) for z in mean['gradient_L']]
    effects = {name: previous.project(g,gi,v,q) for name,v in vectors.items()}
    assert effects['fixed_triangle'] == moving['projections']['fixed_triangle']
    assert effects['moving_own_gate'] == moving['projections']['moving_continuous']
    assert q.add(F(effects['state_with_mean_gate']['exact']), F(effects['own_gate_change']['exact'])) == F(moving['projections']['moving_minus_fixed']['exact'])
    return {'seed': KEY[0], 'rate': KEY[1], 'initialization': KEY[2],
            'held_C_triangle': list(map(str,ch)), 'vectors': {n:list(map(str,v)) for n,v in vectors.items()},
            'projections': effects, 'order': 'moving_numbers_under_mean_gate_then_own_gate',
            'first_coordinate_gate_effect_zero': True, 'alternate_policy_propagated': False}


def analyze(out):
    assert not (out/'results.json').exists()
    q = Budget(load(out/'protocol.json')['main_limits']); done = False
    try:
        guard(out,q); moving,fixed,weighted,mean = inputs(q); words,low,hr = arrays(q)
        q.charge('export_cells',2*W+6); k = previous.export(low); kh = previous.export(hr)
        assert kh[2:].tolist() == fixed['original_rear_codes']
        assert [str(F(int(z),1024)) for z in kh[:2]] == fixed['continuous_kappa'][2:]
        assert [str(F(q.isum(k[:,j]),1024*W)) for j in range(2)] == mean['mean_kappa']
        coeff = list(map(F,fixed['continuous_kappa'])); den = lcm(*(z.denominator for z in coeff))
        kn = [int(z.numerator*(den//z.denominator)) for z in coeff]; assert den % 1024 == 0
        q2,sar,bits = (words[:,:,j] for j in range(3)); h = (W-1-np.arange(W))[:,None]
        q.charge('tag_decode_cells',2*N); d,d2 = 2*(bits & 1)-1, 2*((bits >> 1) & 1)-1
        q.charge('rear_Q3_PWL_cells',N); rear = vector_rear(q.vm(8,sar),fixed['original_rear_codes'])
        raw = q.vs(q.va(q.vm(1024,q2),rear),q.vm(128,d2)); assert np.all((raw >= -4096) & (raw < 4096))
        q.charge('basis_geometry_cells',4*N); phi = basis(raw)
        q.charge('front_continuous_cells',2*N)
        high = q.vs(q.va(q.vm(phi[:,:,2],kh[0]),q.vm(phi[:,:,3],kh[1])),q.vm(d,512*1024))
        ym = q.va(q.va(q.vm(phi[:,:,0],k[:,0,None]),q.vm(phi[:,:,1],k[:,1,None])),high)
        yf = q.va(q.va(q.vm(phi[:,:,0],kn[0]),q.vm(phi[:,:,1],kn[1])),q.vm(high,den//1024))
        q.charge('fixed_gate_tests',N); gf = abs(yf) >= 1024*kn[0]
        fixed_dy = q.vm(d,yf); moving_dy = q.vm(d,ym)
        fixed_sums = [q.isum(q.vm(fixed_dy,h)),q.isum(q.vm(q.vm(fixed_dy,gf),h))]
        held_sums = [q.isum(q.vm(moving_dy,h)),q.isum(q.vm(q.vm(moving_dy,gf),h))]
        cf = [F(z,8*den*N) for z in fixed_sums]; ch = [F(z,8*1024*N) for z in held_sums]
        assert list(map(str,cf)) == weighted['C_triangle']
        gate_count = int(np.count_nonzero(gf)); eq_count = int(np.count_nonzero(abs(yf) == 1024*kn[0]))
        assert gate_count == fixed['gate2_count'] and eq_count == fixed['gate_equalities']
        r = describe(ch,moving,weighted,mean,q)
        r.update(fixed_C_triangle=list(map(str,cf)),fixed_gate_count=gate_count,fixed_gate_equalities=eq_count)
        guard(out,q); write(out/'results.json',{'completed':True,'rows':[r]})
        write(out/'verification.json',{'passed':True,'cases':1,'old_fixed_weighted_moments_gate_mean_restored':True,
            'specified_order_vector_projections_and_first_coordinate_zero_exact':True,'new_policy_requests_scores_fft':0})
        done = True
        print('Mean-gate cumulative=',r['projections']['mean_gate_moving']['value'],
              'state=',r['projections']['state_with_mean_gate']['value'],'gate=',r['projections']['own_gate_change']['value'],flush=True)
    finally: q.accounting(out,'accounting_main.json',done)


def check(out):
    assert not (out/'independent_check.json').exists()
    q = Budget(load(out/'protocol.json')['independent_limits']); done = False
    try:
        guard(out,q); moving,fixed,weighted,mean = inputs(q); words,low,hr = arrays(q)
        q.charge('result_json_bytes',(out/'results.json').stat().st_size); r = load(out/'results.json')['rows'][0]
        q.charge('export_cells',2*W+6)
        k = np.array([[round(F(int(z),4096)) for z in row] for row in low],dtype=np.int64)
        kh = [round(F(int(z),4096)) for z in hr]
        assert kh[2:] == fixed['original_rear_codes']
        assert [str(F(z,1024)) for z in kh[:2]] == fixed['continuous_kappa'][2:]
        assert [str(q.div(q.total(F(int(z),1024) for z in k[:,j]),F(W))) for j in range(2)] == mean['mean_kappa']
        joint = np.concatenate([words.reshape(N,3),np.repeat(k,120,axis=0)],axis=1)
        q.charge('group_word_inputs',N)
        cells,indices,counts = np.unique(joint,axis=0,return_inverse=True,return_counts=True)
        hsums = np.zeros(len(cells),dtype=np.int64); q.charge('group_weight_integer_adds',N)
        np.add.at(hsums,indices,np.repeat(W-1-np.arange(W),120))
        assert q.total(F(int(z)) for z in counts) == N
        assert q.total(F(int(z)) for z in hsums) == F(N*(W-1),2)
        sars = sorted(set(int(z[1]) for z in cells)); q.charge('rear_Fraction_PWL_cells',len(sars))
        rt = {z:scalar_rear(z,fixed['original_rear_codes'],q) for z in sars}
        cf = list(map(F,fixed['continuous_kappa'])); sums_f = [F(0),F(0)]; sums_h = [F(0),F(0)]
        gate_count = eq_count = 0
        for cell,nn,hh in zip(cells,counts,hsums):
            q.charge('digital_state_groups'); q2,sar,bits,k1,k2 = map(int,cell)
            d,d2 = 2*(bits & 1)-1, 2*((bits >> 1) & 1)-1
            raw = int(q.sub(q.add(q.mul(1024,q2),rt[sar]),q.mul(128,d2)))
            assert -4096 <= raw < 4096
            psi = [F((1 if raw >= 0 else -1)*min(max(abs(raw)-1024*j,0),1024),8) for j in range(4)]
            cm = [F(k1,1024),F(k2,1024),*cf[2:]]
            yf = q.sub(q.total(q.mul(psi[j],cf[j]) for j in range(4)),F(64*d))
            ym = q.sub(q.total(q.mul(psi[j],cm[j]) for j in range(4)),F(64*d))
            threshold = q.mul(F(128),cf[0]); gf = abs(yf) >= threshold
            if gf: gate_count = q.add(gate_count,int(nn))
            if abs(yf) == threshold: eq_count = q.add(eq_count,int(nn))
            wf = q.mul(F(int(hh)),q.mul(F(d),yf)); wh = q.mul(F(int(hh)),q.mul(F(d),ym))
            sums_f[0] = q.add(sums_f[0],wf); sums_h[0] = q.add(sums_h[0],wh)
            if gf: sums_f[1] = q.add(sums_f[1],wf); sums_h[1] = q.add(sums_h[1],wh)
        ch = [q.div(z,F(N)) for z in sums_h]; cf_h = [q.div(z,F(N)) for z in sums_f]
        assert list(map(str,ch)) == r['held_C_triangle']
        assert list(map(str,cf_h)) == weighted['C_triangle'] == r['fixed_C_triangle']
        assert gate_count == r['fixed_gate_count'] and eq_count == r['fixed_gate_equalities']
        held = [q.mul(F(-3072*f,25*4*(1 << 22)),ch[j]) for j,f in enumerate((1,3))]
        frozen = list(map(F,weighted['vectors']['fixed_triangle'])); own = list(map(F,moving['vectors']['moving_continuous']))
        vectors = {'fixed_triangle':frozen,'mean_gate_moving':held,
            'state_with_mean_gate':[q.sub(held[j],frozen[j]) for j in range(2)],
            'own_gate_change':[q.sub(own[j],held[j]) for j in range(2)],'moving_own_gate':own}
        assert vectors['own_gate_change'][0] == 0
        for j in range(2): assert q.add(vectors['state_with_mean_gate'][j],vectors['own_gate_change'][j]) == F(moving['vectors']['moving_minus_fixed'][j])
        for name,v in vectors.items():
            assert list(map(str,v)) == r['vectors'][name]
            value = q.total(q.mul(F(mean['gradient_L'][j]['exact']),v[j]) for j in range(2))
            ends = [q.total(q.mul(F(mean['gradient_L'][j]['interval'][end if v[j] >= 0 else 1-end]),v[j]) for j in range(2)) for end in (0,1)]
            assert pack(value,ends) == r['projections'][name]
        guard(out,q)
        write(out/'independent_check.json',{'passed':True,'cases':1,'digital_export_groups':len(cells),
            'rear_Fraction_lookups':len(sars),'fixed_gate_and_two_weighted_correlations_exact':True,
            'separate_vector_and_target_interval_checks_exact':True,'main_masks_or_bases_read':0})
        p = r['projections']['mean_gate_moving']; lo,hi = map(F,p['interval'])
        write(out/'summary.json',{'passed':True,'cases':1,'held_gate_cumulative_positive_certified':lo > 0,
            'held_gate_cumulative_negative_certified':hi < 0,'held_gate_cumulative_unresolved':lo <= 0 <= hi,
            'own_gate_necessary_for_flip_in_this_comparison':hi < 0,
            'all20_original_context_preserved':True,'new_policies_scores_fft':0})
        done = True; print('Independent Fraction joint-state/digital mean-gate check passed.',flush=True)
    finally: q.accounting(out,'accounting_independent.json',done)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('mode',choices=['freeze','analyze','check']); p.add_argument('--out',type=Path,required=True)
    args = p.parse_args()
    try: {'freeze':freeze,'analyze':analyze,'check':check}[args.mode](args.out)
    except Exception:
        if args.out.exists(): write(args.out/(args.mode+'_failure.json'),{'traceback':traceback.format_exc()})
        raise
