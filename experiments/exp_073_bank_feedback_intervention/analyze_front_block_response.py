"""Saved block-centered accumulation: fixed-state requests and own response.

References are offline continuous differences of the original histories. No
readout, gate, request, learner, source conversion or future policy is run.
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
from experiments.exp_073_bank_feedback_intervention.analyze_front_block_requests import B, D, SCALE

HISTORY = ROOT/'artifacts/research/front_forcing_response_20261013_v2'
BASIS = ROOT/'artifacts/research/front_block_migration_20261014_v1'
PRIOR = ROOT/'artifacts/research/front_centered_requests_20261014_v1'
TAGS = ['block_position', 'actual_linear_drive', 'frozen_centered_accumulation',
        'own_response_centered_accumulation', 'actual_centered_export', 'current_readout']
LIMITS = {'old24col_matrix_values': 983040, 'old8col_matrix_values': 327680,
    'basis_values': 9830400, 'saved_integer_output_values': 9830400,
    'profile_basis_word_products': 49152000, 'projected_score_word_inputs': 88473600,
    'off_diagonal_Gram_word_products': 147456000, 'new_profile_matrix_bytes': 1310720}


class Budget:
    def __init__(self):
        self.used = dict.fromkeys(LIMITS, 0)

    def charge(self, key, count):
        assert self.used[key]+count <= LIMITS[key], (key, self.used[key], count)
        self.used[key] += count


def centered_prefix(u):
    assert u.shape == (W, 2)
    z = u.reshape(8, B, 2)
    sums = z.sum(axis=1)
    pre = np.concatenate((np.zeros((8, 1, 2), dtype=np.int64), np.cumsum(z, axis=1)), axis=1)
    r = np.arange(B, dtype=np.int64)[None, :, None]
    cp = B*pre[:, :-1]-r*sums[:, None]
    result = B*cp-cp.sum(axis=1)[:, None]
    assert not (B*pre[:, -1]-B*sums).any()
    assert not result.sum(axis=1).any()
    return result.reshape(W, 2)


def controls():
    u0 = np.array([[((i*7)%11)-5, ((i*3)%7)-3] for i in range(W)], dtype=np.int64)
    response = np.array([[((i*5)%13)-6, ((i*2)%9)-4] for i in range(W)], dtype=np.int64)
    assert np.array_equal(centered_prefix(u0+response), centered_prefix(u0)+centered_prefix(response))
    assert not centered_prefix(np.full((W, 2), 3, dtype=np.int64)).any()
    assert not centered_prefix(np.zeros((W, 2), dtype=np.int64)).any()
    assert np.array_equal(centered_prefix(-u0), -centered_prefix(u0))
    # Opposing output components need not reduce target loss in both contexts.
    f, r = F(2), F(-1)
    assert 2*f*r == -4 and (f+r)**2-f*f == -3
    assert (f+r)**2-f*f+2*F(-2)*r == 1
    # Exact cancellation is possible despite nonzero individual powers.
    assert np.array_equal(centered_prefix(u0)+centered_prefix(-u0), np.zeros((W, 2), dtype=np.int64))
    return {'passed': True, 'exact_controls': 7, 'physical_source': False}


def prepare(out):
    assert not out.exists(), 'Refuse overwrite'
    assert load(PRIOR/'delivery_verification.json')['passed']
    out.mkdir(parents=True)
    files = dict(load(PRIOR/'source_hashes.json'))
    files.update(load(PRIOR/'new_moment_hashes.json'))
    for name in ('protocol.json', 'results.json', 'verification.json', 'delivery_verification.json',
                 'accounting_main.json', 'accounting_independent.json', 'matrix_schema.json'):
        p = PRIOR/name; files[str(p)] = digest(p)
    guard(files); write(out/'source_hashes.json', files)
    sources = list((ROOT/'src/adc_research').rglob('*.py'))+list((ROOT/'experiments').rglob('*.py'))
    write(out/'execution_hashes.json', {str(p): digest(p) for p in sources})
    shutil.copyfile(Path(__file__), out/'frozen_analysis.py')
    write(out/'protocol.json', {
        'version': 'EXP073-block-centered-fixed-forcing-own-response-v1', 'date': '2026-10-14',
        'authority': 'User continue research; D136..139 and current STATUS steps1..3',
        'scope': 'Original20 front-only/held cases, five seeds/two rates/two starts, blocks128..135. No new horizon, model, policy, optimizer or holdout.',
        'question': 'Does the centered accumulated actual request harm arise from fixed-initial-state four-word forcing, or does own-state response suppress/amplify that forcing?',
        'reference': 'u0 already saved from same four words at original evaluation-before front/rear state; no submissions. Response is saved actual u minus u0. Apply the identical per-block centered-prefix linear map to both.',
        'contexts': ['original block-mean exported position plus actual linear mean drive',
                     'original block-mean exported position without linear mean drive'],
        'orders': ['frozen accumulation then own response', 'own response then frozen accumulation'],
        'alternatives': [
            'Own-state response primarily cancels fixed-state accumulated forcing, versus it adding harmful output after that forcing.',
            'A negative output cross determines helpful loss, versus original error/target and actual linear context changing the sign.',
            'Finite fixed-state request history is sufficient for output attribution, versus all actual linear/export/readout pieces and cross terms being needed.'],
        'predictions': [
            'Two centered histories sum exactly to the old actual centered accumulation, with output-before timing and all block centers retained.',
            'Full6x6 Gram and target/error projections restore old accumulated, linear, export, readout, actual20 losses and160 block sums.',
            'Keep all8 context/order loss additions, both powers, cross terms and any uncertified signs; do not pick large seeds.',
            'Retain original21 cumulative and25 linear conditional-benefit blocks, original39 complete-variation benefits and all9 adverse/11 beneficial mean positions.'],
        'limits': LIMITS,
        'independent_limits': {'source24_values': 983040, 'old8_values': 327680, 'new4_values': 163840,
            'basis_values': 9830400, 'saved_output_values': 9830400, 'saved_window_Gram_values': 204800,
            'window_Gram_contractions': 614400, 'window_error_projection_contractions': 204800,
            'basis_target_word_products': 9830400, 'sparse_Fraction_word_probes': 240},
        'budget_enforcement': 'Reserve declared operations before execution; compute each off-diagonal Gram once and mirror. No new gradient/basis multiplication matrix or PWL.',
        'matrix': {'shape': [2048, 4], 'dtype': 'little-endian int64',
            'columns': ['frozen1_centered_prefix_numB2_Q22', 'frozen2_centered_prefix_numB2_Q22',
                        'own_response1_centered_prefix_numB2_Q22', 'own_response2_centered_prefix_numB2_Q22'],
            'Q22_denominator': D, 'output_after_Q3_basis_denominator': SCALE},
        'stop': 'Original20/160 only. Refuse arithmetic/source/prior-score/domain/budget mismatch, preserve failure; no automatic extra cases, PWL, branches or limits.',
        'information_limits': 'Centered histories use future block means and old shadow fixed-state requests. These are not additional free original-Gu online features. Reference loss uses unchanged NG39/43 extra sine target knowledge; own response is a stored-history difference, not separately propagated learner or unique causal share.',
        'new_PWL_gate_request_learning_submissions_paths_source_fft_holdout': 0})
    write(out/'controls.json', controls())
    for name in DOCS:
        p = out/'documents_before'/name; p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, p)
    print('Frozen original20/160, two contexts/two orders, zero readout and enforced operation limits', flush=True)


def inspect(nums, held, projector, old, budget):
    n = held.size; scored = []
    for z in nums:
        budget.charge('projected_score_word_inputs', n)
        scored.append(projector.projected(z, held, SCALE))
    q = [[F(0) for _ in nums] for _ in nums]
    for i in range(6):
        q[i][i] = F(scored[i]['power']['exact'])
        for j in range(i):
            budget.charge('off_diagonal_Gram_word_products', n)
            q[i][j] = q[j][i] = F(mulsum(nums[i], nums[j]), n*SCALE*SCALE)
    bc = [F(s['error_cross']['exact']) for s in scored]
    net = lambda ids: sum(bc[i] for i in ids)+sum(q[i][j] for i in ids for j in ids)
    for i, name in ((0, 'block_position'), (1, 'linear_mean_drive'), (4, 'centered_export_rounding'), (5, 'current_readout')):
        for key in ('power', 'error_cross', 'net'):
            assert scored[i][key] == old['components'][name][key]
    combined = []
    for ids in ([2, 3], [1, 2, 3, 4], [0, 1, 2, 3, 4]):
        budget.charge('projected_score_word_inputs', n)
        s = projector.projected(sum(nums[i] for i in ids), held, SCALE)
        assert F(s['net']['exact']) == net(ids)
        combined.append(s)
    for key in ('power', 'error_cross', 'net'):
        assert combined[0][key] == old['components']['centered_request_accumulation'][key]
        assert combined[1][key] == old['within_combined'][key]
        assert combined[2][key] == old['linear_total'][key]
    assert net(list(range(6))) == F(old['actual']['net']['exact'])
    effects = {}
    for context, base in [('with_linear', [0, 1]), ('without_linear', [0])]:
        for name, i, before in [('frozen_first', 2, base), ('response_after_frozen', 3, base+[2]),
                                ('response_first', 3, base), ('frozen_after_response', 2, base+[3])]:
            extra = 2*sum(q[i][j] for j in before)
            value = F(scored[i]['net']['exact'])+extra
            assert value == net(before+[i])-net(before)
            interval = [F(z)+extra for z in scored[i]['intersection_interval']]
            effects[context+'_'+name] = {**pack(value), 'interval': list(map(str, interval)),
                'sign_certified': interval[0] > 0 or interval[1] < 0}
        k = context+'_'
        assert F(effects[k+'frozen_first']['exact'])+F(effects[k+'response_after_frozen']['exact']) == F(effects[k+'response_first']['exact'])+F(effects[k+'frozen_after_response']['exact'])
        assert F(effects[k+'response_after_frozen']['exact'])-F(effects[k+'response_first']['exact']) == 2*q[2][3]
    assert F(effects['with_linear_frozen_first']['exact'])+F(effects['with_linear_response_after_frozen']['exact']) == F(old['effects']['accumulation_after_linear']['exact'])
    assert F(effects['without_linear_frozen_first']['exact'])+F(effects['without_linear_response_after_frozen']['exact']) == F(old['effects']['accumulation_first']['exact'])
    return {'components': dict(zip(TAGS, scored)), 'gram': [[str(z) for z in row] for row in q],
        'error_cross': list(map(str, bc)), 'effects': effects,
        'frozen_response_output_cross': pack(2*q[2][3]),
        'response_added_to_accumulation_power': pack(q[3][3]+2*q[2][3]),
        'actual_accumulation': combined[0], 'within_combined': combined[1], 'linear_total': combined[2],
        'actual': old['actual'], 'original_effects': old['effects']}


def analyze(out):
    assert not (out/'results.json').exists(), 'Refuse completed overwrite'
    assert digest(Path(__file__)) == digest(out/'frozen_analysis.py')
    assert load(out/'independent_controls.json')['passed']
    guard(load(out/'source_hashes.json')); guard(load(out/'execution_hashes.json'))
    old = {(r['seed'], r['rate'], r['initialization']): r for r in load(PRIOR/'results.json')['rows']}
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
                    budget.charge('old8col_matrix_values', W*8)
                    saved = np.fromfile(PRIOR/f'{stem}_{init}_block_request_profiles.bin', dtype='<i8').reshape(W, 8)
                    h0 = centered_prefix(mom[:, 2:4]); hr = centered_prefix(mom[:, :2]-mom[:, 2:4])
                    assert np.array_equal(h0+hr, saved[:, 2:4])
                    k = (mom[:, 10:12]-mom[0, 10:12]).reshape(8, B, 2)
                    bpos = (4096*B*np.repeat(k.sum(axis=1)[:, None], B, axis=1)).reshape(W, 2)
                    parts = [bpos, saved[:, :2], h0, hr, saved[:, 4:6]]
                    budget.charge('basis_values', W*120*2)
                    phi = np.fromfile(BASIS/f'{stem}_{init}_basis.bin', dtype='<i2').reshape(W, 120, 2).astype(np.int64)
                    nums = []
                    for z in parts:
                        budget.charge('profile_basis_word_products', W*120*2)
                        nums.append(sum(z[:, j, None]*phi[:, :, j] for j in range(2)))
                    budget.charge('saved_integer_output_values', W*120*2)
                    actual = np.array(outputs[:, index], dtype=np.int64); held = np.array(holds[:, index+1], dtype=np.int64)
                    nums.append((actual-held)*SCALE-sum(nums))
                    assert np.all(np.abs(nums[5]) <= 9*SCALE//8)
                    prev = old[seed, rate, init]
                    stat = inspect(nums, held, projector, prev['stats'], budget)
                    row = {'seed': seed, 'rate': rate, 'initialization': init, 'stats': stat, 'blocks': []}
                    for bb in range(8):
                        sl = slice(B*bb, B*(bb+1))
                        row['blocks'].append({'block': 128+bb,
                            'stats': inspect([z[sl] for z in nums], held[sl], projector, prev['blocks'][bb]['stats'], budget)})
                    for i in range(6):
                        assert F(stat['error_cross'][i]) == sum(F(b['stats']['error_cross'][i]) for b in row['blocks'])/8
                        for j in range(6):
                            assert F(stat['gram'][i][j]) == sum(F(b['stats']['gram'][i][j]) for b in row['blocks'])/8
                    for name in stat['effects']:
                        assert F(stat['effects'][name]['exact']) == sum(F(b['stats']['effects'][name]['exact']) for b in row['blocks'])/8
                    record = np.column_stack((h0, hr)).astype('<i8')
                    budget.charge('new_profile_matrix_bytes', record.nbytes)
                    record.tofile(out/f'{stem}_{init}_block_response_profiles.bin')
                    rows.append(row)
                    print(seed, rate, init, 'frozen', stat['effects']['with_linear_frozen_first']['value'],
                        'response_after', stat['effects']['with_linear_response_after_frozen']['value'],
                        'actual_accum', prev['stats']['effects']['accumulation_after_linear']['value'], flush=True)
        assert len(rows) == 20 and budget.used == LIMITS
        guard(load(out/'source_hashes.json')); guard(load(out/'execution_hashes.json'))
        write(out/'results.json', {'completed': True, 'rows': rows})
        files = list(out.glob('*_block_response_profiles.bin'))
        write(out/'new_moment_hashes.json', {str(p): digest(p) for p in files})
        write(out/'verification.json', {'passed': True, 'cases': 20, 'blocks': 160,
            'all_centers_old_components_original_losses_orders_and_block_sums_exact': True,
            'source_files_preserved': len(load(out/'source_hashes.json')),
            'python_sources_preserved': len(load(out/'execution_hashes.json')),
            'all_enforced_budgets_met': budget.used == LIMITS,
            'new_PWL_gate_request_learning_source_fft_holdout': 0})
        print('All fixed-driving/own-response histories, original losses and frozen budgets pass', flush=True)
    finally:
        write(out/'accounting_main.json', {'used': budget.used, 'limits': LIMITS,
            'all_limits_met': all(budget.used[k] <= LIMITS[k] for k in LIMITS), 'completed_all20': len(rows) == 20,
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
