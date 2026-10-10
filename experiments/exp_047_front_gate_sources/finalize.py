"""Independent old mean-map reconstruction, source audit, tests and links."""
from fractions import Fraction as F
import json
from pathlib import Path
import re
import sys
import unittest
from urllib.parse import unquote

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.constrained_mean_root import weighted_cascade_mean
from experiments.exp_042_correlation_roots.run import digest, histogram, write
from experiments.exp_047_front_gate_sources.run import CASE, PARTITIONS

ROOT = Path(__file__).resolve().parents[2]
DOCS = ('docs/STATUS.md', 'docs/DECISIONS.md', 'docs/README.md', 'docs/theory/README.md',
        'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
        'docs/theory/FRONT_GATE_SOURCES_AND_TARGET_BIAS_V1.md',
        'docs/reports/experiments/README.md', 'docs/reports/experiments/EXP_047_FRONT_GATE_SOURCES_V1.md',
        'docs/reports/RESEARCH_STATUS_PLAIN_2026-10-09.md',
        'docs/stages/02_end_to_end_theory/README.md', 'docs/stages/03_gu_baseline/README.md',
        'experiments/README.md', 'experiments/exp_047_front_gate_sources/README.md')


def main(source, folder):
    summary = json.loads((folder/'summary.json').read_text())
    fingerprints = {**summary['source_sha256'], **summary['source_evidence_sha256']}
    for name, expected in fingerprints.items():
        assert digest(ROOT/name) == expected, name
    for name, expected in summary['output_sha256'].items():
        assert digest(folder/name) == expected, name
    digital = json.loads((folder/'digital_gate_sources.json').read_text())
    offline = json.loads((folder/'offline_target_bias.json').read_text())
    coefficients = tuple(tuple(map(F, k)) for k in digital['coefficients'])
    lines = tuple(json.loads(line) for line in (source/CASE/'analog_digital_records.jsonl').read_text().splitlines())
    samples = tuple(Sample(**line['sample']) for line in lines)
    checks = 0
    for label, (start, end) in PARTITIONS.items():
        observations = samples[start:end]
        counts = histogram(observations)
        means = tuple(weighted_cascade_mean(counts, k) for k in coefficients)
        lookups = tuple(dict(zip((s for s, _ in counts), m.base.rows)) for m in means)
        target_counts = histogram(tuple((sample, F(line['ideal_code_offline_only']-2048-512*sample.stage1_symbol))
                                        for sample, line in zip(observations, lines[start:end])))
        for index, (mean, lookup) in enumerate(zip(means, lookups)):
            archived = digital['partitions'][label]['branches'][index]
            assert tuple(F(g['correlation']) for g in archived['gates']) == mean.mean_products[4:]
            assert tuple(tuple(map(F, row)) for row in archived['fixed_mask_low_matrix']) == tuple(
                tuple(mean.jacobian[4+i][4+j] for j in range(2)) for i in range(2))
            for i in range(4):
                for supported in (False, True):
                    rows = tuple((lookup[s], count) for s, count in counts
                                 if lookup[s].gates1[i] and (lookup[s].basis1[i] != 0) == supported)
                    group = archived['gates'][i]['groups'][int(supported)]
                    assert group['count'] == sum(count for _, count in rows)
                    assert F(group['correlation']) == sum((count*r.dither1*r.local1 for r, count in rows), F(0))/len(observations)
                    assert F(group['self_sensitivity']) == sum((count*r.dither1*r.basis1[i] for r, count in rows), F(0))/len(observations)
            terms = offline['partition_target_terms'][label][index]
            for i in range(4):
                signal = sum((count*lookup[s].dither1*t for (s, t), count in target_counts
                              if lookup[s].gates1[i]), F(0))/len(observations)
                error = sum((count*lookup[s].dither1*(lookup[s].local1-t) for (s, t), count in target_counts
                             if lookup[s].gates1[i]), F(0))/len(observations)
                assert F(terms['gates'][i]['gated_target_correlation']) == signal
                assert F(terms['gates'][i]['continuous_error_correlation']) == error
                assert signal+error == mean.mean_products[4+i]
            mse = sum((count*(lookup[s].local1-t)**2 for (s, t), count in target_counts), F(0))/len(observations)
            assert F(terms['continuous_mse']) == mse
            support_correlation = sum((count*lookup[s].dither1*lookup[s].local1 for s, count in counts
                                       if lookup[s].basis1[1] != 0), F(0))/len(observations)
            assert support_correlation == F(digital['partitions'][label]['common_raw_support_correlations'][index])
            if label == 'fit':
                assert mse == F(offline['fit_branch_bias'][index]['continuous_mse'])
            checks += 1
        cross = tuple(tuple(sum((count*lookups[value][s].dither1*lookups[value][s].local1
                                 for s, count in counts if lookups[mask][s].gates1[1]), F(0))/len(observations)
                            for value in range(2)) for mask in range(2))
        assert cross == tuple(tuple(map(F, row)) for row in digital['partitions'][label]['mask_comparison']['cross_mask_correlations'])
    fit_samples = samples[:11520]
    projection = offline['fit_only_projection']
    reference = (*coefficients[0][:4], *tuple(map(F, projection['coefficients'])))
    ref_mean = weighted_cascade_mean(histogram(fit_samples), reference)
    ref_lookup = dict(zip((s for s, count in histogram(fit_samples)), ref_mean.base.rows))
    normal = [F(0), F(0)]
    ref_mse = F(0)
    for sample, line in zip(fit_samples, lines[:11520]):
        row = ref_lookup[sample]
        target = line['ideal_code_offline_only']-2048-512*sample.stage1_symbol
        error = row.local1-target
        ref_mse += error**2/len(fit_samples)
        for i in range(2):
            normal[i] += row.basis1[i]*error/len(fit_samples)
    assert normal == [F(0), F(0)]
    assert ref_mse == F(projection['minimum_continuous_mse'])
    assert all(b['fixed_mask_low_determinant'] != '0' for b in digital['partitions']['fit']['branches'])
    assert digital['partitions']['fit']['mask_comparison']['membership_counts'] == {
        'neither': 747, 'left_only': 0, 'right_only': 5552, 'both': 5221}
    assert summary['fit_second_gate_counts'] == [5221, 10773]
    assert summary['fit_second_gate_zero_basis_counts'] == [1423, 6085]
    assert not digital['targets_used'] and not offline['projection_fitted_to_sine']
    assert not summary['online_algorithm_changed'] and not summary['new_training']
    missing = []
    links = 0
    for name in DOCS:
        path = ROOT/name
        for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
            if '://' in target or target.startswith('#'):
                continue
            clean = unquote(target.split('#', 1)[0]).strip('<>')
            if not (path.parent/clean).resolve().exists():
                missing.append((name, target))
            links += 1
    assert not missing, missing
    sys.path.insert(0, str(ROOT/'tests'))
    regression = unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.discover(str(ROOT/'tests')))
    if not regression.wasSuccessful():
        raise SystemExit(1)
    for name, expected in fingerprints.items():
        assert digest(ROOT/name) == expected, name
    verification = {'source_and_output_sha256_checks_passed': True,
        'independent_original_mean_map_branch_partition_checks': checks,
        'independent_original_mean_map_conversion_assignments': 38400,
        'independent_offline_projection_normal_equations_passed': True,
        'independent_offline_projection_mse_passed': True,
        'regression': {'tests_run': regression.testsRun, 'failures': len(regression.failures), 'errors': len(regression.errors)},
        'checked_local_document_links': links, 'missing_local_links': missing,
        'extra_source_sha256': {name: digest(ROOT/name) for name in
                               ('experiments/exp_047_front_gate_sources/finalize.py',
                                'experiments/exp_047_front_gate_sources/plot_results.py')},
        'document_sha256': {name: digest(ROOT/name) for name in DOCS},
        'figure_sha256': {name: digest(folder/name) for name in ('front_gate_sources.png', 'front_gate_sources.svg')},
        'figure_visually_inspected': True, 'new_training': False, 'cadence_used': False,
        'online_algorithm_changed': False, 'new_algorithm_compared': False, 'long_term_convergence_proved': False}
    write(folder/'verification.json', verification)
    print(json.dumps({'independent_branch_partition_checks': checks, 'tests': regression.testsRun,
                      'local_document_links': links, 'source_fingerprints_unchanged': True}, indent=2), flush=True)


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
