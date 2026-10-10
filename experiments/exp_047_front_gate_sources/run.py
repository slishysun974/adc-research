"""Explain the preselected EXP-046 pair; no feedback replay or new training."""

import argparse
from collections import Counter
from fractions import Fraction as F
import json
from pathlib import Path

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.evaluation.front_target_projection import project_low_front_targets, decompose_front_target_bias
from adc_research.evaluation.gated_target_diagnostics import decompose_target_correlation
from adc_research.theory.front_gate_attribution import stage_gate_frames, gate_sources, compare_gate_masks, inner_second_gate
from adc_research.theory.gated_correlation_roots import WeightedStageRow, scan_two_slope_roots, stage_correlations, stage_basis
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_042_correlation_roots.run import digest, write, stage_rows, quantized_reference, offline_score, check_scan

ROOT = Path(__file__).resolve().parents[2]
CASE = 'periodic255_reset'
PAIR = (4, 5)  # Already specified in EXP-046 and its theory/report, before this analysis.
PARTITIONS = {'fit': (0, 11520), 'training_suffix': (11520, 15360), 'online_sine': (15360, 19200)}
WIDTH = F(128)


def digital_raw(sample, backend):
    basis = stage_basis(F(sample.backend_centered_code), F(32))
    return 128*sample.stage2_symbol+sum((k*p for k, p in zip(backend, basis)), F(0))-16*sample.stage2_dither_symbol


def offline_record(samples, targets, backend):
    """Targets first enter here, after all digital diagnostics and root checks."""
    cache = {sample: digital_raw(sample, backend) for sample in set(samples)}
    counts = Counter((cache[s], F(64*s.stage1_dither_symbol),
                      F(target-2048-512*s.stage1_symbol)) for s, target in zip(samples, targets, strict=True))
    return tuple((WeightedStageRow(raw, dither, count), target)
                 for (raw, dither, target), count in sorted(counts.items()))


def offline_target_terms(record, coefficients):
    frames = stage_gate_frames(tuple(row for row, _ in record), coefficients, WIDTH)
    total = sum(row.count for row, _ in record)
    results = []
    for i in range(4):
        terms = decompose_target_correlation(tuple((target, row.dither, frame.gates[i], row.count)
                                                   for (row, target), frame in zip(record, frames)))
        error = sum((row.count*row.dither*(frame.local-target) for (row, target), frame
                     in zip(record, frames) if frame.gates[i]), F(0))/total
        learning = sum((row.count*row.dither*frame.local for (row, _), frame
                        in zip(record, frames) if frame.gates[i]), F(0))/total
        assert terms['gated_target_correlation']+error == learning
        terms.update(continuous_error_correlation=error, learning_correlation=learning,
                     target_error_identity_verified=True)
        results.append(terms)
    support = decompose_target_correlation(tuple((target, row.dither, frame.basis[1] != 0, row.count)
                                                 for (row, target), frame in zip(record, frames)))
    support_error = sum((row.count*row.dither*(frame.local-target)
                         for (row, target), frame in zip(record, frames) if frame.basis[1] != 0), F(0))/total
    support.update(continuous_error_correlation=support_error,
                   learning_correlation=support['gated_target_correlation']+support_error)
    return {'gates': results, 'common_raw_support_gate': support,
            'continuous_mse': sum((row.count*(frame.local-target)**2
                                                    for (row, target), frame in zip(record, frames)), F(0))/total}


def analyze_digital(samples, coefficients):
    rows = stage_rows(samples, 1, coefficients[0][:4])
    frames = tuple(stage_gate_frames(rows, k[4:], WIDTH) for k in coefficients)
    branches = []
    for k, branch in zip(coefficients, frames):
        sources = gate_sources(branch)
        assert tuple(g['correlation'] for g in sources['gates']) == stage_correlations(rows, k[4:], WIDTH)
        inner = tuple(f for f in branch if abs(f.observation.raw) <= WIDTH)
        for f in inner:
            assert f.basis[1] == 0
            assert f.gates[1] == inner_second_gate(f.observation.raw, f.observation.dither, k[4], WIDTH)
            if f.gates[1]:
                assert f.observation.dither*f.local <= -abs(f.observation.dither)*WIDTH*k[4]
        sources.update(first_slope=k[4], second_gate_threshold=WIDTH*k[4],
                       inner_raw_count=sum(f.observation.count for f in inner),
                       inner_rows_open_count=sum(f.observation.count for f in inner if f.gates[1]),
                       all_inner_rows_open_proved=k[4] <= F(1, 4),
                       exact_inner_gate_checks=len(inner))
        branches.append(sources)
    comparisons = compare_gate_masks(*frames)
    support_correlations = tuple(sum((f.observation.count*f.observation.dither*f.local
                                     for f in branch if f.basis[1] != 0), F(0))/len(samples)
                                 for branch in frames)
    witnesses = {}
    for a, b in zip(*frames):
        key = (str(a.gates[1]), str(b.gates[1]), str(a.basis[1] != 0))
        if key not in witnesses:
            witnesses[key] = {'raw': a.observation.raw, 'dither': a.observation.dither,
                              'second_basis': a.basis[1], 'branch_locals': (a.local, b.local),
                              'branch_second_gates': (a.gates[1], b.gates[1])}
    return {'branches': branches, 'mask_comparison': comparisons,
            'common_raw_support_correlations': support_correlations,
            'common_raw_support_count': sum(f.observation.count for f in frames[0] if f.basis[1] != 0),
            'representative_digital_rows': list(witnesses.values())}


def run(source, previous, output):
    fingerprints = {}
    previous_summary = json.loads((previous/'summary.json').read_text())
    previous_verification = json.loads((previous/'verification.json').read_text())
    for name, expected in {**previous_summary['source_sha256'], **previous_summary['source_evidence_sha256'],
                           **previous_verification['extra_source_sha256']}.items():
        assert digest(ROOT/name) == expected, name
        fingerprints[ROOT/name] = expected
    for name in ('summary.json', 'verification.json', CASE+'.json'):
        fingerprints[previous/name] = digest(previous/name)
    case = next(c for c in previous_summary['cases'] if c['name'] == CASE)
    assert fingerprints[previous/(CASE+'.json')] == case['output_sha256']
    candidates = json.loads((previous/(CASE+'.json')).read_text())['candidates']
    pair = tuple(candidates[i] for i in PAIR)
    coefficients = tuple(tuple(map(F, c['seed_coefficients'])) for c in pair)
    assert coefficients[0][:4] == coefficients[1][:4]
    assert all(k[6:] == (F(1), F(1)) for k in coefficients)
    path = source/CASE/'analog_digital_records.jsonl'
    source_summary = json.loads((source/'summary.json').read_text())
    expected = next(c for c in source_summary['cases'] if c['name'] == CASE)['physical']['raw_record_sha256']
    assert digest(path) == expected
    fingerprints[path] = expected
    fingerprints[source/'summary.json'] = digest(source/'summary.json')
    lines = tuple(json.loads(line) for line in path.read_text().splitlines())
    assert len(lines) == 19200
    samples = tuple(Sample(**line['sample']) for line in lines)
    # All targets, physical waveforms and input values remain outside this section.
    digital = {name: analyze_digital(samples[a:b], coefficients) for name, (a, b) in PARTITIONS.items()}
    fit_rows = stage_rows(samples[:11520], 1, coefficients[0][:4])
    scan = scan_two_slope_roots(fit_rows, WIDTH)
    scan_check = check_scan(scan, fit_rows, WIDTH)
    assert scan.complete_on_declared_domain and len(scan.roots) == 2 and not scan.zero_intervals
    assert {r.coefficients for r in scan.roots} == {k[4:] for k in coefficients}
    assert all(g['correlation'] == 0 for branch in digital['fit']['branches'] for g in branch['gates'])
    root_cells = []
    for root in scan.roots:
        cell = next(c for c in scan.cells if c.low < root.parameter < c.high)
        root_cells.append({'root': root, 'fixed_mask_parameter_cell': cell})
    output.mkdir(parents=True, exist_ok=False)
    write(output/'digital_gate_sources.json', {'case': CASE, 'prior_pair_indices': PAIR,
          'coefficients': coefficients, 'partitions': digital, 'complete_front_slice_scan': scan_check,
          'root_cells': root_cells, 'targets_used': False})

    # Independent offline targets now quantify error; they never select the roots or masks.
    targets = tuple(line['ideal_code_offline_only'] for line in lines)
    records = {name: offline_record(samples[a:b], targets[a:b], coefficients[0][:4])
               for name, (a, b) in PARTITIONS.items()}
    projection = project_low_front_targets(records['fit'])
    fit_bias = tuple(decompose_front_target_bias(records['fit'], k[4:], projection) for k in coefficients)
    target_terms = {name: tuple(offline_target_terms(record, k[4:]) for k in coefficients)
                    for name, record in records.items()}
    cfg = _config()
    reference_coefficients = (*coefficients[0][:4], *projection['coefficients'])
    assert all(0 < k < 2 for k in reference_coefficients)
    all_coefficients = (*coefficients, reference_coefficients)
    scores = []
    for index, k in enumerate(all_coefficients):
        _, cascade, exported = quantized_reference(k, cfg)
        branch_scores = {name: offline_score(samples[a:b], targets[a:b], cascade, spectrum=name == 'online_sine')
                         for name, (a, b) in PARTITIONS.items()}
        if index < 2:
            for name in PARTITIONS:
                archived = pair[index]['offline_frozen_scores'][name]
                assert branch_scores[name]['mae_codes'] == F(archived['mae_codes'])
                assert branch_scores[name]['maximum_error_codes'] == archived['maximum_error_codes']
                if name == 'online_sine':
                    for metric in ('sndr_db', 'sfdr_dbc'):
                        assert abs(branch_scores[name]['spectrum_float'][metric]-archived['spectrum_float'][metric]) < 1e-10
        scores.append({'label': ('A', 'B', 'offline_fit_projection')[index],
                       'exported_coefficients': exported, 'scores': branch_scores})
    write(output/'offline_target_bias.json', {'fit_only_projection': projection, 'fit_branch_bias': fit_bias,
          'partition_target_terms': target_terms, 'frozen_quantized_scores': scores,
          'target_definition': 'ideal_integer_code-2048-512*stage1_symbol',
          'reference_is_online_algorithm': False, 'projection_fitted_to_sine': False})
    for path, expected in fingerprints.items():
        assert digest(path) == expected, str(path)
    dependencies = ('src/adc_research/theory/front_gate_attribution.py',
                    'src/adc_research/evaluation/front_target_projection.py',
                    'src/adc_research/evaluation/gated_target_diagnostics.py',
                    'experiments/exp_047_front_gate_sources/run.py',
                    'tests/test_front_gate_attribution.py', 'tests/test_front_target_projection.py')
    write(output/'summary.json', {'case': CASE, 'prior_pair_indices': PAIR, 'partitions': PARTITIONS,
          'scope': 'preselected same-backend pair: exact digital gate sources and separate offline error bias',
          'fit_second_gate_counts': [b['gates'][1]['open_count'] for b in digital['fit']['branches']],
          'fit_second_gate_zero_basis_counts': [b['gates'][1]['groups'][0]['count'] for b in digital['fit']['branches']],
          'fit_continuous_mse': [b['continuous_mse'] for b in fit_bias],
          'fit_projection_continuous_mse': projection['minimum_continuous_mse'],
          'source_evidence_sha256': {str(path.relative_to(ROOT)).replace('\\', '/'): expected for path, expected in fingerprints.items()},
          'source_sha256': {name: digest(ROOT/name) for name in dependencies},
          'output_sha256': {name: digest(output/name) for name in ('digital_gate_sources.json', 'offline_target_bias.json')},
          'source_package_unchanged': True, 'new_training': False, 'new_physical_samples': 0,
          'cadence_used': False, 'online_algorithm_changed': False, 'rtl_changed': False,
          'long_term_convergence_proved': False, 'new_algorithm_compared': False})
    print(json.dumps({'second_gate_counts': [b['gates'][1]['open_count'] for b in digital['fit']['branches']],
                      'zero_basis_counts': [b['gates'][1]['groups'][0]['count'] for b in digital['fit']['branches']],
                      'mse': [float(b['continuous_mse']) for b in fit_bias],
                      'projection_mse': float(projection['minimum_continuous_mse'])}, indent=2), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('source', 'previous', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    run(args.source.resolve(), args.previous.resolve(), args.output.resolve())
