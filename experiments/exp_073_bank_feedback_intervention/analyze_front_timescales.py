"""Read-only block means, within-block changes and output-loss moments.

The mean references use the saved future record. They are continuous output
differences, not new legal coefficient policies or online learning features.
"""
import argparse
from fractions import Fraction as F
from pathlib import Path
import shutil
import traceback
import numpy as np

from experiments.exp_073_bank_feedback_intervention.analyze_front_history import (
    ROOT, OLD, BASE, NEW, SEEDS, W, source, load, write, digest, guard,
    round_ratio, pwl_scaled, ExactProjector, SCALE, mulsum, pack, DOCS,
)

HISTORY = ROOT/'artifacts/research/front_forcing_response_20261013_v2'
POSITION = ROOT/'artifacts/research/front_position_variation_20261013_v1'
TAGS = ['position', 'block_migration', 'within_block', 'current_readout']


def partition(delta, length=256):
    n = len(delta)
    assert n % length == 0
    total = delta.sum(axis=0, dtype=np.int64)
    blocks = np.repeat(delta.reshape(-1, length, 2).sum(axis=1), length, axis=0)
    # All three integer numerators have the common denominator n.
    position = np.broadcast_to(total, delta.shape)
    migration = (n//length)*blocks-total
    within = n*delta-(n//length)*blocks
    assert np.array_equal(position+migration+within, n*delta)
    assert not migration.sum(axis=0).any()
    assert not within.reshape(-1, length, 2).sum(axis=1).any()
    return position, migration, within


def controls():
    d = np.array([[0, 1], [2, 3], [4, 1], [6, 3]], dtype=np.int64)
    p, m, v = partition(d, 2)
    assert p[:, 0].tolist() == [12]*4
    assert m[:, 0].tolist() == [-8, -8, 8, 8]
    assert v[:, 0].tolist() == [-4, 4, -4, 4]
    # Temporal centering does not imply orthogonality under changing bases.
    basis = [F(1), F(2), F(3), F(4)]
    ms = [basis[i]*F(int(m[i, 0]), 4) for i in range(4)]
    vs = [basis[i]*F(int(v[i, 0]), 4) for i in range(4)]
    cross = 2*sum(a*b for a, b in zip(ms, vs))/4
    assert cross == 4
    # A within-block change can help after migration and harm before it.
    e, pp, mm, vv = F(0), F(0), F(2), F(-1)
    net = lambda z: z*z+2*e*z
    assert net(pp+mm+vv)-net(pp+mm) == -3
    assert net(pp+vv)-net(pp) == 1
    assert (net(pp+mm+vv)-net(pp+mm))-(net(pp+vv)-net(pp)) == 2*mm*vv
    # MSE gradient and selected update need not have a compatible sign.
    H, h, k, u = F(5, 4), F(1), F(1), F(1, 10)
    g = H*k-h
    assert g == F(1, 4) and 2*g*u > 0
    assert (H*(k+u)**2-2*h*(k+u))-(H*k*k-2*h*k) == 2*g*u+H*u*u
    # Zero histories give zero changes; singleton blocks have no within part.
    assert all(not z.any() for z in partition(np.zeros((4, 2), dtype=np.int64), 2))
    assert not partition(d, 1)[2].any()
    return {'passed': True, 'exact_controls': 7, 'physical_source': False}


def prepare(out):
    assert not out.exists(), 'Refuse overwrite'
    assert load(HISTORY/'delivery_verification.json')['passed']
    assert load(POSITION/'verification.json')['passed']
    out.mkdir(parents=True)
    files = dict(load(POSITION/'source_hashes.json'))
    for folder in (HISTORY, POSITION):
        for name in ('results.json', 'protocol.json', 'verification.json'):
            p = folder/name
            files[str(p)] = digest(p)
    guard(files)
    write(out/'source_hashes.json', files)
    sources = list((ROOT/'src/adc_research').rglob('*.py'))+list((ROOT/'experiments').rglob('*.py'))
    write(out/'execution_hashes.json', {str(p): digest(p) for p in sources})
    shutil.copyfile(Path(__file__), out/'frozen_analysis.py')
    write(out/'controls.json', controls())
    write(out/'protocol.json', {
        'version': 'EXP073-front-block-means-within-block-v1', 'date': '2026-10-14',
        'authority': 'D136..139 and user continue; current STATUS next steps1..3',
        'scope': 'All original20 front-only/held cases, five seeds, rates1/1/4, actual/prefix, blocks128..135; no new policies or horizons.',
        'references': 'Whole-record mean exported gap, original eight256-window block means, within-block centered exports. Continuous differences from held integer output. Future means do not supply an online initializer.',
        'missing_quantity': 'Saved24-column histories hold exports/requests, and old5x5 output Gram holds weighted forcing histories. Neither contains unweighted two-basis per-block matrices/projections required by new block-mean profiles. Prior position results only hold aggregates for its own two profiles.',
        'minimal_readout': 'Reuse actual requests/exports, actual/held integer outputs and original targets. Reconstruct fixed-rear Q3 and two raw bases only; no front PWL, gates, requests, learner or source conversion.',
        'alternatives': [
            'Block-mean migration explains most added variation loss, versus within-block changes still making a large contribution.',
            'Within-block centering removes output/error crosses, versus varying bases and targets retaining crosses and order sensitivity.',
            'The nine adverse mean positions are output stationary or mean requests identify a correcting direction, versus finite update and output moments requiring distinct conditions.'],
        'predictions': [
            'All three coefficient profiles close exactly and within-block centers are zero; saved integer loss and prior position/variation/remainder scores reproduce.',
            'Retain every Gram/error cross, both addition orders, all160 block results and all39 previously beneficial variation blocks.',
            'Compute all20 mean-position gradients and actual-request moments before isolating the nine adverse positions; do not call moving-state average a fixed-state root.',
            'No score sign or dominance is assumed; intervals use unchanged NG39/43 extra sine knowledge and retain any uncertified result.'],
        'budget': {'source_unique_word_tuples': 1228800, 'initial_Q22_values': 160,
            'old_window_matrix_values': 983040, 'actual_export_values_used': 81920,
            'saved_integer_outputs_loaded': 9830400, 'rear_Q3_PWL': 4915200, 'front_Q3_PWL': 0,
            'projected_reference_code_inputs_total_and_blocks': 58982400,
            'gradient_basis_code_inputs': 9830400, 'Gram_cross_products_total_and_blocks': 58982400,
            'extra_gradient_products': 24576000,
            'new_basis_matrix_bytes': 19660800, 'new_window_Gram_projection_bytes': 1638400,
            'independent_sparse_Fraction_word_probes': 240,
            'new_learning_submissions_paths_source_fft_holdout': 0},
        'stop': 'Original20/160 only. Refuse source, domain, arithmetic or prior-score mismatch; preserve failure. No optimizer, legal-mean readout, event intervention, extra block length or long matrix.',
        'limits': 'Block means describe migration, not proven slow physical noise. Order-dependent loss additions are descriptive continuous references, not independent variance costs or unique causal shares. Mean-position gradient uses held integer baseline and continuous exported difference; actual mean requests came from moving states, not this mean reference.'})
    for name in DOCS:
        p = out/'documents_before'/name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, p)
    print('Frozen original20/160, both orders, mean-position moments and minimal rear-only budget', flush=True)


def inspect(nums, held, projector, old):
    size = held.size
    scored = [projector.projected(u, held, SCALE) for u in nums]
    q = [[F(0) for _ in nums] for _ in nums]
    for i in range(4):
        q[i][i] = F(scored[i]['power']['exact'])
        for j in range(i):
            q[i][j] = q[j][i] = F(mulsum(nums[i], nums[j]), size*SCALE*SCALE)
    bc = [F(s['error_cross']['exact']) for s in scored]
    net = lambda ids: sum(bc[i] for i in ids)+sum(q[i][j] for i in ids for j in ids)
    whole = projector.projected(sum(nums[:3]), held, SCALE)
    variation = projector.projected(nums[1]+nums[2], held, SCALE)
    assert net([0]) == F(old['mean_position']['net']['exact'])
    assert net([1, 2]) == F(old['centered_variation']['net']['exact'])
    assert net([0, 1, 2]) == F(old['linear_total']['net']['exact']) == F(whole['net']['exact'])
    assert net([0, 1, 2, 3]) == F(old['actual']['net']['exact'])
    # Original current-readout component comes from the forcing/response result,
    # and is checked separately by the caller. Its interactions stay here.
    effects = {}
    for name, i, before in [('migration_after_position', 1, [0]),
                            ('within_after_position_migration', 2, [0, 1]),
                            ('within_after_position', 2, [0]),
                            ('migration_after_position_within', 1, [0, 2])]:
        extra = 2*sum(q[i][j] for j in before)
        value = F(scored[i]['net']['exact'])+extra
        assert value == net(before+[i])-net(before)
        interval = [F(z)+extra for z in scored[i]['intersection_interval']]
        effects[name] = {**pack(value), 'interval': list(map(str, interval)),
                         'sign_certified': interval[0] > 0 or interval[1] < 0}
    assert F(effects['within_after_position_migration']['exact'])-F(effects['within_after_position']['exact']) == 2*q[1][2]
    assert F(effects['migration_after_position_within']['exact'])-F(effects['migration_after_position']['exact']) == 2*q[1][2]
    assert F(effects['migration_after_position']['exact'])+F(effects['within_after_position_migration']['exact']) == F(old['variation_added_after_position']['exact'])
    return {'components': dict(zip(TAGS, scored)), 'gram': [[str(z) for z in row] for row in q],
            'error_cross': list(map(str, bc)), 'effects': effects,
            'migration_within_cross': pack(2*q[1][2]), 'linear_total': whole,
            'variation_total': variation, 'actual': old['actual'],
            'readout_added': pack(net([0, 1, 2, 3])-net([0, 1, 2]))}


def position_moments(phi, pnum, held, moments, projector):
    size = held.size
    h = [[F(mulsum(phi[:, :, i], phi[:, :, j]), 64*size) for j in range(2)] for i in range(2)]
    bs = [projector.projected(phi[:, :, j], held, 8) for j in range(2)]
    gradient = [F(bs[j]['error_cross']['exact'])+F(2*mulsum(pnum, phi[:, :, j]), SCALE*8*size) for j in range(2)]
    # Each uncertainty radius is linear in its target projection. This is a
    # conservative component interval, not a common-target joint rectangle.
    gi = []
    for j in range(2):
        center = F(bs[j]['net']['exact'])
        gi.append([F(z)-center+gradient[j] for z in bs[j]['intersection_interval']])
    requests = [F(int(moments[:, j].sum()), W) for j in range(2)]
    corr = [F(int(moments[:, j].sum()), 4*W*8) for j in (6, 8)]
    step = [z/(1 << 22) for z in requests]
    directional = sum(a*b for a, b in zip(gradient, step))
    enclosure = [sum(min(a*z, b*z) for (a, b), z in zip(gi, step)),
                 sum(max(a*z, b*z) for (a, b), z in zip(gi, step))]
    return {'Gram_H': [[str(z) for z in row] for row in h],
            'gradient_at_mean_position': [pack(z) for z in gradient],
            'gradient_intervals': [list(map(str, z)) for z in gi],
            'nonstationary_certified': any(a > 0 or b < 0 for a, b in gi),
            'actual_moving_state_mean_request_Q22': [pack(z) for z in requests],
            'actual_selected_d_times_y_g_mean_code': [pack(z) for z in corr],
            'gradient_dot_mean_hidden_step': {**pack(directional), 'interval': list(map(str, enclosure)),
                'sign_certified': enclosure[0] > 0 or enclosure[1] < 0},
            'mean_request_is_fixed_state_root': False}


def analyze(out):
    assert not (out/'results.json').exists(), 'Refuse complete overwrite'
    assert digest(Path(__file__)) == digest(out/'frozen_analysis.py')
    guard(load(out/'source_hashes.json')); guard(load(out/'execution_hashes.json'))
    old = {(r['seed'], r['rate'], r['initialization']): r for r in load(POSITION/'results.json')['rows']}
    history = {(r['seed'], r['rate'], r['initialization']): r for r in load(HISTORY/'results.json')['rows']}
    projector = ExactProjector(); rows = []
    for seed in SEEDS:
        words = source(seed)
        q2, sar, bits = (words[:, :, j].astype(np.int64) for j in (1, 2, 3))
        d2 = 2*((bits >> 1) & 1)-1
        for rate in ('base', 'quarter'):
            stem = f'{seed}_{rate}'
            states = np.memmap(NEW/f'{stem}_q22.bin', dtype='<i4', mode='r', shape=(W+1, 4, 8))
            outputs = np.memmap(NEW/f'{stem}_outputs.bin', dtype='<i2', mode='r', shape=(W, 4, 120))
            holds = np.memmap(BASE/f'{stem}_outputs.bin', dtype='<i2', mode='r', shape=(W, 4, 120))
            for index, init in ((0, 'actual'), (2, 'prefix')):
                a0 = np.array(states[0, index], dtype=np.int64)
                mom = np.memmap(HISTORY/f'{stem}_{init}_front_moments.bin', dtype='<i8', mode='r', shape=(W, 24))
                delta = np.array(mom[:, 10:12], dtype=np.int64)-round_ratio(a0[:2], 4096)
                p, m, v = partition(delta)
                rear = np.broadcast_to(round_ratio(a0[4:], 4096), (W, 4))
                raw = 1024*q2+pwl_scaled(8*sar, rear, 32)-128*d2
                assert np.all((raw >= -4096) & (raw < 4096))
                phi = np.stack([np.sign(raw)*np.minimum(np.maximum(np.abs(raw)-1024*j, 0), 1024) for j in range(2)], axis=2)
                nums = [4096*sum(z[:, j, None]*phi[:, :, j] for j in range(2)) for z in (p, m, v)]
                actual = np.array(outputs[:, index], dtype=np.int64)
                held = np.array(holds[:, index+1], dtype=np.int64)
                nums.append((actual-held)*SCALE-sum(nums))
                assert np.all(np.abs(nums[3]) <= 9*SCALE//8)
                prev = old[seed, rate, init]; hist = history[seed, rate, init]
                stat = inspect(nums, held, projector, prev['stats'])
                for key in ('power', 'error_cross', 'net'):
                    assert stat['components']['current_readout'][key] == hist['stats']['components']['current_readout_rounding'][key]
                row = {'seed': seed, 'rate': rate, 'initialization': init, 'stats': stat,
                       'position_moments': position_moments(phi, nums[0], held, mom, projector),
                       'block_mean_export_gaps': [[pack(F(int(z), 256*1024)) for z in b] for b in delta.reshape(8, 256, 2).sum(axis=1)],
                       'blocks': []}
                for b in range(8):
                    sl = slice(256*b, 256*(b+1))
                    ss = inspect([z[sl] for z in nums], held[sl], projector, prev['blocks'][b]['stats'])
                    for key in ('power', 'error_cross', 'net'):
                        assert ss['components']['current_readout'][key] == hist['blocks'][b]['stats']['components']['current_readout_rounding'][key]
                    row['blocks'].append({'block': 128+b, 'stats': ss})
                for i in range(4):
                    assert F(stat['error_cross'][i]) == sum(F(b['stats']['error_cross'][i]) for b in row['blocks'])/8
                    for j in range(4):
                        assert F(stat['gram'][i][j]) == sum(F(b['stats']['gram'][i][j]) for b in row['blocks'])/8
                for name in stat['effects']:
                    assert F(stat['effects'][name]['exact']) == sum(F(b['stats']['effects'][name]['exact']) for b in row['blocks'])/8
                phi.astype('<i2').tofile(out/f'{stem}_{init}_basis.bin')
                matrices = np.column_stack(((phi[:, :, 0]**2).sum(axis=1),
                    (phi[:, :, 0]*phi[:, :, 1]).sum(axis=1), (phi[:, :, 1]**2).sum(axis=1),
                    (phi[:, :, 0]*held).sum(axis=1), (phi[:, :, 1]*held).sum(axis=1)))
                matrices.astype('<i8').tofile(out/f'{stem}_{init}_basis_moments.bin')
                rows.append(row)
                print(seed, rate, init, 'migration', stat['effects']['migration_after_position']['value'],
                      'within_after_migration', stat['effects']['within_after_position_migration']['value'], flush=True)
    assert len(rows) == 20
    guard(load(out/'source_hashes.json')); guard(load(out/'execution_hashes.json'))
    write(out/'results.json', {'completed': True, 'rows': rows})
    files = list(out.glob('*_basis*.bin'))
    write(out/'new_moment_hashes.json', {str(p): digest(p) for p in files})
    write(out/'verification.json', {'passed': True, 'cases': 20, 'blocks': 160,
        'prior_position_variation_actual_and_readout_exact': True,
        'both_orders_all_Gram_crosses_block_sums_exact': True,
        'source_files_preserved': len(load(out/'source_hashes.json')),
        'python_sources_preserved': len(load(out/'execution_hashes.json')),
        'new_matrix_bytes': sum(p.stat().st_size for p in files),
        'new_learning_submissions_paths_source_fft_holdout': 0})
    print('All original losses, temporal profiles, Gram crosses and block sums close exactly', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('mode', choices=['prepare', 'analyze'])
    ap.add_argument('--out', type=Path, required=True); args = ap.parse_args()
    try:
        (prepare if args.mode == 'prepare' else analyze)(args.out)
    except Exception:
        if args.out.exists():
            write(args.out/'failure.json', {'mode': args.mode, 'traceback': traceback.format_exc()})
        raise
