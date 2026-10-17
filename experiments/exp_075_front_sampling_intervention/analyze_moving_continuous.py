"""One saved full120 path: continuous readout with its own continuous gate.

The Q1.10 exports come from the original Q22 history. No counterfactual
learner is propagated; rear Q3, front high coefficients and target stay fixed.
"""
import argparse
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import shutil
import sys
import traceback
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from experiments.exp_075_front_sampling_intervention.analyze_fixed_mean_statistics import (
    Budget, vector_rear, scalar_rear, basis, pack,
)

W = 2048; N = W*120; START = 128*256
KEY = (202610625, 'quarter', 'prefix')
OLD = ROOT/'artifacts/runs/EXP_062/background_v1'
RUN = ROOT/'artifacts/runs/EXP_075/front_sampling_v1'
MEAN = ROOT/'artifacts/research/full_front_mean_learning_20261014_v1'
FIXED = ROOT/'artifacts/research/full_front_fixed_mean_statistics_20261014_v1'
WEIGHTED = ROOT/'artifacts/research/full_front_weighted_fixed_mean_20261014_v1'
BOUND = ROOT/'artifacts/research/full_front_q22_rounding_bound_20261014_v1'
DEPENDENCY = ROOT/'experiments/exp_075_front_sampling_intervention/analyze_fixed_mean_statistics.py'
META = [MEAN/'results.json', MEAN/'verification.json', MEAN/'independent_check.json',
        FIXED/'results.json', FIXED/'verification.json', FIXED/'independent_check.json',
        WEIGHTED/'results.json', WEIGHTED/'verification.json', WEIGHTED/'independent_check.json',
        BOUND/'results.json', BOUND/'verification.json', BOUND/'independent_check.json',
        RUN/'summary.json', RUN/'verification.json']
DATA = [OLD/'both_smooth_202610625_words.bin',
        RUN/'202610625_quarter_q22.bin', RUN/'202610625_quarter_requests.bin']
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
def write(p, x): p.write_text(json.dumps(x, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as stream:
        for block in iter(lambda: stream.read(4194304), b''): h.update(block)
    return h.hexdigest()


def export(a):
    # Declared export kernel: quotient/remainder, nearest-even and legal range.
    quotient, remainder = np.divmod(a, 4096)
    k = quotient+((2*remainder > 4096) | ((2*remainder == 4096) & (quotient % 2 != 0)))
    assert np.all((k >= 256) & (k <= 1792))
    return k


def controls():
    # Legal coefficient ties are checked without bypassing the range check.
    a = np.array([1024*4096+2048, 1025*4096+2048, 1024*4096-2048])
    assert export(a).tolist() == [1024, 1026, 1024]
    assert export(a).tolist() == [round(F(int(z), 4096)) for z in a]
    codes = [1089, 1103, 1024, 1024]
    sar = np.array([-128, -96, -64, -32, -1, 0, 1, 31, 32, 64, 96, 127])
    assert vector_rear(8*sar, codes).tolist() == [scalar_rear(int(z), codes) for z in sar]
    # At raw=1536 Q3 units, psi=(128,64,0,0): equality and both sides.
    def y(k): return F(128)*k[0]+F(64)*k[1]-64
    k = [F(1), F(1)]
    assert y(k) == 128*k[0]
    assert abs(y(k)) >= 128*k[0]
    assert abs(y([k[0], k[1]-F(1, 1024)])) < 128*k[0]
    assert abs(y([k[0], k[1]+F(1, 1024)])) > 128*k[0]
    # Changing the saved state is an algebraic substitution, not a new path.
    psi = [F(1), F(2)]; states = [F(0), F(2)]; mean = F(1); h = [1, 0]
    fixed = sum(h[j]*psi[j]*mean for j in range(2))/2
    moving = sum(h[j]*psi[j]*states[j] for j in range(2))/2
    assert fixed == F(1, 2) and moving == 0 and moving-fixed == -F(1, 2)
    # Positive difference and positive cumulative projection are separate.
    assert F(-1)-F(-2) > 0 and F(-1) < 0
    assert F(1)-F(-2) > 0 and F(1) > 0
    assert sum(h[j]*z for j, z in enumerate([1, 2]))/2 == F(1, 2)
    assert sum(h[j]*z for j, z in enumerate([1, 900]))/2 == F(1, 2)
    return {'passed': True, 'exact_controls': 6, 'rear_scalar_vector_probes': 12,
            'export_ties_gate_equality_and_sides_same_history_last_zero': True,
            'positive_difference_does_not_imply_positive_cumulative': True}


def freeze(out):
    assert not out.exists(), 'Refuse overwrite'
    qualification_bytes = 0
    for p in META:
        if p.name in ('verification.json', 'independent_check.json', 'summary.json'):
            qualification_bytes += p.stat().st_size; assert load(p)['passed'], p
    qual = load(RUN/'summary.json')
    assert qual['state_clipped_components_total'] == qual['high_export_changed_windows_total'] == 0
    assert digest(DEPENDENCY) == digest(FIXED/'frozen_analysis.py')
    files = META+DATA+[DEPENDENCY]
    hashes = {str(p): digest(p) for p in files}
    for folder in (MEAN, FIXED, WEIGHTED, BOUND):
        for name, z in load(folder/'source_hashes.json').items():
            if name in hashes: assert hashes[name] == z, name
    out.mkdir(parents=True)
    write(out/'source_hashes.json', hashes)
    shutil.copyfile(Path(__file__), out/'frozen_analysis.py')
    for name in DOCS:
        target = out/'documents_before'/name
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT/name, target)
    common = {'fingerprint_bytes': 2*sum(p.stat().st_size for p in files),
              'metadata_json_bytes': sum(p.stat().st_size for p in META), 'case_objects': 1,
              'source_values': N*3, 'state_values': (W+1)*8, 'request_values': W*8,
              'export_cells': (W+1)*8}
    main = {**common, 'tag_decode_cells': 2*N, 'rear_Q3_PWL_cells': N,
            'front_continuous_cells': N, 'basis_geometry_cells': 4*N, 'gate_tests': N,
            'vector_add': 8*N+W*8, 'vector_mul': 16*N+2*W, 'reduction_inputs': 4*N+4*W,
            'scalar_add': 300, 'scalar_mul': 300, 'scalar_div': 30}
    independent = {**common, 'result_json_bytes': 30000, 'group_word_inputs': N,
                   'group_weight_integer_adds': N, 'digital_group_cells': N,
                   'rear_Fraction_PWL_cells': 256, 'scalar_add': 20*N+12*W,
                   'scalar_mul': 18*N+2*W, 'scalar_div': 2000}
    write(out/'protocol.json', {
        'date': '2026-10-14', 'version': 'EXP075-one-moving-continuous-history-v1',
        'authority': 'User continues D136..140; STATUS identifies625 prefix/quarter moving-continuous-versus-fixed triangle relation.',
        'case': KEY, 'scope': 'Exactly one existing case, same2048 windows/full120/eight blocks/source order/endpoint. No other19 cases evaluated, no new model/input/holdout/target/score.',
        'question': 'Does the actual Q1.10 export history with continuous front readout and its own continuous gate supply positive projection relative to the fixed mean triangle; does its own cumulative projection already turn positive?',
        'history': 'Read original output-before A[w], K[w]=nearest_even(A[w]/4096), k[w]=K[w]/1024. All8 state/request coordinates are read only to verify high/rear constancy and low state recurrence; no state is updated. High2/rear codes equal original fixed case. Low mean exactly equals old continuous_kappa. No front Q3 or Q22 request is computed.',
        'readout': 'Rear Q3 keeps separate offset/product nearest-even. psi=sign(raw)*clamp(abs(raw)-1024*j,0,1024)/8. y*_moving=sum psi_j*k[w,j]-64*d1; G1=1, G2=abs(y*)>=128*k[w,1]. This is its own continuous gate, not the original Q3 mask, not a frozen mean mask.',
        'derivation': 'Cw_M=mean120(dG_M y*_M); C_h_M=sum h_w*Cw_M/W, h=W-1-w. delta_M=-3072/(25*4*2^22)*diag(1,3)*C_h_M. delta_F is saved fixed-mean triangle. delta_move=delta_M-delta_F; delta_quant=delta_actual_Q22-delta_M. Same g_L at mean: P_F+P_move=P_M, P_M+P_quant=P_actual. Every interval directly projects its own vector onto the old SAME gradient coordinate box.',
        'Q22_bound_reuse': 'Old B22 additionally bounds projection of last request rounding on the same saved Q3 history. P_Q3_pre_minus_continuous lies in [lower(P_quant)-B22,upper(P_quant)+B22]; this involves Q3 readout AND its gate, not uniquely either. No actual rounding errors or Q3 readout are newly computed.',
        'predictions': ['Positive certified P_M means the flip already exists in the continuous readout/own-gate diagnostic, without needing the final Q3/Q22 conversion in this comparison; saved state-path quantization is still retained.',
                        'Positive P_move with negative P_M means the positive moving difference is insufficient; Q3 readout/gate relation is still needed to reach the old positive pre-Q22 actual projection.',
                        'Nonpositive P_move or intervals crossing0 preserve unresolved requirements. Never infer an alternate continuous policy or MSE improvement.'],
        'main_limits': main, 'independent_limits': independent,
        'units': 'Reviewed Budget/kernel dependency SHA frozen. Every explicit scientific outer vector add/sub/mul and reduction INPUT is charged including gate/time products; scalar binary add/sub/mul/div wrapped. Export/tag/rear-PWL/four-basis/gate kernels include internals; gate kernel includes threshold/equality/counts, export independent kernel uses Fraction round. Fixed scale/index/denominator construction, parsing/unary/compare/display/gcd excluded. Independent groups by (q2,SAR,tags,K1,K2) retain exact sum(h) through N charged integer adds; independent Fraction y/gates do not read main masks or bases. Offline units, not chip costs.',
        'validation': 'Six algebra/boundary controls and12 rear probes before scientific records. Main restores old mean, original state/request recurrence, original actual weighted low2 vector and same target projection. Independent Fraction export and per-coordinate scalar history plus joint digital/state grouping with integer h sums recover weighted continuous correlations, vector identities and independently signed endpoint intervals.',
        'stop': 'One difference and cumulative sign judgment or preserve failure. No automatic state-versus-gate split, all20 sweep, block matrices, Q3 readout/gate counterfactuals, roots, policies, learner, commits, legal references, target tables/precision chase, scores, FFT or future6007/8009.'})
    write(out/'preparation_accounting.json', {'fingerprint_bytes': sum(p.stat().st_size for p in files),
        'qualification_json_bytes': qualification_bytes, 'dependency_source_bytes': DEPENDENCY.stat().st_size,
        'new_scientific_record_calculations': 0})
    write(out/'controls.json', controls())
    print('Frozen one original export history / continuous own-gate diagnostic.', flush=True)


def guard(out, q):
    assert digest(Path(__file__)) == digest(out/'frozen_analysis.py')
    for name, z in load(out/'source_hashes.json').items():
        p = Path(name); q.charge('fingerprint_bytes', p.stat().st_size); assert digest(p) == z, p


def inputs(q):
    values = {}
    for p in META: q.charge('metadata_json_bytes', p.stat().st_size); values[str(p)] = load(p)
    def row(p):
        return next(r for r in values[str(p)]['rows'] if (r['seed'], r['rate'], r['initialization']) == KEY)
    return row(MEAN/'results.json'), row(FIXED/'results.json'), row(WEIGHTED/'results.json'), row(BOUND/'results.json')


def arrays(q):
    q.charge('case_objects'); q.charge('source_values', N*3)
    words = np.array(np.memmap(DATA[0], dtype='i1', mode='r', shape=(65536, 120, 4))[START:START+W, :, 1:], dtype=np.int64)
    q.charge('state_values', (W+1)*8); q.charge('request_values', W*8)
    states = np.array(np.memmap(DATA[1], dtype='<i4', mode='r', shape=(W+1, 2, 8))[:, 1], dtype=np.int64)
    req = np.array(np.memmap(DATA[2], dtype='<i4', mode='r', shape=(W, 2, 8))[:, 1], dtype=np.int64)
    return words, states, req


def project(g, gi, v, q):
    products = [[q.mul(endpoint, v[j]) for endpoint in gi[j]] for j in range(2)]
    return pack(q.dot(g, v), [q.total(min(line) for line in products), q.total(max(line) for line in products)])


def describe(ch, actual, mean, fixed, prior, bound, q):
    assert list(map(str, actual)) == mean['history_parts']['weighted_requests'] == prior['vectors']['actual_weighted']
    scales = [F(-3072*f, 25*4*(1 << 22)) for f in (1, 3)]
    moving = [q.mul(scales[j], ch[j]) for j in range(2)]
    frozen = list(map(F, prior['vectors']['fixed_triangle']))
    shift = [q.sub(moving[j], frozen[j]) for j in range(2)]
    quant = [q.sub(actual[j], moving[j]) for j in range(2)]
    vectors = {'fixed_triangle': frozen, 'moving_continuous': moving,
               'moving_minus_fixed': shift, 'Q3_Q22_minus_continuous': quant, 'actual_weighted': actual}
    g = [F(z['exact']) for z in mean['gradient_L']]
    gi = [list(map(F, z['interval'])) for z in mean['gradient_L']]
    assert list(map(str, gi[0])) == bound['gradient_L_intervals'][0]
    assert list(map(str, gi[1])) == bound['gradient_L_intervals'][1]
    effects = {name: project(g, gi, v, q) for name, v in vectors.items()}
    assert effects['fixed_triangle'] == prior['projections']['fixed_triangle']
    assert effects['actual_weighted'] == prior['projections']['actual_weighted']
    assert q.add(F(effects['fixed_triangle']['exact']), F(effects['moving_minus_fixed']['exact'])) == F(effects['moving_continuous']['exact'])
    assert q.add(F(effects['moving_continuous']['exact']), F(effects['Q3_Q22_minus_continuous']['exact'])) == F(effects['actual_weighted']['exact'])
    b22 = F(bound['Q22_projection_abs_upper'])
    interval = effects['Q3_Q22_minus_continuous']['interval']
    pre = [q.sub(F(interval[0]), b22), q.add(F(interval[1]), b22)]
    return {'seed': KEY[0], 'rate': KEY[1], 'initialization': KEY[2],
            'old_mean_kappa': fixed['continuous_kappa'], 'moving_C_triangle': list(map(str, ch)),
            'vectors': {name: list(map(str, v)) for name, v in vectors.items()}, 'projections': effects,
            'Q22_projection_abs_upper': str(b22), 'Q3_pre_minus_continuous_interval': list(map(str, pre)),
            'Q3_pre_minus_continuous_interval_values': list(map(float, pre)),
            'Q3_pre_difference_sign_certified': pre[0] > 0 or pre[1] < 0,
            'new_continuous_policy_propagated': False}


def analyze(out):
    assert not (out/'results.json').exists()
    q = Budget(load(out/'protocol.json')['main_limits']); done = False
    try:
        guard(out, q); mean, fixed, prior, bound = inputs(q); words, states, req = arrays(q)
        assert np.array_equal(q.vs(states[1:], states[:-1]), req)
        assert np.all(req[:, 2:] == 0)
        q.charge('export_cells', (W+1)*8); k = export(states)
        assert np.all(k[:, 2:] == k[0, 2:])
        assert k[0, 4:].tolist() == fixed['original_rear_codes']
        assert [str(F(int(q.isum(k[:-1, j])), 1024*W)) for j in range(2)] == mean['mean_kappa'] == fixed['continuous_kappa'][:2]
        assert [str(F(int(z), 1024)) for z in k[0, 2:4]] == fixed['continuous_kappa'][2:]
        h = (W-1-np.arange(W))[:, None]
        actual = [F(q.isum(q.vm(req[:, j], h[:, 0])), W*(1 << 22)) for j in range(2)]
        q2, sar, bits = (words[:, :, j] for j in range(3))
        q.charge('tag_decode_cells', 2*N); d, d2 = 2*(bits & 1)-1, 2*((bits >> 1) & 1)-1
        q.charge('rear_Q3_PWL_cells', N); rear = vector_rear(q.vm(8, sar), fixed['original_rear_codes'])
        raw = q.vs(q.va(q.vm(1024, q2), rear), q.vm(128, d2))
        assert np.all((raw >= -4096) & (raw < 4096))
        q.charge('basis_geometry_cells', 4*N); phi = basis(raw)
        q.charge('front_continuous_cells', N)
        high = q.vs(q.va(q.vm(phi[:, :, 2], k[0, 2]), q.vm(phi[:, :, 3], k[0, 3])), q.vm(d, 512*1024))
        yn = q.va(q.va(q.vm(phi[:, :, 0], k[:-1, 0, None]), q.vm(phi[:, :, 1], k[:-1, 1, None])), high)
        q.charge('gate_tests', N); gate = abs(yn) >= 1024*k[:-1, 0, None]
        dy = q.vm(d, yn); gated = q.vm(dy, gate)
        sums = [q.isum(q.vm(dy, h)), q.isum(q.vm(gated, h))]
        ch = [F(z, 8*1024*N) for z in sums]
        r = describe(ch, actual, mean, fixed, prior, bound, q)
        r['continuous_gate2_count'] = int(np.count_nonzero(gate))
        r['continuous_gate_equalities'] = int(np.count_nonzero(abs(yn) == 1024*k[:-1, 0, None]))
        r['output_before_export_pair_count'] = len(np.unique(k[:-1, :2], axis=0))
        guard(out, q); write(out/'results.json', {'completed': True, 'rows': [r]})
        write(out/'verification.json', {'passed': True, 'cases': 1,
            'old_output_before_mean_high_rear_actual_weighted_vector_exact': True,
            'original_all8_state_request_recurrence_exact': True, 'same_gradient_vector_identities_exact': True,
            'new_learner_requests_scores_fft': 0})
        done = True
        print('Continuous cumulative=', r['projections']['moving_continuous']['value'],
              'moving minus fixed=', r['projections']['moving_minus_fixed']['value'], flush=True)
    finally: q.accounting(out, 'accounting_main.json', done)


def check(out):
    assert not (out/'independent_check.json').exists()
    q = Budget(load(out/'protocol.json')['independent_limits']); done = False
    try:
        guard(out, q); mean, fixed, prior, bound = inputs(q); words, states, req = arrays(q)
        q.charge('result_json_bytes', (out/'results.json').stat().st_size)
        r = load(out/'results.json')['rows'][0]
        k = np.empty_like(states)
        for w in range(W+1):
            for j in range(8):
                q.charge('export_cells'); k[w, j] = round(F(int(states[w, j]), 4096))
                if w < W: assert q.add(int(states[w, j]), int(req[w, j])) == int(states[w+1, j])
        assert np.all(k[:, 2:] == k[0, 2:]) and np.all(req[:, 2:] == 0)
        assert k[0, 4:].tolist() == fixed['original_rear_codes']
        means = [q.div(q.total(F(int(z), 1024) for z in k[:-1, j]), F(W)) for j in range(2)]
        assert list(map(str, means)) == mean['mean_kappa']
        actual = [q.div(q.total(q.mul(F(W-1-w), F(int(req[w, j]))) for w in range(W)), F(W*(1 << 22))) for j in range(2)]
        # Joint state/digital groups preserve weighted source order exactly.
        joint = np.concatenate([words.reshape(N, 3), np.repeat(k[:-1, :2], 120, axis=0)], axis=1)
        q.charge('group_word_inputs', N)
        cells, indices, counts = np.unique(joint, axis=0, return_inverse=True, return_counts=True)
        hsums = np.zeros(len(cells), dtype=np.int64)
        q.charge('group_weight_integer_adds', N)
        np.add.at(hsums, indices, np.repeat(W-1-np.arange(W), 120))
        assert q.total(F(int(z)) for z in counts) == N
        assert q.total(F(int(z)) for z in hsums) == F(N*(W-1), 2)
        sars = sorted(set(int(z[1]) for z in cells))
        q.charge('rear_Fraction_PWL_cells', len(sars))
        rt = {z: scalar_rear(z, fixed['original_rear_codes'], q) for z in sars}
        sums = [F(0), F(0)]; gate_count = equality_count = 0
        for (q2, sar, bits, k1, k2), nn, hh in zip(cells, counts, hsums):
            q.charge('digital_group_cells'); q2, sar, bits, k1, k2 = map(int, (q2, sar, bits, k1, k2))
            d, d2 = 2*(bits & 1)-1, 2*((bits >> 1) & 1)-1
            raw = int(q.sub(q.add(q.mul(1024, q2), rt[sar]), q.mul(128, d2)))
            assert -4096 <= raw < 4096
            psi = [F((1 if raw >= 0 else -1)*min(max(abs(raw)-1024*j, 0), 1024), 8) for j in range(4)]
            coeff = [F(k1, 1024), F(k2, 1024), *map(F, fixed['continuous_kappa'][2:])]
            y = q.sub(q.total(q.mul(psi[j], coeff[j]) for j in range(4)), F(64*d))
            threshold = q.mul(F(128), coeff[0]); gate = abs(y) >= threshold
            if gate: gate_count = q.add(gate_count, int(nn))
            if abs(y) == threshold: equality_count = q.add(equality_count, int(nn))
            weighted = q.mul(F(int(hh)), q.mul(F(d), y))
            sums[0] = q.add(sums[0], weighted)
            if gate: sums[1] = q.add(sums[1], weighted)
        ch = [q.div(z, F(N)) for z in sums]
        assert list(map(str, ch)) == r['moving_C_triangle']
        assert gate_count == r['continuous_gate2_count'] and equality_count == r['continuous_gate_equalities']
        # Separate scalar vector construction and endpoint selection; no main projection helper.
        moving = [q.mul(F(-3072*f, 25*4*(1 << 22)), ch[j]) for j, f in enumerate((1, 3))]
        frozen = list(map(F, prior['vectors']['fixed_triangle']))
        vectors = {'fixed_triangle': frozen, 'moving_continuous': moving,
                   'moving_minus_fixed': [q.sub(moving[j], frozen[j]) for j in range(2)],
                   'Q3_Q22_minus_continuous': [q.sub(actual[j], moving[j]) for j in range(2)],
                   'actual_weighted': actual}
        for name, v in vectors.items():
            assert list(map(str, v)) == r['vectors'][name]
            value = q.total(q.mul(F(mean['gradient_L'][j]['exact']), v[j]) for j in range(2))
            ends = [q.total(q.mul(F(mean['gradient_L'][j]['interval'][end if v[j] >= 0 else 1-end]), v[j]) for j in range(2)) for end in (0, 1)]
            assert pack(value, ends) == r['projections'][name]
        interval = r['projections']['Q3_Q22_minus_continuous']['interval']; b22 = F(bound['Q22_projection_abs_upper'])
        assert [str(q.sub(F(interval[0]), b22)), str(q.add(F(interval[1]), b22))] == r['Q3_pre_minus_continuous_interval']
        guard(out, q)
        write(out/'independent_check.json', {'passed': True, 'cases': 1, 'digital_state_groups': len(cells),
            'rear_Fraction_lookups': len(sars), 'Fraction_export_state_recurrence_exact': True,
            'integer_group_weight_sums_continuous_gates_correlations_exact': True,
            'independent_vector_and_target_intervals_exact': True, 'main_masks_or_basis_words_read': 0})
        write(out/'summary.json', {'passed': True, 'cases': 1,
            'moving_difference_positive_certified': F(r['projections']['moving_minus_fixed']['interval'][0]) > 0,
            'moving_cumulative_positive_certified': F(r['projections']['moving_continuous']['interval'][0]) > 0,
            'moving_cumulative_negative_certified': F(r['projections']['moving_continuous']['interval'][1]) < 0,
            'Q3_pre_difference_positive_certified': F(r['Q3_pre_minus_continuous_interval'][0]) > 0,
            'all20_context_preserved': True, 'new_policies_legal_readouts_scores_fft': 0})
        done = True; print('Independent joint digital/export-state grouping verified.', flush=True)
    finally: q.accounting(out, 'accounting_independent.json', done)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('mode', choices=['freeze', 'analyze', 'check'])
    parser.add_argument('--out', type=Path, required=True); args = parser.parse_args()
    try: {'freeze': freeze, 'analyze': analyze, 'check': check}[args.mode](args.out)
    except Exception:
        if args.out.exists(): write(args.out/(args.mode+'_failure.json'), {'traceback': traceback.format_exc()})
        raise
