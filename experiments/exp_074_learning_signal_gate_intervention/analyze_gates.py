"""Read-only second-gate request/history and output-support analysis.

This uses the four already completed EXP074 policies. It does not train,
alter a policy, assign a future effect to one event, or select an algorithm.
"""
import argparse
from fractions import Fraction as F
import json
from pathlib import Path
import shutil
import traceback
import numpy as np

from experiments.exp_074_learning_signal_gate_intervention.run import (
    ROOT, OLD, BASE, NEW, PHASE, SEEDS, N, W, FACT, source, original,
    load, write, digest, guard, probe_channels,
)
from experiments.exp_073_bank_feedback_intervention.run import evaluate, round_ratio

CHANNEL = ROOT / 'artifacts/runs/EXP_074/learning_channels_v1'
DOCS = [
    'docs/STATUS.md', 'docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md',
    'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md',
    'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md', 'docs/theory/README.md',
    'docs/reports/GU_ALGORITHM_EVALUATION_V1.md',
    'docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
    'docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md',
    'docs/reports/experiments/EXP_074_LEARNING_SIGNAL_GATE_INTERVENTION_V1.md',
    'experiments/exp_074_learning_signal_gate_intervention/README.md',
]


def controls():
    # Fixed digital outputs and state changes do not fix squared-loss direction.
    base = [F(2), F(2)]
    moved = [F(3), F(1)]
    loss = lambda y, t: sum((a - b) ** 2 for a, b in zip(y, t)) / 2
    assert loss(moved, moved) - loss(base, moved) == -1
    assert loss(moved, [1, 3]) - loss(base, [1, 3]) == 3
    # A change only in slope 2 has no current output effect below 128.
    phi = lambda r: [min(r, 128), min(max(r - 128, 0), 128)]
    assert phi(64) == [64, 0] and phi(192) == [128, 64]
    assert sum(p * k for p, k in zip(phi(64), [1, 10])) == 64
    # Exact cancellation needs the cross between the two coefficient responses.
    s1, s2 = F(2), F(-1)
    assert (s1 + s2) ** 2 == s1 ** 2 + s2 ** 2 + 2 * s1 * s2 == 1
    return {'passed': True, 'controls': [
        'same digital output pair, two opposite target preferences',
        'lower support has zero second basis', 'coefficient cross retained'],
        'physical_input_counterexample': False}


def prepare(out):
    assert not out.exists(), 'Refuse analysis overwrite'
    assert load(CHANNEL / 'verification.json')['passed']
    files = [OLD / 'tone.bin', OLD / 'source_protocol.json', PHASE,
             CHANNEL / 'results.json', CHANNEL / 'verification.json',
             NEW / 'results.json', NEW / 'verification.json']
    for seed in SEEDS:
        files.append(OLD / f'both_smooth_{seed}_words.bin')
        for rate in ('base', 'quarter'):
            stem = f'{seed}_{rate}'
            files.extend(BASE / f'{stem}_{s}.bin' for s in ('q22', 'outputs', 'requests'))
            files.extend(NEW / f'{stem}_{s}.bin' for s in ('q22', 'bridge_outputs', 'requests'))
            files.extend(CHANNEL / f'{stem}_{s}.bin' for s in
                         ('front_q22', 'outputs', 'front_requests'))
    out.mkdir(parents=True)
    write(out / 'source_hashes.json', {str(p): digest(p) for p in files})
    sources = list((ROOT / 'src/adc_research').rglob('*.py'))
    sources += list((ROOT / 'experiments').rglob('*.py'))
    write(out / 'execution_hashes.json', {str(p): digest(p) for p in sources})
    shutil.copyfile(Path(__file__), out / 'frozen_analysis.py')
    write(out / 'protocol.json', {
        'version': 'EXP074-second-gate-history-v1', 'date': '2026-10-13',
        'authority': 'D136..138 and current continue research; STATUS next read-only analysis',
        'object': 'all5 original seeds, rates1/1/4, actual/prefix starts, all8 blocks128..135; two gate contexts a=1 and a=0, 40 pairs, 320 paired blocks',
        'pairs': 'gate_moving_signal:11 versus10; gate_held_signal:01 versus00; output always autonomous moving rear',
        'requests': 'At baseline own front, switch only gate rear source; forcing=Rcorner-Rbase; response=Rtreat-Rcorner. First gate always open implies first forcing exactly0. All saved own requests and hidden differences checked.',
        'output': 'At common moving rear, use actual exported gaps and first2 PWL bases; retain coordinate cross and integer readout remainder. Zero second basis below or at128 separates current support from learning gate.',
        'classifiers_fixed_before_scores': {
            'raw_support': 'abs(raw1_Q3)<1024; [1024,2048); [2048,3072); >=3072',
            'export_gap_sign': 'all9 sign(deltaK1),sign(deltaK2) combinations, no score-chosen thresholds',
            'blocks': 'all8 consecutive256-window blocks; no selected extrema'},
        'predictions': [
            'All40 saved outputs/requests and cumulative Q22 gaps must reproduce; otherwise reject.',
            'Direct gate forcing first coordinate0 but a later nonzero first gap supports transfer through own learner history.',
            'Below first support boundary output-gap reference is entirely first-coefficient; a nonzero loss there rules out localization to second-supported output words.',
            'A gate effect benefits only if its error cross outweighs its squared output change; same digital sign/support summaries may contain opposite effects, limiting summary-based selection.',
            'Original40 gate totals and all8-block sums reproduce exactly. Target interval certification may fail for small blocks; retain all failures.'],
        'budget': {'vector_readouts': 39321600,
                   'vector_gate_support_product_components_each': 314572800,
                   'additional_policy_product_components': 3932160,
                   'rational_and_formal_readouts_each': 4320,
                   'independent_mixed_request_vectors': 360,
                   'saved_pair_output_words_scored': 9830400,
                   'request_window_pairs': 81920,
                   'new_learning_submissions_paths_source_conversions_fft': 0},
        'stopping': 'Fixed40 pairs/320 blocks only; source/arithmetic/domain mismatch stops and is archived; no new event interventions, horizon, model, algorithm, or holdout.',
        'limits': 'Whole gate-channel histories are causal policies already run. Forcing/response and support/coordinate strata are exact conditional decompositions, not per-event causal effects or unique shares. Shadow paths and target scoring are offline; simple stratum collisions are not a full-history indistinguishability proof. NG38/39 input conditions remain separate.'})
    write(out / 'controls.json', controls())
    for name in DOCS:
        dst = out / 'documents_before' / name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, dst)
    print('Frozen all40 gate pairs, all320 blocks, fixed support/state strata', flush=True)


def isum(v):
    v = np.asarray(v, dtype=np.int64)
    assert int(np.max(np.abs(v), initial=0)) * v.size < 1 << 63
    return int(v.sum(dtype=np.int64))


def mulsum(a, b):
    assert int(np.max(np.abs(a), initial=0)) * int(np.max(np.abs(b), initial=0)) < 1 << 63
    return isum(a * b)


def pack(v):
    return {'value': float(v), 'exact': str(v)}


def stats(v):
    return {'sum': isum(v), 'abs_sum': isum(np.abs(v)),
            'nonzero': int(np.count_nonzero(v)),
            'min': int(v.min()), 'max': int(v.max())}


class Scorer:
    def __init__(self):
        t = 2048 * (1 + np.fromfile(OLD / 'tone.bin', dtype='<f8'))
        ratios = [float(v).as_integer_ratio() for v in t]
        self.D = max(b for _, b in ratios)
        self.ti = [a * (self.D // b) for a, b in ratios]
        self.rad = F(load(PHASE)['target_radius'])

    def score(self, num, y, scale=1, mask=None):
        num = np.asarray(num, dtype=np.int64).reshape(-1, N)
        y = np.asarray(y, dtype=np.int64).reshape(-1, N)
        size = num.size
        if mask is not None:
            mask = np.asarray(mask).reshape(num.shape)
            num = np.where(mask, num, 0)
        phase_sum = num.sum(axis=0, dtype=np.int64)
        target_dot = sum(int(v) * self.ti[i] for i, v in enumerate(phase_sum) if v)
        power = F(mulsum(num, num), size * scale * scale)
        cross = F(2 * mulsum(num, y), size * scale)
        cross -= F(2 * target_dot, size * scale * self.D)
        net = power + cross
        uncertainty = 2 * self.rad * F(isum(np.abs(num)), size * scale)
        interval = [net - uncertainty, net + uncertainty]
        return {'power': pack(power), 'error_cross': pack(cross), 'net': pack(net),
                'target_interval': [str(v) for v in interval],
                'sign_certified': interval[0] > 0 or interval[1] < 0,
                'count': size if mask is None else int(np.count_nonzero(mask)),
                'normalization_count': size,
                'error_projection_over_power': float(cross / (2 * power)) if power else None}


def analyze(out):
    assert not (out / 'results.json').exists(), 'Refuse completed analysis overwrite'
    assert digest(Path(__file__)) == digest(out / 'frozen_analysis.py')
    guard(load(out / 'source_hashes.json')); guard(load(out / 'execution_hashes.json'))
    controls(); scorer = Scorer()
    prior = {(r['seed'], r['rate'], r['initialization']): r
             for r in load(CHANNEL / 'results.json')['rows']}
    rows = []; scalar = vectors = 0
    for seed in SEEDS:
        words = source(seed)
        for rate, den in (('base', 1), ('quarter', 4)):
            stem = f'{seed}_{rate}'
            a, b, ay, by, ar, br = original(seed, rate)
            fs = np.fromfile(CHANNEL / f'{stem}_front_q22.bin', dtype='<i4').reshape(W + 1, 4, 4).astype(np.int64)
            fy = np.fromfile(CHANNEL / f'{stem}_outputs.bin', dtype='<i2').reshape(W, 4, 120)
            fr = np.fromfile(CHANNEL / f'{stem}_front_requests.bin', dtype='<i4').reshape(W, 4, 4)
            for h, init in ((0, 'actual'), (2, 'prefix')):
                for aa, context in ((1, 'gate_signal_moving'), (0, 'gate_signal_held')):
                    if aa:
                        bst, tst, yr, yt, rb, rt = fs[:, h], a[:, h, :4], fy[:, h], ay[:, h], fr[:, h], ar[:, h, :4]
                    else:
                        bst, tst, yr, yt, rb, rt = b[:, h, :4], fs[:, h + 1], by[:, h // 2], fy[:, h + 1], br[:, h, :4], fr[:, h + 1]
                    rear = a[:-1, h, 4:]
                    held = np.broadcast_to(a[0, h, 4:], (W, 4))
                    vb = evaluate(words, np.column_stack((bst[:-1], rear)))
                    sb = evaluate(words, np.column_stack((bst[:-1], held)))
                    vt = evaluate(words, np.column_stack((tst[:-1], rear)))
                    st = evaluate(words, np.column_stack((tst[:-1], held)))
                    assert np.array_equal(vb[0], yr) and np.array_equal(vt[0], yt)
                    sig_b = vb[5] if aa else sb[5]
                    sig_t = vt[5] if aa else st[5]
                    dd = 2 * (words[:, :4, 3].astype(np.int64) & 1) - 1
                    gb, gc, gt = sb[1][:, :4, :4], vb[1][:, :4, :4], vt[1][:, :4, :4]
                    p = lambda sig, g: (8 * dd * sig[:, :4])[:, :, None] * g
                    rq = lambda products: round_ratio(products.sum(axis=1) * FACT * 30, 125 * den)
                    base_r = rq(p(sig_b, gb)); corner_r = rq(p(sig_b, gc)); treat_r = rq(p(sig_t, gt))
                    assert np.array_equal(base_r, rb) and np.array_equal(treat_r, rt)
                    forcing, response = corner_r - base_r, treat_r - corner_r
                    gap = tst - bst
                    assert not gap[0].any() and np.array_equal(np.diff(gap, axis=0), forcing + response)
                    assert np.array_equal(np.cumsum(forcing + response, axis=0), gap[1:])
                    assert not forcing[:, 0].any() and not forcing[:, 2:].any()
                    assert not rb[:, 2:].any() and not rt[:, 2:].any() and not gap[:, 2:].any()
                    assert gb[:, :, 0].all() and gc[:, :, 0].all() and gt[:, :, 0].all()
                    assert np.all((bst >= 0) & (bst <= 2047 * 4096))
                    assert np.all((tst >= 0) & (tst <= 2047 * 4096))
                    assert np.array_equal(np.clip(bst[:-1] + rb, 0, 2047 * 4096), bst[1:])
                    assert np.array_equal(np.clip(tst[:-1] + rt, 0, 2047 * 4096), tst[1:])
                    for w in (0, 1024, 2047):
                        slots = [0, 1, 2, 3, 59, 119]
                        fronts = np.stack((bst[w], bst[w], tst[w]))
                        policies = np.array([[aa, 0], [aa, 1], [aa, 1]])
                        rqs = np.stack((base_r[w], corner_r[w], treat_r[w]))
                        x, z = probe_channels(words[w, slots], fronts,
                            np.stack([rear[w]] * 3), np.stack([held[w]] * 3),
                            np.stack((yr[w, slots], yr[w, slots], yt[w, slots])),
                            rqs, np.clip(fronts + rqs, 0, 2047 * 4096), den, policies, w)
                        scalar += x; vectors += z
                    K = round_ratio(tst[:-1], 4096) - round_ratio(bst[:-1], 4096)
                    raw = vb[4]; mag = np.abs(raw); sign = np.sign(raw)
                    assert np.all((raw >= -4096) & (raw < 4096))
                    phi1 = sign * np.minimum(mag, 1024)
                    phi2 = sign * np.minimum(np.maximum(mag - 1024, 0), 1024)
                    s1 = phi1 * K[:, 0, None]; s2 = phi2 * K[:, 1, None]
                    d = yt.astype(np.int64) - yr.astype(np.int64)
                    rem = d * 8192 - s1 - s2
                    assert np.all(np.abs(rem) <= 9216)
                    score = scorer.score(d, yr)
                    assert F(score['net']['exact']) == F(prior[seed, rate, init]['effects'][context]['net_exact'])
                    q1 = scorer.score(s1, yr, 8192); q2 = scorer.score(s2, yr, 8192)
                    reference = scorer.score(s1 + s2, yr, 8192)
                    interaction = F(2 * mulsum(s1, s2), W * 120 * 8192 ** 2)
                    assert F(reference['net']['exact']) == F(q1['net']['exact']) + F(q2['net']['exact']) + interaction
                    remainder = F(score['net']['exact']) - F(reference['net']['exact'])
                    # The above remainder is independently expanded before acceptance.
                    rr = scorer.score(rem, yr, 8192)
                    rr_net = F(rr['net']['exact']) + F(2 * mulsum(rem, s1 + s2), W * 120 * 8192 ** 2)
                    assert rr_net == remainder
                    row = {'seed': seed, 'rate': rate, 'initialization': init, 'context': context,
                           'gate_loss': score, 'first_coordinate_reference': q1,
                           'second_coordinate_reference': q2, 'coordinate_interaction': pack(interaction),
                           'continuous_gap_reference': reference, 'readout_remainder_loss': pack(remainder),
                           'request_forcing': [stats(forcing[:, i]) for i in range(4)],
                           'request_history_response': [stats(response[:, i]) for i in range(4)],
                           'final_hidden_gap': gap[-1].tolist(), 'export_gap_mean': K.mean(axis=0).tolist(),
                           'gate_flips_at_same_front': int(np.count_nonzero(gc[:, :, 1] != gb[:, :, 1])),
                           'gate_flip_opens': int(np.count_nonzero(gc[:, :, 1] & ~gb[:, :, 1])),
                           'gate_flip_closes': int(np.count_nonzero(gb[:, :, 1] & ~gc[:, :, 1])),
                           'first_export_gap_nonzero_windows': int(np.count_nonzero(K[:, 0])),
                           'blocks': []}
                    for bb in range(8):
                        sl = slice(bb * 256, (bb + 1) * 256)
                        bs = scorer.score(d[sl], yr[sl])
                        supports = []
                        for ii in range(4):
                            mask = (mag[sl] >= ii * 1024) & (mag[sl] < (ii + 1) * 1024)
                            ss = scorer.score(d[sl], yr[sl], mask=mask)
                            if ii == 0:
                                assert not s2[sl][mask].any()
                            supports.append({'slice': ii + 1, **ss})
                        assert sum((F(s['net']['exact']) for s in supports), F(0)) == F(bs['net']['exact'])
                        signs = []
                        for i1 in (-1, 0, 1):
                            for i2 in (-1, 0, 1):
                                mk = (np.sign(K[sl, 0]) == i1) & (np.sign(K[sl, 1]) == i2)
                                mask = np.broadcast_to(mk[:, None], d[sl].shape)
                                signs.append({'deltaK1_sign': i1, 'deltaK2_sign': i2,
                                              **scorer.score(d[sl], yr[sl], mask=mask)})
                        assert sum((F(s['net']['exact']) for s in signs), F(0)) == F(bs['net']['exact'])
                        row['blocks'].append({'block': 128 + bb, 'loss': bs,
                                             'support': supports, 'export_gap_sign': signs,
                                             'forcing': [stats(forcing[sl, i]) for i in range(2)],
                                             'response': [stats(response[sl, i]) for i in range(2)],
                                             'hidden_gap_start': gap[bb * 256].tolist(),
                                             'hidden_gap_end': gap[(bb + 1) * 256].tolist()})
                    assert sum((F(z['loss']['net']['exact']) for z in row['blocks']), F(0)) / 8 == F(score['net']['exact'])
                    record = np.stack((base_r, corner_r, treat_r, forcing, response), axis=1)
                    record.astype('<i4').tofile(out / f'{stem}_{init}_{aa}_requests.bin')
                    rows.append(row)
                    print(seed, rate, init, aa, 'loss', score['net']['value'],
                          'K1/K2/cross', q1['net']['value'], q2['net']['value'], float(interaction), flush=True)
    assert len(rows) == 40 and scalar == 4320 and vectors == 360
    guard(load(out / 'source_hashes.json')); guard(load(out / 'execution_hashes.json'))
    write(out / 'results.json', {'completed': True, 'rows': rows})
    write(out / 'verification.json', {
        'passed': True, 'gate_context_pairs': 40, 'paired_blocks': 320,
        'all_saved_outputs_and_requests_exact': True, 'all_Q22_gap_cumulative_sums_exact': True,
        'first_direct_forcing_zero_all_pairs': True, 'high_requests_and_state_gaps_zero': True,
        'all_original_gate_losses_and_block_sums_exact': True,
        'all_support_and_state_sign_partitions_exact': True,
        'all_coordinate_cross_and_readout_remainder_splits_exact': True,
        'max_remainder_bound': '9/8', 'vector_readouts': 39321600,
        'vector_gate_support_product_components_each': 314572800,
        'additional_policy_product_components': 3932160,
        'rational_and_formal_readouts_each': scalar,
        'independent_mixed_request_vectors': vectors,
        'scored_saved_output_pair_words': 9830400,
        'used_source_files_preserved': len(load(out / 'source_hashes.json')),
        'existing_python_sources_preserved': len(load(out / 'execution_hashes.json')),
        'new_learning_submissions_trajectories_source_conversions_fft': 0,
        'new_holdout': False})
    print('All40 pairs/320 blocks and exact structural/support/loss chains passed', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['prepare', 'analyze'])
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    try:
        globals()[args.mode](args.out)
    except Exception:
        if args.out.exists():
            write(args.out / f'{args.mode}_failure.json', {'traceback': traceback.format_exc()})
        raise
