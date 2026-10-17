"""D-126 read-only contract, output acceptance and checkpoint audit.

Extends EXP-069 analysis without changing its frozen protocol or learner.
The protocol is saved before score inspection. No ADC or learning runs.
"""
import argparse
from collections import defaultdict
from dataclasses import fields
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import shutil
import traceback
import zipfile

import numpy as np

from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.theory.finite_output_acceptance import (
    benefit, group_scores, intervals, recovery,
)
from adc_research.theory.joint_selection_output import four_grid_loss
from adc_research.theory.static_fixed_contract import export, nearest_even, readout
from experiments.exp_062_same_input_background.verify import digital

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT/'artifacts/runs/EXP_062/background_v1'
NEW = ROOT/'artifacts/runs/EXP_069/background_v1'
SWITCH = ROOT/'artifacts/runs/EXP_066/tracking_v1'
DOCS = ['docs/STATUS.md', 'docs/DECISIONS.md', 'docs/README.md',
        'docs/RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md',
        'docs/reports/GU_ALGORITHM_EVALUATION_V1.md',
        'docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
        'docs/theory/README.md', 'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md',
        'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
        'docs/theory/MILLION_SAMPLE_SCALAR_MEAN_NOISE_AND_QUANTIZATION_V1.md',
        'docs/theory/EXCITATION_AND_CONSTRAINED_STABILITY_V1.md',
        'experiments/exp_069_gu_learning_rate/README.md']


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def digest(path):
    h = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4*1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def relative(path):
    return path.relative_to(ROOT).as_posix()


def unchanged(manifest):
    for name, expected in manifest.items():
        assert digest(ROOT/name) == expected, name


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=False)
    protocol = {
        'version': 'Gu-baseline-closure-read-only-v2', 'date': '2026-10-11',
        'authority': 'D-126 tasks1/2/3/5; user continues research',
        'cases': ['ideal', 'both_linear', 'both_smooth'],
        'seeds': list(range(202610621, 202610626)),
        'rates': ['base', 'quarter'], 'methods': ['point30', 'full120'],
        'score_source': 'original saved scores, no FFT recomputation',
        'score_intervals': {'startup_blocks': [0, 24], 'tail_blocks': [128, 256],
                            'switch_startup_blocks': [0, 24], 'switch_tail_blocks': [64, 128]},
        'finite_output_contract': {
            'group_blocks': 8, 'consecutive_groups': 3,
            'mse_ratio_to_unit_maximum': '9/10',
            'residual_power_ratio_to_unit_maximum': '9/10',
            'mean_block_sndr_gain_minimum_db': 0,
            'recovery_relative_fresh_loss_gap_maximum': '1/10',
            'recovery_mean_block_sndr_gap_maximum_db': 1,
            'zero_reference': 'positive benefit not certified',
            'supported_coordinates': 'original criterion preserved; output never masked',
            'definition': 'MSE and powers pooled over equal-duration blocks before comparison; each of three groups must pass. Recovery needs independent benefit for BOTH carry and fresh and same future words, rate and method. First pass, all later violations and terminal suffix reported. Engineering margins, not confidence limits or online stopping.'},
        'checkpoint_blocks': [1, 8, 24, 64, 128, 256],
        'checkpoint_window': 'last120 conversions BEFORE each original block checkpoint; use its window-start Q22 state, not post-commit state',
        'four_grid': 'same words/target; base both, quarter front/base rear, base front/quarter rear, quarter both; no fitting/mean-state candidate',
        'targets': 'exact rational representation of stored binary64 tone, t=2048*(1+x); offline only',
        'checkpoint_windows': 180, 'words': 21600, 'four_grid_integer_readouts': 86400,
        'rational_readout_checks': 86400, 'direct_loss_identity_checks': 180,
        'contract_probes': 'boundary32768 initial states, carry/fresh word equality, sample fields, source fingerprints and declared resource endpoints',
        'new_adc_conversions': 0, 'new_learning_observations': 0,
        'new_online_outputs': 0, 'new_fft': 0,
        'predictions': ['both actual corner outputs equal stored window outputs exactly',
                        'joint MSE difference equals front+rear+all interaction terms exactly',
                        'relative output benefit, state criterion and recovery may disagree',
                        'startup old scores cannot determine quarter post-switch states'],
        'failure_rules': 'preserve failure; no parameter, horizon or checkpoint selection after scores; missing data not synthesized',
        'limits': 'seen static models/seeds, finite old-word intervention; no unique causal MSE attribution, future failure rate, physical holdout, new algorithm or RTL implementation',
    }
    write(folder/'protocol.json', protocol)
    backups = folder/'documents_before'
    for name in DOCS:
        dest = backups/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, dest)
    original = {relative(Path(item['Path'])): item['Hash'].lower()
                for item in load(NEW/'source_hashes.json')}
    # D-125 synchronized two RTL reading indexes. This changes no executable
    # source; retain exact old/new fingerprints instead of claiming all155 match.
    revised = {}
    for name, expected in list(original.items()):
        actual = digest(ROOT/name)
        if actual != expected:
            assert name in ('rtl/README.md', 'rtl/gu_baseline/README.md'), name
            revised[name] = {'original': expected, 'current': actual,
                             'reason': 'D-125 synchronized hardware reading index; non-executable'}
            del original[name]
    unchanged(original)
    write(folder/'original_source_hashes.json', original)
    write(folder/'revised_reading_index_hashes.json', revised)
    current_names = [relative(Path(__file__)),
                     'src/adc_research/theory/finite_output_acceptance.py',
                     'tests/test_finite_output_acceptance.py']
    write(folder/'source_hashes.json', {name: digest(ROOT/name) for name in current_names})
    package = ROOT/'docs/reports/circuit_review_2026-10-11/ADC_Circuit_Review_Package.zip'
    public = load(package.parent/'publication_validation.json')
    assert digest(package) == public['files'][package.name]['sha256']
    evidence = {relative(package): digest(package),
                **{name: entry['current'] for name, entry in revised.items()}}
    write(folder/'evidence_hashes.json', evidence)
    data = {}
    for source, names in (
        (OLD, ['protocol.json', 'analysis.json', 'delivery_validation.json', 'tone.bin']),
        (NEW, ['protocol.json', 'analysis.json', 'summary.json', 'delivery_validation.json']),
        (SWITCH, ['protocol.json', 'analysis.json', 'delivery_validation.json'])):
        manifest = load(source/'delivery_hashes.json')
        assert load(source/'delivery_validation.json')['passed']
        extra = []
        for case in protocol['cases']:
            for seed in protocol['seeds']:
                stem = f'{case}_{seed}'
                if source == OLD:
                    extra += [stem+'_words.bin', stem+'_outputs.bin',
                              stem+'_point30_q22.bin', stem+'_full120_q22.bin']
                elif source == NEW:
                    extra += [stem+'_outputs.bin', stem+'_quarter_point30_q22.bin',
                              stem+'_quarter_full120_q22.bin']
                else:
                    extra += [f'{case}_{v}_{seed}_words.bin' for v in ('carry', 'fresh')]
                    extra += [f'{case}_carry_{seed}_initial.json']
        for name in names+extra:
            actual = digest(source/name)
            assert actual == manifest[name], (source, name)
            data[relative(source/name)] = actual
    write(folder/'data_hashes.json', data)
    return protocol


def finite_rows(rows, units):
    result = []
    for row in rows:
        key = (row['case'], row['method'], row['seed'])
        unit_scores = units[key]
        g, u = group_scores(row['block_scores']), group_scores(unit_scores)
        flags = [bool(benefit(a, b)) for a, b in zip(g, u, strict=True)]
        item = {key: row[key] for key in ('case', 'method', 'seed')}
        for key in ('rate', 'variant'):
            if key in row:
                item[key] = row[key]
        item.update(intervals(flags))
        result.append(item)
    return result


def summarize_acceptance(rows, keys):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[key] for key in keys)].append(row)
    return [{**dict(zip(keys, key)), 'paths': len(group),
             'ever_passed': sum(r['first_pass_block'] is not None for r in group),
             'terminal_passed': sum(r['terminal_pass'] for r in group),
             'later_violations': sum(r['later_violations'] for r in group),
             'first_pass_blocks': [r['first_pass_block'] for r in group]}
            for key, group in groups.items()]


def run(folder, p):
    old_rows = load(OLD/'analysis.json')['paths']
    new_rows = [r for r in load(NEW/'analysis.json')['paths'] if r['rate'] in p['rates']]
    switch_rows = load(SWITCH/'analysis.json')['paths']
    old_index = {(r['case'], r['method'], r['seed']): r for r in old_rows}
    units = {key: row['unit_block_scores'] for key, row in old_index.items()}
    startup = finite_rows(new_rows, units)
    su = {(r['case'], r['method'], r['seed']): r['unit_block_scores'] for r in switch_rows}
    switching = finite_rows(switch_rows, su)
    pair_rows = []
    switch_index = {(r['case'], r['method'], r['seed'], r['variant']): r for r in switch_rows}
    for key in su:
        carry = switch_index[(*key, 'carry')]
        fresh = switch_index[(*key, 'fresh')]
        assert carry['unit_block_scores'] == fresh['unit_block_scores']
        groups = [group_scores(row['block_scores']) for row in (carry, fresh)]
        flags = [bool(recovery(c, f, u)) for c, f, u in
                 zip(*groups, group_scores(su[key]), strict=True)]
        pair_rows.append(dict(zip(('case', 'method', 'seed'), key)) | intervals(flags))
    write(folder/'finite_output.json', {'startup': startup, 'switch_base': switching,
                                        'base_recovery': pair_rows})

    # No new FFT: resummarize every saved block, preserving power and dB means.
    pairs = []
    for case in p['cases']:
        for method in p['methods']:
            for begin, end in p['score_intervals']['startup_blocks'], p['score_intervals']['tail_blocks']:
                rate_scores = {}
                for rate in p['rates']:
                    rr = [r for r in new_rows if r['case'] == case and r['method'] == method and r['rate'] == rate]
                    rate_scores[rate] = {key: float(np.mean([np.mean([s[key] for s in r['block_scores'][begin:end]]) for r in rr]))
                                         for key in ('mse_codes_squared', 'residual_power', 'sndr_db', 'sfdr_dbc', 'mean_error_codes')}
                pairs.append({'case': case, 'method': method, 'blocks': [begin, end], 'scores': rate_scores})

    tone = np.fromfile(OLD/'tone.bin', dtype='<f8')
    detail = []
    original_codes = rational_codes = raw_domains = boundary_states = equal_words = 0
    for case in p['cases']:
        for seed in p['seeds']:
            stem = f'{case}_{seed}'
            words = np.memmap(OLD/(stem+'_words.bin'), dtype='i1', mode='r', shape=(65536, 120, 4))
            outputs0 = np.memmap(OLD/(stem+'_outputs.bin'), dtype='<i2', mode='r', shape=(65536, 120, 3))
            outputs1 = np.memmap(NEW/(stem+'_outputs.bin'), dtype='<i2', mode='r', shape=(65536, 120, 6))
            carry_words = np.memmap(SWITCH/f'{case}_carry_{seed}_words.bin', dtype='i1', mode='r')
            fresh_words = np.memmap(SWITCH/f'{case}_fresh_{seed}_words.bin', dtype='i1', mode='r')
            assert np.array_equal(carry_words, fresh_words)
            equal_words += carry_words.size//4
            initial = load(SWITCH/f'{case}_carry_{seed}_initial.json')
            for mi, method in enumerate(p['methods']):
                base = np.memmap(OLD/(stem+'_'+method+'_q22.bin'), dtype='<f8', mode='r', shape=(65537, 8))
                quarter = np.memmap(NEW/(stem+'_quarter_'+method+'_q22.bin'), dtype='<i4', mode='r', shape=(65537, 8))
                a0 = np.rint(base[32768]*(1 << 22)).astype(np.int64)
                assert np.array_equal(a0, np.rint(np.asarray(initial[mi])*(1 << 22)).astype(np.int64))
                assert len(quarter[32768]) == 8
                boundary_states += 8
                for block in p['checkpoint_blocks']:
                    w = block*256-1
                    base_acc = np.rint(base[w]*(1 << 22)).astype(np.int64)
                    next_acc = np.asarray(quarter[w], dtype=np.int64)
                    state_rows = [base_acc, np.r_[next_acc[:4], base_acc[4:]],
                                  np.r_[base_acc[:4], next_acc[4:]], next_acc]
                    yy = [digital(words[w:w+1], state[None, :])[0].ravel() for state in state_rows]
                    assert np.array_equal(yy[0], outputs0[w, :, mi+1])
                    assert np.array_equal(yy[3], outputs1[w, :, mi])
                    original_codes += 240
                    rr = []
                    segments = []
                    for acc, y in zip(state_rows, yy, strict=True):
                        coeff = tuple(F(k, 1024) for k in export(tuple(map(int, acc))))
                        rational = []
                        seg = []
                        for word in words[w]:
                            q1, q2, be, bits = map(int, word)
                            read = readout(q1, q2, F(be), 2*(bits & 1)-1,
                                           2*((bits >> 1) & 1)-1, coeff, data_q3=True)
                            rational.append(nearest_even(read.output))
                            seg.append(min(int(abs(read.raw1)//128), 3))
                            raw_domains += int(-512 <= read.raw1 < 512)
                        assert rational == y.tolist()
                        rational_codes += 120
                        rr.append(rational)
                        segments.append(seg)
                    targets = [2048*(1+F(float(x))) for x in tone[-120:]]
                    loss = four_grid_loss(*rr, targets)
                    direct = sum(((F(j)-t)**2-(F(z)-t)**2 for z, j, t in zip(rr[0], rr[3], targets)), F(0))/120
                    assert direct == loss.joint_loss
                    assert direct == loss.front_loss+loss.rear_loss+loss.loss_interaction
                    detail.append({'case': case, 'seed': seed, 'method': method, 'block': block,
                        'joint_mse_difference': float(direct), 'front_loss': float(loss.front_loss),
                        'rear_loss': float(loss.rear_loss), 'loss_interaction': float(loss.loss_interaction),
                        'front_rear_cross': float(loss.front_rear_cross),
                        'output_interaction_words': sum(c != 0 for c in loss.output_interaction),
                        'output_interaction_maximum': float(max(map(abs, loss.output_interaction))),
                        'segment_changes': sum(a != b for a, b in zip(segments[0], segments[3])),
                        'exact_joint_loss': str(direct)})
            print('checked', stem, 'original checkpoints and switch word pair', flush=True)

    expected_fields = ['stage1_symbol', 'stage2_symbol', 'backend_centered_code',
                       'stage1_dither_symbol', 'stage2_dither_symbol']
    assert [field.name for field in fields(DigitalCalibrationSample)] == expected_fields
    resources = []
    for n, front_bits, rear_bits in ((4, 26, 22), (120, 30, 26)):
        bounds = (n*512*8700, n*128*2175)
        assert all(b <= (1 << (bits-1))-1 for b, bits in zip(bounds, (front_bits, rear_bits)))
        resources.append({'selected_per_stage': n, 'gated_contribution_upper': 8*n,
                          'distinct_DY_upper': 2*n, 'sum_bits': 4*(front_bits+rear_bits),
                          'sum_magnitude_bounds': bounds, 'persistent_coefficient_bits': 8*23,
                          'conversion_slots': 120, 'pair_commit_instants': 1})
    assert original_codes == 43200 and rational_codes == 86400 and len(detail) == 180
    assert raw_domains == 86400 and boundary_states == 240 and equal_words == 58982400
    interaction_summary = []
    for case in p['cases']:
        for method in p['methods']:
            rows = [r for r in detail if r['case'] == case and r['method'] == method]
            interaction_summary.append({'case': case, 'method': method, 'windows': len(rows),
                'joint_improvement_windows': sum(r['joint_mse_difference'] < 0 for r in rows),
                'single_sum_wrong_sign_windows': sum((r['front_loss']+r['rear_loss'])*r['joint_mse_difference'] < 0 for r in rows),
                'nonzero_loss_interaction_windows': sum(r['loss_interaction'] != 0 for r in rows),
                'output_interaction_words': sum(r['output_interaction_words'] for r in rows),
                'segment_changes': sum(r['segment_changes'] for r in rows)})
    write(folder/'analysis.json', {'saved_score_pairs': pairs, 'checkpoint_four_grid': detail,
                                   'checkpoint_summary': interaction_summary, 'resources': resources})
    package = ROOT/'docs/reports/circuit_review_2026-10-11/ADC_Circuit_Review_Package.zip'
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        hardware = {}
        for name in ('hardware/reports/rechecked/utilization.rpt',
                     'hardware/reports/rechecked/timing_synth.rpt',
                     'hardware/netlists/gu_review_rechecked_funcsim.v'):
            content = archive.read(name)
            (folder/Path(name).name).write_bytes(content)
            hardware[name] = sha256(content).hexdigest()
    write(folder/'hardware_evidence.json', {'archive_members_sha256': hardware,
            'archive_crc_pass': True, 'raw_original_machine_directory_present': False,
            'new_synthesis': False, 'window_full120_implemented_by_this_netlist': False})
    unchanged(load(folder/'original_source_hashes.json'))
    unchanged(load(folder/'source_hashes.json'))
    unchanged(load(folder/'data_hashes.json'))
    unchanged(load(folder/'evidence_hashes.json'))
    write(folder/'validation.json', {'passed': True,
        'original_execution_sources': len(load(folder/'original_source_hashes.json')),
        'used_data_files': len(load(folder/'data_hashes.json')),
        'original_corner_codes_checked': original_codes, 'rational_four_grid_readouts': rational_codes,
        'four_grid_loss_identities': len(detail), 'switch_boundary_Q22_components': boundary_states,
        'carry_fresh_same_future_words': equal_words,
        'new_adc_conversions': 0, 'new_learning_observations': 0, 'new_online_outputs': 0,
        'new_counterfactual_integer_readouts': 43200, 'new_offline_four_grid_evaluations': 86400,
        'new_fft': 0, 'source_and_data_unchanged': True,
        'startup_acceptance': summarize_acceptance(startup, ('case', 'method', 'rate')),
        'switch_base_acceptance': summarize_acceptance(switching, ('case', 'method', 'variant')),
        'base_recovery_acceptance': summarize_acceptance(pair_rows, ('case', 'method')),
        'chip_or_asymptotic_convergence_proved': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    folder = parser.parse_args().folder.resolve()
    if not folder.is_relative_to(ROOT/'artifacts/research'):
        raise ValueError('output must be under artifacts/research')
    try:
        protocol = prepare(folder)
        run(folder, protocol)
    except Exception:
        if folder.exists():
            write(folder/'failure.json', {'traceback': traceback.format_exc()})
        raise
