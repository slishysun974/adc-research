"""Read-only, predeclared kernel/line/second-jet checks on old EXP-068 words."""
import argparse
from fractions import Fraction as F
from hashlib import sha256
from itertools import combinations
import json
from pathlib import Path
import traceback

import numpy as np

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.correlation_preserving_directions import (
    correlation_geometry, direction_polynomial, exact_nullspace, mixed_direction_terms,
)
from adc_research.theory.static_fixed_contract import basis, export, nearest_even, readout
from adc_research.theory.target_moment_bounds import loss_change_interval
from adc_research.theory.window_mean_map import analyze_window_mean, certify_mean_cell, exact_matrix_rank

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT/'artifacts/runs/EXP_068/background_v1'
PREVIOUS = ROOT/'artifacts/research/coupled_stationarity_20261011_v1'
TARGET_CHECK = ROOT/'artifacts/research/target_bounds_20261011_v1'
SOURCES = (
    'src/adc_research/theory/correlation_preserving_directions.py',
    'src/adc_research/theory/gated_mean_objective.py',
    'src/adc_research/theory/window_mean_map.py',
    'src/adc_research/theory/static_fixed_contract.py',
    'src/adc_research/theory/target_moment_bounds.py',
    'src/adc_research/calibration/observation.py',
    'tests/test_correlation_preserving_directions.py',
    'experiments/exp_068_dynamic_background/check_preserving_directions.py',
)


def digest(path):
    h = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def vector(v):
    return [str(x) for x in v]


def dot(a, b):
    return sum((x*y for x, y in zip(a, b, strict=True)), F(0))


def weighted(values, weights):
    return tuple(sum((q*row[j] for q, row in zip(weights, values)), F(0)) for j in range(8))


def products(readings, samples):
    return tuple(tuple(16*s.stage2_dither_symbol*r.y2*int(g) for g in r.gates[1])+
                 tuple(64*s.stage1_dither_symbol*r.y1*int(g) for g in r.gates[0])
                 for r, s in zip(readings, samples))


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=False)
    old = load(PREVIOUS/'protocol.json')
    write(folder/'protocol.json', {
        'scope': 'Approved plan 10.2 and its necessary 10.3 checks; fixed old digital laws only.',
        'cases': old['cases'], 'histories': old['histories'], 'seeds': old['seeds'],
        'methods': old['methods'], 'windows': old['windows'], 'candidate_rows': 21600,
        'learning_laws': ['full_120', 'first_four'], 'evaluation_law': 'full_120',
        'direction_rule': 'ALL rational RREF nullspace basis vectors, ascending free columns, then scale each to infinity norm 1/4096. No sign/loss/output selection.',
        'direction_radius': '1/4096', 'cross_rule': 'All unordered pairs of canonical basis vectors; do not infer whole-kernel preservation from diagonals alone.',
        'digital_change': 'nearest-even h*2^22 added to original saved Q22 accumulators, saturated to [0,2047*4096], independently Q1.10 exported; offline intervention, not a Gu request or training.',
        'target': old['target'], 'diagnostic_target_half_width': '1/2',
        'predictions': [
            'Each kernel vector gives exactly M*h=0; fixed-mask polynomial difference equals its quadratic term.',
            'All current C and M agree with stored NG-21 values; diagonal and mixed terms equal independent weighted row products.',
            'Actual finite continuous C agrees with the polynomial only where original masks/selectors remain unchanged; derivative claims require regular support.',
            'Same-segment continuous row increments equal linear plus bilinear terms; preserve all boundaries/crossings as flagged direct readouts.',
            'All saved original integer outputs, Q22/export readouts and sharp finite target-box endpoints agree exactly.',
        ],
        'acceptance': 'Rational residuals zero, saved old codes exact, original/prior source and data hashes unchanged; no nonlinear roots or fit.',
        'limits': 'Old current C need not be zero: level-preservation diagnostics are not population root curves. Second-jet consistency is necessary only. Half-code target box has no physical coverage evidence; no future gain, algorithm or spectrum claim.',
        'budget': {'new_adc_conversions': 0, 'new_training': 0, 'new_spectrum_scans': 0},
    })
    write(folder/'source_hashes.json', {name: digest(ROOT/name) for name in SOURCES})
    previous_files = ['protocol.json', 'source_hashes.json', 'data_hashes.json', 'analysis.json', 'validation.json', 'delivery_validation.json']
    write(folder/'previous_hashes.json', {str((PREVIOUS/name).relative_to(ROOT)): digest(PREVIOUS/name) for name in previous_files} |
          {str((TARGET_CHECK/name).relative_to(ROOT)): digest(TARGET_CHECK/name) for name in ('source_hashes.json', 'validation.json', 'delivery_validation.json')})


def run(folder):
    protocol, sources = load(folder/'protocol.json'), load(folder/'source_hashes.json')
    previous_hashes = load(folder/'previous_hashes.json')
    assert all(digest(ROOT/name) == h for name, h in sources.items())
    assert all(digest(ROOT/name) == h for name, h in previous_hashes.items())
    for directory in (DATA, PREVIOUS, TARGET_CHECK):
        assert load(directory/'delivery_validation.json')['passed']
    frozen = {str(Path(e['Path']).relative_to(ROOT)): e['Hash'].lower() for e in load(DATA/'source_hashes.json')}
    for name, h in frozen.items():
        assert digest(ROOT/name) == h
    for directory in (PREVIOUS, TARGET_CHECK):
        assert all(digest(ROOT/name) == h for name, h in load(directory/'source_hashes.json').items())
    data_hashes = load(PREVIOUS/'data_hashes.json')
    assert all(digest(DATA/name) == h for name, h in data_hashes.items())
    write(folder/'data_hashes.json', data_hashes)
    previous = {(p['case'], p['history'], p['seed'], p['method']): p for p in load(PREVIOUS/'analysis.json')['paths']}
    n = load(DATA/'protocol.json')['budget']['windows_per_path']
    tone = np.fromfile(DATA/'tone.bin', dtype='<f8')
    radius = F(protocol['direction_radius'])
    paths, counts = [], {name: 0 for name in (
        'directions', 'mixed_pairs', 'certified_direction_changes', 'actual_masks_preserved_direction_changes',
        'finite_continuous_rows', 'base_boundary_direction_rows', 'segment_crossing_direction_rows',
        'continuous_new_readouts', 'digital_new_q3_readouts', 'finite_loss_endpoint_checks')}
    for case in protocol['cases']:
        for history in protocol['histories']:
            for seed in protocol['seeds']:
                stem = f'{case}_{history}_{seed}'
                words = np.memmap(DATA/(stem+'_words.bin'), dtype='i1', mode='r', shape=(n, 120, 4))
                codes = np.memmap(DATA/(stem+'_outputs.bin'), dtype='<i2', mode='r', shape=(n, 120, 3))
                for mi, method in enumerate(protocol['methods']):
                    states = np.memmap(DATA/(stem+'_'+method+'_q22.bin'), dtype='<f8', mode='r', shape=(n+1, 8))
                    probes = []
                    for w, old_probe in zip(protocol['windows'], previous[case, history, seed, method]['probes'], strict=True):
                        samples = tuple(Sample(int(q1), int(q2), int(be), 2*(int(tags)&1)-1, 2*((int(tags)>>1)&1)-1)
                                        for q1, q2, be, tags in words[w])
                        fixed = tuple(F.from_float(float(x))*(1 << 22) for x in states[w])
                        assert all(x.denominator == 1 for x in fixed)
                        front_rear_acc = tuple(map(int, fixed))
                        acc = front_rear_acc[4:]+front_rear_acc[:4]
                        front_rear = tuple(F(x, 1024) for x in export(front_rear_acc))
                        k = front_rear[4:]+front_rear[:4]
                        result = analyze_window_mean(samples, k)
                        certified = certify_mean_cell(result, radius).all_masks_and_domains_stable
                        targets = tuple(2048*(1+F.from_float(float(tone[(120*w+i)%len(tone)]))) for i in range(120))
                        half = F(protocol['diagnostic_target_half_width'])
                        lo, hi = tuple(t-half for t in targets), tuple(t+half for t in targets)
                        args = tuple((s.stage1_symbol, s.stage2_symbol, F(s.backend_centered_code),
                                      s.stage1_dither_symbol, s.stage2_dither_symbol) for s in samples)
                        old = tuple(readout(*a, front_rear, data_q3=False) for a in args)
                        old_q3 = tuple(readout(*a, front_rear, data_q3=True) for a in args)
                        old_int = tuple(F(nearest_even(r.output)) for r in old_q3)
                        assert old_int == tuple(F(int(x)) for x in codes[w, :, mi+1])
                        z = tuple(r.output for r in old)
                        jrows = tuple(tuple(k[4+row.selector1]*x for x in row.basis2)+row.basis1 for row in result.rows)
                        laws = []
                        for law, weights in (('full_120', None), ('first_four', (1,)*4+(0,)*116)):
                            q = (F(1, 120),)*120 if weights is None else (F(1, 4),)*4+(F(0),)*116
                            geo = correlation_geometry(result, weights)
                            saved = next(item for item in old_probe['laws'] if item['learning'] == law)
                            assert geo.correlations == tuple(F(x) for x in saved['C'])
                            assert geo.jacobian == tuple(tuple(F(x) for x in row) for row in saved['correlation_matrix'])
                            assert geo.correlations == weighted(products(old, samples), q)
                            basis_vectors = exact_nullspace(geo.jacobian)
                            rank = exact_matrix_rank(geo.jacobian)
                            assert len(basis_vectors) == 8-rank
                            extended_rank = exact_matrix_rank(geo.jacobian+jrows)
                            directions = []
                            all_diag_c, all_diag_z = True, True
                            for vector_index, v in enumerate(basis_vectors):
                                h = tuple(x*radius/max(map(abs, v)) for x in v)
                                poly = direction_polynomial(result, geo, h)
                                assert poly.first_order_neutral and poly.linear_correlations == (0,)*8
                                if poly.second_jet_acceleration is not None:
                                    assert tuple(dot(row, poly.second_jet_acceleration) for row in geo.jacobian) == tuple(-2*x for x in poly.quadratic_correlations)
                                all_diag_c &= not any(poly.quadratic_correlations)
                                all_diag_z &= not any(poly.quadratic_outputs)
                                end = tuple(a+b for a, b in zip(k, h))
                                new = tuple(readout(*a, end[4:]+end[:4], data_q3=False) for a in args)
                                actual_c = weighted(products(new, samples), q)
                                polynomial_rows = []
                                boundary, crossing = [], []
                                masks_preserved = True
                                for i, (row, r, s) in enumerate(zip(result.rows, new, samples)):
                                    direct_j = tuple(k[4+row.selector1]*x for x in basis(F(s.backend_centered_code), 32))+basis(old[i].raw1, 128)
                                    assert poly.linear_outputs[i] == dot(direct_j, h)
                                    b = h[4+row.selector1]*dot(basis(F(s.backend_centered_code), 32), h[:4])
                                    assert b == poly.quadratic_outputs[i]
                                    polynomial_rows.append((F(0),)*4+tuple(64*s.stage1_dither_symbol*int(old[i].gates[0][a])*b for a in range(4)))
                                    predicted_basis = tuple(x+(dot(row.basis2, h[:4]) if a == row.selector1 else 0) for a, x in enumerate(row.basis1))
                                    same_segment = basis(r.raw1, 128) == predicted_basis
                                    if row.selector_margin1 == 0 or row.domain_margin1 == 0:
                                        boundary.append(i)
                                    elif not same_segment:
                                        crossing.append(i)
                                    else:
                                        assert r.output-old[i].output == poly.linear_outputs[i]+poly.quadratic_outputs[i]
                                        counts['finite_continuous_rows'] += 1
                                    if q[i]:
                                        masks_preserved &= same_segment and r.gates == old[i].gates
                                assert weighted(polynomial_rows, q) == poly.quadratic_correlations
                                if masks_preserved:
                                    assert tuple(a-b for a, b in zip(actual_c, geo.correlations)) == poly.quadratic_correlations
                                    counts['actual_masks_preserved_direction_changes'] += 1
                                if certified:
                                    assert masks_preserved
                                    counts['certified_direction_changes'] += 1
                                requests = tuple(nearest_even(x*(1 << 22)) for x in h)
                                after = tuple(min(2047*4096, max(0, a+b)) for a, b in zip(acc, requests))
                                bank = tuple(F(x, 1024) for x in export(after[4:]+after[:4]))
                                effective = tuple(a-b for a, b in zip(bank[4:]+bank[:4], k))
                                digital = tuple(readout(*a, bank, data_q3=True) for a in args)
                                digital_int = tuple(F(nearest_even(r.output)) for r in digital)
                                digital_c = weighted(products(digital, samples), q)
                                base_digital_c = weighted(products(old_q3, samples), q)
                                finite = {}
                                for name, initial, final in (('continuous', z, tuple(r.output for r in new)), ('digital_integer', old_int, digital_int)):
                                    interval = loss_change_interval(initial, final, lo, hi)
                                    direct = sum(((b-t)**2-(a-t)**2 for a, b, t in zip(initial, final, targets)), F(0))/120
                                    assert direct == interval.center
                                    for endpoint, expected in ((interval.minimizing_targets, interval.lower), (interval.maximizing_targets, interval.upper)):
                                        assert sum(((b-t)**2-(a-t)**2 for a, b, t in zip(initial, final, endpoint)), F(0))/120 == expected
                                        counts['finite_loss_endpoint_checks'] += 1
                                    finite[name] = {'changed_rows': sum(a != b for a, b in zip(initial, final)),
                                                    'point_target_loss_difference': str(direct),
                                                    'half_code_lower': str(interval.lower), 'half_code_upper': str(interval.upper)}
                                directions.append({'index': vector_index, 'h': vector(h),
                                    'quadratic_C': vector(poly.quadratic_correlations), 'actual_continuous_C_change': vector(tuple(a-b for a, b in zip(actual_c, geo.correlations))),
                                    'straight_line_preserves_C_polynomial': poly.straight_line_preserves_correlations,
                                    'first_order_output_invariant': poly.first_order_output_invariant,
                                    'straight_line_preserves_output_polynomial': poly.straight_line_preserves_output,
                                    'second_jet_consistent': poly.second_jet_acceleration is not None,
                                    'actual_masks_and_segments_preserved': masks_preserved,
                                    'base_boundary_rows': boundary, 'segment_crossing_rows': crossing,
                                    'q22_hidden_state_changed': after != acc, 'effective_export_delta': vector(effective),
                                    'effective_export_changed': any(effective),
                                    'q3_C_changed': digital_c != base_digital_c, 'q3_C_change': vector(tuple(a-b for a, b in zip(digital_c, base_digital_c))),
                                    'finite_loss': finite})
                                counts['directions'] += 1
                                counts['base_boundary_direction_rows'] += len(boundary)
                                counts['segment_crossing_direction_rows'] += len(crossing)
                                counts['continuous_new_readouts'] += 120
                                counts['digital_new_q3_readouts'] += 120
                            pairs, all_cross_c, all_cross_z = [], True, True
                            for a, b in combinations(range(len(basis_vectors)), 2):
                                v, wv = basis_vectors[a], basis_vectors[b]
                                c, out = mixed_direction_terms(result, geo, v, wv)
                                direct_terms = []
                                for row, s in zip(result.rows, samples):
                                    mixed = v[4+row.selector1]*dot(row.basis2, wv[:4])+wv[4+row.selector1]*dot(row.basis2, v[:4])
                                    direct_terms.append((F(0),)*4+tuple(64*s.stage1_dither_symbol*int(g)*mixed for g in row.gates1))
                                assert c == weighted(direct_terms, q)
                                all_cross_c &= not any(c); all_cross_z &= not any(out)
                                pairs.append({'basis_pair': [a, b], 'mixed_C': vector(c), 'output_mixed_nonzero_rows': sum(x != 0 for x in out)})
                                counts['mixed_pairs'] += 1
                            first_output_flat = all(d['first_order_output_invariant'] for d in directions)
                            assert first_output_flat == (extended_rank == rank)
                            laws.append({'learning': law, 'C_is_zero': not any(geo.correlations),
                                'derivative_regular': geo.correlation_derivative_regular, 'rank_M': rank, 'rank_M_output': extended_rank,
                                'nullity': len(basis_vectors), 'whole_kernel_first_output_invariant': first_output_flat,
                                'whole_kernel_lines_preserve_C_polynomial': all_diag_c and all_cross_c,
                                'whole_kernel_lines_preserve_output_polynomial': first_output_flat and all_diag_z and all_cross_z,
                                'directions': directions, 'mixed_pairs': pairs})
                        probes.append({'window': w, 'whole_window_radius_certified': certified,
                                       'output_derivative_regular': result.open_cell_regular or old_probe['output_derivative_regular'], 'laws': laws})
                    paths.append({'case': case, 'history': history, 'seed': seed, 'method': method, 'probes': probes})
                    print('checked', stem, method, flush=True)
    assert all(digest(ROOT/name) == h for name, h in sources.items())
    assert all(digest(ROOT/name) == h for name, h in previous_hashes.items())
    assert all(digest(ROOT/name) == h for name, h in frozen.items())
    assert all(digest(DATA/name) == h for name, h in data_hashes.items())
    for directory in (PREVIOUS, TARGET_CHECK):
        assert all(digest(ROOT/name) == h for name, h in load(directory/'source_hashes.json').items())
    write(folder/'analysis.json', {'paths': paths})
    probes = [p for path in paths for p in path['probes']]
    laws = [law for p in probes for law in p['laws']]
    directions = [d for law in laws for d in law['directions']]
    assert len(probes)*120 == protocol['candidate_rows']
    validation = {'passed': True, 'paths': len(paths), 'windows': len(probes), 'candidate_rows': len(probes)*120,
        'learning_laws': len(laws), 'counts': counts, 'original_saved_integer_codes': len(probes)*120,
        'zero_C_laws': sum(l['C_is_zero'] for l in laws),
        'regular_C_laws': sum(l['derivative_regular'] for l in laws),
        'regular_output_windows': sum(p['output_derivative_regular'] for p in probes),
        'certified_windows': sum(p['whole_window_radius_certified'] for p in probes),
        'whole_kernel_first_output_invariant_laws': sum(l['whole_kernel_first_output_invariant'] for l in laws),
        'whole_kernel_C_line_polynomial_laws': sum(l['whole_kernel_lines_preserve_C_polynomial'] for l in laws),
        'whole_kernel_output_line_polynomial_laws': sum(l['whole_kernel_lines_preserve_output_polynomial'] for l in laws),
        'canonical_straight_C_polynomial_directions': sum(d['straight_line_preserves_C_polynomial'] for d in directions),
        'canonical_first_output_invariant_directions': sum(d['first_order_output_invariant'] for d in directions),
        'canonical_output_line_polynomial_directions': sum(d['straight_line_preserves_output_polynomial'] for d in directions),
        'canonical_second_jet_consistent_directions': sum(d['second_jet_consistent'] for d in directions),
        'effective_export_changed_directions': sum(d['effective_export_changed'] for d in directions),
        'q3_C_changed_directions': sum(d['q3_C_changed'] for d in directions),
        'integer_output_changed_directions': sum(d['finite_loss']['digital_integer']['changed_rows'] > 0 for d in directions),
        'exact_residual': '0', 'old_source_files_verified': len(frozen), 'used_data_files_verified': len(data_hashes),
        'previous_files_verified': len(previous_hashes), 'new_adc_conversions': 0, 'new_training': 0,
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
