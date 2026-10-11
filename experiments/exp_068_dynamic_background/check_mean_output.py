"""Supplementary offline theory check; read existing EXP-068 data, never train.

Freeze the probe contract and source hashes with --prepare before --run.
The seven-term finite loss polynomial is checked with exact rationals against
an independently evaluated continuous/Q3 chain and existing integer replay.
New-state scoring uses the SAME old window words, not the next window.
"""
import argparse
from dataclasses import replace
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import traceback

import numpy as np

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.static_fixed_contract import readout, export, nearest_even
from adc_research.theory.window_mean_map import analyze_window_mean
from adc_research.theory.cascade_mean_output import cascade_loss_change
from experiments.exp_065_input_switch_tracking.verify import digital

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT/'artifacts/runs/EXP_068/background_v1'
SOURCE_NAMES = (
    'src/adc_research/theory/window_mean_map.py',
    'src/adc_research/theory/cascade_mean_output.py',
    'tests/test_static_fixed_contract.py',
    'src/adc_research/theory/static_fixed_contract.py',
    'src/adc_research/theory/dither_information.py',
    'tests/test_window_mean_map.py', 'tests/test_dither_information.py',
    'experiments/exp_065_input_switch_tracking/verify.py',
    'experiments/exp_068_dynamic_background/check_mean_output.py',
)


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def digest(path):
    h = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=False)
    original = json.loads((DATA/'protocol.json').read_text(encoding='utf-8-sig'))
    n = original['budget']['windows_per_path']
    write(folder/'protocol.json', {
        'scope': 'Approved T3/T4 supplemental finite theory check; no training or tuning.',
        'source_data': str(DATA.relative_to(ROOT)),
        'source_protocol_sha256': digest(DATA/'protocol.json'),
        'windows': [0, n//2-1, n-1],
        'cases': [c['name'] for c in original['cases']],
        'seeds': original['seeds'], 'histories': ['reset', 'hold'],
        'methods': [m['name'] for m in original['methods']],
        'samples_per_probe': 120, 'candidate_rows': 21600,
        'prediction': 'Exact seven-term MSE change on every affine-preserved row; zero identity residual.',
        'boundary_rule': 'Base front selector/domain boundaries and crossed affine segments are counted/excluded; never fit or force the polynomial.',
        'reference': 'Old/new effective Q1.10 on same old words. Independent rational continuous/Q3 readout plus existing vector integer replay. Old codes must equal saved actual outputs.',
        'target': 'Offline only: 2048*(1+stored tone[n mod 30720]), stored double interpreted as exact rational.',
        'interpretation': 'Same-record counterfactual update diagnostic, not next-window gain, average-root identification, stationary distribution or chip prediction.',
        'acceptance': 'Old/new integer codes exact; exact continuous bilinear and seven loss terms match. No FFT, state fitting, parameter change or new ADC conversion.',
    })
    write(folder/'source_hashes.json', {name: digest(ROOT/name) for name in SOURCE_NAMES})


def run(folder):
    protocol = json.loads((folder/'protocol.json').read_text(encoding='utf-8'))
    sources = json.loads((folder/'source_hashes.json').read_text(encoding='utf-8'))
    assert all(digest(ROOT/name) == expected for name, expected in sources.items())
    assert digest(DATA/'protocol.json') == protocol['source_protocol_sha256']
    original = json.loads((DATA/'protocol.json').read_text(encoding='utf-8-sig'))
    assert json.loads((DATA/'delivery_validation.json').read_text())['passed']
    delivery = json.loads((DATA/'delivery_hashes.json').read_text())
    n = original['budget']['windows_per_path']
    tone = np.fromfile(DATA/'tone.bin', dtype='<f8')
    used = {'protocol.json', 'tone.bin'}
    paths = []
    fields = ('linear_error_cross', 'linear_square', 'bilinear_error_cross',
              'linear_bilinear_cross', 'bilinear_square', 'arithmetic_cross', 'arithmetic_square')
    for case in protocol['cases']:
        for history in protocol['histories']:
            for seed in protocol['seeds']:
                stem = f'{case}_{history}_{seed}'
                words = np.memmap(DATA/(stem+'_words.bin'), dtype='i1', mode='r', shape=(n,120,4))
                outputs = np.memmap(DATA/(stem+'_outputs.bin'), dtype='<i2', mode='r', shape=(n,120,3))
                used.update((stem+'_words.bin', stem+'_outputs.bin'))
                for method_index, method in enumerate(protocol['methods']):
                    state_name = stem+'_'+method+'_q22.bin'
                    used.add(state_name)
                    states = np.memmap(DATA/state_name, dtype='<f8', mode='r', shape=(n+1,8))
                    probes = []
                    for w in protocol['windows']:
                        acc = np.rint(states[w:w+2]*(1 << 22)).astype(np.int64)
                        old_front_rear, new_front_rear = [tuple(F(c,1024) for c in export(tuple(map(int,a)))) for a in acc]
                        old = old_front_rear[4:]+old_front_rear[:4]
                        new = new_front_rear[4:]+new_front_rear[:4]
                        delta = tuple(b-a for a,b in zip(old,new))
                        block = np.array(words[w:w+1])
                        old_codes = digital(block, acc[:1])[0].ravel()
                        new_codes = digital(block, acc[1:])[0].ravel()
                        assert np.array_equal(old_codes, outputs[w,:,method_index+1])
                        samples = tuple(Sample(int(q1),int(q2),int(be),2*(int(bits)&1)-1,
                                               2*((int(bits)>>1)&1)-1) for q1,q2,be,bits in block[0])
                        mean = analyze_window_mean(samples, old)
                        kept, errors, arithmetic = [], [], []
                        excluded = {'base_boundary': 0, 'segment_crossing': 0}
                        exact_direct = F(0)
                        changed_codes = 0
                        for i,(sample,row) in enumerate(zip(samples,mean.rows)):
                            base = readout(sample.stage1_symbol,sample.stage2_symbol,F(sample.backend_centered_code),
                                           sample.stage1_dither_symbol,sample.stage2_dither_symbol,old_front_rear,data_q3=True)
                            end = readout(sample.stage1_symbol,sample.stage2_symbol,F(sample.backend_centered_code),
                                          sample.stage1_dither_symbol,sample.stage2_dither_symbol,new_front_rear,data_q3=True)
                            assert nearest_even(base.output) == int(old_codes[i])
                            assert nearest_even(end.output) == int(new_codes[i])
                            assert 0 <= old_codes[i] <= 4095 and 0 <= new_codes[i] <= 4095
                            changed_codes += int(old_codes[i] != new_codes[i])
                            target = 2048*(1+F.from_float(float(tone[(w*120+i)%len(tone)])))
                            e = F(int(old_codes[i]))-target
                            one = replace(mean, rows=(row,))
                            if row.selector_margin1 == 0 or row.domain_margin1 == 0:
                                excluded['base_boundary'] += 1
                                continue
                            try:
                                prediction = cascade_loss_change(one, delta, (e,))
                            except ValueError as failure:
                                if 'crosses' not in str(failure):
                                    raise
                                excluded['segment_crossing'] += 1
                                continue
                            continuous = readout(sample.stage1_symbol,sample.stage2_symbol,F(sample.backend_centered_code),
                                                sample.stage1_dither_symbol,sample.stage2_dither_symbol,new_front_rear,data_q3=False)
                            predicted = prediction.linear_changes[0]+prediction.bilinear_changes[0]
                            assert continuous.y1-row.local1 == predicted
                            actual = F(int(new_codes[i])-int(old_codes[i]))
                            kept.append(row); errors.append(e); arithmetic.append(actual-predicted)
                            exact_direct += (e+actual)**2-e**2
                        terms = cascade_loss_change(replace(mean,rows=tuple(kept)),delta,errors,arithmetic) if kept else None
                        if terms:
                            assert terms.mse_difference == exact_direct/len(kept)
                        probes.append({'window':w, 'included':len(kept), 'excluded':excluded,
                            'all_integer_changes':changed_codes,
                            'delta_effective_rear_front':[str(x) for x in delta],
                            'terms':{field:float(getattr(terms,field)) for field in fields} if terms else {},
                            'mse_difference':float(terms.mse_difference) if terms else None,
                            'exact_identity_residual':'0' if terms else None})
                    paths.append({'case':case,'history':history,'seed':seed,'method':method,'probes':probes})
                    print('checked',stem,method,flush=True)
    hashes = {name:digest(DATA/name) for name in sorted(used)}
    assert all(value == delivery[name] for name,value in hashes.items())
    write(folder/'data_hashes.json',hashes)
    write(folder/'analysis.json',{'paths':paths})
    probes = [p for path in paths for p in path['probes']]
    included = sum(p['included'] for p in probes)
    excluded = {key:sum(p['excluded'][key] for p in probes) for key in ('base_boundary','segment_crossing')}
    assert included+sum(excluded.values()) == protocol['candidate_rows']
    validation = {'passed':True, 'new_conversions':0, 'paths':len(paths), 'window_probes':len(probes),
        'candidate_rows':protocol['candidate_rows'], 'rational_q3_readouts':2*protocol['candidate_rows'],
        'integer_codes_checked':2*protocol['candidate_rows'], 'exact_polynomial_rows':included,
        'excluded':excluded,'exact_identity_residual':'0', 'used_data_files_hashed':len(hashes),
        'sources_unchanged':all(digest(ROOT/name)==value for name,value in sources.items()),
        'scope':'Same old words scored before/after existing update; not actual future output or causal attribution.'}
    write(folder/'validation.json',validation)
    print(json.dumps(validation,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--folder',type=Path,required=True)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    if args.prepare == args.run:
        parser.error('select exactly one of --prepare / --run')
    if args.prepare:
        prepare(args.folder)
    else:
        try:
            run(args.folder)
        except Exception:
            write(args.folder/'failure.json',{'traceback':traceback.format_exc()})
            raise
