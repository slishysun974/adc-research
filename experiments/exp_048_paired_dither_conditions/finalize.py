"""Independent source counters, old mean/Q3 paths, graph BFS, tests and links."""
from collections import Counter, defaultdict
from fractions import Fraction as F
import json
from pathlib import Path
import re
import sys
import unittest
from urllib.parse import unquote

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.fixed_pwl import correct_fixed
from adc_research.theory.constrained_mean_root import weighted_cascade_mean
from adc_research.theory.gated_correlation_roots import stage_basis
from adc_research.theory.window_mean_map import exact_matrix_rank
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_042_correlation_roots.run import digest, histogram, write

ROOT = Path(__file__).resolve().parents[2]
PARTITIONS = {'fit': (0, 11520), 'training_suffix': (11520, 15360), 'online_sine': (15360, 19200)}
DOCS = ('docs/STATUS.md', 'docs/DECISIONS.md', 'docs/README.md', 'docs/theory/README.md',
        'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
        'docs/theory/PAIRED_DITHER_CANCELLATION_AND_PERIODIC_ERRORS_V1.md',
        'docs/reports/experiments/README.md', 'docs/reports/experiments/EXP_048_PAIRED_DITHER_CONDITIONS_V1.md',
        'docs/reports/RESEARCH_STATUS_PLAIN_2026-10-09.md',
        'docs/stages/02_end_to_end_theory/README.md', 'docs/stages/03_gu_baseline/README.md',
        'experiments/README.md', 'experiments/exp_048_paired_dither_conditions/README.md')


def independent_components(nodes, steps):
    unseen, components, edge_count = set(nodes), [], 0
    for node in nodes:
        edge_count += sum(node+s in unseen for s in steps)
    node_set = set(nodes)
    while unseen:
        queue, group = [min(unseen)], set()
        while queue:
            node = queue.pop()
            if node in group:
                continue
            group.add(node)
            unseen.discard(node)
            queue.extend(v for s in steps for v in (node+s, node-s) if v in node_set and v not in group)
        components.append(tuple(sorted(group)))
    return tuple(components), edge_count


def main(source, folder):
    summary = json.loads((folder/'summary.json').read_text())
    fingerprints = {**summary['source_sha256'], **summary['source_evidence_sha256']}
    for name, expected in fingerprints.items():
        assert digest(ROOT/name) == expected, name
    for name, expected in summary['output_sha256'].items():
        assert digest(folder/name) == expected, name
    audit = json.loads((folder/'source_pair_audit.json').read_text())
    source_lines = {}
    partition_checks = 0
    for case, partitions in audit['cases'].items():
        lines = tuple(json.loads(line) for line in (source/case/'analog_digital_records.jsonl').read_text().splitlines())
        source_lines[case] = lines
        for label, (a, b) in PARTITIONS.items():
            counts = defaultdict(Counter)
            digital, target = defaultdict(Counter), defaultdict(Counter)
            for line in lines[a:b]:
                sample = line['sample']
                sign = sample['stage1_dither_symbol']
                key = (line['input_normalized'], tuple(line['tracking_starts']), sample['stage1_symbol'], sample['stage2_dither_symbol'])
                counts[key][sign] += 1
                digital[(sample['stage1_symbol'], sample['stage2_symbol'], sample['backend_centered_code'], sample['stage2_dither_symbol'])][sign] += 1
                target[(line['ideal_code_offline_only'], sample['stage1_symbol'], sample['stage2_dither_symbol'])][sign] += 1
            archived = partitions[label]
            assert sum(min(c[1], c[-1]) for c in counts.values()) == archived['same_recorded_input_tracking_start_pairs']
            assert sum(min(c[1], c[-1]) for c in digital.values()) == archived['same_other_four_digital_fields_candidates']
            assert sum(min(c[1], c[-1]) for c in target.values()) == archived['same_ideal_code_coarse_candidates']
            for p, m in archived['matched_conversion_ids']:
                plus, minus = lines[p], lines[m]
                assert plus['input_normalized'] == minus['input_normalized']
                assert plus['tracking_starts'] == minus['tracking_starts']
                assert plus['sample']['stage2_dither_symbol'] == minus['sample']['stage2_dither_symbol']
                assert plus['sample']['stage1_symbol'] == minus['sample']['stage1_symbol']
                assert plus['sample']['stage1_dither_symbol'] == 1 and minus['sample']['stage1_dither_symbol'] == -1
                assert plus['ideal_code_offline_only'] == minus['ideal_code_offline_only']
            partition_checks += 1
    previous = json.loads((ROOT/'artifacts/runs/EXP_047/sources_v2/digital_gate_sources.json').read_text())
    coefficients = tuple(tuple(map(F, k)) for k in previous['coefficients'])
    pair_ids = audit['existing_periodic_sine_pair_ids']
    lines = source_lines['periodic255_reset']
    observations = tuple(Sample(**lines[n]['sample']) for pair in pair_ids for n in pair)
    for index, k in enumerate(coefficients):
        hist = histogram(observations)
        mean = weighted_cascade_mean(hist, k)
        lookup = dict(zip((s for s, count in hist), mean.base.rows))
        residuals = tuple(lookup[Sample(**lines[p]['sample'])].local1-lookup[Sample(**lines[m]['sample'])].local1 for p, m in pair_ids)
        archived = audit['existing_periodic_sine_branch_diagnostics'][index]
        assert residuals == tuple(map(F, archived['contrast_residuals']))
        assert F(archived['contrast_mse']) == sum((r*r for r in residuals), F(0))/len(residuals)
        assert F(archived['shared_gate_correlation']) == 32*sum(residuals, F(0))/len(residuals)
    examples = json.loads((folder/'pair_examples.json').read_text())
    counter_checks = 0
    pwl = _config().cascade.stage1_pwl
    for name in ('single_magnitude_counterexample', 'two_magnitude_counterexample'):
        counter = examples[name]
        fit, score = counter['digital_fit'], counter['offline_score']
        # Single counter stores exact endpoints; second reconstructs them independently.
        centers = tuple(F(13*i) for i in range(-33, 34))
        magnitudes = (F(64),) if name.startswith('single') else (F(64), F(80))
        L, scale = F(counter['half_period']), F(counter['scale'])
        targets, raws = [], []
        for center in centers:
            for d in magnitudes:
                endpoint_raws = []
                for value in (center+d, center-d):
                    # Equivalent remainder expression, independent of the example helper.
                    q = (value+L) % (2*L)-L
                    error = scale*q/L-scale*q**3/L**3
                    endpoint_raws.append(value+error)
                raws.append((*endpoint_raws, d))
                targets.append(center)
        if 'pairs' in counter:
            assert tuple((F(p['raw_plus']), F(p['raw_minus']), F(p['dither_magnitude'])) for p in counter['pairs']) == tuple(raws)
        features, errors, qerrors = [], [], []
        for (plus, minus, d), target in zip(raws, targets):
            assert plus-minus == 2*d
            a, b = stage_basis(plus, F(128)), stage_basis(minus, F(128))
            feature = tuple(x-y for x, y in zip(a, b))
            assert sum(feature) == 2*d
            features.append(feature)
            errors.append((plus-d-target, minus+d-target))
            raw_codes = tuple(round_fraction(8*r.numerator, r.denominator, 'nearest_even') for r in (plus, minus))
            yp = F(correct_fixed(raw_codes[0], pwl).corrected_code_scaled, 8)-d
            ym = F(correct_fixed(raw_codes[1], pwl).corrected_code_scaled, 8)+d
            assert yp == ym
            qerrors.append(yp-target)
            counter_checks += 1
        gram = tuple(tuple(sum((v[i]*v[j] for v in features), F(0))/len(features) for j in range(4)) for i in range(4))
        assert gram == tuple(tuple(map(F, row)) for row in fit['basis_difference_gram'])
        assert exact_matrix_rank(gram) == 4
        assert fit['contrast_least_squares_coefficients'] == ['1']*4
        assert tuple(errors) == tuple(tuple(map(F, row)) for row in score['continuous_output_errors'])
        assert tuple(qerrors) == tuple(map(F, score['q3_output_errors']))
        assert sum((x*x+y*y for x, y in errors), F(0))/(2*len(errors)) == F(score['continuous_output_mse']) > 0
    graph_supports = (range(-256, 257), range(-256, 257), range(-256, 257), range(-64, 65))
    for graph, nodes in zip(examples['finite_constraint_graphs'], graph_supports):
        components, edges = independent_components(nodes, graph['steps'])
        assert components == tuple(tuple(group) for group in graph['components'])
        assert edges == graph['edge_count']
        assert len(components) == graph['component_count']
        assert len(nodes)-len(components) == graph['edge_constraint_rank']
    links, missing = 0, []
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
    result = {'source_and_output_sha256_checks_passed': True,
        'independent_source_partition_checks': partition_checks,
        'existing_pair_original_mean_map_branch_checks': 2,
        'independent_counterexample_q3_pairs': counter_checks,
        'independent_bfs_graphs': len(graph_supports),
        'regression': {'tests_run': regression.testsRun, 'failures': len(regression.failures), 'errors': len(regression.errors)},
        'checked_local_document_links': links, 'missing_local_links': missing,
        'extra_source_sha256': {name: digest(ROOT/name) for name in
                               ('experiments/exp_048_paired_dither_conditions/finalize.py',
                                'experiments/exp_048_paired_dither_conditions/plot_results.py')},
        'document_sha256': {name: digest(ROOT/name) for name in DOCS},
        'figure_sha256': {name: digest(folder/name) for name in ('paired_dither_limits.png', 'paired_dither_limits.svg')},
        'figure_visually_inspected': True, 'new_training': False, 'new_adc_platform_conversions': 0,
        'cadence_used': False, 'online_algorithm_changed': False, 'physical_transfer_identified': False}
    write(folder/'verification.json', result)
    print(json.dumps({'source_partition_checks': partition_checks, 'counterexample_pairs': counter_checks,
                      'independent_graphs': 4, 'tests': regression.testsRun, 'document_links': links}, indent=2), flush=True)


if __name__ == '__main__':
    main(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
