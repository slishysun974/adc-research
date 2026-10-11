"""Offline independent integer replay and original-platform probe audit."""
import argparse
from dataclasses import replace
from fractions import Fraction as F
import json
from pathlib import Path
import traceback

import numpy as np

from adc_research.theory.static_fixed_contract import readout, export, commit
from adc_research.evaluation.observations import digital_sample
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.fixed_four_lane_window import _bank, FourLaneConversion
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState
from experiments.exp_060_static_auxiliary_preflight.run import fixed_setup, voltage_fields, check_physical
from experiments.exp_063_static_comparator_preflight.run import plant
from experiments.exp_062_same_input_background.verify import load, round_ratio, tags, pwl_scaled, digital
from hashlib import sha256
import gzip
from experiments.exp_057_static_two_stage_million.common import word, write
from experiments.exp_061_static_auxiliary_million.verify import sources


ROOT = Path(__file__).resolve().parents[2]


def nominal_check(folder, p):
    nominal = ROOT/p['nominal_folder']
    expected = json.loads((nominal/'delivery_hashes.json').read_text(encoding='utf-8-sig'))
    checked = json.loads((folder/'nominal_hashes.json').read_text(encoding='utf-8-sig'))
    assert all(sha256((nominal/name).read_bytes()).hexdigest() == h == expected[name] for name,h in checked.items())
    assert (folder/'tone.bin').read_bytes() == (nominal/'tone.bin').read_bytes()
    return nominal


def short_check(folder, p):
    prior=ROOT/p['comparator_preflight_folder']
    hashes=json.loads((prior/'delivery_hashes.json').read_text(encoding='utf-8-sig'))
    assert sha256((prior/'short.jsonl.gz').read_bytes()).hexdigest()==hashes['short.jsonl.gz']
    cases = {c['name'] for c in p['cases']}; cache = {}; windows = 0
    with gzip.open(ROOT/p['comparator_preflight_folder']/'short.jsonl.gz', 'rt', encoding='utf-8') as f:
        for line in f:
            r = json.loads(line)
            if r['seed'] != p['seeds'][0] or r['case'] not in cases: continue
            stem = f"{r['case']}_{r['seed']}"
            if stem not in cache:
                cache[stem] = (np.fromfile(folder/(stem+'_words.bin'), dtype='i1').reshape(-1,120,4),
                    np.fromfile(folder/(stem+'_outputs.bin'), dtype='<i2').reshape(-1,120,3),
                    [np.fromfile(folder/(stem+'_'+m['name']+'_q22.bin'),dtype='<f8').reshape(-1,8) for m in p['methods']],
                    np.fromfile(folder/(stem+'_probes.bin'),dtype='<f8').reshape(-1,1369))
            words,out,states,probes = cache[stem]; w=r['window']; m=0 if r['method']=='point30' else 1
            assert np.array_equal(words[w,:,:3], [v['word'] for v in r['values']])
            assert np.array_equal(states[m][w]*(1<<22),r['before'])
            assert np.array_equal(states[m][w+1]*(1<<22),r['after'])
            assert np.array_equal(out[w,:,m+1],round_ratio(np.array(r['output_scaled']),8))
            assert np.array_equal(probes[w,1337:1353].reshape(2,8)[m],np.array(r['products_scaled']).ravel()/64)
            acc = np.array(r['before'],dtype=np.int64)[None,:]
            _,g,b,prod=digital(words[w:w+1],acc)
            span=p['methods'][m]['selected']
            assert np.array_equal(g[:,:span].sum(axis=(0,1)),np.array(r['gate_counts']).ravel())
            assert np.array_equal(g[0].dot(1<<np.arange(8)),r['gates'])
            assert np.array_equal(b[0].dot(1<<np.arange(8)),r['basis'])
            windows+=1
    assert windows == 12*p['preflight']['windows']
    return windows


def physical_words(x, d1, d2, case):
    """Independent vector source; original platform separately audited."""
    thresholds = np.arange(-.875, 1, .25)
    q1 = np.searchsorted(thresholds+np.array([float(F(v)) for v in case['offsets1']]), x, side='right')-4
    z1 = 4*(x-q1/4+d1/32)
    a1, b1 = case['stage1']; a2, b2 = case['stage2']
    m = a1*z1+b1*np.power(z1, 3)
    q2 = np.searchsorted(thresholds+np.array([float(F(v)) for v in case['offsets2']]), m, side='right')-4
    z2 = 4*(m-q2/4+d2/32)
    r2 = a2*z2+b2*np.power(z2, 3)
    assert np.all((x >= -1) & (x < 1) & (np.abs(z1) <= 1) & (m >= -1) & (m < 1) & (np.abs(z2) <= 1) & (r2 >= -1) & (r2 < 1))
    return q1, q2, np.floor((r2+1)*128).astype(np.int64)-128


def verify(folder):
    p, src = load(folder); pipeline, cfg = fixed_setup(src)
    nominal = nominal_check(folder, p)
    tone = np.fromfile(folder/'tone.bin', dtype='<f8')
    n = p['input']['samples_per_block']; assert len(tone) == n
    analytical = p['input']['amplitude']*np.sin(2*np.pi*p['input']['tone_bin']*np.arange(n)/n)
    assert np.max(np.abs(tone-analytical)) < 2e-13
    steps = cfg.stage1_lms.step_sizes+cfg.stage2_lms.step_sizes
    streams = digital_outputs = commits = probe_samples = probe_windows = 0; max_voltage = 0.0
    for case in p['cases']:
        for seed in p['seeds']:
            stem = f"{case['name']}_{seed}"
            if not (folder/(stem+'.json')).exists():
                continue
            meta = json.loads((folder/(stem+'.json')).read_text(encoding='utf-8-sig'))
            nw = meta['Windows']; count = 120*nw
            assert nw in (p['preflight']['windows'], p['budget']['windows_per_path'])
            base_stem = f"{case['model']}_{seed}"
            nominal_words = np.memmap(nominal/(base_stem+'_words.bin'), dtype='i1', mode='r').reshape(-1,120,4)
            nominal_point = np.memmap(nominal/(base_stem+'_point30_q22.bin'), dtype='<f8', mode='r').reshape(-1,8)
            nominal_meta = json.loads((nominal/(base_stem+'.json')).read_text(encoding='utf-8-sig'))
            assert meta['Conversions'] == count
            raw = np.memmap(folder/(stem+'_words.bin'), dtype='i1', mode='r', shape=(nw, 120, 4))
            output = np.memmap(folder/(stem+'_outputs.bin'), dtype='<i2', mode='r', shape=(nw, 120, 3))
            assert (folder/(stem+'_words.bin')).stat().st_size == count*4
            assert (folder/(stem+'_outputs.bin')).stat().st_size == count*6
            state = [np.memmap(folder/(stem+'_'+m['name']+'_q22.bin'), dtype='<f8', mode='r', shape=(nw+1, 8)) for m in p['methods']]
            if case['variant'] == 'stage1_only':
                assert np.array_equal(state[0], nominal_point[:nw+1]), ('stage1 point trajectory', stem)
            for st in state:
                assert np.array_equal(st[0], np.ones(8))
                assert np.all(st*(1 << 22) == np.rint(st*(1 << 22)))
            for b, start in enumerate(range(0, nw, n//120)):
                stop = min(start+n//120, nw); words = raw[start:stop]
                paired = words[:,:,:2] != nominal_words[start:stop,:,:2]
                assert np.array_equal(paired.sum(axis=(0,1)), meta['Blocks'][b]['AllQChanges'])
                assert np.array_equal(paired[:,:4].sum(axis=(0,1)), meta['Blocks'][b]['SelectedPointQChanges'])
                if case['variant'] == 'stage1_only':
                    assert not np.any(paired[:,:4])
                    nominal_output = np.memmap(nominal/(base_stem+'_outputs.bin'), dtype='<i2', mode='r').reshape(-1,120,3)
                    unchanged = ~paired[:,:,0]
                    assert np.array_equal(words[unchanged], nominal_words[start:stop][unchanged])
                    assert np.array_equal(output[start:stop,:,1][unchanged], nominal_output[start:stop,:,1][unchanged])
                    if stop-start == n//120:
                        for key in ('Gates','Basis','Both','Correlations'):
                            assert meta['Blocks'][b]['Selected'][0][key] == nominal_meta['Blocks'][b]['Selected'][0][key]
                        for key in ('ZeroRequest','HiddenChanged','ExportChanged'):
                            assert meta['Blocks'][b][key][0] == nominal_meta['Blocks'][b][key][0]
                indices = np.arange(120*start, 120*stop); d1, d2 = tags(seed, indices)
                bits = (d1 > 0)+2*(d2 > 0)
                assert np.array_equal(words[:, :, 3].ravel(), bits)
                xx = tone[indices % n]; native = physical_words(xx, d1, d2, case)
                for h, v in enumerate(native): assert np.array_equal(words[:, :, h].ravel(), v)
                unit = np.full((stop-start, 8), 1 << 22, dtype=np.int64)
                yu = digital(words, unit)[0]; assert np.array_equal(yu, output[start:stop, :, 0])
                for m, method in enumerate(p['methods']):
                    acc = (state[m][start:stop]*(1 << 22)).astype(np.int64)
                    after = (state[m][start+1:stop+1]*(1 << 22)).astype(np.int64)
                    y, g, bs, products = digital(words, acc)
                    assert np.array_equal(y, output[start:stop, :, m+1])
                    assert np.all((y >= 0) & (y <= 4095))
                    selected = method['selected']; sums = products[:, :selected].sum(axis=1)
                    numerator = np.tile(np.array([-2, -6, -12, -24, -32, -96, -192, -384]), (stop-start, 1))*method['multiplier']*sums
                    delta = round_ratio(numerator, 125)
                    assert np.all((acc+delta >= 0) & (acc+delta <= 2047*4096))
                    assert np.array_equal(acc+delta, after)
                    for key, span in (('All', 120), ('Selected', selected)):
                        c = meta['Blocks'][b][key][m]
                        for field, actual in (('Gates', g[:, :span].sum(axis=(0, 1))), ('Basis', bs[:, :span].sum(axis=(0, 1))),
                                              ('Both', (g[:, :span] & bs[:, :span]).sum(axis=(0, 1))), ('Correlations', products[:, :span].sum(axis=(0, 1)))):
                            assert np.array_equal(actual, c[field]), (stem, b, m, key, field)
                    for field, actual in (('ZeroRequest', (delta == 0).sum(axis=0)), ('HiddenChanged', (acc != after).sum(axis=0)),
                                          ('ExportChanged', (round_ratio(acc, 4096) != round_ratio(after, 4096)).sum(axis=0))):
                        assert np.array_equal(actual, meta['Blocks'][b][field][m])
                    digital_outputs += 120*(stop-start); commits += stop-start
            rows = np.fromfile(folder/(stem+'_probes.bin'), dtype='<f8').reshape(-1, 1369)
            assert len(rows) == meta['ProbeWindows']
            expected_windows=list(range(nw)) if nw==p['preflight']['windows'] else sorted(
                {b*(n//120)+j for b in p['verification']['long_probe_blocks'] for j in range(4)}|set(range(nw-4,nw)))
            assert np.array_equal(rows[:,0],expected_windows)
            for row in rows:
                w = int(row[0]); before = row[1:17].reshape(2, 8)
                obs = row[17:1337].reshape(120, 11); recorded_sums = row[1337:1353].reshape(2, 8); after = row[1353:].reshape(2, 8)
                conversions = []; digital_values = [[], []]; computed_sums = np.zeros((2, 8))
                for m in range(2):
                    assert np.array_equal(before[m], state[m][w]) and np.array_equal(after[m], state[m][w+1])
                ks = [tuple(F(v, 1024) for v in export(tuple(int(v*(1 << 22)) for v in before[m]))) for m in range(2)]
                cascades = [replace(cfg.cascade,
                    stage1_pwl=replace(cfg.cascade.stage1_pwl, coefficient_codes=tuple(int(v*1024) for v in ks[m][:4])),
                    stage2_pwl=replace(cfg.cascade.stage2_pwl, coefficient_codes=tuple(int(v*1024) for v in ks[m][4:]))) for m in range(2)]
                for j, sample in enumerate(obs):
                    x, dd1, dd2, q1, q2, z1, main, aux, z2, r2, be = sample
                    idx = 120*w+j; dt = tuple(-1 if word(seed, s, idx) >> 63 == 0 else 1 for s in (2, 3))
                    assert x == tone[idx % n] and dt == (dd1, dd2)
                    original = plant(x, int(dd1), int(dd2), case, pipeline, idx); check_physical(original)
                    d = digital_sample(original.pipeline)
                    assert (d.stage1_symbol, d.stage2_symbol, d.backend_centered_code) == (q1, q2, be)
                    error = max(abs(v-u) for v, u in zip(voltage_fields(original), (z1, main, aux, z2, r2), strict=True))
                    max_voltage = max(max_voltage, error); assert error < p['verification']['voltage_tolerance']
                    assert np.array_equal(raw[w, j, :3], (q1, q2, be))
                    conversions.append(FourLaneConversion(idx, j % 4, d))
                    for m, method in enumerate(p['methods']):
                        rd = readout(int(q1), int(q2), F(int(be)), int(dd1), int(dd2), ks[m], data_q3=True)
                        core = correct_two_stage_fixed_observed(d, cascades[m])
                        assert core.unclipped_output_scaled == int(8*rd.output)
                        assert core.stage1_raw_scaled == int(8*rd.raw1)
                        assert round(float(rd.output)) == output[w, j, m+1]
                        digital_values[m].append([(int(512*dd1), int(8*rd.y1)), (int(128*dd2), int(8*rd.y2))])
                        if j < method['selected']:
                            for bank, local in enumerate((rd.y1, rd.y2)):
                                for h, gate in enumerate(rd.gates[bank]):
                                    computed_sums[m, 4*bank+h] += float((64*dd1 if bank == 0 else 16*dd2)*local*gate)
                    probe_samples += 1
                assert np.array_equal(computed_sums, recorded_sums)
                for m, method in enumerate(p['methods']):
                    acc = tuple(int(v*(1 << 22)) for v in before[m])
                    requests, expected = commit(acc, tuple(F(int(v)) for v in computed_sums[m]), method['multiplier'], steps)
                    assert expected == tuple(int(v*(1 << 22)) for v in after[m])
                    for bank, bcfg in enumerate((cfg.stage1_lms, cfg.stage2_lms)):
                        bs = FixedGatedLmsState(acc[4*bank:4*bank+4], (0,)*4, (0,)*4, (0,)*4, 120*w)
                        result = _bank(bs, bcfg, conversions, [v[bank] for v in digital_values[m]], tuple(j < method['selected'] for j in range(120)), method['multiplier'])
                        assert result.requested_deltas == requests[4*bank:4*bank+4]
                        assert result.state.accumulator_codes == expected[4*bank:4*bank+4]
                probe_windows += 1
            assert meta['CoefficientClips'] == meta['OutputClips'] == [0, 0]
            streams += 1; print('verified', stem, count, 'conversions and', nw*2, 'commits', flush=True)
    preflight = nw == p['preflight']['windows']
    assert streams == (6 if preflight else 30)
    short_matches = short_check(folder, p) if preflight else 0
    nominal_check(folder, p)
    sources(folder)
    result = {'passed': True, 'streams': streams, 'online_paths': 2*streams, 'all_online_output_codes_replayed': digital_outputs,
              'all_q22_bank_pair_commits_replayed': commits, 'all_unit_output_codes_replayed': digital_outputs//2,
              'original_platform_probe_conversions': probe_samples, 'rational_probe_readouts': 2*probe_samples,
              'original_fixed_bank_commits': 4*probe_windows, 'maximum_voltage_error': max_voltage,
              'all_stored_tags_and_native_vector_words_checked': True, 'all_block_counters_replayed': True,
              'source_hashes_unchanged': True, 'full_digital_transition_replay': True,
              'full_original_platform_physical_replay': preflight,
              'original_exp063_matching_short_windows': short_matches, 'all_nominal_delivery_hashes_matched': True,
              'all_stage1_point_states_equal_nominal': True, 'all_stage1_point_output_changes_localized': True,
              'all_q_change_block_counts_replayed': True}
    write(folder/'verification.json', result); print(json.dumps(result), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('folder', type=Path); folder = parser.parse_args().folder.resolve()
    try: verify(folder)
    except Exception:
        write(folder/'verification_failure.json', {'traceback': traceback.format_exc()}); raise
