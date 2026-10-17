"""One saved mean-to-witness direction: required target information.

Scalar JSON reuse only. No source arrays, PWL, gates, output score or learning.
The coarse q1 set is a relaxation, not a set of full-history physical worlds.
"""
import argparse
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import shutil
import traceback

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'artifacts/research'
INFO = BASE / 'discrepancy_information_20261014_v1'
CON = BASE / 'full_front_mean_learning_20261014_v1'
FIX = BASE / 'fixed_shadow_statistics_20261015_v1'
POS = BASE / 'mean_shadow_position_bridge_20261015_v3'
FILES = ([INFO / n for n in ('results.json', 'verification.json', 'independent_check.json')]
         + [CON / n for n in ('results.json', 'source_hashes.json', 'verification.json', 'independent_check.json')]
         + [FIX / n for n in ('results.json', 'protocol.json', 'independent_check.json', 'residual_reuse.json')]
         + [POS / n for n in ('results.json', 'protocol.json', 'independent_check.json')])
KEY = (202610625, 'quarter', 'prefix')


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


class Budget:
    def __init__(self, limits):
        self.limits, self.used = limits, dict.fromkeys(limits, 0)

    def charge(self, name, count=1):
        self.used[name] += count
        assert self.used[name] <= self.limits[name], (name, self.used[name], self.limits[name])

    def add(self, a, b):
        self.charge('fraction_add'); return a + b

    def sub(self, a, b):
        self.charge('fraction_add'); return a - b

    def mul(self, a, b):
        self.charge('fraction_mul'); return a * b

    def div(self, a, b):
        self.charge('fraction_div'); return a / b

    def dot(self, a, b):
        return self.add(self.mul(a[0], b[0]), self.mul(a[1], b[1]))

    def mv(self, h, v):
        return [self.dot(line, v) for line in h]

    def load(self, path):
        self.charge('old_json_bytes', path.stat().st_size); return read(path)

    def sha(self, path):
        self.charge('fingerprint_bytes', path.stat().st_size)
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def save(self, out, stage, done):
        write(out / ('accounting_' + stage + '.json'),
              {'completed': done, 'used': self.used, 'limits': self.limits,
               'all_limits_met': all(self.used[k] <= v for k, v in self.limits.items())})


def row(value):
    return next(r for r in value['rows'] if (r['seed'], r['rate'], r['initialization']) == KEY)


def normalize(mapping):
    return {str((Path(n) if Path(n).is_absolute() else ROOT / n).resolve()): z
            for n, z in mapping.items()}


def inputs(q, protocol):
    d = {str(p): q.load(p) for p in FILES}
    for folder in (INFO, CON):
        for name in ('verification.json', 'independent_check.json'):
            assert d[str(folder / name)]['passed']
    for folder in (FIX, POS):
        assert d[str(folder / 'independent_check.json')]['passed']
    assert d[str(FIX / 'residual_reuse.json')]['r_nonzero_certified']
    lineage = normalize(d[str(CON / 'source_hashes.json')])
    assert lineage[str(INFO / 'results.json')] == protocol['source_sha256'][str(INFO / 'results.json')]
    for folder in (FIX, POS):
        lineage = normalize(d[str(folder / 'protocol.json')]['source_hashes'])
        assert lineage[str(CON / 'results.json')] == protocol['source_sha256'][str(CON / 'results.json')]
    lineage = normalize(d[str(FIX / 'protocol.json')]['source_hashes'])
    assert lineage[str(POS / 'results.json')] == protocol['source_sha256'][str(POS / 'results.json')]
    info, con, fixed = row(d[str(INFO / 'results.json')]), row(d[str(CON / 'results.json')]), d[str(FIX / 'results.json')]
    assert fixed['case'] == d[str(POS / 'results.json')]['case'] == list(KEY)
    assert [r['position'] for r in fixed['rows']] == ['shadow_actual_mean', 'prior_legal_witness']
    return info, con, fixed


def guard(q, out, protocol):
    for name, expected in protocol['source_sha256'].items():
        assert q.sha(Path(name)) == expected, name
    assert q.sha(Path(__file__)) == q.sha(out / 'frozen_analysis.py') == protocol['execution_sha256']


def pack(value, interval=None):
    answer = {'exact': str(value), 'value': float(value)}
    if interval is not None:
        answer.update(interval=list(map(str, interval)), sign_certified=interval[0] > 0 or interval[1] < 0)
    return answer


def project(q, boxes, vector):
    lo = hi = F(0)
    for (a, b), z in zip(boxes, vector):
        x, y = q.mul(a, z), q.mul(b, z)
        lo, hi = q.add(lo, min(x, y)), q.add(hi, max(x, y))
    return lo, hi


def controls(q):
    # Finite cost has curvature; the directional derivative alone is insufficient.
    g, delta, h = F(-3), F(2), F(2)
    assert q.add(q.mul(g, delta), q.mul(h, q.mul(delta, delta))) == 2
    # Shared-sign bases give a lower AND an upper absolute projection bound.
    ma, v = [F(2), F(1)], [F(-1), F(2)]
    assert abs(q.dot(ma, v)) == 0
    upper = q.dot(ma, list(map(abs, v)))
    direct = q.div(q.add(abs(q.dot(v, [F(4), F(0)])), abs(q.dot(v, [F(0), F(2)]))), F(2))
    assert direct == upper == 4
    # A strict threshold needs the entire interval on one side; equality is not descent.
    assert q.sub(F(2), q.mul(F(2), F(1))) == 0
    # Signed projection must reverse interval endpoints for a negative coordinate.
    assert project(q, [(F(1), F(2)), (F(3), F(4))], [F(-1), F(1)]) == (F(1), F(3))
    # Fixed digital learning C can accompany either target direction (NG-28 algebra).
    assert q.mul(F(-1), q.mul(F(2), q.sub(F(1), F(0)))) < 0
    assert q.mul(F(-1), q.mul(F(2), q.sub(F(1), F(3, 2)))) > 0
    # Zero proposed output change gives zero cost under any target bound.
    assert q.dot([F(0), F(0)], [F(100), F(-100)]) == 0
    return {'passed': True, 'controls': 6, 'physical_counterexample_added': False}


def prepare(out):
    assert not out.exists(), 'Refuse overwrite'
    out.mkdir(parents=True)
    code = Path(__file__).stat().st_size
    size = sum(p.stat().st_size for p in FILES)
    limits = {'old_json_bytes': size, 'fingerprint_bytes': 2 * size + 4 * code,
              'fraction_add': 512, 'fraction_mul': 512, 'fraction_div': 64}
    # Preparation hashes/parses no science values and does not evaluate a direction.
    q = Budget({'fingerprint_bytes': size + 2 * code})
    hashes = {str(p): q.sha(p) for p in FILES}
    digest = q.sha(Path(__file__))
    shutil.copyfile(__file__, out / 'frozen_analysis.py')
    assert q.sha(out / 'frozen_analysis.py') == digest
    protocol = {
        'version': 'EXP076-single-direction-information-v1', 'date': '2026-10-15',
        'case': list(KEY), 'authority': 'D136..140; user continues mainline; STATUS prioritizes direction information.',
        'scope': 'One direction only: saved mean-shadow low2 mean to the original legal witness. No new position, root, path or score.',
        'formula': 'delta=kW-kF; u=psi_low^T delta; B=2(H*kF+pd)^T delta+delta^T H delta; p=tp^T delta. DeltaL*=B-2p. Strict improvement certified iff lower p>B/2 for the supplied scalar interval.',
        'coarse_test': 'Nominal inner q1 gives |tau|<=256. Shared-sign PWL bases imply |delta^T E|psi||<=E|u|<=|delta|^T E|psi|. If |B|<512 times the lower bound, even the EXACT independent-q1-box support interval crosses zero. Do not claim these relaxed endpoints fit q2/SAR/full history.',
        'target_condition': 'Reuse original NG39 box via stored gradient intervals; no phase refinement or target table. Interval width preserved under known gradient shift. Independent W-gradient trapezoid and endpoint quadratic expansion.',
        'prediction': 'A finite witness direction can remain conditionally descending while Gu C is nonzero. Test whether coarse q1 constraints certify it; do not assume sign before execution. Passing sine bounds do not prove Gu owns target knowledge.',
        'units': 'Full old JSON bytes; every source and both execution copies hashed before/after. Wrapped Fraction add/sub/mul/div counted. Fraction parse, unary/abs/compare/index/display and administrative local protocol/result/document reads excluded and identified. No source arrays or binary64 target generation.',
        'stages': {k: limits for k in ('controls', 'main', 'independent')},
        'source_sha256': hashes, 'execution_sha256': digest,
        'stop': 'Complete this scalar direction choice or preserve a failed qualification/budget. No new matrices, absolute-projection arrays, model/horizon, optimization, online algorithm, FFT or holdout.'}
    # Controls do not read old JSON or fingerprint files.
    protocol['stages']['controls'] = {'fraction_add': 128, 'fraction_mul': 128, 'fraction_div': 16}
    write(out / 'protocol.json', protocol)
    q.save(out, 'preparation', True)


def execute(stage, out):
    p = read(out / 'protocol.json')
    q = Budget(p['stages'][stage])
    done = False
    try:
        if stage == 'controls':
            write(out / 'controls.json', controls(q)); done = True; return
        assert read(out / 'controls.json')['passed']
        guard(q, out, p)
        info, con, fixed = inputs(q, p)
        h = [list(map(F, line)) for line in con['H']]
        pd, tp, ma = [list(map(F, info[name])) for name in ('pd', 'tp', 'mean_abs_basis')]
        kr = list(map(F, con['mean_kappa'][:2]))
        k, w = [list(map(F, r['kappa_low2'])) for r in fixed['rows']]
        delta = [q.sub(w[j], k[j]) for j in range(2)]
        hk, hr = q.mv(h, k), q.mv(h, kr)
        # Confirms unchanged rear/high/source/evaluation contract via the original gradient.
        original = [q.mul(F(2), q.sub(q.add(hr[j], pd[j]), tp[j])) for j in range(2)]
        assert original == [F(z['exact']) for z in con['gradient_L']]
        mean_g = [F(z) for z in fixed['rows'][0]['true_continuous_gradient']]
        assert mean_g == [q.mul(F(2), q.sub(q.add(hk[j], pd[j]), tp[j])) for j in range(2)]
        curve = q.dot(delta, q.mv(h, delta))
        if stage == 'main':
            digital = q.add(q.mul(F(2), q.dot([q.add(hk[j], pd[j]) for j in range(2)], delta)), curve)
            target = q.dot(tp, delta)
            cost = q.sub(digital, q.mul(F(2), target))
            tpbox = []
            for j, old in enumerate(con['gradient_L']):
                a, b = map(F, old['interval'])
                center = q.add(hr[j], pd[j])
                tpbox.append((q.sub(center, q.div(b, F(2))), q.sub(center, q.div(a, F(2)))))
            pl, pu = project(q, tpbox, delta)
            bounds = (q.sub(digital, q.mul(F(2), pu)), q.sub(digital, q.mul(F(2), pl)))
            lower, upper = abs(q.dot(ma, delta)), q.dot(ma, list(map(abs, delta)))
            coarse_radius = q.mul(F(512), upper)
            exact_coarse_crosses = abs(digital) < q.mul(F(512), lower)
            threshold = q.div(digital, F(2))
            result = {'case': list(KEY), 'family': 'L*: continuous front, original fixed Q3 rear/high',
                      'k_mean': list(map(str, k)), 'k_witness': list(map(str, w)), 'delta': list(map(str, delta)),
                      'digital_B': pack(digital), 'target_projection_p': pack(target, (pl, pu)),
                      'strict_improvement_threshold': pack(threshold),
                      'certified_projection_margin': pack(q.sub(pl, threshold)),
                      'curvature': pack(curve), 'finite_Lstar_difference': pack(cost, bounds),
                      'absolute_output_change_lower': str(lower), 'absolute_output_change_upper': str(upper),
                      'coarse_outer_cost_interval': list(map(str, (q.sub(digital, coarse_radius), q.add(digital, coarse_radius)))),
                      'exact_independent_q1_box_cost_interval_crosses_zero_proved': exact_coarse_crosses,
                      'all_full_history_compatible_targets_on_both_sides_proved': False,
                      'legal_mean_integer_readout_or_online_choice_proved': False}
            write(out / 'results.json', result)
        else:
            result = read(out / 'results.json')
            gw = [F(z) for z in fixed['rows'][1]['true_continuous_gradient']]
            # Endpoint quadratic contrast, with no nominal digital/target cost subtraction.
            e = [q.sub(pd[j], tp[j]) for j in range(2)]
            def polynomial(z):
                return q.add(q.dot(z, q.mv(h, z)), q.mul(F(2), q.dot(e, z)))
            cost = q.sub(polynomial(w), polynomial(k))
            trapezoid = q.dot([q.div(q.add(gw[j], mean_g[j]), F(2)) for j in range(2)], delta)
            assert cost == trapezoid == F(result['finite_Lstar_difference']['exact'])
            # W endpoint derivative gives the SAME finite contrast after subtracting curvature.
            gl, gu = project(q, [list(map(F, z)) for z in fixed['rows'][1]['gradient_intervals']], delta)
            bounds = (q.sub(gl, curve), q.sub(gu, curve))
            assert list(map(str, bounds)) == result['finite_Lstar_difference']['interval']
            digital = q.add(cost, q.mul(F(2), q.dot(tp, delta)))
            assert digital == F(result['digital_B']['exact'])
            # Opposite-sign delta: reverse triangle lower bound uses same-sign bases.
            assert delta[0] < 0 < delta[1] and all(z >= 0 for z in ma)
            a, b = q.mul(abs(delta[0]), ma[0]), q.mul(delta[1], ma[1])
            assert abs(q.sub(b, a)) == F(result['absolute_output_change_lower'])
            assert q.add(a, b) == F(result['absolute_output_change_upper'])
            threshold = q.div(digital, F(2))
            pl, pu = map(F, result['target_projection_p']['interval'])
            assert bounds[1] < 0 and pl > threshold
            assert result['exact_independent_q1_box_cost_interval_crosses_zero_proved']
            assert abs(digital) < q.mul(F(512), abs(q.sub(b, a)))
            write(out / 'independent_check.json', {'passed': True, 'endpoint_polynomial_and_trapezoid_exact': True,
                  'W_endpoint_gradient_box_exact': True, 'coarse_crossing_lower_bound_verified': True,
                  'target_projection_threshold_verified': True, 'new_target_table_or_PWL_used': False})
        guard(q, out, p)
        if stage == 'main':
            write(out / 'summary.json', {'completed': True, 'one_direction': True,
                  'conditional_sine_improvement_certified': bounds[1] < 0,
                  'coarse_q1_relaxation_insufficient': exact_coarse_crosses,
                  'no_all_history_impossibility_or_online_algorithm_claim': True})
        done = True
    except Exception:
        write(out / ('failure_' + stage + '.json'), {'error': traceback.format_exc(), 'used': q.used})
        raise
    finally:
        q.save(out, stage, done)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('prepare', 'controls', 'main', 'independent'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if args.stage == 'prepare':
        prepare(args.out)
    else:
        execute(args.stage, args.out)
