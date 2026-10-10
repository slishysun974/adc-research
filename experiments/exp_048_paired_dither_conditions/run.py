"""Existing-record pairing audit and exact conditional pair counterexamples."""

from collections import Counter, defaultdict
from fractions import Fraction as F
import json
from pathlib import Path
import sys

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.fixed_pwl import correct_fixed
from adc_research.evaluation.paired_target_diagnostics import decompose_pair_targets
from adc_research.theory.paired_dither_conditions import (
    PairedDitherObservation as Pair, analyze_pair_equations, pair_constraint_components,
)
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_042_correlation_roots.run import digest, write
from experiments.exp_047_front_gate_sources.run import digital_raw
from experiments.exp_048_paired_dither_conditions.examples import periodic_counterexample

ROOT = Path(__file__).resolve().parents[2]
PARTITIONS = {'fit': (0, 11520), 'training_suffix': (11520, 15360), 'online_sine': (15360, 19200)}


def recorded_key(row):
    """Offline source-model key; input and tracking starts are not online buses."""
    s = row['sample']
    return (F(str(row['input_normalized'])), tuple(F(str(v)) for v in row['tracking_starts']),
            s['stage1_symbol'], s['stage2_dither_symbol'])


def source_audit(lines):
    results = {}
    for label, (a, b) in PARTITIONS.items():
        exact, digital, oracle = defaultdict(lambda: {1: [], -1: []}), defaultdict(Counter), defaultdict(Counter)
        for row in lines[a:b]:
            sample = row['sample']
            sign = sample['stage1_dither_symbol']
            exact[recorded_key(row)][sign].append(row)
            key = (sample['stage1_symbol'], sample['stage2_symbol'], sample['backend_centered_code'], sample['stage2_dither_symbol'])
            digital[key][sign] += 1
            oracle[(row['ideal_code_offline_only'], sample['stage1_symbol'], sample['stage2_dither_symbol'])][sign] += 1
        pairs = tuple((plus, minus) for group in exact.values() for plus, minus in zip(group[1], group[-1]))
        for plus, minus in pairs:
            assert recorded_key(plus) == recorded_key(minus)
            assert plus['ideal_code_offline_only'] == minus['ideal_code_offline_only']
        results[label] = {'rows': b-a, 'same_recorded_input_tracking_start_pairs': len(pairs),
                         'same_other_four_digital_fields_candidates': sum(min(c[1], c[-1]) for c in digital.values()),
                         'same_ideal_code_coarse_candidates': sum(min(c[1], c[-1]) for c in oracle.values()),
                         'matched_conversion_ids': [(p['conversion_id'], m['conversion_id']) for p, m in pairs],
                         'metadata_scope': 'equal recorded input and three effective tracking starts in the declared synthetic source model',
                         'chip_pair_contract_verified': False}
    return results


def score_example(pairs, targets):
    # Ideal centers are read only after digital contrast solve.
    outputs = tuple((p.raw_plus-p.dither_magnitude, p.raw_minus+p.dither_magnitude)
                    for p in pairs)
    errors = tuple((a-t, b-t) for (a, b), t in zip(outputs, targets))
    cfg = _config().cascade.stage1_pwl
    quantized = []
    for pair, target in zip(pairs, targets):
        raws = tuple(round_fraction(8*r.numerator, r.denominator, 'nearest_even')
                     for r in (pair.raw_plus, pair.raw_minus))
        plus = F(correct_fixed(raws[0], cfg).corrected_code_scaled, 8)-pair.dither_magnitude
        minus = F(correct_fixed(raws[1], cfg).corrected_code_scaled, 8)+pair.dither_magnitude
        assert plus == minus
        quantized.append(plus-target)
    mse = sum((a*a+b*b for a, b in errors), F(0))/(2*len(pairs))
    return {'continuous_output_errors': errors, 'continuous_output_mse': mse,
            'maximum_continuous_output_error': max(abs(e) for row in errors for e in row),
            'q3_output_errors': tuple(quantized),
            'q3_output_mse': sum((e*e for e in quantized), F(0))/len(pairs),
            'q3_pair_contrasts_all_zero': True, 'ideal_target_used_in_contrast_fit': False,
            'full_adc_spectrum_computed': False}


def run(source, previous, output):
    evidence = {}
    prior = json.loads((previous/'summary.json').read_text())
    for name, expected in {**prior['source_sha256'], **prior['source_evidence_sha256']}.items():
        assert digest(ROOT/name) == expected, name
        evidence[ROOT/name] = expected
    for name in ('summary.json', 'verification.json', 'digital_gate_sources.json', 'offline_target_bias.json'):
        evidence[previous/name] = digest(previous/name)
    source_summary = json.loads((source/'summary.json').read_text())
    evidence[source/'summary.json'] = digest(source/'summary.json')
    audits = {}
    source_lines = {}
    for case in source_summary['cases']:
        path = source/case['name']/'analog_digital_records.jsonl'
        expected = case['physical']['raw_record_sha256']
        assert digest(path) == expected
        evidence[path] = expected
        lines = tuple(json.loads(line) for line in path.read_text().splitlines())
        assert len(lines) == 19200
        source_lines[case['name']] = lines
        audits[case['name']] = source_audit(lines)
    assert all(a['fit']['same_recorded_input_tracking_start_pairs'] == 0 for a in audits.values())
    coefficients = tuple(tuple(map(F, k)) for k in json.loads((previous/'digital_gate_sources.json').read_text())['coefficients'])
    periodic_rows = source_lines['periodic255_reset']
    ids = audits['periodic255_reset']['online_sine']['matched_conversion_ids']
    actual_pairs = tuple(Pair(digital_raw(Sample(**periodic_rows[a]['sample']), coefficients[0][:4]),
                              digital_raw(Sample(**periodic_rows[b]['sample']), coefficients[0][:4]), F(64))
                         for a, b in ids)
    existing_pair_diagnostics = tuple(analyze_pair_equations(actual_pairs, k[4:]) for k in coefficients)

    # Synthetic examples predeclare centers and transfers; the digital solver sees only pairs.
    centers = tuple(F(13*i) for i in range(-33, 34))
    counter_pairs, counter_targets = periodic_counterexample(centers)
    counter_fit = analyze_pair_equations(counter_pairs)
    assert counter_fit['basis_difference_rank'] == 4
    assert counter_fit['contrast_least_squares_coefficients'] == (F(1),)*4
    assert counter_fit['contrast_mse'] == 0
    counter_score = score_example(counter_pairs, counter_targets)
    assert counter_score['continuous_output_mse'] > 0 and counter_score['q3_output_mse'] > 0
    two_pairs, two_targets = periodic_counterexample(centers, (F(64), F(80)), F(16), F(2))
    two_fit = analyze_pair_equations(two_pairs)
    assert two_fit['contrast_mse'] == 0 and two_fit['basis_difference_rank'] == 4
    two_score = score_example(two_pairs, two_targets)
    inner = tuple(Pair(t+64, t-64, F(64)) for t in map(F, range(-48, 49, 16)))
    inner_fit = analyze_pair_equations(inner)
    assert inner_fit['basis_difference_rank'] == 1
    leakage = {'matched_common_gate': decompose_pair_targets(F(100), F(100), F(104), F(102), F(64)),
               'different_gates': decompose_pair_targets(F(100), F(100), F(100), F(100), F(64), True, False),
               'different_targets': decompose_pair_targets(F(101), F(99), F(101), F(99), F(64))}
    graphs = [dict(label=label, **pair_constraint_components(range(lo, hi+1), steps))
              for label, lo, hi, steps in (('D64_wide', -256, 256, (128,)),
                    ('D64_D80_wide', -256, 256, (128, 160)),
                    ('D64_D65_wide', -256, 256, (128, 130)),
                    ('D64_D65_narrow', -64, 64, (128, 130)))]
    for path, expected in evidence.items():
        assert digest(path) == expected, str(path)
    output.mkdir(parents=True, exist_ok=False)
    write(output/'source_pair_audit.json', {'cases': audits, 'existing_periodic_sine_pair_ids': ids,
          'existing_periodic_sine_branch_diagnostics': existing_pair_diagnostics,
          'digital_observations_prove_controlled_pair': False, 'new_training': False})
    write(output/'pair_examples.json', {'leakage_examples': leakage, 'inner_support': inner_fit,
          'single_magnitude_counterexample': {'half_period': F(64), 'scale': F(8), 'centers': centers,
                 'pairs': counter_pairs, 'digital_fit': counter_fit, 'offline_score': counter_score,
                 'transfer_derivative_lower': F(3, 4), 'transfer_derivative_upper': F(9, 8),
                 'transfer_is_odd': True, 'transfer_zero_anchor': True, 'transfer_is_C1': True,
                 'physical_transfer_assumption': False},
          'two_magnitude_counterexample': {'half_period': F(16), 'scale': F(2),
                 'magnitudes': (F(64), F(80)), 'digital_fit': two_fit, 'offline_score': two_score},
          'finite_constraint_graphs': graphs, 'paired_contrast_is_correct_calibration_certificate': False})
    sources = ('src/adc_research/theory/paired_dither_conditions.py',
               'src/adc_research/evaluation/paired_target_diagnostics.py',
               'experiments/exp_048_paired_dither_conditions/run.py',
               'experiments/exp_048_paired_dither_conditions/examples.py',
               'tests/test_paired_dither_conditions.py', 'tests/test_paired_periodic_counterexample.py')
    write(output/'summary.json', {'scope': 'conditional paired cancellation, periodic error, digital excitation and source pairing availability',
          'source_evidence_sha256': {str(path.relative_to(ROOT)).replace('\\', '/'): expected for path, expected in evidence.items()},
          'source_sha256': {name: digest(ROOT/name) for name in sources},
          'output_sha256': {name: digest(output/name) for name in ('source_pair_audit.json', 'pair_examples.json')},
          'fit_controlled_pairs': 0, 'sine_recorded_model_pairs': sum(a['online_sine']['same_recorded_input_tracking_start_pairs'] for a in audits.values()),
          'single_magnitude_counter_pairs': len(counter_pairs), 'two_magnitude_counter_pairs': len(two_pairs),
          'new_training': False, 'new_adc_platform_conversions': 0, 'cadence_used': False,
          'online_algorithm_changed': False, 'rtl_changed': False, 'physical_transfer_identified': False,
          'source_package_unchanged': True, 'paired_dataset_is_chip_evidence': False})
    print(json.dumps({'fit_pairs_all_cases': 0, 'existing_sine_pairs': 5,
          'single_counter_rank': counter_fit['basis_difference_rank'],
          'single_counter_contrast_mse': float(counter_fit['contrast_mse']),
          'single_counter_output_mse': float(counter_score['continuous_output_mse']),
          'single_counter_q3_output_mse': float(counter_score['q3_output_mse']),
          'graph_components': [g['component_count'] for g in graphs]}, indent=2), flush=True)


if __name__ == '__main__':
    run(*(Path(p).resolve() for p in sys.argv[1:4]))
