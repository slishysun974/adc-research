"""Read-only fixed-state moments on previously delivered EXP-068 windows.

Prepare freezes probes and sources before computation. No ADC conversion,
training, root fitting, parameter selection or future-performance claim.
"""
import argparse
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import traceback

import numpy as np

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.gated_mean_objective import (
    affine_loss_change, gated_affine_moments, phase_selection_moments,
)
from adc_research.theory.static_fixed_contract import export, nearest_even, readout
from adc_research.theory.window_mean_map import analyze_window_mean

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT/'artifacts/runs/EXP_068/background_v1'
SOURCES = (
    'src/adc_research/theory/gated_mean_objective.py',
    'src/adc_research/theory/window_mean_map.py',
    'src/adc_research/theory/static_fixed_contract.py',
    'src/adc_research/calibration/observation.py',
    'tests/test_gated_mean_objective.py',
    'experiments/exp_068_dynamic_background/check_gated_mean.py',
)


def digest(path):
    h = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def vector(values):
    return [str(x) for x in values]


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=False)
    old = json.loads((DATA/'protocol.json').read_text(encoding='utf-8-sig'))
    n = old['budget']['windows_per_path']
    write(folder/'protocol.json', {
        'scope': 'Approved fixed-state T3/T4 selection and minimum-loss theory; read-only old words.',
        'source_data': str(DATA.relative_to(ROOT)),
        'source_protocol_sha256': digest(DATA/'protocol.json'),
        'cases': [c['name'] for c in old['cases']], 'histories': ['reset', 'hold'],
        'seeds': old['seeds'], 'methods': [m['name'] for m in old['methods']],
        'windows': [0, n//2-1, n-1], 'candidate_rows': 21600,
        'phase_laws': 'Uniform 30 phases and deterministic first four, conditional on the SAME complete window and old state; no PRNG inference.',
        'learning_laws': 'Unrounded front: full 120 and first four, normalized per observation. Evaluation: all 120.',
        'loss_delta_front': ['1/1024', '-1/2048', '0', '0'],
        'target': 'Offline T=2048*(1+exact stored double tone)-2048-512*q1; fixed back and continuous front only.',
        'q3_rule': 'No exclusion: exact actual-minus-continuous correlation equals readout correction plus gate-switch term. Boundary masks are values, not derivatives.',
        'prediction': 'Uniform phase mean equals full mean; exact A*k-b, H*k-h, target/residual split, covariance and finite front loss identities have zero residual.',
        'acceptance': 'All exact identities and original Q3 integer outputs agree; all used data delivery hashes and original frozen source hashes remain unchanged.',
        'interpretation': 'Finite empirical laws conditional on each old window, not fixed-state population moments, root solution, stationary law, future gain or algorithm recommendation.',
    })
    write(folder/'source_hashes.json', {name:digest(ROOT/name) for name in SOURCES})


def run(folder):
    protocol = json.loads((folder/'protocol.json').read_text(encoding='utf-8'))
    sources = json.loads((folder/'source_hashes.json').read_text(encoding='utf-8'))
    assert all(digest(ROOT/name) == expected for name, expected in sources.items())
    assert digest(DATA/'protocol.json') == protocol['source_protocol_sha256']
    assert json.loads((DATA/'delivery_validation.json').read_text())['passed']
    delivery = json.loads((DATA/'delivery_hashes.json').read_text())
    original_sources = json.loads((DATA/'source_hashes.json').read_text(encoding='utf-8-sig'))
    frozen = {str(Path(entry['Path']).relative_to(ROOT)):entry['Hash'].lower()
              for entry in original_sources}
    assert all(digest(ROOT/name) == expected for name, expected in frozen.items())
    old = json.loads((DATA/'protocol.json').read_text(encoding='utf-8-sig'))
    n = old['budget']['windows_per_path']
    tone = np.fromfile(DATA/'tone.bin', dtype='<f8')
    used = {'protocol.json', 'tone.bin'}
    paths = []
    delta = tuple(F(x) for x in protocol['loss_delta_front'])
    for case in protocol['cases']:
        for history in protocol['histories']:
            for seed in protocol['seeds']:
                stem = f'{case}_{history}_{seed}'
                word_name, output_name = stem+'_words.bin', stem+'_outputs.bin'
                used.update((word_name, output_name))
                words = np.memmap(DATA/word_name, dtype='i1', mode='r', shape=(n,120,4))
                outputs = np.memmap(DATA/output_name, dtype='<i2', mode='r', shape=(n,120,3))
                for mi, method in enumerate(protocol['methods']):
                    state_name = stem+'_'+method+'_q22.bin'
                    used.add(state_name)
                    states = np.memmap(DATA/state_name, dtype='<f8', mode='r', shape=(n+1,8))
                    probes = []
                    for w in protocol['windows']:
                        acc = tuple(map(int, np.rint(states[w]*(1 << 22))))
                        front_rear = tuple(F(c,1024) for c in export(acc))
                        mean = analyze_window_mean(tuple(
                            Sample(int(q1), int(q2), int(be), 2*(int(bits)&1)-1, 2*((int(bits)>>1)&1)-1)
                            for q1,q2,be,bits in words[w]), front_rear[4:]+front_rear[:4])
                        raw_products, q3_products, corrections = [], [], []
                        targets, direct_old, direct_new = [], [], []
                        gate_changes = [0]*8
                        changed_front = tuple(k+h for k,h in zip(front_rear[:4],delta))+front_rear[4:]
                        assert all(0 < k < 2 for k in changed_front)
                        for i, row in enumerate(mean.rows):
                            q1,q2,be,bits = map(int, words[w,i])
                            d1,d2 = 2*(bits&1)-1, 2*((bits>>1)&1)-1
                            actual = readout(q1,q2,F(be),d1,d2,front_rear,data_q3=True)
                            base = readout(q1,q2,F(be),d1,d2,front_rear,data_q3=False)
                            end = readout(q1,q2,F(be),d1,d2,changed_front,data_q3=False)
                            assert nearest_even(actual.output) == int(outputs[w,i,mi+1])
                            assert base.y1 == row.local1 and base.y2 == row.local2
                            target = 2048*(1+F.from_float(float(tone[(w*120+i)%len(tone)])))
                            targets.append(target-2048-512*q1)
                            direct_old.append((base.output-target)**2)
                            direct_new.append((end.output-target)**2)
                            cp, aq, correction = [], [], []
                            for local, d, gates, y, ag in (
                                (row.local2,row.dither2,row.gates2,actual.y2,actual.gates[1]),
                                (row.local1,row.dither1,row.gates1,actual.y1,actual.gates[0]),
                            ):
                                cp.extend(d*local*int(g) for g in gates)
                                aq.extend(d*y*int(g) for g in ag)
                                correction.extend(d*((y-local)*int(gq)+local*(int(gq)-int(g)))
                                                  for g,gq in zip(gates,ag))
                            assert all(a-c == e for a,c,e in zip(aq,cp,correction))
                            raw_products.append(tuple(cp)); q3_products.append(tuple(aq)); corrections.append(tuple(correction))
                            for j,(g,gq) in enumerate(zip(row.gates2+row.gates1,actual.gates[1]+actual.gates[0])):
                                gate_changes[j] += int(g != gq)
                        phases = phase_selection_moments(raw_products)
                        qphases = phase_selection_moments(q3_products)
                        fixed = phase_selection_moments(raw_products, (F(1),)+(F(0),)*29)
                        assert phases.selected_mean == mean.mean_products == phases.full_mean
                        assert qphases.selected_mean == qphases.full_mean
                        law_details = []
                        for learn in (None, (1,)*4+(0,)*116):
                            moments = gated_affine_moments([r.basis1 for r in mean.rows], [r.dither1 for r in mean.rows],
                                [r.gates1 for r in mean.rows], front_rear[:4], targets, learning_weights=learn)
                            indices = range(120) if learn is None else range(4)
                            size = len(indices)
                            selected = tuple(sum((raw_products[i][j] for i in indices),F(0))/size for j in range(8))
                            rounded = tuple(sum((q3_products[i][j] for i in indices),F(0))/size for j in range(8))
                            adjustment = tuple(sum((corrections[i][j] for i in indices),F(0))/size for j in range(8))
                            assert moments.correlations == selected[4:]
                            assert all(c == a+b for c,a,b in zip(moments.correlations,moments.instrument_target,moments.instrument_residual))
                            assert all(q-c == a for q,c,a in zip(rounded,selected,adjustment))
                            direct_g = tuple(sum(((r.local1-t)*r.basis1[j] for r,t in zip(mean.rows,targets)),F(0))/120 for j in range(4))
                            assert direct_g == moments.half_gradient
                            assert moments.mse == sum(direct_old,F(0))/120
                            assert affine_loss_change(moments,delta) == sum((b-a for a,b in zip(direct_old,direct_new)),F(0))/120
                            if learn is None:
                                assert moments.instrument_matrix == tuple(row[4:] for row in mean.fixed_mask_jacobian[4:])
                            law_details.append({'learning':'full' if learn is None else 'first_four',
                                'C_front':vector(moments.correlations), 'A_front':[vector(row) for row in moments.instrument_matrix],
                                'b_front':vector(moments.dither_square), 'g_front':vector(moments.half_gradient),
                                'instrument_target':vector(moments.instrument_target), 'instrument_residual':vector(moments.instrument_residual),
                                'C_q3_all_banks':vector(rounded), 'q3_correction_all_banks':vector(adjustment)})
                        # Independently expand conditional selector covariance about the complete mean.
                        for a in range(8):
                            for b in range(8):
                                direct = sum(((sum((raw_products[i][a] for i in range(p*4,p*4+4)),F(0))/4-mean.mean_products[a])*
                                              (sum((raw_products[i][b] for i in range(p*4,p*4+4)),F(0))/4-mean.mean_products[b])
                                              for p in range(30)),F(0))/30
                                assert direct == phases.covariance[a][b]
                        probes.append({'window':w,'open_cell_regular':mean.open_cell_regular,
                            'four_minus_full':vector(fixed.bias), 'phase_covariance':[vector(row) for row in phases.covariance],
                            'q3_gate_changes':gate_changes,'mse_continuous':str(moments.mse),
                            'front_loss_delta':str(affine_loss_change(moments,delta)), 'laws':law_details})
                    paths.append({'case':case,'history':history,'seed':seed,'method':method,'probes':probes})
                    print('checked',stem,method,flush=True)
    hashes = {name:digest(DATA/name) for name in sorted(used)}
    assert all(value == delivery[name] for name,value in hashes.items())
    assert all(digest(ROOT/name) == expected for name,expected in frozen.items())
    assert all(digest(ROOT/name) == expected for name,expected in sources.items())
    write(folder/'data_hashes.json',hashes)
    write(folder/'analysis.json',{'paths':paths})
    probes = [p for path in paths for p in path['probes']]
    assert len(probes)*120 == protocol['candidate_rows']
    validation = {'passed':True,'paths':len(paths),'window_probes':len(probes),'rows':len(probes)*120,
        'q3_readouts_and_saved_integer_codes':len(probes)*120,'front_affine_laws':len(probes)*2,
        'conditional_covariance_entries':len(probes)*64,'exact_identity_residual':'0',
        'windows_with_four_full_difference':sum(any(F(x) != 0 for x in p['four_minus_full']) for p in probes),
        'q3_gate_change_counts_rear_front':[sum(p['q3_gate_changes'][i] for p in probes) for i in range(8)],
        'old_source_files_verified':len(frozen),'used_data_files_hashed':len(hashes),
        'new_conversions':0,'training':False,'frozen_sources_unchanged':True,
        'scope':protocol['interpretation']}
    write(folder/'validation.json',validation)
    print(json.dumps(validation,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder',type=Path,required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',action='store_true')
    group.add_argument('--run',action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare(args.folder)
    else:
        try:
            run(args.folder)
        except Exception:
            write(args.folder/'failure.json',{'traceback':traceback.format_exc()})
            raise
