"""Independent full short replay, exact controls and paired gate diagnostics.

No experimental-platform or online-calibration imports. The source generator
uses those implementations separately. Native and exact endpoints stay separate.
"""
import argparse
from fractions import Fraction as F
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
import traceback

import numpy as np

from adc_research.theory.static_auxiliary_mismatch import CubicTransfer, rear_reconstruction_error
from adc_research.theory.static_comparator_offsets import convert, thresholds, safety, branch_shift
from adc_research.theory.static_fixed_contract import readout, export, commit, nearest_even
from experiments.exp_057_static_two_stage_million.common import input_tags, write

ROOT = Path(__file__).resolve().parents[2]


def rows(path):
    with gzip.open(path, 'rt', encoding='utf-8') as f:
        for line in f: yield json.loads(line)


def transfer(value): return CubicTransfer(*(F(str(v)) for v in value))


def exact(x, d1, d2, case):
    return convert(x, d1, d2, transfer(case['stage1']), transfer(case['stage2']),
        tuple(F(v) for v in case['offsets1']), tuple(F(v) for v in case['offsets2']))


def native(x, d1, d2, case):
    t1 = [(2*j-7)/8+float(F(v)) for j, v in enumerate(case['offsets1'])]
    t2 = [(2*j-7)/8+float(F(v)) for j, v in enumerate(case['offsets2'])]
    q1 = sum(x >= t for t in t1)-4; z1 = 4*(x-q1/4+d1/32)
    a1, b1 = case['stage1']; a2, b2 = case['stage2']
    m = a1*z1+b1*z1**3; q2 = sum(m >= t for t in t2)-4
    z2 = 4*(m-q2/4+d2/32); r2 = a2*z2+b2*z2**3
    assert abs(z1) <= 1 and abs(z2) <= 1 and -1 <= m < 1 and -1 <= r2 < 1
    return [q1, q2, math.floor((r2+1)*128)-128], [z1, m, m, z2, r2]


def fields(v): return [int(8*v.raw1), int(8*v.y1), int(8*v.y2), int(8*v.output)]


def checked(row, case, p, disagreements, rational=True):
    word, voltage = native(row['x'], *row['d'], case)
    assert word == row['word'], (case['name'], row['x'], 'native word')
    assert max(abs(a-b) for a, b in zip(voltage, row['v'])) <= p['acceptance']['voltage_tolerance']
    if not rational: return None
    x = F(row['x_rational']) if 'x_rational' in row else F.from_float(row['x'])
    trace = exact(x, *row['d'], case); ew = [trace.q1, trace.q2, trace.backend]
    if ew != word:
        changed = [i for i in range(3) if ew[i] != word[i]]; first = min(changed)
        margins = [min(abs(x-t) for t in thresholds(tuple(F(v) for v in case['offsets1']))),
            min(abs(trace.main1-t) for t in thresholds(tuple(F(v) for v in case['offsets2']))),
            min((128*(trace.main2+1)) % 1, 1-(128*(trace.main2+1)) % 1)/128]
        assert float(margins[first]) <= p['acceptance']['exact_boundary_margin'], ('unprotected exact difference', row)
        disagreements.append({'kind': row.get('kind', 'grid'), 'case': case['name'], 'x': str(x), 'd': row['d'],
            'native': word, 'exact': ew, 'first_changed_component': first, 'propagated_components': changed,
            'first_boundary_margin': str(margins[first])})
    bound = safety(transfer(case['stage1']), transfer(case['stage2']), tuple(F(v) for v in case['offsets1']), tuple(F(v) for v in case['offsets2']))
    assert abs(trace.z1) <= bound.nominal_output_radius1 and abs(trace.z2) <= bound.nominal_output_radius2
    assert abs(trace.backend) <= bound.backend_magnitude < 96
    return trace


def fixed(out, p, cc, differences):
    unit = (F(1),)*8; grid = {}; stats = {}; moments = {}; count = 0
    for row in rows(out/'grid.jsonl.gz'):
        case = cc[row['case']]; trace = checked(row, case, p, differences)
        v = readout(row['word'][0], row['word'][1], F(row['word'][2]), *row['d'], unit, data_q3=True)
        assert fields(v) == row['unit']; assert abs(v.raw1) < 384
        entry = stats.setdefault(row['case'], {mode: {'gates': [0]*8, 'basis': [0]*8, 'both': [0]*8} for mode in ('unit', 'inverse_export')})
        scored = [('unit', v)]
        if 'inverse_export' in row:
            k = (1/F(str(case['stage1'][0])),)*4+(1/F(str(case['stage2'][0])),)*4
            kh = tuple(F(nearest_even(1024*a), 1024) for a in k)
            vi = readout(*row['word'][:2], F(row['word'][2]), *row['d'], kh, data_q3=True)
            assert fields(vi) == row['inverse_export']; scored.append(('inverse_export', vi))
            mc = moments.setdefault(row['case'], {'continuous_inverse': [F(0)]*8, 'sar_inverse': [F(0)]*8})
            for mode, be in (('continuous_inverse', 128*trace.main2), ('sar_inverse', F(trace.backend))):
                vr = readout(trace.q1, trace.q2, be, *row['d'], k, data_q3=False)
                for bank, (d, y) in enumerate(((64*row['d'][0], vr.y1), (16*row['d'][1], vr.y2))):
                    for j in range(4): mc[mode][4*bank+j] += d*y*vr.gates[bank][j]
            if case['model'] == 'ideal':
                vr = readout(trace.q1, trace.q2, F(trace.backend), *row['d'], unit, data_q3=True)
                assert vr.output == (2048*(F(row['x_rational'])+1)).__floor__()
        for mode, vr in scored:
            for bank in range(2):
                for j in range(4):
                    h = 4*bank+j; g = vr.gates[bank][j]; b = vr.support[bank][j]
                    entry[mode]['gates'][h] += int(g); entry[mode]['basis'][h] += int(b); entry[mode]['both'][h] += int(g and b)
        for be in (128*trace.main2, F(trace.backend)):
            raw, delta = rear_reconstruction_error(trace, row['d'][1], be)
            assert raw == 512*trace.main1+delta
        grid[(row['case'], row['i'], *row['d'])] = row; count += 1
    for name, entry in moments.items():
        assert entry['continuous_inverse'] == [0]*8, (name, 'continuous zero correlations')
        if cc[name]['model'] == 'ideal': assert entry['sar_inverse'] == [0]*8
    pairs = []
    for case in cc.values():
        if case['variant'] == 'nominal_zero': continue
        ref = case['model']+'_nominal_zero'
        s = {'case': case['name'], 'q1_changes': 0, 'q2_changes': 0, 'unit_output_changes': 0,
            'unit_gate_changes': [0]*8, 'unit_joint_changes': [0]*8, 'largest_unit_code_difference': 0,
            'mse_unit': 0.0, 'mse_nominal_unit': 0.0}
        for i in range(p['grid']['points']):
            for d1, d2 in p['grid']['dither_pairs']:
                a, b = grid[(ref, i, d1, d2)], grid[(case['name'], i, d1, d2)]
                va, vb = [readout(*r['word'][:2], F(r['word'][2]), d1, d2, unit, data_q3=True) for r in (a, b)]
                ta, tb = exact(F(a['x_rational']), d1, d2, cc[ref]), exact(F(b['x_rational']), d1, d2, case)
                assert branch_shift(tb.q1-ta.q1, tb.q2-ta.q2, tb.main1-ta.main1) == (tb.z1-ta.z1, tb.z2-ta.z2)
                s['q1_changes'] += int(a['word'][0] != b['word'][0]); s['q2_changes'] += int(a['word'][1] != b['word'][1])
                s['unit_output_changes'] += int(va.output != vb.output)
                s['largest_unit_code_difference'] = max(s['largest_unit_code_difference'], float(abs(va.output-vb.output)))
                target = 2048*(F(a['x_rational'])+1)
                s['mse_unit'] += float((vb.output-target)**2); s['mse_nominal_unit'] += float((va.output-target)**2)
                for bank in range(2):
                    for j in range(4):
                        h = 4*bank+j; s['unit_gate_changes'][h] += int(va.gates[bank][j] != vb.gates[bank][j])
                        s['unit_joint_changes'][h] += int((va.gates[bank][j] and va.support[bank][j]) != (vb.gates[bank][j] and vb.support[bank][j]))
        s['mse_unit'] /= 4*p['grid']['points']; s['mse_nominal_unit'] /= 4*p['grid']['points']; pairs.append(s)
    return {'records': count, 'support_counts': stats, 'paired_unit': pairs,
        'exact_balanced_correlations_per_sample': {name: {mode: [str(v/(4*p['grid']['points'])) for v in sums] for mode, sums in e.items()} for name, e in moments.items()}}


def boundaries(out, p, cc, differences):
    counts = {}; examples = []
    for row in rows(out/'boundaries.jsonl.gz'):
        case = cc[row['case']]; kind = row['kind']; counts[kind] = counts.get(kind, 0)+1
        if kind == 'direct':
            bank = row['bank']; ts = [(2*j-7)/8+float(F(v)) for j, v in enumerate(case['offsets'+str(bank)])]
            assert row['threshold'] == ts[row['j']]
            expected = row['j']-4 if row['position'] == 'lower' else row['j']-3
            assert row['q'] == expected == sum(row['x'] >= t for t in ts)-4
        elif kind == 'node':
            m = row['m']; ts = [(2*j-7)/8+float(F(v)) for j, v in enumerate(case['offsets2'])]
            q = sum(m >= t for t in ts)-4; z = 4*(m-q/4+row['d2']/32)
            a, b = case['stage2']; r = a*z+b*z**3
            assert (q, math.floor((r+1)*128)-128) == (row['q2'], row['be'])
            assert max(abs(z-row['z2']), abs(r-row['r2'])) < p['acceptance']['voltage_tolerance']
            mr = F(row['m_rational']); tr = thresholds(tuple(F(v) for v in case['offsets2']))
            qr = sum(mr >= t for t in tr)-4; zr = 4*(mr-F(qr, 4)+F(row['d2'], 32)); rr = transfer(case['stage2'])(zr)
            ber = (128*(rr+1)).__floor__()-128
            if (qr, ber) != (q, row['be']):
                margin = min(abs(mr-t) for t in tr) if qr != q else min((128*(rr+1)) % 1, 1-(128*(rr+1)) % 1)/128
                assert float(margin) <= p['acceptance']['exact_boundary_margin']
                differences.append({'kind': 'node', 'case': case['name'], 'm': str(mr), 'd2': row['d2'],
                    'native': [q, row['be']], 'exact': [qr, ber], 'first_boundary_margin': str(margin)})
        else:
            checked(row, case, p, differences)
            v = readout(*row['word'][:2], F(row['word'][2]), *row['d'], (F(1),)*8, data_q3=True)
            assert fields(v) == row['unit']
            if kind == 'example': examples.append({'case': case['name'], 'x_rational': row['x_rational'], 'd': row['d'],
                'word': row['word'], 'unit': row['unit'], 'inverse_export': row.get('inverse_export'),
                'unit_gates': sum(v.gates, ()), 'unit_basis': sum(v.support, ())})
    return {'counts': counts, 'examples': examples}


def shorts(out, p, cc):
    tone = np.fromfile(out/'tone.bin', dtype='<f8'); steps = tuple(F(n, den) for den in (262144000, 16384000) for n in (1, 3, 6, 12))
    states = {}; final = {}; nominal = {}; methods = {m['name']: m for m in p['short']['methods']}
    reference = ROOT/p['nominal_record']; manifest = json.loads((reference/'delivery_hashes.json').read_text())
    for model in sorted(set(c['model'] for c in cc.values())):
        for seed in p['short']['seeds']:
            stem = f'{model}_{seed}'; files = [stem+'_words.bin', stem+'_outputs.bin']+[stem+'_'+m+'_q22.bin' for m in methods]
            for filename in files: assert sha256((reference/filename).read_bytes()).hexdigest() == manifest[filename]
            nominal[(model, seed)] = (np.memmap(reference/(stem+'_words.bin'), dtype='i1', mode='r').reshape(-1, 4),
                np.memmap(reference/(stem+'_outputs.bin'), dtype='<i2', mode='r').reshape(-1, 3),
                {m: np.memmap(reference/(stem+'_'+m+'_q22.bin'), dtype='<f8', mode='r').reshape(-1, 8) for m in methods})
    windows = conversions = obs = nominal_outputs = 0
    for row in rows(out/'short.jsonl.gz'):
        case = cc[row['case']]; key = (row['case'], row['seed'], row['method']); method = methods[row['method']]
        assert row['before'] == states.get(key, [1 << 22]*8)
        k = tuple(F(v, 1024) for v in export(tuple(row['before'])))
        assert list(export(tuple(row['before']))) == sum(row['coefficients'], [])
        sums = [F(0)]*8; counts = [0]*8
        entry = final.setdefault(key, {'case': key[0], 'seed': key[1], 'method': key[2],
            'selected': {s: [0]*8 for s in ('gates', 'basis', 'both')}, 'all': {s: [0]*8 for s in ('gates', 'basis', 'both')},
            'zero_requests': [0]*8, 'hidden_changes': [0]*8, 'export_changes': [0]*8})
        for j, value in enumerate(row['values']):
            idx = row['window']*120+j; assert value['x'] == tone[idx % len(tone)] and tuple(value['d']) == input_tags(row['seed'], idx)[1]
            checked(value, case, p, [], rational=False)
            v = readout(*value['word'][:2], F(value['word'][2]), *value['d'], k, data_q3=True)
            assert fields(v) == [row['raw1_scaled'][j], row['y1_scaled'][j], row['y2_scaled'][j], row['output_scaled'][j]]
            assert 0 <= v.output <= 4095
            gm = sum(int(g) << i for i, g in enumerate(sum(v.gates, ())))
            bm = sum(int(b) << i for i, b in enumerate(sum(v.support, ())))
            assert (gm, bm) == (row['gates'][j], row['basis'][j])
            selected = j < method['selected']
            for bank, (d, y) in enumerate(((64*value['d'][0], v.y1), (16*value['d'][1], v.y2))):
                for h in range(4):
                    i = 4*bank+h; g = v.gates[bank][h]; b = v.support[bank][h]
                    for scope in ('all', 'selected') if selected else ('all',):
                        entry[scope]['gates'][i] += int(g); entry[scope]['basis'][i] += int(b); entry[scope]['both'][i] += int(g and b)
                    if selected: sums[i] += d*y*g; counts[i] += int(g)
            if case['variant'] == 'nominal_zero':
                words, outputs, _ = nominal[(case['model'], row['seed'])]
                assert np.array_equal(words[idx, :3], value['word'])
                assert outputs[idx, 1 if method['selected'] == 4 else 2] == nearest_even(v.output)
                nominal_outputs += 1
            conversions += 1; obs += int(selected)
        requests, after = commit(tuple(row['before']), tuple(sums), method['multiplier'], steps)
        assert list(requests) == sum(row['requests'], []) and list(after) == row['after']
        assert [64*s for s in sums] == sum(row['products_scaled'], []) and counts == sum(row['gate_counts'], [])
        assert tuple(a-b for a, b in zip(after, row['before'])) == requests
        if case['variant'] == 'nominal_zero':
            st = nominal[(case['model'], row['seed'])][2][row['method']]
            assert np.array_equal(st[row['window']]*(1 << 22), row['before'])
            assert np.array_equal(st[row['window']+1]*(1 << 22), after)
        for i in range(8):
            entry['zero_requests'][i] += int(requests[i] == 0)
            entry['hidden_changes'][i] += int(after[i] != row['before'][i])
            entry['export_changes'][i] += int(export(after)[i] != export(tuple(row['before']))[i])
        states[key] = list(after); entry['final_accumulators'] = list(after); entry['final_export'] = list(export(after)); windows += 1
        if row['window'] == p['short']['windows']-1: print('verified short', *key, flush=True)
    assert len(states) == p['short']['paths'] and conversions == p['short']['physical_conversions']
    assert obs == p['short']['observations_per_bank'] and 2*windows == p['short']['single_bank_commits']
    return {'paths': len(states), 'windows': windows, 'conversions': conversions, 'observations_per_bank': obs,
        'single_bank_commits': 2*windows, 'existing_nominal_output_prefix_matches': nominal_outputs,
        'existing_nominal_state_prefix_exact': True, 'final': list(final.values())}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--run-id', required=True); arg = parser.parse_args()
    if not arg.run_id.replace('_', '').replace('-', '').isalnum(): raise ValueError('simple run id required')
    out = ROOT/'artifacts/runs/EXP_063'/arg.run_id
    if (out/'validation.json').exists() or (out/'verification_failure.json').exists(): raise ValueError('preserve previous verification')
    try:
        p = json.loads((out/'protocol.json').read_text()); cc = {c['name']: c for c in json.loads((out/'cases.json').read_text())}
        for filename, expected in json.loads((out/'source_hashes.json').read_text()).items(): assert sha256((ROOT/filename).read_bytes()).hexdigest() == expected, filename
        differences = []; bounds = {}
        for name, case in cc.items():
            b = safety(transfer(case['stage1']), transfer(case['stage2']), tuple(F(v) for v in case['offsets1']), tuple(F(v) for v in case['offsets2']))
            bounds[name] = {k: str(v) for k, v in vars(b).items()}
            assert b.backend_magnitude <= 81 and b.unit_front_raw_magnitude < 384
        grid = fixed(out, p, cc, differences); print('grid verified', grid['records'], flush=True)
        edge = boundaries(out, p, cc, differences); print('boundaries verified', edge['counts'], flush=True)
        short = shorts(out, p, cc)
        for filename, expected in json.loads((out/'source_hashes.json').read_text()).items(): assert sha256((ROOT/filename).read_bytes()).hexdigest() == expected, filename
        write(out/'validation.json', {'passed': True, 'grid': grid, 'boundaries': edge, 'short': short, 'safety_bounds': bounds,
            'exact_double_endpoint_disagreements': differences, 'native_word_mismatches': 0, 'digital_mismatches': 0,
            'physical_overloads': 0, 'coefficient_saturations': 0, 'output_clips': 0, 'source_hashes_unchanged': True,
            'long_record_executed': False, 'chip_certified': False})
        print('PASS', short['paths'], 'paths; endpoint exceptions', len(differences), flush=True)
    except Exception:
        write(out/'verification_failure.json', {'traceback': traceback.format_exc()}); raise


if __name__ == '__main__': main()
