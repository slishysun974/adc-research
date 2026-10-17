"""Connect saved full120 mean positions to actual requests and output targets.

Only old scalar moments and saved low-two Q22/request histories are read.
No fixed-state correlation, gate, PWL, learner or new ADC score is evaluated.
"""
import argparse
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import shutil
import traceback
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
W = 2048
RUN = ROOT/'artifacts/runs/EXP_075/front_sampling_v1'
FULL = ROOT/'artifacts/research/full_front_position_variation_20261014_v1'
MIG = ROOT/'artifacts/research/front_block_migration_20261014_v1'
ALIGN = ROOT/'artifacts/research/front_fixed_alignment_20261014_v2'
INFO = ROOT/'artifacts/research/discrepancy_information_20261014_v1'
PARAM = ROOT/'artifacts/research/front_low_parameter_statistics_20261014_v1'
DOCS = ['docs/STATUS.md', 'docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md',
        'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md',
        'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
        'docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md',
        'docs/reports/GU_ALGORITHM_EVALUATION_V1.md',
        'docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
        'docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md',
        'docs/reports/experiments/EXP_075_FRONT_SAMPLING_INTERVENTION_V1.md',
        'experiments/exp_075_front_sampling_intervention/README.md']
INPUTS = [FULL/'results.json', FULL/'verification.json', FULL/'independent_check.json',
          MIG/'results.json', MIG/'verification.json', ALIGN/'results.json',
          ALIGN/'verification.json', INFO/'results.json', INFO/'verification.json',
          PARAM/'results.json', PARAM/'verification.json', RUN/'results.json',
          RUN/'verification.json', RUN/'independent_check.json', RUN/'summary.json']


def load(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))


def write(p, x):
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as stream:
        for block in iter(lambda: stream.read(4194304), b''):
            h.update(block)
    return h.hexdigest()


class Budget:
    def __init__(self, limits):
        self.limits, self.used = limits, dict.fromkeys(limits, 0)

    def charge(self, name, n=1):
        assert self.used[name]+n <= self.limits[name], (name, self.used[name], n)
        self.used[name] += n

    def add(self, a, b):
        self.charge('fraction_add'); return a+b

    def sub(self, a, b):
        self.charge('fraction_add'); return a-b

    def mul(self, a, b):
        self.charge('fraction_mul'); return a*b

    def div(self, a, b):
        self.charge('fraction_div'); return a/b

    def dot(self, a, b):
        return self.add(self.mul(a[0], b[0]), self.mul(a[1], b[1]))

    def mv(self, a, b):
        return [self.dot(row, b) for row in a]

    def accounting(self, out, name, completed):
        write(out/name, {'completed': completed, 'used': self.used,
                        'limits': self.limits, 'all_limits_met': True})


def packed(z, bounds=None):
    result = {'exact': str(z), 'value': float(z)}
    if bounds is not None:
        result.update(interval=list(map(str, bounds)), sign_certified=bounds[0] > 0 or bounds[1] < 0)
    return result


def projected(g, intervals, v, q):
    lo = hi = F(0)
    for (a, b), z in zip(intervals, v):
        x, y = q.mul(a, z), q.mul(b, z)
        lo, hi = q.add(lo, min(x, y)), q.add(hi, max(x, y))
    return packed(q.dot(g, v), (lo, hi))


def controls():
    # A two-phase, fixed-gate scalar cycle: zero mean actual request,
    # nonzero fixed-state correlation at its output-before mean.
    k = [F(0), F(2)]; a = [F(1), F(2)]; b = [F(-2), F(-2)]
    c = [a[j]*k[j]+b[j] for j in range(2)]
    u = [-z for z in c]
    assert k[0]+u[0] == k[1] and k[1]+u[1] == k[0]
    assert sum(u) == 0 and sum(a[j]*F(1)+b[j] for j in range(2))/2 == -F(1, 2)
    assert ((2-1-0)*u[0]+(2-1-1)*u[1])/2 == 1
    # Convex quadratic endpoint: a bad finite position is nonstationary.
    h, g0, d = F(2), F(-1), F(1)
    change = g0*d+h*d*d; end = g0+2*h*d
    assert change == end*d-h*d*d == 1 and end*d > 0
    # Integer-held and truly continuous-front families differ in baseline.
    eps = F(1, 4)
    assert (g0+2*eps)*d+h*d*d-change == 2*eps*d
    assert round(F(3, 2)) == 2 and round(F(5, 2)) == 2
    assert F(3, 2) != round(F(3, 2))
    # Old local gate protection is a sufficient condition only.
    assert abs(F(2)-F(1)) > F(1, 4)
    return {'passed': True, 'exact_controls': 6,
            'cycle_is_algebra_control_not_physical_model': True}


def freeze(out):
    assert not out.exists(), 'Refuse overwrite'
    for p in INPUTS:
        if p.name in ('verification.json', 'independent_check.json'):
            assert load(p)['passed'], p
    qual = load(RUN/'summary.json')
    assert qual['state_clipped_components_total'] == qual['high_export_changed_windows_total'] == 0
    files = INPUTS.copy()
    for seed in range(202610621, 202610626):
        for rate in ('base', 'quarter'):
            files.extend(RUN/f'{seed}_{rate}_{suffix}.bin' for suffix in ('q22', 'requests'))
    out.mkdir(parents=True)
    write(out/'source_hashes.json', {str(p): digest(p) for p in files})
    shutil.copyfile(Path(__file__), out/'frozen_analysis.py')
    for name in DOCS:
        target = out/'documents_before'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, target)
    common = {'fingerprint_bytes': 2*sum(p.stat().st_size for p in files),
              'metadata_json_bytes': sum(p.stat().st_size for p in INPUTS),
              'state_low_values': 20*(W+1)*2, 'request_low_values': 20*W*2,
              'export_round_checks': 20*W*2, 'history_integer_products': 20*W*2*3,
              'history_integer_adds': 20*W*2*10,
              'fraction_add': 30000, 'fraction_mul': 20000, 'fraction_div': 3000,
              'case_objects': 20}
    write(out/'protocol.json', {
        'date': '2026-10-14', 'version': 'EXP075-saved-mean-learning-connection-v1',
        'authority': 'User continues D136..140; latest STATUS asks how four bad full120 means arise from learning.',
        'scope': 'Original all20 cases; same5 seeds/two rates/two starts/eight blocks. Four positive mean-position effects are explanation subset only.',
        'question': 'Which output-target and actual-request relations follow from existing H/pd/tp and saved histories, and do old gate certificates permit fixed C/A transfer to new means?',
        'reference': 'Keep Y0 INTEGER plus psi*(k-k0) family (J) separate from true continuous-front/fixed-Q3-rear family (L). New mean is arithmetic average of output-before Q1.10 exports, without legal-grid rounding or fixed integer readout.',
        'derivation': 'gJnew=gJold+2H*(delta_new-delta_old). gLnew=2*(H*k_new+pd-tp). Endpoint changes=gnew dot delta-delta H delta. Baseline-reference change=(gJ0-gL0) dot delta. No fixed-gate condition needed for output affine family.',
        'history': 'delta=(A0-4096K0)/2^22+sum((W-1-s)*u_s)/(W*2^22)+sum(4096K_s-A_s)/(W*2^22). Last request weight0; reconstruct every saved output-before state and export. Project all three terms onto endpoint gradients; keep full curvature. Unweighted request projection is separate and is not fixed-state C.',
        'target': 'Reuse already certified coordinate gradient intervals and new position intervals under NG39/43 input conditions; interval transfer is conservative. No new tone/target tables, narrower phase box or unknown-input claim.',
        'gate_check': 'Compare new mean with both old legal mean/witness using their full continuous sufficient L-infinity rho. Failure only means no transfer certificate; it does NOT establish a gate crossing. Do not evaluate new fixed C/A/gates/Q3/requests.',
        'predictions': ['Actual three time-weighted terms exactly recover all20 saved mean gaps and original positive positions.',
                        'Bad J positions have positive endpoint radial derivative because curvature is positive. True L signs and request-source dominance are checked independently, with all exceptions retained.',
                        'No certified old cell cover leaves same-new-state fixed C/A missing; moving request means cannot replace them, even in fixed-gate linear controls.'],
        'main_limits': common, 'independent_limits': {**common, 'result_json_bytes': 1000000},
        'budget_units': 'All scientific binary Fraction operations use wrappers. Integer trajectory products/additions separately charged. Fraction construction/parsing, denominator/fixed-scale constants, quotient/remainder export kernel, index/compare/unary/display arithmetic excluded. Hash full-file bytes separate from scientific memmap low2 reads. No chip cost interpretation. Controls are fixed six algebra examples, outside data arithmetic quotas.',
        'validation': 'Six exact controls first; main state/request/export replay and endpoint/target identities. Independent scalar prefix-state average, Fraction round, two-direction elimination of baseline J gradient and initial-gradient endpoint polynomial. Exact radial agreement with saved new position power/error cross.',
        'zero_scientific_operations': ['source_conversion', 'digital_source_word_reads', 'basis_word_reads', 'tone_target_construction', 'PWL', 'gates', 'fixed_C_A', 'new_requests', 'learning', 'commits', 'ADC_integer_score', 'FFT', 'optimizer', 'future_holdout'],
        'stop': 'All20 output/history/old-cell checks or preserve failure. Deliver exact missing C/A conditions; no new fixed positions, roots, policies, horizons, precision chase or algorithms.'})
    write(out/'controls.json', controls())
    print('Frozen all20 scalar-moment / saved-history audit; no new fixed statistics.', flush=True)


def guard(out, q):
    assert digest(Path(__file__)) == digest(out/'frozen_analysis.py')
    for name, expected in load(out/'source_hashes.json').items():
        p = Path(name); q.charge('fingerprint_bytes', p.stat().st_size)
        assert digest(p) == expected, p


def inputs(q):
    values = {}
    for p in INPUTS:
        q.charge('metadata_json_bytes', p.stat().st_size)
        values[str(p)] = load(p)
    def rows(path):
        return {(r['seed'], r['rate'], r['initialization']): r for r in values[str(path)]['rows']}
    fixed = values[str(ALIGN/'results.json')]['rows']
    gates = values[str(PARAM/'results.json')]['rows']
    return rows(FULL/'results.json'), rows(MIG/'results.json'), rows(INFO/'results.json'), fixed, gates, rows(RUN/'results.json')


def arrays(key, q):
    seed, rate, init = key; h = 0 if init == 'actual' else 1
    q.charge('state_low_values', (W+1)*2); q.charge('request_low_values', W*2)
    states = np.array(np.memmap(RUN/f'{seed}_{rate}_q22.bin', dtype='<i4', mode='r', shape=(W+1, 2, 8))[:, h, :2], dtype=np.int64)
    requests = np.array(np.memmap(RUN/f'{seed}_{rate}_requests.bin', dtype='<i4', mode='r', shape=(W, 2, 8))[:, h, :2], dtype=np.int64)
    return states, requests


def gradients(key, full, mig, info, fixed, q):
    rr = next(r for r in fixed if (r['seed'], r['rate'], r['initialization']) == key and r['reference'] == 'mean')
    d = list(map(F, full['mean_export_gap']))
    # Recover the old non-grid mean from the eight block means, already saved.
    oldd = [q.div(sum_counted([F(z[j]['exact']) for z in mig['block_mean_export_gaps']], q), F(8)) for j in range(2)]
    h = [[F(z) for z in row] for row in rr['total']['H']]
    assert h == [[F(z) for z in row] for row in mig['position_moments']['Gram_H']]
    assert h[0][0] > 0 and q.sub(q.mul(h[0][0], h[1][1]), q.mul(h[0][1], h[1][0])) > 0
    k0 = [F(z, 1024) for z in rr['initial_codes'][:2]]
    knew = [q.add(k0[j], d[j]) for j in range(2)]
    shift = q.mv(h, [q.sub(d[j], oldd[j]) for j in range(2)])
    gjold = [F(z['exact']) for z in mig['position_moments']['gradient_at_mean_position']]
    gj = [q.add(gjold[j], q.mul(F(2), shift[j])) for j in range(2)]
    jintervals = [[q.add(F(z), q.mul(F(2), shift[j])) for z in line] for j, line in enumerate(mig['position_moments']['gradient_intervals'])]
    hk = q.mv(h, knew)
    gl = [q.mul(F(2), q.sub(q.add(hk[j], F(info['pd'][j])), F(info['tp'][j]))) for j in range(2)]
    oldlegal = [F(z, 1024) for z in rr['codes'][:2]]
    hshift = q.mv(h, [q.sub(knew[j], oldlegal[j]) for j in range(2)])
    lintervals = []
    for j in range(2):
        assert gl[j] == q.add(F(rr['total']['gradient'][j]['exact']), q.mul(F(2), hshift[j]))
        lintervals.append([q.add(F(z), q.mul(F(2), hshift[j])) for z in rr['total']['gradient'][j]['interval']])
    return rr, d, oldd, h, gj, jintervals, gl, lintervals


def sum_counted(values, q):
    result = F(0)
    for z in values:
        result = q.add(result, z)
    return result


def analyze(out):
    assert not (out/'results.json').exists()
    p = load(out/'protocol.json'); q = Budget(p['main_limits']); done = []
    try:
        guard(out, q); fulls, migrations, infos, fixed, gates, runrows = inputs(q)
        for key, full in fulls.items():
            q.charge('case_objects')
            rr, d, oldd, h, gj, ji, gl, li = gradients(key, full, migrations[key], infos[key], fixed, q)
            a, u = arrays(key, q)
            q.charge('history_integer_adds', W*2*2)
            reconstructed = a[0] + np.vstack((np.zeros((1, 2), dtype=np.int64), np.cumsum(u, axis=0, dtype=np.int64)))
            assert np.array_equal(a, reconstructed)
            assert a[0].tolist() == runrows[key]['initial_Q22'][:2]
            assert int(np.max(abs(u), initial=0))*W*W < 1 << 63
            q.charge('export_round_checks', W*2)
            k = np.array([[round(F(int(z), 4096)) for z in line] for line in a[:-1]], dtype=np.int64)
            k0 = rr['initial_codes'][:2]; assert k[0].tolist() == k0
            q.charge('history_integer_products', W*2*2)
            # Weighted reduction, two subtract/reduce pairs: five word kernels.
            # The six terminal reduction additions not executed are conservatively charged.
            q.charge('history_integer_adds', W*2*5)
            weighted = (u*(W-1-np.arange(W))[:, None]).sum(axis=0, dtype=np.int64)
            exp = (4096*k-a[:-1]).sum(axis=0, dtype=np.int64)
            kd = (k-np.array(k0)).sum(axis=0, dtype=np.int64)
            parts = {'initial_hidden': [F(int(a[0,j])-4096*k0[j], 1 << 22) for j in range(2)],
                     'weighted_requests': [F(int(z), W*(1 << 22)) for z in weighted],
                     'mean_export_remainder': [F(int(z), W*(1 << 22)) for z in exp]}
            assert [F(int(z), W*1024) for z in kd] == d
            assert [sum_counted([v[j] for v in parts.values()], q) for j in range(2)] == d
            q.charge('history_integer_adds', W*2)
            meanstep = [F(int(z), W*(1 << 22)) for z in u.sum(axis=0, dtype=np.int64)]
            curve = q.dot(d, q.mv(h, d))
            assert curve == F(full['stats']['components']['position']['power']['exact'])
            jp = full['stats']['effects']['position']
            radial = q.dot(gj, d)
            assert q.sub(radial, curve) == F(jp['exact'])
            radial_range = [q.add(F(z), curve) for z in jp['interval']]
            lrad = projected(gl, li, d, q)
            lpos = q.sub(F(lrad['exact']), curve)
            lpos_range = [q.sub(F(z), curve) for z in lrad['interval']]
            bridge = q.dot([q.sub(gj[j], gl[j]) for j in range(2)], d)
            assert q.sub(F(jp['exact']), lpos) == bridge
            histories = {}
            for family, grad, ints in (('J', gj, ji), ('L', gl, li)):
                ps = {name: projected(grad, ints, vec, q) for name, vec in parts.items()}
                assert sum_counted([F(z['exact']) for z in ps.values()], q) == q.dot(grad, d)
                histories[family] = {'component_projections': ps,
                                    'unweighted_mean_request_projection': projected(grad, ints, meanstep, q)}
            covers = []
            for reference in ('mean', 'witness'):
                cell = next(r for r in gates if (r['seed'], r['rate'], r['initialization']) == key and r['reference'] == reference)
                distance = max(abs(q.sub(q.add(F(rr['initial_codes'][j], 1024), d[j]), F(cell['codes'][j], 1024))) for j in range(2))
                radius = F(cell['total']['cell']['full']['rho_sufficient'])
                covers.append({'old_reference': reference, 'distance_linf': str(distance), 'rho_sufficient': str(radius),
                               'old_cell_transfer_certified': distance < radius,
                               'uncovered_does_not_prove_crossing': True})
            done.append({'seed': key[0], 'rate': key[1], 'initialization': key[2],
                         'mean_gap': list(map(str, d)), 'mean_kappa': [str(q.add(F(k0[j], 1024), d[j])) for j in range(2)],
                         'H': [[str(z) for z in line] for line in h], 'curvature': packed(curve),
                         'gradient_J': [packed(gj[j], ji[j]) for j in range(2)],
                         'gradient_L': [packed(gl[j], li[j]) for j in range(2)],
                         'nonstationary_J_certified': any(z[0] > 0 or z[1] < 0 for z in ji),
                         'nonstationary_L_certified': any(z[0] > 0 or z[1] < 0 for z in li),
                         'position_J': jp, 'radial_J': packed(radial, radial_range),
                         'position_L': packed(lpos, lpos_range), 'radial_L': lrad,
                         'baseline_reference_bridge': packed(bridge),
                         'history_parts': {name: list(map(str, vec)) for name, vec in parts.items()},
                         'mean_hidden_step': list(map(str, meanstep)), 'history_projections': histories,
                         'old_gate_cell_coverage': covers, 'new_fixed_C_A_computed': False})
        guard(out, q)
        write(out/'results.json', {'completed': True, 'rows': done})
        write(out/'verification.json', {'passed': True, 'cases': len(done),
              'saved_state_request_export_recovery': True, 'both_output_families_exact': True,
              'original_J_position_and_curvature_recovered': True, 'new_fixed_statistics': 0})
    finally:
        q.accounting(out, 'accounting_main.json', len(done) == 20)


def check(out):
    assert not (out/'independent_check.json').exists()
    q = Budget(load(out/'protocol.json')['independent_limits']); count = 0
    try:
        guard(out, q); fulls, migrations, infos, fixed, gates, runrows = inputs(q)
        q.charge('result_json_bytes', (out/'results.json').stat().st_size)
        rows = load(out/'results.json')['rows']
        solved = 0
        for r in rows:
            q.charge('case_objects'); key = r['seed'], r['rate'], r['initialization']
            a, u = arrays(key, q); current = list(map(int, a[0])); ss = [0, 0]; ks = [0, 0]; es = [0, 0]
            for w in range(W):
                for j in range(2):
                    assert current[j] == int(a[w,j])
                    q.charge('export_round_checks'); k = round(F(current[j], 4096))
                    q.charge('history_integer_products'); q.charge('history_integer_adds', 5)
                    ss[j] += current[j]; ks[j] += k; es[j] += 4096*k-current[j]
                    current[j] += int(u[w,j])
            assert current == a[-1].tolist()
            rr = next(z for z in fixed if (z['seed'], z['rate'], z['initialization']) == key and z['reference'] == 'mean')
            k0 = rr['initial_codes'][:2]; d = list(map(F, r['mean_gap']))
            weighted = [q.sub(F(ss[j], W*(1 << 22)), F(int(a[0,j]), 1 << 22)) for j in range(2)]
            assert list(map(str, weighted)) == r['history_parts']['weighted_requests']
            assert [str(F(es[j], W*(1 << 22))) for j in range(2)] == r['history_parts']['mean_export_remainder']
            assert [F(ks[j]-W*k0[j], W*1024) for j in range(2)] == d
            h = [[F(z) for z in line] for line in r['H']]
            old = migrations[key]
            od = [q.div(sum_counted([F(z[j]['exact']) for z in old['block_mean_export_gaps']], q), F(8)) for j in range(2)]
            oldpower = F(old['stats']['components']['position']['power']['exact'])
            oldlinear = F(old['stats']['components']['position']['error_cross']['exact'])
            newlinear = F(fulls[key]['stats']['components']['position']['error_cross']['exact'])
            det = q.sub(q.mul(od[0], d[1]), q.mul(od[1], d[0]))
            assert oldpower == q.dot(od, q.mv(h, od))
            if det:
                g0j = [q.div(q.sub(q.mul(oldlinear, d[1]), q.mul(od[1], newlinear)), det),
                       q.div(q.sub(q.mul(od[0], newlinear), q.mul(oldlinear, d[0])), det)]
                solved += 1
            else:
                oldg = [F(z['exact']) for z in old['position_moments']['gradient_at_mean_position']]
                ho = q.mv(h, od); g0j = [q.sub(oldg[j], q.mul(F(2), ho[j])) for j in range(2)]
            hd = q.mv(h, d); gj = [q.add(g0j[j], q.mul(F(2), hd[j])) for j in range(2)]
            assert list(map(str, gj)) == [z['exact'] for z in r['gradient_J']]
            kinit = [F(z, 1024) for z in k0]; hk = q.mv(h, kinit); info = infos[key]
            g0l = [q.mul(F(2), q.sub(q.add(hk[j], F(info['pd'][j])), F(info['tp'][j]))) for j in range(2)]
            gl = [q.add(g0l[j], q.mul(F(2), hd[j])) for j in range(2)]
            assert list(map(str, gl)) == [z['exact'] for z in r['gradient_L']]
            curve = q.dot(d, hd)
            assert a[0].tolist() == runrows[key]['initial_Q22'][:2]
            oldgj = [F(z['exact']) for z in old['position_moments']['gradient_at_mean_position']]
            jints = [[q.add(F(z), q.sub(gj[j], oldgj[j])) for z in line]
                     for j, line in enumerate(old['position_moments']['gradient_intervals'])]
            lints = [[q.add(F(z), q.sub(gl[j], F(rr['total']['gradient'][j]['exact']))) for z in line]
                     for j, line in enumerate(z['interval'] for z in rr['total']['gradient'])]
            assert [[str(z) for z in line] for line in jints] == [z['interval'] for z in r['gradient_J']]
            assert [[str(z) for z in line] for line in lints] == [z['interval'] for z in r['gradient_L']]
            assert [str(q.add(F(z), curve)) for z in fulls[key]['stats']['effects']['position']['interval']] == r['radial_J']['interval']
            lrad = projected(gl, lints, d, q)
            assert lrad == r['radial_L']
            assert [str(q.sub(F(z), curve)) for z in lrad['interval']] == r['position_L']['interval']
            for family, g0, grad in (('J', g0j, gj), ('L', g0l, gl)):
                assert q.add(q.dot(g0, d), curve) == F(r['position_'+family]['exact'])
                assert q.dot(grad, d) == F(r['radial_'+family]['exact'])
                ints = [list(map(F, z['interval'])) for z in r['gradient_'+family]]
                ps = r['history_projections'][family]['component_projections']
                for name, vec in r['history_parts'].items():
                    assert projected(grad, ints, list(map(F, vec)), q) == ps[name]
                assert projected(grad, ints, list(map(F, r['mean_hidden_step'])), q) == r['history_projections'][family]['unweighted_mean_request_projection']
            for cover in r['old_gate_cell_coverage']:
                cell = next(z for z in gates if (z['seed'], z['rate'], z['initialization']) == key and z['reference'] == cover['old_reference'])
                distance = max(abs(q.sub(q.add(F(k0[j], 1024), d[j]), F(cell['codes'][j], 1024))) for j in range(2))
                assert str(distance) == cover['distance_linf']
                assert (distance < F(cell['total']['cell']['full']['rho_sufficient'])) == cover['old_cell_transfer_certified']
            count += 1
        guard(out, q)
        write(out/'independent_check.json', {'passed': True, 'cases': count,
              'prefix_state_mean_and_export_exact': True,
              'two_direction_baseline_gradient_eliminations': solved,
              'both_initial_gradient_polynomials_and_history_projections_exact': True})
        summary = {'passed': True, 'cases': count,
                   'J_positions_positive': sum(F(r['position_J']['exact']) > 0 for r in rows),
                   'L_positions_positive': sum(F(r['position_L']['exact']) > 0 for r in rows),
                   'L_position_signs_certified': sum(r['position_L']['sign_certified'] for r in rows),
                   'nonstationary_J_certified': sum(r['nonstationary_J_certified'] for r in rows),
                   'nonstationary_L_certified': sum(r['nonstationary_L_certified'] for r in rows),
                   'new_means_covered_by_any_old_full_cell': sum(any(z['old_cell_transfer_certified'] for z in r['old_gate_cell_coverage']) for r in rows),
                   'bad_J_cases': [{k: r[k] for k in ('seed', 'rate', 'initialization', 'position_J', 'position_L', 'radial_J', 'radial_L', 'baseline_reference_bridge', 'history_parts', 'history_projections')} for r in rows if F(r['position_J']['exact']) > 0],
                   'new_fixed_C_A_gates_requests_readouts_learning_scores_fft': 0}
        write(out/'summary.json', summary)
    finally:
        q.accounting(out, 'accounting_independent.json', count == 20)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['freeze', 'analyze', 'check'])
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    try:
        {'freeze': freeze, 'analyze': analyze, 'check': check}[args.mode](args.out)
    except Exception:
        if args.out.exists():
            write(args.out/(args.mode+'_failure.json'), {'traceback': traceback.format_exc()})
        raise
