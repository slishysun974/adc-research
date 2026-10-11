"""Read-only EXP-069 temporal diagnostics; never runs a learner or FFT."""

import argparse
from collections import Counter
from fractions import Fraction as F
from hashlib import sha256
import json
import math
from pathlib import Path
import re
import shutil
import traceback

import numpy as np

from adc_research.theory.temporal_state_moments import partition_moments

ROOT = Path(__file__).resolve().parents[2]
NEW = ROOT/'artifacts/runs/EXP_069/background_v1'
OLD = ROOT/'artifacts/runs/EXP_062/background_v1'
DOCS = ['docs/README.md', 'docs/STATUS.md', 'docs/DECISIONS.md',
        'docs/RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md',
        'docs/reports/GU_ALGORITHM_EVALUATION_V1.md',
        'docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
        'docs/reports/experiments/EXP_069_GU_LEARNING_RATE_V1.md',
        'docs/theory/README.md', 'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md',
        'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
        'docs/theory/MILLION_SAMPLE_SCALAR_MEAN_NOISE_AND_QUANTIZATION_V1.md',
        'experiments/exp_069_gu_learning_rate/README.md']


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def digest(path):
    h = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4*1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def unchanged(manifest):
    for name, expected in manifest.items():
        assert digest(ROOT/name) == expected, name


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=False)
    p = read(NEW/'protocol.json')
    protocol = {
        'version': 'EXP069-read-only-finite-stability-v1', 'date': '2026-10-11',
        'authority': 'D-116 / plan13.5 / user continues Gu learning-rate research',
        'question': 'Which unchanged criterion components cause later violations, and how do finite group means and state variance differ?',
        'paths': 120, 'cases': p['cases'], 'seeds': p['seeds'],
        'rates': ['quarter', 'half', 'base', 'double'], 'methods': ['point30', 'full120'],
        'criterion': p['empirical_convergence'],
        'state_order': 'front k1..k4 then rear k1..k4',
        'state_selection': 'all65536 window-start states; exclude final65537th from moments; include it only in boundary differences',
        'group_windows': 2048, 'group_count': 32, 'tail_first_group': 16,
        'tail_partition': '16 equal2048-window groups / original128..255 blocks',
        'comparisons': 'all intervals, later than original first pass, terminal interval; every seed/rate/model retained',
        'triggers': 'SNDR only / coefficient only / both; active iff any selected joint support in the three groups; exact rational coefficient threshold1/200',
        'support_diagnostic': 'failure coordinate absent/present in first-passing active set; full/all joint and update totals retained, no Gram rank claim',
        'moments': 'exact integer sums/squares ANOVA for hidden Q22 and effective Q1.10; total=within+between; no iid CI or stationary root estimate',
        'scalar_theory': 'iid affine multiplier with deterministic additive term; transient covariance r^lag V_i; stationary averaging only under second-order stationary initialization',
        'predictions': ['independent criterion exactly reproduces all3600 original decisions/ranges/support masks',
                        'positive temporal memory inflates average variance above iid formula under stated scalar conditions',
                        'finite partition identity exact for every coordinate, zero support need not be coefficient freeze'],
        'acceptance': 'zero integer/rational identity and original criterion mismatches; saved floating SNDR differences<1e-10 and distance from threshold>1e-9; preserve failures',
        'new_adc_conversions': 0, 'new_learning_observations': 0, 'new_outputs': 0,
        'new_fft': 0, 'new_rates_seeds_inputs_horizon': 0,
        'limits': 'diagnostic cause of finite criterion failure is not unique causal attribution of output MSE; no general eight-state convergence, future failure rate, physical holdout or chip statement',
    }
    write(folder/'protocol.json', protocol)
    backup = folder/'documents_before'; backup.mkdir()
    for name in DOCS:
        dest = backup/name; dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, dest)
    frozen = {str(Path(item['Path']).relative_to(ROOT)).replace('\\', '/'): item['Hash'].lower()
              for item in read(NEW/'source_hashes.json')}
    unchanged(frozen)
    write(folder/'original_source_hashes.json', frozen)
    source_names = [str(Path(__file__).relative_to(ROOT)).replace('\\', '/'),
                    'src/adc_research/theory/temporal_state_moments.py',
                    'tests/test_temporal_state_moments.py']
    write(folder/'source_hashes.json', {name: digest(ROOT/name) for name in source_names})
    data = {}
    for directory, rates in ((NEW, ['quarter', 'half', 'double']), (OLD, ['base'])):
        manifest = read(directory/'delivery_hashes.json')
        names = ['delivery_hashes.json']
        if directory == NEW:
            names += ['analysis.json', 'protocol.json', 'summary.json', 'terminal_criterion.json', 'verification.json']
        for case in p['cases']:
            for seed in p['seeds']:
                stem = f'{case}_{seed}'
                names.append(stem+'.json')
                for rate in rates:
                    for method in ('point30', 'full120'):
                        names.append(stem+'_'+('' if rate == 'base' else rate+'_')+method+'_q22.bin')
        for name in names:
            path = directory/name; actual = digest(path)
            if name != 'delivery_hashes.json':
                assert actual == manifest[name], name
            data[str(path.relative_to(ROOT)).replace('\\', '/')] = actual
    write(folder/'data_hashes.json', data)
    write(folder/'environment.json', {'numpy': np.__version__})
    print(json.dumps({'prepared': True, 'original_sources': len(frozen), 'used_data': len(data)}), flush=True)


def export_integer(q):
    quotient, remainder = np.divmod(q, 4096)
    return quotient + ((remainder > 2048) | ((remainder == 2048) & ((quotient & 1) != 0)))


def finite_moments(values, unit, saved):
    # The domain check guarantees square accumulation fits int64 here.
    assert values.shape == (32768, 8) and np.max(np.abs(values)) <= 8384512
    groups = values.reshape(16, 2048, 8)
    sums = groups.sum(axis=1, dtype=np.int64)
    squares = (groups*groups).sum(axis=1, dtype=np.int64)
    rows = []
    for j in range(8):
        out = partition_moments(sums[:, j], squares[:, j], [2048]*16)
        assert out['variance'] == out['within_variance']+out['between_variance']
        assert abs(float(out['mean']/unit)-saved['mean'][j]) < 1e-12
        assert abs(math.sqrt(float(out['variance']))/unit-saved['standard_deviation'][j]) < 1e-11
        assert abs(float(max(out['group_means'])-min(out['group_means']))/unit-saved['block_mean_range'][j]) < 1e-12
        rows.append({key: float(out[key]/(unit if key == 'mean' else unit*unit))
                     for key in ('mean', 'variance', 'within_variance', 'between_variance')} | {
            'between_fraction': float(out['between_variance']/out['variance']) if out['variance'] else None,
            'half_mean_difference': float(F(int(sums[8:, j].sum())-int(sums[:8, j].sum()), 16384*unit)),
            'group_mean_range': float((max(out['group_means'])-min(out['group_means']))/unit),
        })
    return rows


def run(folder):
    assert not (folder/'analysis.json').exists()
    for name in ('original_source_hashes.json', 'source_hashes.json', 'data_hashes.json'):
        unchanged(read(folder/name))
    p = read(folder/'protocol.json'); original = read(NEW/'analysis.json')
    pp = read(NEW/'protocol.json'); c = p['criterion']; rows = []; near = math.inf
    decision_checks = group_mean_checks = variance_checks = 0
    for old in original['paths']:
        case, seed, rate, method = (old[key] for key in ('case', 'seed', 'rate', 'method'))
        stem = f'{case}_{seed}'; directory = OLD if rate == 'base' else NEW
        meta = read(directory/(stem+'.json'))
        if rate == 'base':
            name = method; h = p['methods'].index(method)
            states = np.fromfile(directory/(stem+'_'+name+'_q22.bin'), dtype='<f8').reshape(65537, 8)
            q = np.rint(states*2**22).astype(np.int64)
            assert np.array_equal(q/2**22, states)
        else:
            name = rate+'_'+method; h = meta['Paths'].index(name)
            q = np.fromfile(directory/(stem+'_'+name+'_q22.bin'), dtype='<i4').astype(np.int64).reshape(65537, 8)
        effective = export_integer(q[:-1])
        sums = effective.reshape(32, 2048, 8).sum(axis=1, dtype=np.int64)
        joint_blocks = np.asarray([b['Selected'][h]['Both'] for b in meta['Blocks']], dtype=np.int64)
        joint = joint_blocks.reshape(32, 8, 8).sum(axis=1)
        scores = old['block_scores']
        sm = [math.fsum(s['sndr_db'] for s in scores[g*8:(g+1)*8])/8 for g in range(32)]
        assert np.max(np.abs(np.asarray(sm)-old['convergence']['group_sndr_means_db'])) < 1e-10
        assert np.array_equal(sums/(2048*1024), old['convergence']['group_effective_state_means'])
        group_mean_checks += 32*8
        first = old['convergence']['first_satisfying_block_exclusive']; first_active = None
        if first is not None:
            end = first//8; first_active = np.any(joint[end-3:end] > 0, axis=0)
        intervals = []
        for i, end in enumerate(range(3, 33)):
            active = np.any(joint[end-3:end] > 0, axis=0)
            span_sum = np.ptp(sums[end-3:end], axis=0)
            kr = span_sum/(2048*1024)
            coords = np.flatnonzero(active & (200*span_sum > 2048*1024)).tolist()
            sr = max(sm[end-3:end])-min(sm[end-3:end]); near = min(near, abs(sr-1))
            spectrum_failed = sr > 1
            passed = not spectrum_failed and not coords
            prior = old['convergence']['intervals'][i]
            assert passed == prior['passed']
            assert np.array_equal(kr, prior['coefficient_mean_ranges'])
            assert np.array_equal(np.flatnonzero(~active), prior['unsupported_coordinates'])
            assert abs(sr-prior['sndr_range_db']) < 1e-10
            kind = ('both' if spectrum_failed and coords else 'sndr_only' if spectrum_failed
                    else 'coefficient_only' if coords else 'passed')
            intervals.append({'end_block_exclusive': end*8, 'passed': passed, 'trigger': kind,
                              'sndr_range_db': sr, 'coefficient_ranges': kr.tolist(),
                              'failing_coordinates': coords, 'active_coordinates': np.flatnonzero(active).tolist(),
                              'new_failing_coordinates_since_first_pass': [] if first_active is None else [j for j in coords if not first_active[j]]})
            decision_checks += 1
        assert sum(not x['passed'] for x in intervals if first is not None and x['end_block_exclusive'] > first) == old['convergence']['later_failing_intervals']
        hm = finite_moments(q[32768:-1], 2**22, old['tail_hidden_state'])
        em = finite_moments(effective[32768:], 1024, old['tail_effective_state'])
        variance_checks += 16
        mean_gap = [em[j]['mean']-hm[j]['mean'] for j in range(8)]
        assert max(map(abs, mean_gap)) <= 1/2048
        totals = {field: np.sum([b['Selected'][h][field] for b in meta['Blocks']], axis=0).tolist()
                  for field in meta['Blocks'][0]['Selected'][h]}
        assert totals['Both'] == old['selected_joint_total']
        assert np.sum([b['All'][h]['Both'] for b in meta['Blocks']], axis=0).tolist() == old['all_joint_total']
        rows.append({key: old[key] for key in ('case', 'seed', 'rate', 'method', 'step_ratio')} | {
            'first_pass_end_block': first, 'intervals': intervals, 'tail_hidden': hm, 'tail_effective': em,
            'tail_export_mean_gap': mean_gap, 'selected_totals': totals,
            'all_joint_total': old['all_joint_total'], 'counters': old['counters'],
            'tail_net_hidden_increment_per_window': ((q[-1]-q[32768])/(32768*2**22)).tolist(),
        })
        print('checked', case, seed, rate, method, flush=True)
    groups = []
    for case in p['cases']:
        for method in p['methods']:
            for rate in p['rates']:
                rr = [r for r in rows if (r['case'], r['method'], r['rate']) == (case, method, rate)]
                all_intervals = [x for r in rr for x in r['intervals']]
                later = [x for r in rr for x in r['intervals'] if r['first_pass_end_block'] is not None and x['end_block_exclusive'] > r['first_pass_end_block'] and not x['passed']]
                terminal = [r['intervals'][-1] for r in rr]
                def coordinate_counts(xx):
                    return [sum(j in x['failing_coordinates'] for x in xx) for j in range(8)]
                groups.append({'case': case, 'method': method, 'rate': rate,
                    'first_pass_paths': sum(r['first_pass_end_block'] is not None for r in rr),
                    'all_trigger_counts': dict(Counter(x['trigger'] for x in all_intervals)),
                    'later_trigger_counts': dict(Counter(x['trigger'] for x in later)),
                    'terminal_trigger_counts': dict(Counter(x['trigger'] for x in terminal)),
                    'later_coordinate_failures': coordinate_counts(later),
                    'terminal_coordinate_failures': coordinate_counts(terminal),
                    'later_intervals_with_new_failing_coordinate': sum(bool(x['new_failing_coordinates_since_first_pass']) for x in later),
                    'tail_effective_mean': np.mean([[m['mean'] for m in r['tail_effective']] for r in rr], axis=0).tolist(),
                    'tail_effective_variance': np.mean([[m['variance'] for m in r['tail_effective']] for r in rr], axis=0).tolist(),
                    'tail_between_fraction_mean': [float(np.mean([r['tail_effective'][j]['between_fraction'] for r in rr if r['tail_effective'][j]['between_fraction'] is not None])) if any(r['tail_effective'][j]['between_fraction'] is not None for r in rr) else None for j in range(8)],
                })
    later = [x for r in rows for x in r['intervals'] if r['first_pass_end_block'] is not None and x['end_block_exclusive'] > r['first_pass_end_block'] and not x['passed']]
    assert len(rows) == 120 and decision_checks == 3600 and len(later) == 318 and near > 1e-9
    result = {'paths': rows, 'groups': groups,
              'later_trigger_counts': dict(Counter(x['trigger'] for x in later)),
              'terminal_trigger_counts': dict(Counter(r['intervals'][-1]['trigger'] for r in rows)),
              'later_coordinate_failures': [sum(j in x['failing_coordinates'] for x in later) for j in range(8)],
              'later_intervals_with_new_failing_coordinate': sum(bool(x['new_failing_coordinates_since_first_pass']) for x in later)}
    write(folder/'analysis.json', result)
    for name in ('original_source_hashes.json', 'source_hashes.json', 'data_hashes.json'):
        unchanged(read(folder/name))
    write(folder/'validation.json', {'passed': True, 'paths': len(rows), 'criterion_intervals': decision_checks,
        'group_effective_mean_components': group_mean_checks, 'exact_partition_identities': variance_checks,
        'original_saved_state_moments_reproduced': True, 'sndr_threshold_minimum_distance_db': near,
        'original_sources': len(read(folder/'original_source_hashes.json')), 'used_data': len(read(folder/'data_hashes.json')),
        'sources_and_used_data_unchanged': True, 'new_conversions_learning_outputs_fft': 0,
        'eight_state_stationarity_proved': False, 'output_loss_causal_decomposition': False})
    print(json.dumps({key: result[key] for key in ('later_trigger_counts', 'terminal_trigger_counts', 'later_coordinate_failures', 'later_intervals_with_new_failing_coordinate')}), flush=True)


def deliver(folder):
    assert read(folder/'validation.json')['passed']
    for name in ('original_source_hashes.json', 'source_hashes.json', 'data_hashes.json'):
        unchanged(read(folder/name))
    missing = []
    for name in DOCS:
        source = ROOT/name
        for link in re.findall(r'\]\(([^)]+)\)', source.read_text(encoding='utf-8')):
            if '://' in link or link.startswith('#'):
                continue
            target = link.split('#')[0]
            if target and not (source.parent/target).exists():
                missing.append([name, link])
    assert not missing, missing
    logs = {}
    for name in ('controls.log', 'run.log', 'regression.log'):
        log = folder/name
        assert log.exists()
        logs[name] = digest(log)
    assert (folder/'controls.log').read_text(encoding='utf-8').rstrip().endswith('OK')
    assert (folder/'regression.log').read_text(encoding='utf-8').rstrip().endswith('OK')
    write(folder/'delivery_validation.json', {'passed': True, 'missing_links': missing,
        'documents': {name: digest(ROOT/name) for name in DOCS}, 'logs': logs,
        'original_sources_and_used_data_unchanged': True,
        'new_experiment': False, 'no_learning_or_fft': True})
    print(json.dumps({'delivery_passed': True, 'documents': len(DOCS)}), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--folder', type=Path, required=True)
    parser.add_argument('action', choices=('prepare', 'run', 'deliver')); args = parser.parse_args()
    try:
        {'prepare': prepare, 'run': run, 'deliver': deliver}[args.action](args.folder.resolve())
    except Exception:
        if args.folder.exists():
            write(args.folder/(args.action+'_failure.json'), {'traceback': traceback.format_exc()})
        raise
