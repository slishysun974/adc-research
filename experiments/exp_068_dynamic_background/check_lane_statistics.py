"""Ideal four-sample selection laws on old windows; no online algorithm run."""
import argparse
from collections import Counter
from dataclasses import asdict
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import traceback

import numpy as np

from adc_research.theory.gated_mean_objective import phase_selection_moments
from adc_research.theory.lane_phase_statistics import lane_phase_moments, is_positive_semidefinite
from adc_research.theory.static_fixed_contract import export, nearest_even, readout

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT/'artifacts/research/gated_mean_20261011_v2'
DATA = ROOT/'artifacts/runs/EXP_068/background_v1'
SOURCES = [
    'src/adc_research/theory/lane_phase_statistics.py',
    'tests/test_lane_phase_statistics.py',
    'experiments/exp_068_dynamic_background/check_lane_statistics.py',
    'src/adc_research/theory/gated_mean_objective.py',
    'src/adc_research/theory/static_fixed_contract.py',
]
DOCUMENTS = ['docs/STATUS.md', 'docs/DECISIONS.md',
    'docs/RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md',
    'docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
    'docs/theory/DITHER_INFORMATION_AND_STOCHASTIC_UPDATE_AUDIT_V1.md',
    'docs/theory/README.md', 'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md',
    'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
    'docs/stages/03_gu_baseline/README.md', 'experiments/exp_068_dynamic_background/README.md']


def digest(path):
    h = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    path.write_text(json.dumps(value, default=str, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def frozen_sources():
    rows = load(DATA/'source_hashes.json')
    assert all(digest(Path(r['Path'])) == r['Hash'].lower() for r in rows)
    for folder in ['gated_mean_20261011_v2', 'coupled_stationarity_20261011_v1',
                   'target_bounds_20261011_v1', 'preserving_directions_20261011_v1']:
        hashes = load(ROOT/'artifacts/research'/folder/'source_hashes.json')
        assert all(digest(ROOT/name) == value for name, value in hashes.items())
    return len(rows)


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=False)
    previous = load(OLD/'protocol.json')
    write(folder/'protocol.json', {
        'scope': 'Concrete statistical-contract preparation within T3/T4; no online implementation or stage-four closed-loop comparison.',
        'cases': previous['cases'], 'histories': previous['histories'],
        'seeds': previous['seeds'], 'methods': previous['methods'], 'windows': previous['windows'],
        'rows': 21600, 'coefficient_and_word_law': 'Each old complete window and old exported bank fixed; no state evolution under alternatives.',
        'selection_laws': ['one ideal uniform common phase', 'four ideal mutually independent uniform lane phases', 'fixed phase zero'],
        'layers': ['continuous', 'Q3'], 'coordinate_order': 'rear four then front four; unscaled D*Y*gate',
        'comparison': 'Exact means, selector covariance, PSD ordering of complete 8x8 matrices; diagonal signs and fixed-phase bias risk retained.',
        'prediction': 'Equal uniform marginals preserve complete mean; covariance difference is cross-lane contribution and has no universal sign.',
        'acceptance': 'Exact formulas match independent common-phase enumeration and old saved continuous covariance; actual Q3 codes match; frozen source/data hashes preserved.',
        'controls': 'Seven predeclared tests: full joint enumeration, legal digital in-phase and cancellation controls, zero cross terms, PSD singular/indefinite controls, coordinate mixing, invalid inputs.',
        'new_ADC_conversions': 0, 'new_training': 0, 'new_FFT_or_spectrum_scans': 0,
        'prohibited_inference': 'No actual PRNG independence, universal lower closed-loop variance, MSE/SNDR gain, chip representativeness or new algorithm authorization.',
    })
    write(folder/'source_hashes.json', {p:digest(ROOT/p) for p in SOURCES})
    write(folder/'previous_hashes.json', {str(p.relative_to(ROOT)):digest(p) for p in
          [OLD/'protocol.json', OLD/'analysis.json', OLD/'data_hashes.json', DATA/'protocol.json',
           DATA/'source_hashes.json', DATA/'delivery_hashes.json']})
    for name in DOCUMENTS:
        dest = folder/'before'/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((ROOT/name).read_bytes())
    write(folder/'before_hashes.json', {p:digest(ROOT/p) for p in DOCUMENTS})
    print(json.dumps({'prepared':str(folder), 'original_source_count':frozen_sources()}))


def classify(cross):
    if all(x == 0 for row in cross for x in row):
        return 'equal'
    if is_positive_semidefinite(cross):
        return 'independent_no_larger'
    if is_positive_semidefinite(tuple(tuple(-x for x in row) for row in cross)):
        return 'shared_no_larger'
    return 'incomparable'


def run(folder):
    assert not (folder/'analysis.json').exists()
    p = load(folder/'protocol.json')
    for manifest in ['source_hashes.json', 'previous_hashes.json']:
        assert all(digest(ROOT/name) == h for name,h in load(folder/manifest).items())
    count_sources = frozen_sources()
    previous = load(OLD/'analysis.json')
    old_probes = {(r['case'],r['history'],r['seed'],r['method'],probe['window']):probe
                  for r in previous['paths'] for probe in r['probes']}
    windows = load(DATA/'protocol.json')['budget']['windows_per_path']
    expected_data = load(OLD/'data_hashes.json')
    used = {'protocol.json'}
    details, totals = [], {'continuous':Counter(), 'Q3':Counter()}
    for case in p['cases']:
        for history in p['histories']:
            for seed in p['seeds']:
                stem = f'{case}_{history}_{seed}'
                wn, on = stem+'_words.bin', stem+'_outputs.bin'
                used.update([wn,on])
                words = np.memmap(DATA/wn, dtype='i1', mode='r', shape=(windows,120,4))
                outputs = np.memmap(DATA/on, dtype='<i2', mode='r', shape=(windows,120,3))
                for mi, method in enumerate(p['methods']):
                    sn = stem+'_'+method+'_q22.bin'
                    used.add(sn)
                    states = np.memmap(DATA/sn, dtype='<f8', mode='r', shape=(windows+1,8))
                    for w in p['windows']:
                        acc = tuple(map(int, np.rint(states[w]*(1 << 22))))
                        k = tuple(F(c,1024) for c in export(acc))
                        products = {'continuous':[], 'Q3':[]}
                        for i, word in enumerate(words[w]):
                            q1,q2,be,bits = map(int,word)
                            d1,d2 = 2*(bits&1)-1, 2*((bits>>1)&1)-1
                            for layer, quantized in [('continuous',False), ('Q3',True)]:
                                z = readout(q1,q2,F(be),d1,d2,k,data_q3=quantized)
                                if quantized:
                                    assert nearest_even(z.output) == int(outputs[w,i,mi+1])
                                products[layer].append(tuple(d*y*int(g) for d,y,gs in
                                    [(F(16*d2),z.y2,z.gates[1]),(F(64*d1),z.y1,z.gates[0])] for g in gs))
                        row = {'case':case,'history':history,'seed':seed,'method':method,'window':w,'layers':{}}
                        for layer, values in products.items():
                            result = lane_phase_moments(values)
                            direct = phase_selection_moments(values)
                            assert result.full_mean == direct.full_mean == direct.selected_mean
                            assert result.shared_covariance == direct.covariance
                            if layer == 'continuous':
                                old = old_probes[(case,history,seed,method,w)]
                                assert result.shared_covariance == tuple(tuple(F(x) for x in r) for r in old['phase_covariance'])
                            bias = tuple(sum(v[j] for v in values[:4])/4-result.full_mean[j] for j in range(8))
                            fixed_risk = tuple(tuple(bias[i]*bias[j] for j in range(8)) for i in range(8))
                            ordering = classify(result.cross_contribution)
                            totals[layer][ordering] += 1
                            diagonal = tuple(result.cross_contribution[i][i] for i in range(8))
                            row['layers'][layer] = dict(asdict(result), ordering=ordering,
                                diagonal_shared_minus_independent=diagonal,
                                fixed_phase_zero_bias=bias, fixed_phase_zero_risk=fixed_risk)
                        details.append(row)
                print('checked',stem,flush=True)
    assert len(details)*120 == p['rows']
    hashes = {name:digest(DATA/name) for name in sorted(used)}
    assert all(h == expected_data[name] for name,h in hashes.items())
    assert frozen_sources() == count_sources
    assert all(digest(ROOT/name) == h for name,h in load(folder/'source_hashes.json').items())
    write(folder/'data_hashes.json',hashes)
    write(folder/'analysis.json', {'windows':details, 'matrix_order_counts':totals})
    write(folder/'validation.json', {'passed':True, 'windows':len(details), 'old_Q3_codes_checked':len(details)*120,
        'old_continuous_covariance_entries_checked':len(details)*64,
        'new_layer_matrix_pairs':len(details)*2, 'exact_identity_residual':'0',
        'matrix_order_counts':totals, 'original_source_files_verified':count_sources,
        'data_files_hashed':len(hashes), 'new_ADC_conversions':0, 'new_training':0,
        'new_FFT_or_spectrum_scans':0, 'online_selector_or_update_changed':False})
    print(json.dumps(load(folder/'validation.json'),ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder',type=Path,required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--prepare',action='store_true')
    action.add_argument('--run',action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare(args.folder)
    else:
        try:
            run(args.folder)
        except Exception:
            write(args.folder/'failure.json', {'traceback':traceback.format_exc()})
            raise
