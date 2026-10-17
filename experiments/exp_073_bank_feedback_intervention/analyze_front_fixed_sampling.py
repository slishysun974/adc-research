"""Fixed first-request sampling/background through saved centered histories.

Full120 is a normalized same-word offline moment, not a new learning policy.
Qualification checks original anchors, duplicate corners and exact Q3 scales.
"""
import argparse
from fractions import Fraction as F
from pathlib import Path
import shutil
import traceback
import numpy as np

from experiments.exp_073_bank_feedback_intervention.analyze_front_history import (
    ROOT, BASE, NEW, OLD, SEEDS, W, load, write, digest, guard, ExactProjector,
    mulsum, pack, DOCS, round_ratio,
)
from experiments.exp_073_bank_feedback_intervention.analyze_front_block_response import centered_prefix
from experiments.exp_073_bank_feedback_intervention.analyze_front_block_requests import B, D, SCALE as OLD_SCALE

HISTORY = ROOT/'artifacts/research/front_forcing_response_20261013_v2'
ANCHOR = ROOT/'artifacts/research/anchor_sampling_20261013_v1'
BASIS = ROOT/'artifacts/research/front_block_migration_20261014_v1'
BLOCKS = ROOT/'artifacts/research/front_centered_requests_20261014_v1'
PRIOR = ROOT/'artifacts/research/front_centered_response_20261014_v1'
REQUEST_DEN = 500
SCALE = OLD_SCALE*REQUEST_DEN
TAGS = ['block_position', 'actual_linear', 'full120_first', 'selected_first_gap',
        'first_request_rounding', 'frozen_second', 'own_response', 'export_rounding', 'current_readout']
QUAL_LIMITS = {'old24_values': 983040, 'anchor7_values_both_contexts': 573440,
    'initial_Q22_values': 320, 'first_request_rounding_checks': 40960,
    'source_pair_matrix_bytes': 1966080}
LIMITS = {'source_pair6_values': 245760, 'old8_values': 327680, 'old4_values': 163840,
    'basis_values': 9830400, 'saved_output_values': 9830400,
    'profile_basis_word_products': 58982400, 'projected_score_word_inputs': 127795200,
    'off_diagonal_Gram_word_products': 353894400, 'new_profile_matrix_bytes': 2293760}


class Budget:
    def __init__(self, limits):
        self.limits = limits; self.used = dict.fromkeys(limits, 0)

    def charge(self, key, n):
        assert self.used[key]+n <= self.limits[key], (key, self.used[key], n)
        self.used[key] += n


def split_requests(selected, full, frozen, den):
    factor = 4 if den == 1 else 1
    f = -16*full*factor
    s = 16*(full-30*selected)*factor
    r = REQUEST_DEN*frozen+480*selected*factor
    assert np.array_equal(f+s+r, REQUEST_DEN*frozen)
    assert np.all(np.abs(r) <= 240)
    return f, s, r


def controls():
    sel = np.arange(W, dtype=np.int64)%17-8
    full = 30*sel+(np.arange(W, dtype=np.int64)%13-6)
    for den in (1, 4):
        frozen = round_ratio(-96*sel, 25*den)
        f, s, r = split_requests(sel, full, frozen, den)
        to2 = lambda z: np.column_stack((z, np.zeros(W, dtype=np.int64)))
        assert np.array_equal(centered_prefix(to2(f))+centered_prefix(to2(s))+centered_prefix(to2(r)), REQUEST_DEN*centered_prefix(to2(frozen)))
    same = split_requests(sel, 30*sel, round_ratio(-96*sel, 25), 1)
    assert not same[1].any()
    # Full-vs-selected means preserve the full-minus-selected sign convention.
    a, b = F(3), F(1)
    gap = a-b
    assert b == a-gap
    # Source normalization and finite loss still need cross terms.
    f, s, e = F(2), F(-1), F(0)
    loss = lambda z: z*z+2*e*z
    assert loss(f+s)-loss(f)-loss(s) == 2*f*s == -4
    assert loss(f+s)-loss(f) == -3 and loss(s) == 1
    assert F(240, REQUEST_DEN) == F(12, 25)
    return {'passed': True, 'exact_controls': 7, 'new_physical_source': False}


def prepare(out):
    assert not out.exists(), 'Refuse overwrite'
    assert load(PRIOR/'delivery_verification.json')['passed']
    assert load(ANCHOR/'delivery_verification.json')['passed']
    out.mkdir(parents=True)
    files = dict(load(PRIOR/'source_hashes.json')); files.update(load(PRIOR/'new_moment_hashes.json'))
    files.update(load(ANCHOR/'new_moment_hashes.json'))
    for folder, names in [(PRIOR, ['protocol.json', 'results.json', 'verification.json', 'delivery_verification.json']),
                          (ANCHOR, ['protocol.json', 'verification.json', 'source_hashes.json', 'frozen_analysis.py']),
                          (HISTORY, ['protocol.json', 'verification.json', 'source_hashes.json', 'frozen_analysis.py'])]:
        for name in names:
            p = folder/name; files[str(p)] = digest(p)
    guard(files); write(out/'source_hashes.json', files)
    sources = list((ROOT/'src/adc_research').rglob('*.py'))+list((ROOT/'experiments').rglob('*.py'))
    write(out/'execution_hashes.json', {str(p): digest(p) for p in sources})
    shutil.copyfile(Path(__file__), out/'frozen_analysis.py')
    write(out/'protocol.json', {
        'version': 'EXP073-fixed-first-full-selected-accumulation-v1', 'date': '2026-10-14',
        'authority': 'User continue, D136..139 and STATUS first fixed-state sampling steps1..3',
        'scope': 'All original20 cases/five seeds/two rates/two starts/eight256-window blocks128..135. First coordinate source split only; keep second and all actual pieces.',
        'qualification': 'Check old anchor/history source-file hashes and frozen entry code, shared BASE initial Q22, actual NEW same initial, duplicate gap00 across both40 corners, exported initial agreement, gap00 divisible by120, full product integer and stored first rounding.',
        'source_scales': 'gap00=120*(full120_dy_Q3_sum-30*selected4_dy_Q3_sum). Thus full sum=gap00/120+30*stored selected first product. First frozen Q22 request=round_even(-96*selected/(25m)), m=1 or4 for rates1 or1/4.',
        'reference': 'Use exact rational normalized full120 request -16*full_sum/(125m), selection difference16*(full_sum-30*selected)/(125m), plus actual selected-request rounding. They sum to stored actual frozen first request; no full learner or legal rounded full request is run.',
        'contexts': ['block position + actual linear + fixed second accumulation',
                     'same context + actual own-response accumulation'],
        'orders': ['full background then selected gap then request rounding',
                   'selected gap then full background then request rounding'],
        'alternatives': ['Fixed-first accumulation is mainly the normalized full background, versus the four-word difference retaining substantial output/target action.',
                         'Background and sampling losses add independently, versus their coordinate/time cross changing signs and dominance.',
                         'Selected rounding can be dropped, versus it needing exact restoration despite small effect.'],
        'predictions': ['All qualification scales/initials and both fixed corners match; otherwise stop before scoring.',
            'Full+selected+rounding first histories restore old fixed-first exactly; keep fixed-second, actual linear/response, export/readout.',
            'Full9x9 Gram restores all old fixed/actual accumulation, within/actual loss and160 block sums.',
            'Keep10 context/order additions, all zero/opposite/uncertified cases, prior1 unresolved block and all original beneficial cases; no score-picked seeds.'],
        'qualification_limits': QUAL_LIMITS, 'limits': LIMITS,
        'independent_limits': {'pair6_values': 245760, 'old8_values': 327680, 'old4_values': 163840,
            'new7_values': 286720, 'basis_values': 9830400, 'saved_output_values': 9830400,
            'saved_window_Gram_values': 204800, 'window_Gram_contractions': 1474560,
            'window_error_projection_contractions': 327680, 'basis_target_word_products': 9830400,
            'sparse_Fraction_word_probes': 240},
        'budget_enforcement': 'Reserve declared operations before execution. Off-diagonal Gram once and mirrored. Verify int64 numerator/phase-sum bounds before scoring. No new gradient, basis matrix, PWL, gate or learner.',
        'source_pair_matrix': {'shape': [2048, 6], 'dtype': 'little-endian int64',
            'columns': ['selected_first_product_Q3_sum', 'full_first_product_Q3_sum', 'gap00_num', 'actual_K1', 'actual_K2', 'frozen_first_request_Q22']},
        'new_profile_matrix': {'shape': [2048, 7], 'dtype': 'little-endian int64',
            'columns': ['selected_first_product_Q3_sum', 'full_first_product_Q3_sum', 'gap00_num',
                        'full_first_centered_numB2x500_Q22', 'sampling_first_centered_numB2x500_Q22',
                        'rounding_first_centered_numB2x500_Q22', 'rounding_request_num500_Q22'],
            'centered_Q22_denominator': D*REQUEST_DEN, 'output_after_Q3_basis_denominator': SCALE},
        'stop': 'Same20/160 only. Source/initial/scale/arithmetic/domain/budget mismatch rejects and preserves failure. No automatic new readout or limit increase.',
        'information_limits': 'Full120 uses30 times four-word observations and old fixed-state shadow; it is an offline reference, not same-cost Gu or a learned full policy. Block means use future history. Original NG39/43 sine target knowledge only certifies saved comparisons; first-source split does not identify second gating or all physical error.',
        'new_PWL_gate_request_learning_submissions_paths_source_fft_holdout': 0})
    write(out/'controls.json', controls())
    for name in DOCS:
        p = out/'documents_before'/name; p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, p)
    print('Frozen original20/160 source qualification, first full/selected/rounding split and budgets', flush=True)


def qualify(out):
    assert not (out/'qualification.json').exists(), 'Refuse qualification overwrite'
    assert digest(Path(__file__)) == digest(out/'frozen_analysis.py')
    guard(load(out/'source_hashes.json')); guard(load(out/'execution_hashes.json'))
    anchor_sources = load(ANCHOR/'source_hashes.json'); history_sources = load(HISTORY/'source_hashes.json')
    budget = Budget(QUAL_LIMITS); rows = []
    try:
        # Frozen reference code and common source contract remain the ones audited.
        assert digest(ROOT/'experiments/exp_074_learning_signal_gate_intervention/analyze_anchor_sampling.py') == digest(ANCHOR/'frozen_analysis.py')
        assert digest(ROOT/'experiments/exp_073_bank_feedback_intervention/analyze_front_history.py') == digest(HISTORY/'frozen_analysis.py')
        for seed in SEEDS:
            p = OLD/f'both_smooth_{seed}_words.bin'
            assert anchor_sources[str(p)] == history_sources[str(p)] == digest(p)
            for rate, den in [('base', 1), ('quarter', 4)]:
                stem = f'{seed}_{rate}'; p = BASE/f'{stem}_q22.bin'
                assert anchor_sources[str(p)] == history_sources[str(p)] == digest(p)
                bs = np.memmap(p, dtype='<i4', mode='r', shape=(W+1, 4, 8))
                ns = np.memmap(NEW/f'{stem}_q22.bin', dtype='<i4', mode='r', shape=(W+1, 4, 8))
                for index, init in ((0, 'actual'), (2, 'prefix')):
                    budget.charge('initial_Q22_values', 16)
                    assert np.array_equal(bs[0, index], ns[0, index])
                    budget.charge('old24_values', W*24)
                    mom = np.fromfile(HISTORY/f'{stem}_{init}_front_moments.bin', dtype='<i8').reshape(W, 24)
                    assert np.array_equal(mom[0, 10:12], round_ratio(bs[0, index, :2], 4096))
                    budget.charge('anchor7_values_both_contexts', W*7*2)
                    corners = [np.fromfile(ANCHOR/f'{stem}_{init}_{ctx}_anchor_moments.bin', dtype='<i8').reshape(W, 7) for ctx in (0, 1)]
                    gap = corners[0][:, 1]
                    assert np.array_equal(gap, corners[1][:, 1]) and np.all(gap % 120 == 0)
                    selected = mom[:, 7]; full = gap//120+30*selected
                    budget.charge('first_request_rounding_checks', W)
                    assert np.all(np.abs(25*den*mom[:, 2]+96*selected) <= 12*den)
                    f, s, r = split_requests(selected, full, mom[:, 2], den)
                    assert np.array_equal(full-30*selected, gap//120)
                    record = np.column_stack((selected, full, gap, mom[:, 10:12], mom[:, 2])).astype('<i8')
                    budget.charge('source_pair_matrix_bytes', record.nbytes)
                    record.tofile(out/f'{stem}_{init}_source_pair.bin')
                    rows.append({'seed': seed, 'rate': rate, 'initialization': init,
                        'initial_Q22': list(map(int, bs[0, index])), 'all2048_source_pairings_exact': True})
        assert len(rows) == 20 and budget.used == QUAL_LIMITS
        files = list(out.glob('*_source_pair.bin'))
        write(out/'qualification_matrix_hashes.json', {str(p): digest(p) for p in files})
        write(out/'qualification.json', {'passed': True, 'rows': rows, 'all_original_anchors_words_and_Q3_scales_exact': True})
        print('All20 original states, shared source hashes, duplicate fixed corners and first scales qualify', flush=True)
    finally:
        write(out/'accounting_qualification.json', {'used': budget.used, 'limits': QUAL_LIMITS,
            'all_limits_met': all(budget.used[k] <= QUAL_LIMITS[k] for k in QUAL_LIMITS), 'completed_all20': len(rows) == 20,
            'new_PWL_gate_request_learning_source_fft_holdout': 0})


def inspect(nums, held, projector, old, budget):
    n = held.size; scored = []
    for z in nums:
        assert int(np.max(np.abs(z), initial=0))*(z.size//30720) < 1 << 63
        budget.charge('projected_score_word_inputs', n); scored.append(projector.projected(z, held, SCALE))
    q = [[F(0) for _ in nums] for _ in nums]
    for i in range(9):
        q[i][i] = F(scored[i]['power']['exact'])
        for j in range(i):
            budget.charge('off_diagonal_Gram_word_products', n)
            q[i][j] = q[j][i] = F(mulsum(nums[i], nums[j]), n*SCALE*SCALE)
    bc = [F(s['error_cross']['exact']) for s in scored]
    net = lambda ids: sum(bc[i] for i in ids)+sum(q[i][j] for i in ids for j in ids)
    for i, name in [(0, 'block_position'), (1, 'actual_linear_drive'), (6, 'own_response_centered_accumulation'),
                    (7, 'actual_centered_export'), (8, 'current_readout')]:
        for key in ('power', 'error_cross', 'net'):
            assert scored[i][key] == old['components'][name][key]
    combinations = []
    for ids in ([2, 3, 4, 5], [2, 3, 4, 5, 6], list(range(1, 8)), list(range(8))):
        z = sum(nums[i] for i in ids)
        assert int(np.max(np.abs(z), initial=0))*(z.size//30720) < 1 << 63
        budget.charge('projected_score_word_inputs', n)
        ss = projector.projected(z, held, SCALE); assert F(ss['net']['exact']) == net(ids)
        combinations.append(ss)
    for key in ('power', 'error_cross', 'net'):
        assert combinations[0][key] == old['components']['frozen_centered_accumulation'][key]
        assert combinations[1][key] == old['actual_accumulation'][key]
        assert combinations[2][key] == old['within_combined'][key]
        assert combinations[3][key] == old['linear_total'][key]
    assert net(list(range(9))) == F(old['actual']['net']['exact'])
    effects = {}
    for context, base in [('before_response', [0, 1, 5]), ('after_response', [0, 1, 5, 6])]:
        for name, i, before in [('full_first', 2, base), ('sampling_after_full', 3, base+[2]),
                                ('sampling_first', 3, base), ('full_after_sampling', 2, base+[3]),
                                ('rounding_after_sources', 4, base+[2, 3])]:
            extra = 2*sum(q[i][j] for j in before)
            z = F(scored[i]['net']['exact'])+extra
            assert z == net(before+[i])-net(before)
            interval = [F(x)+extra for x in scored[i]['intersection_interval']]
            effects[context+'_'+name] = {**pack(z), 'interval': list(map(str, interval)),
                'sign_certified': interval[0] > 0 or interval[1] < 0}
        k = context+'_'
        assert F(effects[k+'full_first']['exact'])+F(effects[k+'sampling_after_full']['exact']) == F(effects[k+'sampling_first']['exact'])+F(effects[k+'full_after_sampling']['exact'])
        assert F(effects[k+'sampling_after_full']['exact'])-F(effects[k+'sampling_first']['exact']) == 2*q[2][3]
    return {'components': dict(zip(TAGS, scored)), 'gram': [[str(z) for z in row] for row in q],
        'error_cross': list(map(str, bc)), 'effects': effects, 'full_sampling_cross': pack(2*q[2][3]),
        'frozen_total': combinations[0], 'actual_accumulation': combinations[1], 'within_combined': combinations[2],
        'linear_total': combinations[3], 'actual': old['actual'], 'original_effects': old['effects']}


def analyze(out):
    assert not (out/'results.json').exists(), 'Refuse completed overwrite'
    assert digest(Path(__file__)) == digest(out/'frozen_analysis.py')
    assert load(out/'qualification.json')['passed'] and load(out/'independent_controls.json')['passed']
    guard(load(out/'source_hashes.json')); guard(load(out/'execution_hashes.json')); guard(load(out/'qualification_matrix_hashes.json'))
    old = {(r['seed'], r['rate'], r['initialization']): r for r in load(PRIOR/'results.json')['rows']}
    projector = ExactProjector(); budget = Budget(LIMITS); rows = []
    try:
        for seed in SEEDS:
            for rate, den in [('base', 1), ('quarter', 4)]:
                stem = f'{seed}_{rate}'
                ys = np.memmap(NEW/f'{stem}_outputs.bin', dtype='<i2', mode='r', shape=(W, 4, 120))
                hs = np.memmap(BASE/f'{stem}_outputs.bin', dtype='<i2', mode='r', shape=(W, 4, 120))
                for index, init in ((0, 'actual'), (2, 'prefix')):
                    budget.charge('source_pair6_values', W*6)
                    pair = np.fromfile(out/f'{stem}_{init}_source_pair.bin', dtype='<i8').reshape(W, 6)
                    budget.charge('old8_values', W*8)
                    saved = np.fromfile(BLOCKS/f'{stem}_{init}_block_request_profiles.bin', dtype='<i8').reshape(W, 8)
                    budget.charge('old4_values', W*4)
                    response = np.fromfile(PRIOR/f'{stem}_{init}_block_response_profiles.bin', dtype='<i8').reshape(W, 4)
                    selected, full = pair[:, 0], pair[:, 1]
                    frozen = pair[:, 5]
                    f, s, r = split_requests(selected, full, frozen, den)
                    to2 = lambda z: np.column_stack((z, np.zeros(W, dtype=np.int64)))
                    fp, sp, rp = [centered_prefix(to2(z)) for z in (f, s, r)]
                    assert np.array_equal(fp+sp+rp, REQUEST_DEN*to2(response[:, 0]))
                    k = (pair[:, 3:5]-pair[0, 3:5]).reshape(8, B, 2)
                    bp = (4096*B*np.repeat(k.sum(axis=1)[:, None], B, axis=1)).reshape(W, 2)*REQUEST_DEN
                    second = np.column_stack((np.zeros(W, dtype=np.int64), response[:, 1]))*REQUEST_DEN
                    parts = [bp, saved[:, :2]*REQUEST_DEN, fp, sp, rp, second,
                             response[:, 2:]*REQUEST_DEN, saved[:, 4:6]*REQUEST_DEN]
                    budget.charge('basis_values', W*120*2)
                    phi = np.fromfile(BASIS/f'{stem}_{init}_basis.bin', dtype='<i2').reshape(W, 120, 2).astype(np.int64)
                    nums = []
                    for i, z in enumerate(parts):
                        cols = [0] if i in (2, 3, 4) else [1] if i == 5 else [0, 1]
                        assert sum(int(np.abs(z[:, j]).max(initial=0))*1024 for j in cols) < 1 << 63
                        budget.charge('profile_basis_word_products', W*120*len(cols))
                        nums.append(sum(z[:, j, None]*phi[:, :, j] for j in cols))
                    budget.charge('saved_output_values', W*120*2)
                    actual = np.array(ys[:, index], dtype=np.int64); held = np.array(hs[:, index+1], dtype=np.int64)
                    nums.append((actual-held)*SCALE-sum(nums))
                    assert np.all(np.abs(nums[8]) <= 9*SCALE//8)
                    prev = old[seed, rate, init]; stat = inspect(nums, held, projector, prev['stats'], budget)
                    row = {'seed': seed, 'rate': rate, 'initialization': init, 'stats': stat, 'blocks': []}
                    for bb in range(8):
                        sl = slice(B*bb, B*(bb+1))
                        row['blocks'].append({'block': 128+bb, 'stats': inspect([z[sl] for z in nums], held[sl], projector, prev['blocks'][bb]['stats'], budget)})
                    for i in range(9):
                        assert F(stat['error_cross'][i]) == sum(F(b['stats']['error_cross'][i]) for b in row['blocks'])/8
                        for j in range(9):
                            assert F(stat['gram'][i][j]) == sum(F(b['stats']['gram'][i][j]) for b in row['blocks'])/8
                    for name in stat['effects']:
                        assert F(stat['effects'][name]['exact']) == sum(F(b['stats']['effects'][name]['exact']) for b in row['blocks'])/8
                    record = np.column_stack((pair[:, :3], fp[:, 0], sp[:, 0], rp[:, 0], r)).astype('<i8')
                    budget.charge('new_profile_matrix_bytes', record.nbytes)
                    record.tofile(out/f'{stem}_{init}_fixed_sampling_profiles.bin')
                    rows.append(row)
                    print(seed, rate, init, 'full', stat['effects']['before_response_full_first']['value'],
                        'sampling_after', stat['effects']['before_response_sampling_after_full']['value'],
                        'rounding', stat['effects']['before_response_rounding_after_sources']['value'], flush=True)
        assert len(rows) == 20 and budget.used == LIMITS
        guard(load(out/'source_hashes.json')); guard(load(out/'execution_hashes.json'))
        write(out/'results.json', {'completed': True, 'rows': rows})
        files = list(out.glob('*_fixed_sampling_profiles.bin'))
        write(out/'new_moment_hashes.json', {str(p): digest(p) for p in files})
        write(out/'verification.json', {'passed': True, 'cases': 20, 'blocks': 160,
            'all_scales_sources_old_components9x9_Gram_and_blocks_exact': True,
            'source_files_preserved': len(load(out/'source_hashes.json')),
            'python_sources_preserved': len(load(out/'execution_hashes.json')),
            'all_enforced_budgets_met': budget.used == LIMITS,
            'new_PWL_gate_request_learning_source_fft_holdout': 0})
        print('All fixed first-source histories, original loss chains and frozen counters pass', flush=True)
    finally:
        write(out/'accounting_main.json', {'used': budget.used, 'limits': LIMITS,
            'all_limits_met': all(budget.used[k] <= LIMITS[k] for k in LIMITS), 'completed_all20': len(rows) == 20,
            'new_PWL_gate_request_learning_submissions_paths_source_fft_holdout': 0})


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('mode', choices=['prepare', 'qualify', 'analyze'])
    ap.add_argument('--out', type=Path, required=True); args = ap.parse_args()
    try:
        {'prepare': prepare, 'qualify': qualify, 'analyze': analyze}[args.mode](args.out)
    except Exception:
        if args.out.exists():
            write(args.out/'failure.json', {'mode': args.mode, 'traceback': traceback.format_exc()})
        raise
