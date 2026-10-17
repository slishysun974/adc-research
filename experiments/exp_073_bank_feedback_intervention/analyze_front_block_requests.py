"""Read-only actual block requests to centered exported histories and loss.

No digital readout, gate, request or learner is recomputed. All references use
the original future record and are continuous differences for offline scoring.
"""
import argparse
from fractions import Fraction as F
from pathlib import Path
import shutil
import traceback
import numpy as np

from experiments.exp_073_bank_feedback_intervention.analyze_front_history import (
    ROOT, BASE, NEW, SEEDS, W, load, write, digest, guard, ExactProjector,
    mulsum, pack, DOCS,
)

HISTORY = ROOT/'artifacts/research/front_forcing_response_20261013_v2'
PRIOR = ROOT/'artifacts/research/front_block_migration_20261014_v1'
B = 256
D = B*B
SCALE = D*(1 << 25)
TAGS = ['block_position', 'linear_mean_drive', 'centered_request_accumulation',
        'centered_export_rounding', 'current_readout']
LIMITS = {
    'old24col_matrix_values': 983040, 'basis_values': 9830400,
    'saved_integer_output_values': 9830400,
    'profile_basis_word_products': 39321600,
    'projected_score_word_inputs': 68812800,
    'off_diagonal_Gram_word_products': 98304000,
    'request_product_rounding_scalar_checks': 81920,
    'new_profile_matrix_bytes': 2621440,
}


class Budget:
    def __init__(self):
        self.used = dict.fromkeys(LIMITS, 0)

    def charge(self, key, count):
        assert self.used[key]+count <= LIMITS[key], (key, self.used[key], count)
        self.used[key] += count


def prefix(u):
    return np.vstack((np.zeros((1, 2), dtype=np.int64), np.cumsum(u, axis=0)))


def decompose(requests, exports):
    assert requests.shape == exports.shape == (W, 2)
    u = requests.reshape(8, B, 2)
    r = np.arange(B, dtype=np.int64)[None, :, None]
    total = u.sum(axis=1)
    local_prefix = np.concatenate((np.zeros((8, 1, 2), dtype=np.int64), np.cumsum(u, axis=1)), axis=1)
    c = B*local_prefix[:, :-1]-r*total[:, None]
    assert not (B*local_prefix[:, -1]-B*total).any()
    # Numerators represent Q22 displacements with denominator B^2.
    trend = (B//2)*(2*r-(B-1))*total[:, None]
    centered = B*c-c.sum(axis=1)[:, None]
    global_prefix = prefix(requests)[:-1]
    export_gap = 4096*(exports-exports[0])-global_prefix
    eg = export_gap.reshape(8, B, 2)
    eround = B*(B*eg-eg.sum(axis=1)[:, None])
    k = (exports-exports[0]).reshape(8, B, 2)
    block_position = 4096*B*np.repeat(k.sum(axis=1)[:, None], B, axis=1)
    centered_export = 4096*B*(B*k-k.sum(axis=1)[:, None])
    assert np.array_equal(trend+centered+eround, centered_export)
    assert np.array_equal(block_position+trend+centered+eround, 4096*D*k)
    for z in (trend, centered, eround):
        assert not z.sum(axis=1).any()
    # Centered hidden history; keep exact numerator, without integer means.
    hidden = global_prefix.reshape(8, B, 2)
    assert np.array_equal(B*(B*hidden-hidden.sum(axis=1)[:, None]), trend+centered)
    return [z.reshape(W, 2) for z in (block_position, trend, centered, eround)], total, export_gap


def controls():
    constant = np.tile(np.array([3, -2], dtype=np.int64), (W, 1))
    hidden = prefix(constant)[:-1]
    k = np.rint((hidden+np.array([1 << 22, 1 << 22]))/4096).astype(np.int64)
    parts, total, e = decompose(constant, k)
    assert not parts[2].any() and parts[1].any()
    assert np.max(np.abs(e)) <= 4096
    zero = np.zeros((W, 2), dtype=np.int64)
    zz, _, _ = decompose(zero, np.full((W, 2), 1024, dtype=np.int64))
    assert all(not z.any() for z in zz)
    alternating = np.tile(np.array([[4096, -4096], [-4096, 4096]], dtype=np.int64), (W//2, 1))
    ak = 1024+prefix(alternating)[:-1]//4096
    aa, at, _ = decompose(alternating, ak)
    assert not at.any() and not aa[1].any() and aa[2].any() and not aa[3].any()
    # Finite centered-prefix endpoint is zero, even with nonzero motion inside.
    assert prefix(alternating)[-1].tolist() == [0, 0]
    assert aa[2].any()
    # Current export centering cannot be inferred from hidden centering alone.
    tiny = np.tile(np.array([[1, 0], [-1, 0]], dtype=np.int64), (W//2, 1))
    tk = np.full((W, 2), 1024, dtype=np.int64)
    tt, _, _ = decompose(tiny, tk)
    assert tt[2].any() and np.array_equal(tt[2], -tt[3])
    # Loss additions depend on cross terms and on the original target error.
    x, y, e0 = F(2), F(-1), F(-2)
    loss = lambda z: z*z+2*e0*z
    assert (loss(x+y)-loss(x))-(loss(y)-loss(0)) == 2*x*y
    assert loss(y) == 5 and loss(x+y)-loss(x) == 1
    # Exact request remainder bound after the frozen odd denominator reduction.
    assert abs(round(F(12, 25))-F(12, 25)) == F(12, 25)
    return {'passed': True, 'exact_controls': 7, 'new_physical_source': False}


def prepare(out):
    assert not out.exists(), 'Refuse overwrite'
    assert load(PRIOR/'delivery_verification.json')['numerical_and_document_acceptance_passed']
    out.mkdir(parents=True)
    files = dict(load(PRIOR/'source_hashes.json'))
    files.update(load(PRIOR/'new_moment_hashes.json'))
    for name in ('protocol.json', 'results.json', 'verification.json', 'delivery_verification.json', 'accounting.json'):
        p = PRIOR/name; files[str(p)] = digest(p)
    guard(files); write(out/'source_hashes.json', files)
    sources = list((ROOT/'src/adc_research').rglob('*.py'))+list((ROOT/'experiments').rglob('*.py'))
    write(out/'execution_hashes.json', {str(p): digest(p) for p in sources})
    shutil.copyfile(Path(__file__), out/'frozen_analysis.py')
    write(out/'protocol.json', {
        'version': 'EXP073-centered-actual-block-requests-v1', 'date': '2026-10-14',
        'authority': 'User continue research, D136..139, current STATUS block requests next steps1..3',
        'scope': 'Original20 cases, five seeds/two rates/two starts, eight256-window blocks128..135. No other length, policy, model, optimizer or future holdout.',
        'question': 'Does linear movement from the finite block mean request or accumulated centered actual requests account for the previously harmful within-block change?',
        'relation': 'For each block, A_r=A_0+r*mean(u)+prefix(u-mean(u)). Center output-before r=0..255 separately; add centered true export error to recover actual centered Q1.10 exports. Restore original integer output via the saved current-readout remainder.',
        'references': 'Block mean exported position, centered linear actual-mean drive, centered prefix of actual requests, centered actual export error. They are continuous offline differences of the saved trajectory, not separately propagated learners.',
        'alternatives': [
            'Within-block harm comes mainly from linear movement of a nonzero block mean request, versus accumulated centered requests remaining large.',
            'Actual centering removes their output cross, versus chronological integration and changing bases preserving cancellation or amplification.',
            'Hidden-state decomposition suffices, versus centered true Q1.10 export remainder changing small loss directions.'],
        'orders': ['block_position, linear_mean_drive, centered_request_accumulation, export, readout',
                   'block_position, centered_request_accumulation, linear_mean_drive, export, readout'],
        'predictions': [
            'All per-block hidden/export centers and the centered-prefix endpoint relation close exactly; no recovery or stationary-noise assumption.',
            'Full5x5 Gram and original error projections reproduce actual losses, old block-position/within-block/readout scores and160 block sums.',
            'Retain both addition orders, all zeros/opposite/uncertified signs and original39 beneficial complete-variation blocks.',
            'Check actual selected product/request rounding with stored moments and pair block mean requests with stored gate counts; do not infer loss from RMS or counts alone.'],
        'limits': LIMITS,
        'independent_limits': {'window_Gram_contractions': 409600, 'window_error_projection_contractions': 163840,
            'basis_target_word_products': 9830400, 'sparse_Fraction_word_probes': 240,
            'source_matrix_values': 983040, 'basis_values': 9830400, 'saved_output_values': 9830400,
            'saved_window_Gram_values': 204800, 'new_profiles_values': 327680},
        'no_new_counts': ['PWL', 'gates', 'requests', 'learner', 'submissions', 'paths', 'analog_source', 'FFT', 'holdout'],
        'budget_enforcement': 'Counters reserve each declared operation before execution and reject overrun. Gram off-diagonal entries are evaluated once and mirrored. Reuse saved basis/window matrices; no H-gradient multiplication or new basis matrix.',
        'stop': 'Original20/160 only. Reject source, domain, prior-score, integer-center or budget mismatch and preserve failure; do not silently increase limits.',
        'information_limits': 'Block means and centered prefixes use future requests; neither is an online Gu feature at the same cost. Original sine target knowledge certifies saved-reference projections only. Finite request means are not fixed-state roots; centered accumulation is not proven random noise.'})
    write(out/'controls.json', controls())
    for name in DOCS:
        p = out/'documents_before'/name; p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, p)
    print('Frozen original20/160, block-before-output centering, both orders and enforced operation limits', flush=True)


def inspect(nums, held, projector, old, budget):
    n = held.size
    scored = []
    for z in nums:
        budget.charge('projected_score_word_inputs', n)
        scored.append(projector.projected(z, held, SCALE))
    q = [[F(0) for _ in nums] for _ in nums]
    for i in range(5):
        q[i][i] = F(scored[i]['power']['exact'])
        for j in range(i):
            budget.charge('off_diagonal_Gram_word_products', n)
            q[i][j] = q[j][i] = F(mulsum(nums[i], nums[j]), n*SCALE*SCALE)
    bc = [F(s['error_cross']['exact']) for s in scored]
    net = lambda ids: sum(bc[i] for i in ids)+sum(q[i][j] for i in ids for j in ids)
    op = F(old['components']['position']['net']['exact'])+F(old['effects']['migration_after_position']['exact'])
    assert net([0]) == op
    assert net([0, 1, 2, 3, 4]) == F(old['actual']['net']['exact'])
    for key in ('power', 'error_cross', 'net'):
        assert scored[4][key] == old['components']['current_readout'][key]
    combined = []
    for ids in ([1, 2, 3], [0, 1, 2, 3]):
        budget.charge('projected_score_word_inputs', n)
        s = projector.projected(sum(nums[i] for i in ids), held, SCALE)
        assert F(s['net']['exact']) == net(ids)
        combined.append(s)
    assert net([0, 1, 2, 3])-net([0]) == F(old['effects']['within_after_position_migration']['exact'])
    effects = {}
    for name, i, before in [('linear_first', 1, [0]), ('accumulation_after_linear', 2, [0, 1]),
                            ('accumulation_first', 2, [0]), ('linear_after_accumulation', 1, [0, 2]),
                            ('export_after_hidden', 3, [0, 1, 2]), ('readout_after_exports', 4, [0, 1, 2, 3])]:
        extra = 2*sum(q[i][j] for j in before)
        z = F(scored[i]['net']['exact'])+extra
        assert z == net(before+[i])-net(before)
        interval = [F(x)+extra for x in scored[i]['intersection_interval']]
        effects[name] = {**pack(z), 'interval': list(map(str, interval)),
                         'sign_certified': interval[0] > 0 or interval[1] < 0}
    assert F(effects['accumulation_after_linear']['exact'])-F(effects['accumulation_first']['exact']) == 2*q[1][2]
    assert F(effects['linear_after_accumulation']['exact'])-F(effects['linear_first']['exact']) == 2*q[1][2]
    return {'components': dict(zip(TAGS, scored)), 'gram': [[str(z) for z in a] for a in q],
            'error_cross': list(map(str, bc)), 'effects': effects,
            'linear_accumulation_cross': pack(2*q[1][2]), 'within_combined': combined[0],
            'linear_total': combined[1], 'actual': old['actual'],
            'within_added': old['effects']['within_after_position_migration']}


def analyze(out):
    assert not (out/'results.json').exists(), 'Refuse completed overwrite'
    assert digest(Path(__file__)) == digest(out/'frozen_analysis.py')
    assert load(out/'independent_controls.json')['passed']
    guard(load(out/'source_hashes.json')); guard(load(out/'execution_hashes.json'))
    prior = {(r['seed'], r['rate'], r['initialization']): r for r in load(PRIOR/'results.json')['rows']}
    projector = ExactProjector(); budget = Budget(); rows = []
    try:
        for seed in SEEDS:
            for rate in ('base', 'quarter'):
                stem = f'{seed}_{rate}'
                outputs = np.memmap(NEW/f'{stem}_outputs.bin', dtype='<i2', mode='r', shape=(W, 4, 120))
                holds = np.memmap(BASE/f'{stem}_outputs.bin', dtype='<i2', mode='r', shape=(W, 4, 120))
                for index, init in ((0, 'actual'), (2, 'prefix')):
                    budget.charge('old24col_matrix_values', W*24)
                    mom = np.fromfile(HISTORY/f'{stem}_{init}_front_moments.bin', dtype='<i8').reshape(W, 24)
                    u = mom[:, :2]; k = mom[:, 10:12]
                    parts, total, eround = decompose(u, k)
                    assert np.array_equal(W*eround, mom[:, 18:20])
                    den = 1 if rate == 'base' else 4
                    product = mom[:, [6, 8]]
                    budget.charge('request_product_rounding_scalar_checks', W*2)
                    remainder = 25*den*u-product*np.array([-96, -288], dtype=np.int64)
                    assert np.all(np.abs(remainder) <= 12*den)
                    budget.charge('basis_values', W*120*2)
                    phi = np.fromfile(PRIOR/f'{stem}_{init}_basis.bin', dtype='<i2').reshape(W, 120, 2).astype(np.int64)
                    nums = []
                    for z in parts:
                        budget.charge('profile_basis_word_products', W*120*2)
                        nums.append(sum(z[:, j, None]*phi[:, :, j] for j in range(2)))
                    budget.charge('saved_integer_output_values', W*120*2)
                    actual = np.array(outputs[:, index], dtype=np.int64)
                    held = np.array(holds[:, index+1], dtype=np.int64)
                    nums.append((actual-held)*SCALE-sum(nums))
                    assert np.all(np.abs(nums[4]) <= 9*SCALE//8)
                    prev = prior[seed, rate, init]
                    stat = inspect(nums, held, projector, prev['stats'], budget)
                    row = {'seed': seed, 'rate': rate, 'initialization': init, 'stats': stat, 'blocks': [],
                           'max_centered_export_Q22': pack(F(int(np.abs(parts[3]).max()), D)),
                           'actual_gate_count_groups': []}
                    # Gate count is descriptive current history, not a gate intervention.
                    for count in range(5):
                        mask = mom[:, 4] == count
                        if mask.any():
                            row['actual_gate_count_groups'].append({'second_selected_gate_count': count, 'windows': int(mask.sum()),
                                'actual_mean_Q22_request': [pack(F(int(u[mask, j].sum()), int(mask.sum()))) for j in range(2)]})
                    for b in range(8):
                        sl = slice(B*b, B*(b+1)); gates = mom[sl, 4]
                        ss = inspect([z[sl] for z in nums], held[sl], projector, prev['blocks'][b]['stats'], budget)
                        row['blocks'].append({'block': 128+b, 'stats': ss,
                            'actual_mean_Q22_request': [pack(F(int(z), B)) for z in total[b]],
                            'second_gate_selected_word_count': int(gates.sum()),
                            'second_gate_count_histogram': [int(np.count_nonzero(gates == count)) for count in range(5)],
                            'centered_request_prefix_endpoint_Q22': [0, 0]})
                    for i in range(5):
                        assert F(stat['error_cross'][i]) == sum(F(b['stats']['error_cross'][i]) for b in row['blocks'])/8
                        for j in range(5):
                            assert F(stat['gram'][i][j]) == sum(F(b['stats']['gram'][i][j]) for b in row['blocks'])/8
                    for name in stat['effects']:
                        assert F(stat['effects'][name]['exact']) == sum(F(b['stats']['effects'][name]['exact']) for b in row['blocks'])/8
                    record = np.column_stack((parts[1], parts[2], parts[3], np.repeat(total, B, axis=0))).astype('<i8')
                    budget.charge('new_profile_matrix_bytes', record.nbytes)
                    record.tofile(out/f'{stem}_{init}_block_request_profiles.bin')
                    rows.append(row)
                    print(seed, rate, init, 'linear', stat['effects']['linear_first']['value'],
                          'accumulated', stat['effects']['accumulation_after_linear']['value'],
                          'export', stat['effects']['export_after_hidden']['value'], flush=True)
        assert len(rows) == 20 and budget.used == LIMITS
        guard(load(out/'source_hashes.json')); guard(load(out/'execution_hashes.json'))
        write(out/'results.json', {'completed': True, 'rows': rows})
        files = list(out.glob('*_block_request_profiles.bin'))
        write(out/'new_moment_hashes.json', {str(p): digest(p) for p in files})
        write(out/'verification.json', {'passed': True, 'cases': 20, 'blocks': 160,
            'all_original_losses_centers_Gram_orders_and_block_sums_exact': True,
            'source_files_preserved': len(load(out/'source_hashes.json')),
            'python_sources_preserved': len(load(out/'execution_hashes.json')),
            'all_enforced_budgets_met': budget.used == LIMITS,
            'new_PWL_gate_request_learning_source_fft_holdout': 0})
        print('All centers, actual request products, original losses and operation limits pass', flush=True)
    finally:
        write(out/'accounting_main.json', {'used': budget.used, 'limits': LIMITS,
            'all_limits_met': all(budget.used[k] <= LIMITS[k] for k in LIMITS),
            'completed_all20': len(rows) == 20,
            'new_PWL_gate_request_learning_submissions_paths_source_fft_holdout': 0})


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('mode', choices=['prepare', 'analyze'])
    ap.add_argument('--out', type=Path, required=True); args = ap.parse_args()
    try:
        (prepare if args.mode == 'prepare' else analyze)(args.out)
    except Exception:
        if args.out.exists():
            write(args.out/'failure.json', {'mode': args.mode, 'traceback': traceback.format_exc()})
        raise
