"""Actual uninterrupted outputs, empirical stability and finite net benefit."""
import argparse
import json
from pathlib import Path
import traceback

import numpy as np

from experiments.exp_057_static_two_stage_million.common import metrics, write
from experiments.exp_061_static_auxiliary_million.verify import sources
from .verify import load, round_ratio


def tail_statistics(states, protocol):
    start = protocol['tail']['first_block']*(protocol['input']['samples_per_block']//120)
    tail = np.asarray(states[start:], dtype=float)
    mean = tail.mean(axis=0); centered = tail-mean
    blocks = np.array_split(tail, protocol['tail']['groups'])
    bm = np.array([b.mean(axis=0) for b in blocks])
    correlations = {}
    for lag in protocol['tail']['lags_windows']:
        numerator = np.sum(centered[:-lag]*centered[lag:], axis=0)
        denominator = np.sum(centered*centered, axis=0)
        correlations[str(lag)] = [float(n/d) if d > 0 else None for n, d in zip(numerator, denominator)]
    return {'state_count': len(tail), 'mean': mean.tolist(), 'standard_deviation': tail.std(axis=0).tolist(),
            'block_means': bm.tolist(), 'block_standard_deviations': [b.std(axis=0).tolist() for b in blocks],
            'block_mean_range': np.ptp(bm, axis=0).tolist(),
            'second_half_minus_first_half': (tail[len(tail)//2:].mean(axis=0)-tail[:len(tail)//2].mean(axis=0)).tolist(),
            'autocorrelation': correlations, 'confidence_interval_claimed': False}


def stability(scores, states, support, protocol):
    c = protocol['empirical_convergence']; size = c['group_blocks']
    groups = len(scores)//size; bw = protocol['input']['samples_per_block']//120
    means = []; sm = []; joint = []
    effective = round_ratio(np.rint(states[:-1]*(1 << 22)).astype(np.int64), 4096)/1024
    for g in range(groups):
        means.append(np.mean([s['sndr_db'] for s in scores[g*size:(g+1)*size]]))
        sm.append(effective[g*size*bw:(g+1)*size*bw].mean(axis=0))
        joint.append(np.sum(support[g*size:(g+1)*size], axis=0))
    means = np.array(means); sm = np.array(sm); joint = np.array(joint)
    checks = []; first = None
    for end in range(c['minimum_groups'], groups+1):
        start = end-c['minimum_groups']; active = np.any(joint[start:end] > 0, axis=0)
        sr = float(np.ptp(means[start:end])); kr = np.ptp(sm[start:end], axis=0)
        ok = sr <= c['sndr_group_mean_range_db'] and bool(np.all(kr[active] <= c['coefficient_group_mean_range']))
        if ok and first is None: first = end*size
        checks.append({'end_block_exclusive': end*size, 'passed': ok, 'sndr_range_db': sr,
                       'coefficient_mean_ranges': kr.tolist(), 'unsupported_coordinates': np.flatnonzero(~active).tolist()})
    return {'first_satisfying_block_exclusive': first, 'first_satisfying_conversion': None if first is None else first*protocol['input']['samples_per_block'],
            'budget_status': 'criterion reached' if first is not None else 'not reached within frozen budget',
            'later_failing_intervals': sum(not v['passed'] for v in checks if first is not None and v['end_block_exclusive'] > first),
            'passing_intervals': sum(v['passed'] for v in checks), 'intervals': checks,
            'group_sndr_means_db': means.tolist(), 'group_effective_state_means': sm.tolist(), 'stationarity_proved': False}


def net_terms(y, unit, x, tone_bin):
    target = 2048*(x+1); e = unit-target; d = y-unit
    increment = float(np.mean(d*d)); cross = float(2*np.mean(e*d)); actual = float(np.mean((y-target)**2)-np.mean(e*e))
    assert abs(actual-increment-cross) < 1e-9*max(1, abs(actual))
    a = np.fft.rfft(unit-np.mean(unit))/len(unit); b = np.fft.rfft(d-np.mean(d))/len(d)
    a[[0, tone_bin]] = 0; b[[0, tone_bin]] = 0
    weights = np.full(len(a), 2.0); weights[0] = weights[-1] = 1.0
    power = float(np.sum(weights*np.abs(b)**2)); spectral_cross = float(2*np.sum(weights*np.real(np.conj(a)*b)))
    residual_difference = float(np.sum(weights*(np.abs(a+b)**2-np.abs(a)**2)))
    assert abs(residual_difference-power-spectral_cross) < 1e-9*max(1, abs(residual_difference))
    return {'mse_difference': actual, 'change_mse': increment, 'unit_error_change_cross': cross,
            'residual_power_difference': residual_difference, 'change_residual_power': power, 'unit_change_residual_cross': spectral_cross}


def analyze(folder):
    p, _ = load(folder); assert json.loads((folder/'verification.json').read_text())['passed']
    n = p['input']['samples_per_block']; tone = np.fromfile(folder/'tone.bin', dtype='<f8')
    rows = []; summaries = []
    for case in p['cases']:
        for seed in p['seeds']:
            stem = f"{case['name']}_{seed}"; meta = json.loads((folder/(stem+'.json')).read_text(encoding='utf-8-sig'))
            count = meta['Conversions']; assert count == p['budget']['conversions_per_path']
            outputs = np.memmap(folder/(stem+'_outputs.bin'), dtype='<i2', mode='r', shape=(count, 3))
            unit_scores = [metrics(outputs[b*n:(b+1)*n, 0], tone, p['input']['tone_bin']) for b in range(p['budget']['blocks'])]
            for m, method in enumerate(p['methods']):
                state = np.memmap(folder/(stem+'_'+method['name']+'_q22.bin'), dtype='<f8', mode='r', shape=(meta['Windows']+1, 8))
                scores = []; supports = []
                for b in range(p['budget']['blocks']):
                    unit = np.asarray(outputs[b*n:(b+1)*n, 0], dtype=float); y = np.asarray(outputs[b*n:(b+1)*n, m+1], dtype=float)
                    score = metrics(y, tone, p['input']['tone_bin']); score['gain_sndr_db'] = score['sndr_db']-unit_scores[b]['sndr_db']
                    score['gain_sfdr_dbc'] = score['sfdr_dbc']-unit_scores[b]['sfdr_dbc']
                    score['net_identity'] = net_terms(y, unit, tone, p['input']['tone_bin']); scores.append(score)
                    supports.append(meta['Blocks'][b]['Selected'][m]['Both'])
                conv = stability(scores, state, supports, p)
                effective = round_ratio(np.rint(state*(1 << 22)).astype(np.int64), 4096)/1024
                tail = tail_statistics(effective[:-1], p)
                t = p['tail']['first_block']; gains = np.array([s['gain_sndr_db'] for s in scores[t:]])
                row = {'case': case['name'], 'method': method['name'], 'seed': seed,
                    'actual_conversions': count, 'actual_observations_per_stage': meta['Windows']*method['selected'],
                    'commits_per_bank': meta['Windows'], 'startup': scores[0], 'final_block': scores[-1],
                    'tail_mean_sndr_db': float(np.mean([s['sndr_db'] for s in scores[t:]])),
                    'tail_mean_unit_sndr_db': float(np.mean([s['sndr_db'] for s in unit_scores[t:]])),
                    'tail_mean_gain_db': float(gains.mean()), 'tail_min_gain_db': float(gains.min()), 'tail_max_gain_db': float(gains.max()),
                    'tail_positive_blocks': int(np.count_nonzero(gains > 0)), 'convergence': conv,
                    'tail_effective_state': tail, 'tail_effective_covariance': np.cov(effective[t*(n//120):-1].T, bias=True).tolist(),
                    'final_effective_state': effective[-1].tolist(), 'selected_joint_total': np.sum(supports, axis=0).tolist(),
                    'all_conversion_joint_total': np.sum([b['All'][m]['Both'] for b in meta['Blocks']], axis=0).tolist(),
                    'block_scores': scores, 'unit_block_scores': unit_scores}
                rows.append(row)
                print('analyzed', stem, method['name'], 'tail gain', row['tail_mean_gain_db'], flush=True)
    for case in p['cases']:
        for method in p['methods']:
            subset = [r for r in rows if r['case'] == case['name'] and r['method'] == method['name']]
            summaries.append({'case': case['name'], 'method': method['name'], 'seeds': len(subset),
                'tail_mean_sndr_db': float(np.mean([r['tail_mean_sndr_db'] for r in subset])),
                'tail_mean_unit_sndr_db': float(np.mean([r['tail_mean_unit_sndr_db'] for r in subset])),
                'tail_mean_gain_db': float(np.mean([r['tail_mean_gain_db'] for r in subset])),
                'positive_seed_means': sum(r['tail_mean_gain_db'] > 0 for r in subset),
                'criterion_reached_seeds': sum(r['convergence']['first_satisfying_conversion'] is not None for r in subset),
                'later_failing_intervals': [r['convergence']['later_failing_intervals'] for r in subset],
                'selected_joint_total': np.sum([r['selected_joint_total'] for r in subset], axis=0).tolist(),
                'tail_sndr_seed_means': [r['tail_mean_sndr_db'] for r in subset],
                'first_criterion_conversions': [r['convergence']['first_satisfying_conversion'] for r in subset]})
    sources(folder)
    write(folder/'analysis.json', {'paths': rows, 'finite_mse_and_spectrum_cross_identities_passed': True})
    write(folder/'summary.json', {'summary': summaries, 'actual_online_output_codes': sum(r['actual_conversions'] for r in rows),
        'same_conversion_different_learning_cost': True, 'stationarity_proved': False})
    plot(folder, rows, p)


def plot(folder, rows, p):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(3, 2, figsize=(11, 9), sharex=True)
    x = np.arange(1, p['budget']['blocks']+1)*p['input']['samples_per_block']/1e6
    for i, case in enumerate(p['cases']):
        for m, method in enumerate(p['methods']):
            ax = axes[i, m]; subset = [r for r in rows if r['case'] == case['name'] and r['method'] == method['name']]
            y = np.array([[s['sndr_db'] for s in r['block_scores']] for r in subset])
            base = np.mean([[s['sndr_db'] for s in r['unit_block_scores']] for r in subset], axis=0)
            for trace in y: ax.plot(x, trace, color='#2976a8', alpha=.22, linewidth=.7)
            ax.plot(x, y.mean(axis=0), color='#12517e', linewidth=1.6, label='Online mean (5 seeds)')
            ax.plot(x, base, color='#bd6a2f', linewidth=1.3, label='Unit, no updates')
            ax.axvspan(x[127], x[-1], color='#edf2f5', alpha=.6, zorder=-1)
            ax.set_title(case['name']+' / '+method['name']); ax.set_ylabel('Block SNDR (dB)'); ax.grid(alpha=.15)
    for ax in axes[-1]: ax.set_xlabel('Actual conversions (million)')
    axes[0, 0].legend(fontsize=8)
    fig.suptitle('Same sine from unit start: uninterrupted background output\nNominal thresholds; original Q3 / Q1.10 / Q22; equal conversion duration', fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, .94)); fig.savefig(folder/'background_sndr.png', dpi=170); plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('folder', type=Path); folder = parser.parse_args().folder.resolve()
    try: analyze(folder)
    except Exception:
        write(folder/'analysis_failure.json', {'traceback': traceback.format_exc()}); raise
