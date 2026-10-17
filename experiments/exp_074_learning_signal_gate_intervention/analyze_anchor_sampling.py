"""Same-word, pre-evaluation-state references for the sampling correction.

Reuse the sealed NG44 window moments. Compute only the three missing Q3
readouts per seed/rate/start, never gates, requests, commits or a new learner.
The two parameter replacement orders are references, not future policies.
"""
import argparse
from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
import shutil
import traceback
import numpy as np

from experiments.exp_074_learning_signal_gate_intervention.analyze_sampling_history import (
    ROOT, OLD, CHANNEL, SEEDS, W, DOCS, BASE, NEW, source, load, write,
    digest, guard, round_ratio, pwl_scaled, isum, mulsum, pack, fixed_setup,
    readout, export, correct_two_stage_fixed_observed, DigitalCalibrationSample,
    CD, MD, COLS,
)

PRIOR = ROOT/'artifacts/research/sampling_history_20261013_v1'
MOMENT = ROOT/'artifacts/research/first_moment_audit_20261013_v1'
NEW_COLS = ['deltaK1', 'gap00', 'gap10', 'gap01', 'gap11',
            'front_before_rear_linear_num1024', 'front_after_rear_linear_num1024']


def controls():
    # Both labels balance; fixed-state readout still has a sampling gap.
    d = [1, -1, 1, -1]
    y = [F(1), F(1), F(3), F(1)]
    gap = lambda v: sum(a*b for a, b in zip(d, v))/4-sum(d[j]*v[j] for j in range(2))/2
    assert sum(d) == sum(d[:2]) == 0 and gap(y) == F(1, 2)
    assert gap([y[j]-64*d[j] for j in range(4)]) == gap(y)
    # Nonzero interaction persists in an exact, unquantized local PWL segment.
    c00, c10, c01, c11 = F(1), F(2), F(3), F(6)
    assert c11-c00 == (c10-c00)+(c11-c10) == (c01-c00)+(c11-c01)
    assert c11-c10-c01+c00 == 2
    assert c11 == c00+(c10-c00)+(c01-c00)+(c11-c10-c01+c00)
    assert F(4*29+116, 120) == F(29, 15)
    # Replacing a digital correlation does not supply the target projection.
    u, z = F(1), F(2)
    loss_difference = lambda t: (z+u-t)**2-(z-t)**2
    assert loss_difference(2) == 1 and loss_difference(4) == -3
    return {'passed': True, 'exact_controls': 7,
            'physical_counterexample_or_new_source': False}


def compact_audit():
    guard(load(PRIOR/'compact_moment_hashes.json'))
    assert load(PRIOR/'verification.json')['passed']
    rows = load(PRIOR/'results.json')['rows']
    count = 0
    for row in rows:
        aa = int(row['context'] == 'gate_signal_moving')
        name = f"{row['seed']}_{row['rate']}_{row['initialization']}_{aa}_window_moments.bin"
        v = np.fromfile(PRIOR/name, dtype='<i8').reshape(W, len(COLS))
        assert np.array_equal(v[:, 0], v[:, 12]-v[:, 11])
        assert np.array_equal(v[:, 1], v[:, 2]+v[:, 3]+v[:, 4])
        assert np.array_equal(v[:, 1], 120*(v[:, 8]-30*v[:, 7]))
        assert F(mulsum(v[:, 0], v[:, 1]), MD*W) == F(row['moments']['time_partition']['total']['exact'])
        count += W
    return {'passed': True, 'window_pairs': count, 'compact_bytes': 8519680,
            'existing_information': 'Actual state gap, signed correlations and labels are paired in time.',
            'missing_information': 'No frozen-front/frozen-rear same-word correlation or hybrid corners; partitions cannot distinguish readout changes from fixed-state word background.'}


def prepare(out):
    assert not out.exists(), 'Refuse overwrite'
    audit = compact_audit()
    out.mkdir(parents=True)
    files = dict(load(PRIOR/'compact_moment_hashes.json'))
    for folder, names in ((PRIOR, ['protocol.json', 'results.json', 'verification.json']),
                          (MOMENT, ['results.json', 'verification.json']),
                          (BASE, ['results.json', 'verification.json']),
                          (NEW, ['results.json', 'verification.json'])):
        for name in names:
            p = folder/name
            files[str(p)] = digest(p)
    p = OLD/'source_protocol.json'
    files[str(p)] = digest(p)
    old_hashes = load(PRIOR/'source_hashes.json')
    for seed in SEEDS:
        paths = [OLD/f'both_smooth_{seed}_words.bin']
        for rate in ('base', 'quarter'):
            stem = f'{seed}_{rate}'
            paths += [BASE/f'{stem}_q22.bin', NEW/f'{stem}_q22.bin', CHANNEL/f'{stem}_front_q22.bin']
        for p in paths:
            assert digest(p) == old_hashes[str(p)]
            files[str(p)] = digest(p)
    guard(files)
    write(out/'source_hashes.json', files)
    sources = list((ROOT/'src/adc_research').rglob('*.py'))+list((ROOT/'experiments').rglob('*.py'))
    write(out/'execution_hashes.json', {str(p): digest(p) for p in sources})
    shutil.copyfile(Path(__file__), out/'frozen_analysis.py')
    write(out/'compact_audit.json', audit)
    write(out/'controls.json', controls())
    write(out/'protocol.json', {
        'version': 'EXP074-pre-evaluation-anchor-sampling-v1', 'date': '2026-10-13',
        'authority': 'D136..139, user continue mainline to distinguish main remaining-error sources; STATUS steps1/2',
        'object': 'Original all5 seeds, rates1/1/4, actual/prefix starts, both learner-source contexts, 40 pairs/320 blocks128..135.',
        'reference': 'Both front and rear anchors are the common legal Q22 states at window0, before block128 evaluation. No future target/state selects them. Readout uses their Q1.10 exports.',
        'corners': '00=frozen front/frozen learner rear; 10=current baseline front/frozen rear; 01=frozen front/current learner rear; 11=current baseline front/current learner rear. Held-source context has01=00 and11=10. Original k=treated-minus-baseline first export is retained in all weights.',
        'reuse': 'Read sealed40 matrices first; reuse actual11, and held-source10. Only00, moving-source01 and moving-source10 need new readouts; shared00/01 across contexts. No actual readout replays.',
        'alternatives': ['Sampling correction survives fixed-state same-word readout, versus requiring current readout parameter changes.',
                         'One parameter alone explains the change, versus front/rear interaction making replacement order material.',
                         'Interaction is only Q3 rounding, versus nonzero unrounded digital-basis interaction.',
                         'Correcting sampling suffices for target direction, versus the existing target-projection gap remaining.'],
        'predictions': ['All old40/320 weighted corrections and matrix chains close exactly.',
                        'Both replacement orders and the four-term expansion close on every window, block and pair; no zero/sign assumptions for new terms.',
                        'Front change at fixed rear is linear in exported coefficient gaps plus a bounded Q3 remainder; interaction is change of that signed basis moment plus bounded remainder.',
                        'State0 corner equality, held-source degeneracy and fixed rational/formal probes pass; retain all zero, opposite and dominant terms.'],
        'budget': {'unique_source_word_tuples_read': 1228800, 'Q22_values_loaded': 1639200,
                   'sealed_window_matrix_values_loaded': 1064960, 'new_front_Q3_PWL': 14745600,
                   'new_rear_Q3_PWL': 9830400, 'rational_and_formal_readouts_each': 1080,
                   'old_pair_block_loss_comparisons': 360, 'new_window_matrix_bytes': 4587520,
                   'new_learning_gates_requests_commits_paths_source_outputs_scores_fft_holdout': 0},
        'limits': 'Fixed-word readout references condition on actual histories, not future interventions or unique whole-period causal shares. Fixed-state background retains injected-dither/word/input associations and actual k weighting. No target or same-cost online ability claim.',
        'stopping': 'Source/domain/arithmetic/probe mismatch stops and is saved; original40/320 and136 endpoint only, no new policy/model/horizon/seed/rate/target/FFT.'})
    for name in DOCS+['docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md']:
        p = out/'documents_before'/name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, p)
    print('Sealed matrices verified; frozen missing-corner budget for all40/320', flush=True)


def gap_num(y, d):
    return 120*((d*y).sum(axis=1)-30*(d[:, :4]*y[:, :4]).sum(axis=1))


def basis_gap(raw, d, deltaK):
    mag, sign = np.abs(raw), np.sign(raw)
    total = np.zeros(W, dtype=np.int64)
    for j in range(4):
        phi = sign*np.minimum(np.maximum(mag-1024*j, 0), 1024)
        total += deltaK[:, j]*gap_num(phi, d)
    return total


def probes(words, ff, rr, yy, raw):
    _, cfg = fixed_setup(load(OLD/'source_protocol.json'))
    count = 0
    for w in (0, 1024, 2047):
        codes = export(tuple(map(int, np.r_[ff[w], rr[w]])))
        cc = replace(cfg.cascade, stage1_pwl=replace(cfg.cascade.stage1_pwl, coefficient_codes=codes[:4]),
                     stage2_pwl=replace(cfg.cascade.stage2_pwl, coefficient_codes=codes[4:]))
        for j in (0, 1, 2, 3, 59, 119):
            q1, q2, sar, bits = map(int, words[w, j])
            d1, d2 = 2*(bits & 1)-1, 2*((bits >> 1) & 1)-1
            rd = readout(q1, q2, F(sar), d1, d2, tuple(F(k, 1024) for k in codes), data_q3=True)
            formal = correct_two_stage_fixed_observed(DigitalCalibrationSample(q1, q2, sar, d1, d2), cc)
            assert int(8*rd.y1) == int(yy[w, j])
            assert int(8*rd.raw1) == int(raw[w, j])
            assert formal.unclipped_output_scaled == 8*rd.output
            assert formal.stage1_raw_scaled == 8*rd.raw1
            count += 1
    return count


def summarize(k, corners, linear, old):
    c00, c10, c01, c11 = corners
    weighted = lambda x, scale=1: F(mulsum(k, x), MD*len(k)*scale)
    values = {'total': weighted(c11), 'fixed_state_background': weighted(c00),
              'front_before_rear': weighted(c10-c00), 'rear_after_front': weighted(c11-c10),
              'rear_before_front': weighted(c01-c00), 'front_after_rear': weighted(c11-c01),
              'interaction': weighted(c11-c10-c01+c00), 'current_parameter_change': weighted(c11-c00)}
    lf, la = linear
    values['front_before_rear_linear'] = weighted(lf, 1024)
    values['front_after_rear_linear'] = weighted(la, 1024)
    values['interaction_linear'] = weighted(la-lf, 1024)
    for tag in ('front_before_rear', 'front_after_rear', 'interaction'):
        values[tag+'_Q3_remainder'] = values[tag]-values[tag+'_linear']
    assert values['total'] == F(old['terms']['sampling_correction']['exact'])
    assert values['total'] == values['fixed_state_background']+values['front_before_rear']+values['rear_after_front']
    assert values['total'] == values['fixed_state_background']+values['rear_before_front']+values['front_after_rear']
    loss = F(old['exact_first_added_loss']['exact'])
    replaced = loss-values['current_parameter_change']
    return {'terms': {t: pack(x) for t, x in values.items()},
            'old_first_added_loss': pack(loss), 'replace_sampling_by_anchor_expression': pack(replaced),
            'replacement_expression_strict_opposite': loss*replaced < 0,
            'Q3_bounds': {'front_order_each': pack(F(464, 15)*F(isum(np.abs(k)), 1024*len(k))),
                          'interaction': pack(F(928, 15)*F(isum(np.abs(k)), 1024*len(k)))}}


def analyze(out):
    assert not (out/'results.json').exists(), 'Refuse complete overwrite'
    assert digest(Path(__file__)) == digest(out/'frozen_analysis.py')
    guard(load(out/'source_hashes.json')); guard(load(out/'execution_hashes.json'))
    controls()
    prior = {(r['seed'], r['rate'], r['initialization'], r['context']): r for r in load(MOMENT/'results.json')['rows']}
    rows, pc = [], 0
    for seed in SEEDS:
        words = source(seed)
        q2, sar, bits = (words[:, :, j].astype(np.int64) for j in (1, 2, 3))
        d, d2 = 2*(bits & 1)-1, 2*((bits >> 1) & 1)-1
        for rate in ('base', 'quarter'):
            stem = f'{seed}_{rate}'
            a = np.fromfile(BASE/f'{stem}_q22.bin', dtype='<i4').reshape(W+1, 4, 8).astype(np.int64)
            b = np.fromfile(NEW/f'{stem}_q22.bin', dtype='<i4').reshape(W+1, 4, 8).astype(np.int64)
            fs = np.fromfile(CHANNEL/f'{stem}_front_q22.bin', dtype='<i4').reshape(W+1, 4, 4).astype(np.int64)
            for h, init in ((0, 'actual'), (2, 'prefix')):
                anchorF = np.broadcast_to(a[0, h, :4], (W, 4))
                anchorR = np.broadcast_to(a[0, h, 4:], (W, 4))
                movingR = a[:-1, h, 4:]
                assert np.array_equal(a[0, h, :4], b[0, h, :4])
                assert np.array_equal(a[0, h, :4], fs[0, h])
                raw0 = 1024*q2+pwl_scaled(8*sar, round_ratio(anchorR, 4096), 32)-128*d2
                raw1 = 1024*q2+pwl_scaled(8*sar, round_ratio(movingR, 4096), 32)-128*d2
                y00 = pwl_scaled(raw0, round_ratio(anchorF, 4096), 128)-512*d
                y01 = pwl_scaled(raw1, round_ratio(anchorF, 4096), 128)-512*d
                y10 = pwl_scaled(raw0, round_ratio(fs[:-1, h], 4096), 128)-512*d
                x00, x01, x10 = (gap_num(y, d) for y in (y00, y01, y10))
                for ff, rr, y, raw in ((anchorF, anchorR, y00, raw0),
                                        (anchorF, movingR, y01, raw1),
                                        (fs[:-1, h], anchorR, y10, raw0)):
                    pc += probes(words, ff, rr, y, raw)
                for aa, ctx in ((1, 'gate_signal_moving'), (0, 'gate_signal_held')):
                    v = np.fromfile(PRIOR/f'{stem}_{init}_{aa}_window_moments.bin', dtype='<i8').reshape(W, len(COLS))
                    front = fs[:-1, h] if aa else b[:-1, h, :4]
                    k = v[:, 0]
                    assert np.array_equal(v[:, 11], round_ratio(front, 4096)[:, 0])
                    deltaK = round_ratio(front, 4096)-round_ratio(anchorF, 4096)
                    corners = [x00, x10 if aa else v[:, 1], x01 if aa else x00, v[:, 1]]
                    linear = [basis_gap(raw0, d, deltaK), basis_gap(raw1 if aa else raw0, d, deltaK)]
                    cf, ca = corners[1]-corners[0], corners[3]-corners[2]
                    rf, ra = cf*1024-linear[0], ca*1024-linear[1]
                    assert np.all(np.abs(rf) <= F(29, 120)*CD*1024)
                    assert np.all(np.abs(ra) <= F(29, 120)*CD*1024)
                    assert np.all(np.abs(ra-rf) <= F(29, 60)*CD*1024)
                    assert all(int(x[0]) == int(x00[0]) for x in corners)
                    p = prior[seed, rate, init, ctx]
                    row = {'seed': seed, 'rate': rate, 'initialization': init, 'context': ctx,
                           'moments': summarize(k, corners, linear, p['moments']), 'blocks': []}
                    for bb in range(8):
                        sl = slice(bb*256, (bb+1)*256)
                        row['blocks'].append({'block': 128+bb,
                            'moments': summarize(k[sl], [z[sl] for z in corners], [z[sl] for z in linear], p['blocks'][bb]['moments'])})
                    for tag, val in row['moments']['terms'].items():
                        assert F(val['exact']) == sum(F(z['moments']['terms'][tag]['exact']) for z in row['blocks'])/8
                    if not aa:
                        assert np.array_equal(corners[0], corners[2]) and np.array_equal(corners[1], corners[3])
                        assert not (ra-rf).any()
                    record = np.column_stack((k, *corners, *linear)).astype('<i8')
                    record.tofile(out/f'{stem}_{init}_{aa}_anchor_moments.bin')
                    rows.append(row)
                    tt = row['moments']['terms']
                    print(seed, rate, init, aa, 'sampling', tt['total']['value'], 'anchor', tt['fixed_state_background']['value'],
                          'drift', tt['current_parameter_change']['value'], 'interaction', tt['interaction']['value'], flush=True)
    assert len(rows) == 40 and pc == 1080
    guard(load(out/'source_hashes.json')); guard(load(out/'execution_hashes.json'))
    write(out/'results.json', {'completed': True, 'rows': rows})
    files = list(out.glob('*_anchor_moments.bin'))
    write(out/'new_moment_hashes.json', {str(p): digest(p) for p in files})
    write(out/'verification.json', {'passed': True, 'pairs': 40, 'blocks': 320,
        'both_replacement_orders_all_windows_blocks_pairs_exact': True,
        'all_original_sampling_and_Q3_basis_bounds_exact': True,
        'initial_state_equality_and_held_source_degeneracy': True,
        'rational_and_formal_readouts_each': pc, 'source_files_preserved': len(load(out/'source_hashes.json')),
        'python_sources_preserved': len(load(out/'execution_hashes.json')),
        'new_window_matrix_bytes': sum(p.stat().st_size for p in files),
        'new_learning_gates_requests_commits_paths_source_outputs_scores_fft_holdout': 0})
    print('All anchor references, original moments and independent readout probes passed', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['prepare', 'analyze'])
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    try:
        (prepare if args.mode == 'prepare' else analyze)(args.out)
    except Exception:
        if args.out.exists():
            write(args.out/'failure.json', {'mode': args.mode, 'traceback': traceback.format_exc()})
        raise
