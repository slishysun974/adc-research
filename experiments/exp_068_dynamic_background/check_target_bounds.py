"""Predeclared read-only target-box checks of delivered EXP-068 windows.

No conversions or training; original observations and saved states are inputs.
The half-code box is a diagnostic assumption, not a physical target envelope.
"""
import argparse
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import traceback

import numpy as np

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.static_fixed_contract import basis, export, nearest_even, readout
from adc_research.theory.target_moment_bounds import coupled_target_bounds, loss_change_interval
from adc_research.theory.window_mean_map import analyze_window_mean

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT/'artifacts/runs/EXP_068/background_v1'
PREVIOUS = ROOT/'artifacts/research/coupled_stationarity_20261011_v1'
SOURCES = (
    'src/adc_research/theory/target_moment_bounds.py',
    'src/adc_research/theory/gated_mean_objective.py',
    'src/adc_research/theory/window_mean_map.py',
    'src/adc_research/theory/static_fixed_contract.py',
    'src/adc_research/calibration/observation.py',
    'tests/test_target_moment_bounds.py',
    'experiments/exp_068_dynamic_background/check_target_bounds.py',
)


def digest(path):
    h = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=False)
    previous = load(PREVIOUS/'protocol.json')
    write(folder/'protocol.json', {
        'scope': 'Approved plan 10.1: target constraints; exact old-window checks only.',
        'source_data': str(DATA.relative_to(ROOT)),
        'previous_analysis': str(PREVIOUS.relative_to(ROOT)),
        'cases': previous['cases'], 'histories': previous['histories'],
        'seeds': previous['seeds'], 'methods': previous['methods'],
        'windows': previous['windows'], 'candidate_rows': previous['candidate_rows'],
        'joint_delta_rear_front': previous['joint_delta_rear_front'],
        'integer_new_state': 'Original saved next-window Q22 state, independently exported to Q1.10; reread same old words with Q3 and nearest-even integer output.',
        'target': previous['target'], 'diagnostic_box_half_width': '1/2',
        'target_groups': 'Each row independent. No pre-injection/history equality inferred from old records.',
        'learning_laws': previous['learning_laws'], 'evaluation_law': previous['evaluation_law'],
        'predictions': [
            'Point-target gradient and both leakages equal all stored NG-21 moments.',
            'Each component box endpoint is attained by its declared extremizing targets.',
            'Finite continuous and actual exported/Q3/integer same-record loss differences equal the point-target bounds and direct independent squared errors.',
            'All box loss endpoints are attained; plateau yields exactly zero regardless of target width.',
        ],
        'boundaries': 'Keep all rows and direct finite losses; record original selector/domain boundaries and continuous segment crossings separately. Moment at boundary is a frozen-selector value, not a derivative.',
        'acceptance': 'All rational identities and saved old integer codes exact; original sources, prior analysis and used data hashes unchanged. Archive any failure without overwriting.',
        'budget': {'new_adc_conversions': 0, 'new_training': 0, 'new_spectrum_scans': 0},
        'limits': 'Half-code box is an algebraic sensitivity control only, with no chip coverage evidence. Same old-window change is not future causal gain, a population root, a PRNG test or a new algorithm.',
    })
    write(folder/'source_hashes.json', {name: digest(ROOT/name) for name in SOURCES})
    write(folder/'previous_hashes.json', {name: digest(PREVIOUS/name) for name in (
        'protocol.json', 'source_hashes.json', 'data_hashes.json', 'analysis.json',
        'validation.json', 'delivery_validation.json')})


def interval_json(b):
    return {key: str(getattr(b, key)) for key in ('center', 'radius', 'lower', 'upper')}


def mean(values, weights=None):
    weights = (F(1, len(values)),)*len(values) if weights is None else weights
    return sum((p*v for p, v in zip(weights, values, strict=True)), F(0))


def loss(old, new, targets):
    return mean(tuple((b-t)**2-(a-t)**2 for a, b, t in zip(old, new, targets, strict=True)))


def category(bound):
    if bound.upper < 0:
        return 'strict_improvement'
    if bound.lower > 0:
        return 'strict_degradation'
    if bound.lower == bound.upper == 0:
        return 'identical_loss'
    if bound.upper == 0:
        return 'nonincrease'
    if bound.lower == 0:
        return 'nondecrease'
    return 'both_signs_allowed'


def run(folder):
    protocol, sources = load(folder/'protocol.json'), load(folder/'source_hashes.json')
    prior_hashes = load(folder/'previous_hashes.json')
    assert all(digest(ROOT/name) == value for name, value in sources.items())
    assert all(digest(PREVIOUS/name) == value for name, value in prior_hashes.items())
    assert load(PREVIOUS/'validation.json')['passed']
    assert load(PREVIOUS/'delivery_validation.json')['passed']
    assert load(DATA/'delivery_validation.json')['passed']
    frozen = {str(Path(e['Path']).relative_to(ROOT)): e['Hash'].lower()
              for e in load(DATA/'source_hashes.json')}
    assert all(digest(ROOT/name) == value for name, value in frozen.items())
    old_hashes = load(PREVIOUS/'data_hashes.json')
    assert all(digest(DATA/name) == value for name, value in old_hashes.items())
    write(folder/'data_hashes.json', old_hashes)
    prior = {(path['case'], path['history'], path['seed'], path['method']): path
             for path in load(PREVIOUS/'analysis.json')['paths']}
    n = load(DATA/'protocol.json')['budget']['windows_per_path']
    tone = np.fromfile(DATA/'tone.bin', dtype='<f8')
    delta = tuple(F(x) for x in protocol['joint_delta_rear_front'])
    radius = F(protocol['diagnostic_box_half_width'])
    paths, boundary_count, crossing_count, component_count = [], 0, 0, 0
    for case in protocol['cases']:
        for history in protocol['histories']:
            for seed in protocol['seeds']:
                stem = f'{case}_{history}_{seed}'
                words = np.memmap(DATA/(stem+'_words.bin'), dtype='i1', mode='r', shape=(n, 120, 4))
                codes = np.memmap(DATA/(stem+'_outputs.bin'), dtype='<i2', mode='r', shape=(n, 120, 3))
                for mi, method in enumerate(protocol['methods']):
                    states = np.memmap(DATA/(stem+'_'+method+'_q22.bin'), dtype='<f8', mode='r', shape=(n+1, 8))
                    probes = []
                    for w, old_probe in zip(protocol['windows'], prior[case, history, seed, method]['probes'], strict=True):
                        assert w == old_probe['window']
                        samples = tuple(Sample(int(q1), int(q2), int(be), 2*(int(tags)&1)-1,
                                               2*((int(tags)>>1)&1)-1) for q1, q2, be, tags in words[w])
                        banks = []
                        for index in (w, w+1):
                            fixed = tuple(F.from_float(float(x))*(1 << 22) for x in states[index])
                            assert all(x.denominator == 1 for x in fixed)
                            banks.append(tuple(F(x, 1024) for x in export(tuple(int(x) for x in fixed))))
                        front_rear, next_front_rear = banks
                        k = front_rear[4:]+front_rear[:4]
                        result = analyze_window_mean(samples, k)
                        end = tuple(a+b for a, b in zip(k, delta))
                        targets = tuple(2048*(1+F.from_float(float(tone[(120*w+i)%len(tone)]))) for i in range(120))
                        lo, hi = tuple(t-radius for t in targets), tuple(t+radius for t in targets)
                        coarse = tuple(F(2048+512*s.stage1_symbol) for s in samples)
                        old_z, new_z, old_integer, new_integer, direct_rows = [], [], [], [], []
                        boundary, crossing = [], []
                        for i, (s, row) in enumerate(zip(samples, result.rows, strict=True)):
                            args = (s.stage1_symbol, s.stage2_symbol, F(s.backend_centered_code),
                                    s.stage1_dither_symbol, s.stage2_dither_symbol)
                            a = readout(*args, front_rear, data_q3=False)
                            b = readout(*args, end[4:]+end[:4], data_q3=False)
                            ia = nearest_even(readout(*args, front_rear, data_q3=True).output)
                            ib = nearest_even(readout(*args, next_front_rear, data_q3=True).output)
                            assert ia == int(codes[w, i, mi+1])
                            assert (a.raw1, a.y1, a.y2) == (row.raw1, row.local1, row.local2)
                            old_z.append(a.output); new_z.append(b.output)
                            old_integer.append(F(ia)); new_integer.append(F(ib))
                            j = min(int(abs(a.raw1)//128), 3)
                            phi = basis(a.raw1, 128)
                            jac = tuple(k[4+j]*x for x in basis(F(s.backend_centered_code), 32))+phi
                            gamma = tuple(x-(a.y2 if index == j else 0) for index, x in enumerate(phi))
                            direct_rows.append((a, jac, gamma, k[4+j]))
                            if row.selector_margin1 == 0 or row.domain_margin1 == 0:
                                boundary.append(i)
                            else:
                                v = sum((a*b for a, b in zip(row.basis2, delta[:4])), F(0))
                                predicted = tuple(x+(v if index == j else 0) for index, x in enumerate(phi))
                                if basis(b.raw1, 128) != predicted:
                                    crossing.append(i)
                        laws = []
                        for law, raw_weights in (('full_120', None), ('first_four', (1,)*4+(0,)*116)):
                            q = ((F(1, 120),)*120 if raw_weights is None else (F(1, 4),)*4+(F(0),)*116)
                            bounds = coupled_target_bounds(result, coarse, lo, hi, learning_weights=raw_weights)
                            saved = next(item for item in old_probe['laws'] if item['learning'] == law)
                            assert tuple(x.center for x in bounds.half_gradient) == tuple(F(x) for x in old_probe['g'])
                            assert tuple(x.center for x in bounds.leakage) == tuple(F(x) for x in saved['target_leakage'])
                            assert bounds.output_derivative_regular == old_probe['output_derivative_regular']
                            for dim in range(8):
                                for box, field in ((bounds.half_gradient[dim], 'g'), (bounds.leakage[dim], 'leak')):
                                    for endpoint, expected in ((box.minimizing_targets, box.lower),
                                                                (box.maximizing_targets, box.upper)):
                                        values = []
                                        for i, ((a, jac, gamma, slope), t) in enumerate(zip(direct_rows, endpoint)):
                                            if field == 'g':
                                                values.append((a.output-t)*jac[dim])
                                            elif dim < 4:
                                                tau = (F(64*samples[i].stage1_dither_symbol)+t-coarse[i]
                                                       -sum((x*y for x, y in zip(k[4:], gamma)), F(0)))/slope
                                                values.append(16*samples[i].stage2_dither_symbol*int(a.gates[1][dim])*tau)
                                            else:
                                                values.append(64*samples[i].stage1_dither_symbol*int(a.gates[0][dim-4])*(t-coarse[i]))
                                        assert mean(tuple(values), None if field == 'g' else q) == expected
                                    component_count += 1
                            laws.append({'learning': law, 'g': [interval_json(x) for x in bounds.half_gradient],
                                         'leakage': [interval_json(x) for x in bounds.leakage]})
                        finite = {}
                        for name, old, new in (('continuous_declared_delta', old_z, new_z),
                                               ('integer_original_next_export', old_integer, new_integer)):
                            point = loss_change_interval(old, new, targets, targets)
                            box = loss_change_interval(old, new, lo, hi)
                            assert point.center == point.lower == point.upper == loss(old, new, targets)
                            assert box.center == point.center
                            assert loss(old, new, box.minimizing_targets) == box.lower
                            assert loss(old, new, box.maximizing_targets) == box.upper
                            changes = tuple(b-a for a, b in zip(old, new))
                            threshold = (abs(point.center)/(2*mean(tuple(abs(x) for x in changes)))
                                         if any(changes) else None)
                            finite[name] = {'point_target_loss_difference': str(point.center),
                                            'half_code_box': interval_json(box), 'box_class': category(box),
                                            'changed_rows': sum(x != 0 for x in changes),
                                            'uniform_target_radius_sign_threshold': str(threshold) if threshold is not None else None}
                        boundary_count += len(boundary); crossing_count += len(crossing)
                        probes.append({'window': w, 'base_boundary_rows': boundary, 'continuous_crossing_rows': crossing,
                                       'next_export_changed': next_front_rear != front_rear,
                                       'laws': laws, 'finite_loss': finite})
                    paths.append({'case': case, 'history': history, 'seed': seed, 'method': method, 'probes': probes})
                    print('checked', stem, method, flush=True)
    probes = [probe for path in paths for probe in path['probes']]
    assert len(probes)*120 == protocol['candidate_rows']
    assert all(digest(ROOT/name) == value for name, value in frozen.items())
    assert all(digest(ROOT/name) == value for name, value in sources.items())
    assert all(digest(DATA/name) == value for name, value in old_hashes.items())
    assert all(digest(PREVIOUS/name) == value for name, value in prior_hashes.items())
    write(folder/'analysis.json', {'paths': paths})
    classes = {name: {key: sum(probe['finite_loss'][name]['box_class'] == key for probe in probes)
                      for key in ('strict_improvement', 'strict_degradation', 'identical_loss',
                                  'nonincrease', 'nondecrease', 'both_signs_allowed')}
               for name in ('continuous_declared_delta', 'integer_original_next_export')}
    validation = {'passed': True, 'paths': len(paths), 'windows': len(probes), 'rows': len(probes)*120,
                  'learning_moment_sets': len(probes)*2, 'component_intervals': component_count,
                  'component_endpoints': component_count*2, 'finite_loss_intervals': len(probes)*2,
                  'finite_loss_endpoints': len(probes)*4, 'old_saved_integer_codes': len(probes)*120,
                  'direct_continuous_readouts': len(probes)*240, 'direct_q3_readouts': len(probes)*240,
                  'base_boundary_rows': boundary_count, 'continuous_crossing_rows': crossing_count,
                  'next_export_unchanged_windows': sum(not p['next_export_changed'] for p in probes),
                  'finite_loss_box_classes': classes, 'exact_residual': '0',
                  'old_source_files_verified': len(frozen), 'used_data_files_verified': len(old_hashes),
                  'prior_files_verified': len(prior_hashes), 'new_adc_conversions': 0, 'new_training': 0,
                  'interpretation': protocol['limits']}
    write(folder/'validation.json', validation)
    print(json.dumps(validation, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder', type=Path, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare', action='store_true'); group.add_argument('--run', action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare(args.folder)
    else:
        try:
            run(args.folder)
        except Exception:
            write(args.folder/'failure.json', {'traceback': traceback.format_exc()})
            raise
