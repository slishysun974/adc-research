"""Same saved history: Q22 request-rounding support bound, not a new policy."""
import argparse
from fractions import Fraction as F
from itertools import product
from pathlib import Path
import hashlib
import json
import shutil
import traceback

ROOT = Path('D:/ADC')
WEIGHTED = ROOT/'artifacts/research/full_front_weighted_fixed_mean_20261014_v1'
MEAN = ROOT/'artifacts/research/full_front_mean_learning_20261014_v1'
RUN = ROOT/'artifacts/runs/EXP_075/front_sampling_v1'
W = 2048
Q = 1 << 22
CASES = [(202610625, 'base', 'actual'), (202610625, 'quarter', 'prefix')]
META = [WEIGHTED/'results.json', WEIGHTED/'verification.json',
        WEIGHTED/'independent_check.json', WEIGHTED/'summary.json',
        MEAN/'results.json', MEAN/'verification.json',
        MEAN/'independent_check.json', RUN/'summary.json', RUN/'verification.json']
DOCS = ['docs/STATUS.md', 'docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md',
        'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md',
        'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
        'docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md',
        'docs/reports/GU_ALGORITHM_EVALUATION_V1.md',
        'docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
        'docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md',
        'docs/reports/experiments/EXP_075_FRONT_SAMPLING_INTERVENTION_V1.md',
        'experiments/exp_075_front_sampling_intervention/README.md']


def read(p): return p.read_text(encoding='utf-8-sig')
def load(p): return json.loads(read(p))
def write(p, obj): p.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()


class Budget:
    def __init__(self, limits):
        self.limits = limits
        self.used = {k: 0 for k in limits}

    def charge(self, k, n=1):
        assert k in self.limits, k
        self.used[k] += n
        assert self.used[k] <= self.limits[k], (k, self.used[k], self.limits[k])

    def add(self, x, y): self.charge('scalar_add'); return x+y
    def sub(self, x, y): self.charge('scalar_add'); return x-y
    def mul(self, x, y): self.charge('scalar_mul'); return x*y
    def div(self, x, y): self.charge('scalar_div'); return x/y
    def total(self, values):
        z = F(0)
        for v in values: z = self.add(z, v)
        return z

    def accounting(self):
        return {'completed': True, 'all_limits_met': True, 'used': self.used, 'limits': self.limits}


def nearest_even(z):
    a, rem = divmod(z.numerator, z.denominator)
    twice = 2*rem
    return a+(twice > z.denominator or (twice == z.denominator and a % 2 == 1))


def controls(q):
    # The rounding control is an exact rational arithmetic kernel, not an ADC readout.
    for z, expected in [(F(1,2),0),(F(-1,2),0),(F(3,2),2),(F(-3,2),-2),
                        (F(49,100),0),(F(51,100),1)]:
        assert nearest_even(z) == expected
        assert abs(q.sub(F(expected), z)) <= F(1,2)
    h = [2,1,0]
    a = q.div(q.total(q.mul(F(t),F(1,2)) for t in h), F(3))
    assert a == F(1,2) == q.div(F(3-1),F(4))
    assert q.div(q.total(q.mul(F(t),F(-1,2)) for t in h),F(3)) == -a
    changed = [F(1,2),F(1,2),F(-1,2)]
    assert q.div(q.total(q.mul(F(t),z) for t,z in zip(h,changed)),F(3)) == a
    # Correlated, adversarial errors attain the support bound; no cancellation.
    support = q.add(q.mul(F(2),a),q.mul(F(-3),-a))
    assert support == q.mul(F(5),a)
    assert q.div(F(1-1),F(4)) == 0
    # Local error support is not a feedback trajectory bound.
    local = F(1,2)
    assert q.add(q.mul(F(2),local),local) > local
    return {'passed': True, 'controls': 6, 'half_ties_both_signs': True,
            'triangle_correlated_extrema_last_zero_W1': True,
            'gradient_support_and_feedback_boundary': True,
            'accounting': q.accounting()}


def freeze(out):
    assert not out.exists(), 'Refuse overwrite'
    for p in META:
        if p.name != 'results.json': assert load(p)['passed'], p
    assert load(RUN/'summary.json')['state_clipped_components_total'] == 0
    inputs = META+[ROOT/'docs/theory/STATIC_FIXED_POINT_ERROR_AND_LEARNING_V1.md']
    out.mkdir(parents=True)
    write(out/'source_hashes.json', {str(p): digest(p) for p in inputs})
    shutil.copyfile(Path(__file__), out/'frozen_analysis.py')
    for name in DOCS:
        p = out/'documents_before'/name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, p)
    shared = {'fingerprint_bytes': 2*sum(p.stat().st_size for p in inputs),
              'metadata_json_bytes': sum(p.stat().st_size for p in META), 'case_objects': 2}
    write(out/'protocol.json', {
        'date': '2026-10-14', 'version': 'EXP075-same-history-Q22-support-v1',
        'authority': 'User continues D136..140; current STATUS names the two-case Q22-only explanation question.',
        'question': 'Can Q22 nearest-even request rounding ALONE cover either remaining positive target projection?',
        'cases': CASES, 'window_count': W, 'Q22_scale': Q,
        'conditions': 'Original saved full120 trajectories, one request rounding per window/component, no state clipping verified in original EXP075 summary/replay; actual moving states/own Q3 and gates held when defining unrounded requests.',
        'identity': 'epsilon=u-RN_input, abs(epsilon)<=1/2 Q22 integer. delta22=sum((W-1-w)*epsilon)/(W*2^22); per-coordinate b=(W-1)/(4*2^22). Remainder=delta22+pre_round_history_difference at the SAME saved states, NOT a re-run without rounding.',
        'target': 'Same L* mean gradient intervals from completed20-case analysis and same two remaining-history projections from completed weighting analysis. |P22|<=b*sum_j max(|g_j_lower|,|g_j_upper|). Pre-round remainder projection lies in [P_rest_lower-B, P_rest_upper+B]. Original phase/input conditions retained.',
        'prediction': 'If P_rest_lower>B then Q22-only explanation is excluded. Otherwise preserve insufficient bound, not a negative rounding result. No rerun or precision chase.',
        'main_limits': {**shared, 'scalar_add': 64, 'scalar_mul': 64, 'scalar_div': 8},
        'independent_limits': {**shared, 'result_json_bytes': 30000, 'scalar_add': 2400, 'scalar_mul': 160, 'scalar_div': 20},
        'control_limits': {'scalar_add': 64, 'scalar_mul': 64, 'scalar_div': 16},
        'units': 'Scientific Fraction binary operations charged by wrappers; sums charge every input addition. Bound denominator construction counted. Integer indexing, comparisons, absolute values/sign changes, parsing/hash/format not scalar arithmetic; rounding-control kernel separately named (six calls). Offline audit units, not chip cost.',
        'independent': 'Sum all2048 nonnegative h directly, then divide by2WQ22; enumerate all16 combinations of gradient-interval corners and displacement-box corners to obtain support, avoiding main L1 formula. Reconstruct original rest projection from its vector and gradient independently. Exact rational identity/interval checks.',
        'stop': 'Two support judgments or recorded failure; no source/target array, PWL/gate/learner/state/score/FFT/policy, newEXP/NG, extra cases, horizon or future6007/8009. No attribution of pre-round aggregate to a unique source.'})
    write(out/'preparation_accounting.json', {'fingerprint_bytes': sum(p.stat().st_size for p in inputs),
          'qualified_metadata_json_bytes': sum(p.stat().st_size for p in META if p.name != 'results.json'),
          'new_source_words_targets_PWL_learning_scores': 0})
    write(out/'controls.json', controls(Budget(load(out/'protocol.json')['control_limits'])))
    protected = []
    for folder in ('docs', 'src', 'tests', 'experiments', 'rtl', '.cursor/rules'):
        protected.extend(p for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in ('.md','.mdc','.py','.json','.toml','.v','.sv','.yaml','.yml'))
    protected.extend(ROOT/p for p in ('AGENTS.md','CONTRIBUTING.md','README.md'))
    write(out/'before_protected_manifest.json', {p.relative_to(ROOT).as_posix(): digest(p) for p in protected})
    write(out/'before_raw_inventory.json', {p.relative_to(ROOT).as_posix(): [p.stat().st_size,p.stat().st_mtime_ns]
          for p in (ROOT/'artifacts/runs').rglob('*') if p.is_file()})
    print('Frozen two-case same-history Q22 support bound; no new word/target calculation.')


def guard(out, q):
    assert digest(Path(__file__)) == digest(out/'frozen_analysis.py')
    for name, z in load(out/'source_hashes.json').items():
        p = Path(name); q.charge('fingerprint_bytes',p.stat().st_size)
        assert digest(p) == z, p


def inputs(q):
    values = {}
    for p in META:
        q.charge('metadata_json_bytes',p.stat().st_size)
        values[str(p)] = load(p)
    assert values[str(RUN/'summary.json')]['state_clipped_components_total'] == 0
    weighted = {(r['seed'],r['rate'],r['initialization']):r for r in values[str(WEIGHTED/'results.json')]['rows']}
    means = {(r['seed'],r['rate'],r['initialization']):r for r in values[str(MEAN/'results.json')]['rows']}
    assert set(weighted) == set(CASES) and len(means) == 20
    return weighted, means


def analyze(out):
    assert not (out/'results.json').exists(), 'Refuse overwrite'
    q = Budget(load(out/'protocol.json')['main_limits'])
    guard(out,q); weighted,means = inputs(q)
    b = q.div(F(W-1),q.mul(F(4),F(Q)))
    rows = []
    for key in CASES:
        q.charge('case_objects')
        r, mean = weighted[key], means[key]
        gbox = [list(map(F,z['interval'])) for z in mean['gradient_L']]
        G = [max(map(abs,line)) for line in gbox]
        B = q.mul(b,q.total(G))
        rest = r['projections']['remaining_history']
        lo,hi = map(F,rest['interval'])
        interval = [q.sub(lo,B),q.add(hi,B)]
        rows.append({'seed':key[0], 'rate':key[1], 'initialization':key[2],
             'gradient_L_intervals': [[str(v) for v in line] for line in gbox],
             'gradient_abs_upper': list(map(str,G)), 'coordinate_rounding_bound':str(b),
             'Q22_projection_abs_upper':str(B), 'Q22_projection_abs_upper_value':float(B),
             'remaining_history_projection':rest,
             'pre_round_remainder_projection_interval':list(map(str,interval)),
             'pre_round_remainder_projection_interval_values':list(map(float,interval)),
             'Q22_alone_excluded':lo>B, 'pre_round_remainder_positive_certified':interval[0]>0,
             'counterfactual_policy_propagated':False})
    guard(out,q)
    write(out/'results.json', {'completed':True, 'rows':rows})
    write(out/'accounting_main.json',q.accounting())
    write(out/'verification.json', {'passed':True, 'same_saved_history_no_state_clipping':True,
         'same_gradient_box_and_original_phase_conditions':True, 'cases':2,
         'triangle_output_before_last_weight_zero':True, 'bound_not_feedback_trajectory_difference':True})
    print(json.dumps([{'rate':r['rate'],'init':r['initialization'],
                      'Q22_abs_upper':r['Q22_projection_abs_upper_value'],
                      'pre_round_lower':r['pre_round_remainder_projection_interval_values'][0],
                      'excluded':r['Q22_alone_excluded']} for r in rows],indent=2))


def check(out):
    assert not (out/'independent_check.json').exists(), 'Refuse overwrite'
    q = Budget(load(out/'protocol.json')['independent_limits'])
    guard(out,q); weighted,means = inputs(q)
    q.charge('result_json_bytes',(out/'results.json').stat().st_size)
    actual = load(out/'results.json')['rows']
    hsum = q.total(F(W-1-w) for w in range(W))
    denom = q.mul(q.mul(F(2),F(W)),F(Q))
    b = q.div(hsum,denom)
    for key,r in zip(CASES,actual):
        q.charge('case_objects')
        gbox = [list(map(F,z['interval'])) for z in means[key]['gradient_L']]
        # Independent rectangular support optimization, no L1 sum.
        extrema = []
        for gradient in product(*gbox):
            for displacement in product((-b,b),repeat=2):
                extrema.append(q.total(q.mul(x,y) for x,y in zip(gradient,displacement)))
        B = max(extrema)
        assert min(extrema) == -B
        assert str(b) == r['coordinate_rounding_bound'] and str(B) == r['Q22_projection_abs_upper']
        delta = list(map(F,weighted[key]['vectors']['remaining_history']))
        g = [F(z['exact']) for z in means[key]['gradient_L']]
        nominal = q.total(q.mul(x,y) for x,y in zip(g,delta))
        projected = [q.total(q.mul(x,y) for x,y in zip(corner,delta)) for corner in product(*gbox)]
        prior = weighted[key]['projections']['remaining_history']
        assert str(nominal) == prior['exact']
        lo,hi = min(projected),max(projected)
        assert [str(lo),str(hi)] == prior['interval']
        interval = [q.sub(lo,B),q.add(hi,B)]
        assert list(map(str,interval)) == r['pre_round_remainder_projection_interval']
        assert (lo>B) == r['Q22_alone_excluded'] == (interval[0]>0)
    guard(out,q)
    write(out/'accounting_independent.json',q.accounting())
    write(out/'independent_check.json', {'passed':True, 'direct_2048_weight_sum':str(hsum),
          'sixteen_gradient_displacement_corners_per_case':True,
          'old_remaining_vector_nominal_and_gradient_interval_exact':True,
          'same_bound_and_pre_round_interval_exact':True,'new_words_or_PWL_or_target_reads':0})
    write(out/'summary.json', {'passed':True,'cases':2,
          'Q22_alone_excluded':sum(r['Q22_alone_excluded'] for r in actual),
          'pre_round_positive_certified':sum(r['pre_round_remainder_positive_certified'] for r in actual),
          'all20_context_preserved':True,'new_learner_source_target_PWL_scores_fft':0,
          'same_saved_history_bound_not_rerun_difference':True})
    print('Independent2048-weight sum, box corners and old vector projections exact; all limits met.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode',choices=('freeze','analyze','check'))
    parser.add_argument('--out',required=True,type=Path)
    args = parser.parse_args()
    try:
        globals()[args.mode](args.out)
    except Exception:
        if args.out.exists():
            p = args.out/f'failure_{args.mode}.txt'
            assert not p.exists(), 'Existing failure preserved; do not reset'
            p.write_text(traceback.format_exc(),encoding='utf-8')
        raise
