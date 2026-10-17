"""Offline information audit of the existing forty fixed positions.

Recover the target-free constant moment from old certified gradients and
new contractions of saved bases. A separate grouped digital calculation
checks that cancellation without a target or the saved bases. No updater.
"""
import argparse
from collections import Counter
from fractions import Fraction as F
from hashlib import sha256
from math import lcm
from pathlib import Path
import json
import shutil
import traceback
import numpy as np

ROOT = Path('D:/ADC')
ALIGN = ROOT/'artifacts/research/front_fixed_alignment_20261014_v2'
PRIOR = ROOT/'artifacts/research/mean_objective_discrepancy_20261014_v1'
BASIS = ROOT/'artifacts/research/front_block_migration_20261014_v1'
OLD = ROOT/'artifacts/runs/EXP_062/background_v1'
W, N, PERIOD, START = 2048, 2048*120, 30720, 128*256
DOCS = ['docs/STATUS.md', 'docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md',
        'docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md',
        'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md',
        'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
        'docs/reports/GU_ALGORITHM_EVALUATION_V1.md',
        'docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
        'docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md',
        'docs/reports/experiments/EXP_073_BANK_FEEDBACK_INTERVENTION_V1.md',
        'experiments/exp_073_bank_feedback_intervention/README.md']

def load(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def write(p, x):
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def digest(p):
    h = sha256()
    with p.open('rb') as f:
        for z in iter(lambda: f.read(4*1024*1024), b''):
            h.update(z)
    return h.hexdigest()

class Budget:
    def __init__(self, limits):
        self.limits, self.used = limits, dict.fromkeys(limits, 0)
    def charge(self, key, n=1):
        assert self.used[key]+n <= self.limits[key], (key, self.used[key], n)
        self.used[key] += n
    def add(self, a, b):
        self.charge('scalar_add'); return a+b
    def sub(self, a, b):
        self.charge('scalar_add'); return a-b
    def mul(self, a, b):
        self.charge('scalar_mul'); return a*b
    def total(self, vals):
        out = 0
        for v in vals:
            out = self.add(out, v)
        return out

def dot(a, b, q):
    return q.total(q.mul(x, y) for x, y in zip(a, b))

def mv(a, v, q):
    return [dot(row, v, q) for row in a]

def interval(z, rad, q):
    return {'exact': str(z), 'interval': [str(q.sub(z, rad)), str(q.add(z, rad))],
            'sign_certified': abs(z) > rad}

def vector_sum(a, q):
    a = np.asarray(a, dtype=np.int64).ravel()
    q.charge('vector_reduction_inputs', a.size)
    bound = int(np.max(np.abs(a), initial=0))
    step = min(65536, ((1 << 63)-1)//max(bound, 1))
    assert step > 0
    return q.total(int(a[i:i+step].sum()) for i in range(0, a.size, step))

def vector_dot(a, b, q):
    a, b = np.asarray(a, dtype=np.int64), np.asarray(b, dtype=np.int64)
    assert a.shape == b.shape
    assert int(np.max(abs(a), initial=0))*int(np.max(abs(b), initial=0)) < 1 << 63
    q.charge('vector_products', a.size)
    return vector_sum(a*b, q)

def integer_direction(v):
    den = lcm(*(x.denominator for x in v))
    return [x.numerator*(den//x.denominator) for x in v], den

def absolute_projection(phi, v, q):
    u, den = integer_direction(v)
    assert sum(abs(x)*1024 for x in u) < 1 << 63
    q.charge('vector_products', N*2)
    q.charge('vector_additions', N)
    z = phi[:, :, 0]*u[0]+phi[:, :, 1]*u[1]
    return F(vector_sum(abs(z), q), N*8*den)

def controls():
    # r = digital constant - local target projection; changing the target
    # keeps C and all digital quantities, and can reverse the loss direction.
    a, h, c, k, pd, tau = F(1), F(1), F(1), F(1), F(0), F(3, 2)
    b = c-a*k; rd = pd-h*b/a; r = rd-tau; g = 2*(h*k+pd-tau)
    assert r == g/2-h*c/a == -F(3, 2) and -g > 0
    assert -2*(h*k+pd-F(0)) < 0
    # Coarse box, shared target grouping, and exact finite quadratic contrast.
    assert 2*F(1)-2*F(3) < 0 < 2*F(1)+2*F(3)
    assert abs(F(1)-F(1)) < abs(F(1))+abs(F(-1))
    assert 2*(F(2)+F(1))*F(1, 2)-F(2)*F(1, 2)**2 == F(5, 2)
    assert round(F(1, 2)) == 0 and round(F(3, 2)) == 2
    return {'passed': True, 'exact_controls': 6, 'physical_counterexample': False}

def freeze(out):
    assert not out.exists(), 'Refuse overwrite'
    assert load(PRIOR/'verification.json')['passed']
    assert load(PRIOR/'independent_check.json')['passed']
    files = [ALIGN/'results.json', PRIOR/'results.json', PRIOR/'verification.json',
             PRIOR/'independent_check.json', OLD/'tone.bin']
    for seed in range(202610621, 202610626):
        files.append(OLD/f'both_smooth_{seed}_words.bin')
        for rate in ('base', 'quarter'):
            for init in ('actual', 'prefix'):
                files.append(BASIS/f'{seed}_{rate}_{init}_basis.bin')
    expected = load(ALIGN/'source_hashes.json')
    manifest = {}
    for p in files:
        z = digest(p)
        if str(p) in expected:
            assert z == expected[str(p)], p
        manifest[str(p)] = z
    out.mkdir(parents=True)
    write(out/'source_hashes.json', manifest)
    shutil.copyfile(Path(__file__), out/'frozen_analysis.py')
    for name in DOCS:
        p = out/'documents_before'/name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, p)
    metadata = sum(p.stat().st_size for p in (ALIGN/'results.json', PRIOR/'results.json'))
    shared = {'metadata_json_bytes': metadata, 'source_values': 5*N*4,
              'fingerprint_bytes': 2*sum(p.stat().st_size for p in files),
              'scalar_add': 4000000, 'scalar_mul': 4000000}
    main = {**shared, 'basis_values': 20*N*2, 'tone_values': PERIOD,
            'binary64_target_operations': 2*PERIOD,
            'vector_products': 5*N+20*N*2+100*N*2,
            'vector_additions': 5*N+100*N,
            'vector_reduction_inputs': 20*N*4+100*N,
            'phase_reduction_inputs': 20*N*2,
            'target_integer_products': 20*PERIOD*2,
            'cases': 20, 'positions': 40, 'transforms': 80,
            'directions': 80, 'position_contrasts': 20}
    independent = {**shared, 'source_group_inputs': 5*N,
                   'rear_Fraction_PWL_lookup': 20*256,
                   'digital_group_cells': 20*8192,
                   'absolute_projection_group_cells': 100*8192,
                   'cases': 20, 'transforms': 80,
                   'directions': 80, 'position_contrasts': 20}
    write(out/'protocol.json', {
        'date': '2026-10-14', 'version': 'EXP073-discrepancy-information-v1',
        'authority': 'User continues approved D136..140 mainline; STATUS r digital/target information gap.',
        'question': 'Can digital constant moments plus the nominal q1 target enclosure certify the existing uphill directions/positions, or is a stronger target condition still required?',
        'scope': 'Same20 records,40 prescribed fixed positions,80 continuous transforms/directions and20 legal-mean endpoint contrasts. No blocks, new positions, source generation, score, optimization, root, learner or future policy.',
        'decomposition': 'Tq=2048+512q1, tau=T-Tq; a=sum(high2 k_j*psi_j)-64d1. C=A*kappa+b, b=E_Q[d1*G*a]. pd=E_P[psi_low*a]. r=rd-tp, rd=pd-M*b, tp=E_P[psi_low*tau]. Recover pd=g/2-H*kappa+tp from previously certified true gradients and new saved-basis target contractions; independently reconstruct pd/H from grouped digital words WITHOUT target or saved bases.',
        'minimal_missing': '20 local target projections and absolute low-basis/direction projections. Old C,A,H,g suffice to recover b and pd after these contractions; full high bases need not be read or any main PWL repeated. Independent digital calculation supplies a separate authenticity check, with bounded grouped rear Fraction lookup.',
        'q1_condition': 'Original nominal no-offset/no-noise first flash, all q1 in[-3,3]: |tau|<=256, without knowledge of analog amplifiers or the sine. This is an outer box; endpoints need not reproduce q2/SAR/history. Original NG39/43 sine intervals are reused separately, not inferred from q1 alone.',
        'predictions': ['Both references in a case recover identical pd and tp; grouped digital pd and H match exactly.',
                        'rd-tp reproduces all80 r and all80 directions; 20 endpoint contrasts include full curvature.',
                        'If q1 outer intervals cross zero while original sine intervals certify signs, the tested coarse target condition is insufficient. This does not prove full-history unidentifiability.',
                        'If q1 certifies signs, report these finite conditions without claiming future online reachability.'],
        'budget_units': 'Charge all scientific binary scalar add/sub/mul in Budget (including chunk reductions and grouped moments); Fraction construction/parsing, fixed division by2, unary operations/comparisons, integer denominator alignment/gcd, indices, fixed-scale constants, geometric lookup min/sign, serialization and diagnostic counters excluded. Data vector products/additions/reduction inputs and phase reductions separately charged, binary64 target construction declared. Hash checks before/after use full-file bytes, although scientific memmap reads only the specified record. Independent scalar rear PWL lookup is counted separately. These are offline audit units, not hardware costs.',
        'main_limits': main, 'independent_limits': independent,
        'stop': 'Complete this information judgement or stop on source, equality, domain or budget failure. Preserve failed logs; no automatic expansion, new run, more target precision, future6007/8009 or algorithm.'})
    write(out/'controls.json', controls())
    print('Frozen same40 information audit', flush=True)

def guard(out, q):
    assert digest(Path(__file__)) == digest(out/'frozen_analysis.py')
    for path, expected in load(out/'source_hashes.json').items():
        p = Path(path); q.charge('fingerprint_bytes', p.stat().st_size)
        assert digest(p) == expected, path

def inputs(q):
    vals = []
    for p in (ALIGN/'results.json', PRIOR/'results.json'):
        q.charge('metadata_json_bytes', p.stat().st_size); vals.append(load(p))
    return vals[0]['rows'], vals[1]['rows'], vals[1]['positions']

def word_source(seed, q):
    q.charge('source_values', N*4)
    return np.array(np.memmap(OLD/f'both_smooth_{seed}_words.bin', dtype='i1', mode='r',
                             shape=(65536, 120, 4))[START:START+W], dtype=np.int64)

def analyze(out):
    assert not (out/'results.json').exists()
    q = Budget(load(out/'protocol.json')['main_limits']); done = []
    try:
        guard(out, q); assert load(out/'controls.json')['passed']
        aligned, prior, positions = inputs(q)
        q.charge('tone_values', PERIOD)
        tone = np.fromfile(OLD/'tone.bin', dtype='<f8')
        q.charge('binary64_target_operations', 2*PERIOD)
        target = 2048*(1+tone)
        ratios = [float(x).as_integer_ratio() for x in target]
        td = max(b for a, b in ratios); ti = [a*(td//b) for a, b in ratios]
        maps = {(r['seed'], r['rate'], r['initialization'], r['reference']): r for r in aligned}
        for seed in range(202610621, 202610626):
            words = word_source(seed, q); q1 = words[:, :, 0]
            assert np.all((q1 >= -3) & (q1 <= 3))
            q.charge('vector_products', N); q.charge('vector_additions', N)
            tq = 2048+512*q1
            for rate in ('base', 'quarter'):
                for init in ('actual', 'prefix'):
                    q.charge('cases'); case = (seed, rate, init)
                    q.charge('basis_values', N*2)
                    phi = np.fromfile(BASIS/f'{seed}_{rate}_{init}_basis.bin', dtype='<i2').reshape(W, 120, 2).astype(np.int64)
                    tp, ma = [], []
                    for j in range(2):
                        a = phi[:, :, j]
                        q.charge('phase_reduction_inputs', N)
                        ph = a.reshape(-1, PERIOD).sum(axis=0)
                        q.charge('target_integer_products', PERIOD)
                        et = F(q.total(q.mul(int(x), int(y)) for x, y in zip(ph, ti)), N*8*td)
                        eq = F(vector_dot(a, tq, q), N*8)
                        tp.append(q.sub(et, eq)); ma.append(F(vector_sum(abs(a), q), N*8))
                    refs = [maps[case+(ref,)] for ref in ('mean', 'witness')]
                    pd_ref = []
                    for row in refs:
                        q.charge('positions')
                        h = [[F(z) for z in r] for r in row['total']['H']]
                        k = [F(z, 1024) for z in row['codes'][:2]]
                        hk = mv(h, k, q)
                        pd_ref.append([q.add(q.sub(F(row['total']['gradient'][j]['exact'])/2, hk[j]), tp[j]) for j in range(2)])
                    assert pd_ref[0] == pd_ref[1]
                    pd = pd_ref[0]; records = []
                    for old in [r for r in prior if (r['seed'], r['rate'], r['initialization']) == case]:
                        q.charge('transforms'); row = maps[case+(old['reference'],)]
                        h = [[F(z) for z in r] for r in row['total']['H']]
                        a = [[F(z) for z in r] for r in old['A']]
                        m = [[F(z) for z in r] for r in old['M']]
                        k = [F(z, 1024) for z in old['codes'][:2]]
                        ak = mv(a, k, q); b = [q.sub(F(z), ak[j]) for j, z in enumerate(old['C'])]
                        mb = mv(m, b, q); rd = [q.sub(pd[j], mb[j]) for j in range(2)]
                        r = [q.sub(rd[j], tp[j]) for j in range(2)]
                        assert list(map(str, r)) == old['residual_half_gradient']
                        boxes = [interval(rd[j], q.mul(F(256), ma[j]), q) for j in range(2)]
                        d = row['total']['directions'][old['method']+'_continuous_front']
                        v = list(map(F, d['mean_step_low2'])); q.charge('directions')
                        hk = mv(h, k, q); center = q.mul(F(2), dot([q.add(hk[j], pd[j]) for j in range(2)], v, q))
                        rad = q.mul(F(512), absolute_projection(phi, v, q))
                        split = q.sub(q.add(F(old['directions']['continuous_front']['metric']['exact']), q.mul(F(2), dot(rd, v, q))), q.mul(F(2), dot(tp, v, q)))
                        assert split == F(d['derivative']['exact'])
                        records.append({'reference': old['reference'], 'method': old['method'],
                                        'b': list(map(str, b)), 'digital_residual': list(map(str, rd)),
                                        'target_projection': list(map(str, tp)), 'r': list(map(str, r)),
                                        'r_q1_boxes': boxes, 'direction': list(map(str, v)),
                                        'direction_q1_box': interval(center, rad, q),
                                        'direction_sine': d['derivative'],
                                        'digital_residual_projection': str(q.mul(F(2), dot(rd, v, q))),
                                        'target_projection_subtracted': str(q.mul(F(2), dot(tp, v, q)))})
                    pos = next(z for z in positions if (z['seed'], z['rate'], z['initialization']) == case)
                    delta = list(map(F, pos['history']['delta']))
                    row = refs[0]; h = [[F(z) for z in rr] for rr in row['total']['H']]
                    k = [F(z, 1024) for z in row['codes'][:2]]
                    hk = mv(h, k, q); curve = dot(delta, mv(h, delta, q), q)
                    center = q.sub(q.mul(F(2), dot([q.add(hk[j], pd[j]) for j in range(2)], delta, q)), curve)
                    rad = q.mul(F(512), absolute_projection(phi, delta, q)); q.charge('position_contrasts')
                    done.append({'seed': seed, 'rate': rate, 'initialization': init,
                                 'pd': list(map(str, pd)), 'tp': list(map(str, tp)),
                                 'mean_abs_basis': list(map(str, ma)), 'records': records,
                                 'position_delta': list(map(str, delta)),
                                 'position_q1_box': interval(center, rad, q),
                                 'position_sine': next(z for z in prior if (z['seed'], z['rate'], z['initialization']) == case and z['reference'] == 'mean' and z['method'] == 'selected')['position']['continuous_change']})
                    print(seed, rate, init, 'q1 directions', sum(z['direction_q1_box']['sign_certified'] for z in records), flush=True)
        guard(out, q)
        write(out/'results.json', {'completed': True, 'rows': done})
        write(out/'verification.json', {'passed': True, 'cases': 20, 'transforms': 80,
                                       'directions': 80, 'positions': 20, 'new_PWL_gates_requests_scores_learning_fft': 0})
    finally:
        write(out/'accounting_main.json', {'used': q.used, 'limits': q.limits, 'completed': len(done) == 20,
                                            'all_limits_met': all(q.used[k] <= q.limits[k] for k in q.limits)})

def scalar_rear(sar, k):
    raw = 8*sar; mag = abs(raw); j = min(mag//256, 3)
    z = round(F(256*sum(k[:j]), 1024))+round(F((mag-256*j)*k[j], 1024))
    return z if raw >= 0 else -z

def grouped_abs(groups, v, q):
    u, den = integer_direction(v); total = 0
    for pair, count in groups.items():
        q.charge('absolute_projection_group_cells')
        z = q.add(q.mul(u[0], pair[0]), q.mul(u[1], pair[1]))
        total = q.add(total, q.mul(count, abs(z)))
    return F(total, N*8*den)

def check(out):
    assert not (out/'independent_check.json').exists()
    q = Budget(load(out/'protocol.json')['independent_limits']); done = 0
    try:
        guard(out, q); aligned, prior, positions = inputs(q)
        new = load(out/'results.json')['rows']
        for seed in range(202610621, 202610626):
            words = word_source(seed, q); q.charge('source_group_inputs', N)
            # Independent grouping uses only digital q2/SAR/tags. No old phi,
            # target, vector PWL, derivative, mask or main pd contraction.
            cells, counts = np.unique(words[:, :, 1:].reshape(N, 3), axis=0, return_counts=True)
            for result in [z for z in new if z['seed'] == seed]:
                q.charge('cases'); case = (seed, result['rate'], result['initialization'])
                refs = [r for r in aligned if (r['seed'], r['rate'], r['initialization']) == case]
                k = refs[0]['codes']; vals = sorted(set(int(z[1]) for z in cells))
                q.charge('rear_Fraction_PWL_lookup', len(vals))
                rear = {v: scalar_rear(v, k[4:]) for v in vals}
                ps = [0, 0]; hs = [0, 0, 0]; groups = Counter()
                for cell, count in zip(cells, counts):
                    q.charge('digital_group_cells'); q2, sar, bits = map(int, cell); count = int(count)
                    raw = 1024*q2+rear[sar]-128*(2*((bits >> 1) & 1)-1)
                    assert -4096 <= raw < 4096
                    phi = [(1 if raw >= 0 else -1)*min(max(abs(raw)-1024*j, 0), 1024) for j in range(4)]
                    high = q.sub(q.add(q.mul(k[2], phi[2]), q.mul(k[3], phi[3])), 64*8192*(2*(bits & 1)-1))
                    for j in range(2):
                        ps[j] = q.add(ps[j], q.mul(count, q.mul(phi[j], high)))
                    for j, pair in enumerate(((0, 0), (0, 1), (1, 1))):
                        hs[j] = q.add(hs[j], q.mul(count, q.mul(phi[pair[0]], phi[pair[1]])))
                    groups[tuple(phi[:2])] += count
                pd = [F(z, N*8*8192) for z in ps]
                assert list(map(str, pd)) == result['pd']
                h = [[F(hs[0], N*64), F(hs[1], N*64)], [F(hs[1], N*64), F(hs[2], N*64)]]
                assert [[str(z) for z in rr] for rr in h] == refs[0]['total']['H']
                ma = [F(q.total(q.mul(count, abs(pair[j])) for pair, count in groups.items()), N*8) for j in range(2)]
                assert list(map(str, ma)) == result['mean_abs_basis']
                for r in result['records']:
                    q.charge('transforms'); row = next(z for z in refs if z['reference'] == r['reference'])
                    kk = [F(z, 1024) for z in row['codes'][:2]]; hk = mv(h, kk, q)
                    tp = [q.sub(q.add(hk[j], pd[j]), F(row['total']['gradient'][j]['exact'])/2) for j in range(2)]
                    assert list(map(str, tp)) == result['tp']
                    v = list(map(F, r['direction'])); q.charge('directions')
                    center = q.mul(F(2), dot([q.add(hk[j], pd[j]) for j in range(2)], v, q))
                    box = interval(center, q.mul(F(512), grouped_abs(groups, v, q)), q)
                    assert box == r['direction_q1_box']
                    for j in range(2):
                        assert interval(F(r['digital_residual'][j]), q.mul(F(256), ma[j]), q) == r['r_q1_boxes'][j]
                delta = list(map(F, result['position_delta'])); row = next(z for z in refs if z['reference'] == 'mean')
                hk = mv(h, [F(z, 1024) for z in row['codes'][:2]], q)
                center = q.sub(q.mul(F(2), dot([q.add(hk[j], pd[j]) for j in range(2)], delta, q)), dot(delta, mv(h, delta, q), q))
                box = interval(center, q.mul(F(512), grouped_abs(groups, delta, q)), q)
                q.charge('position_contrasts'); assert box == result['position_q1_box']
                done += 1
        guard(out, q)
        write(out/'independent_check.json', {'passed': True, 'cases': done,
            'target_free_grouped_pd_and_H': True, 'all_q1_bounds_exact': True,
            'target_projection_check': 'Independent digital pd/H plus old independently certified gradient; not a second new target-table contraction.',
            'new_full_record_PWL_gates_requests_scores_learning_fft': 0})
        rows = load(out/'results.json')['rows']; recs = [z for r in rows for z in r['records']]
        write(out/'summary.json', {'passed': True,
            'q1_r_nonzero_certified': sum(any(z['sign_certified'] for z in r['r_q1_boxes']) for r in recs),
            'q1_direction_signs_certified': sum(r['direction_q1_box']['sign_certified'] for r in recs),
            'sine_direction_signs_certified': sum(r['direction_sine']['sign_certified'] for r in recs),
            'nominal_uphill_directions': sum(F(r['direction_sine']['exact']) > 0 for r in recs),
            'q1_position_signs_certified': sum(r['position_q1_box']['sign_certified'] for r in rows),
            'sine_position_signs_certified': sum(r['position_sine']['sign_certified'] for r in rows),
            'nominal_uphill_positions': sum(F(r['position_sine']['exact']) > 0 for r in rows)})
        print(json.dumps(load(out/'summary.json')), flush=True)
    finally:
        write(out/'accounting_independent.json', {'used': q.used, 'limits': q.limits, 'completed': done == 20,
                                                 'all_limits_met': all(q.used[k] <= q.limits[k] for k in q.limits)})

if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('mode', choices=['freeze', 'analyze', 'check'])
    ap.add_argument('--out', type=Path, required=True); args = ap.parse_args()
    try:
        globals()[args.mode](args.out)
    except Exception:
        if args.out.exists():
            write(args.out/f'failure_{args.mode}.json', {'traceback': traceback.format_exc()})
        raise
