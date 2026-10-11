"""Original-platform generator; online window receives digital samples only."""
import argparse
from dataclasses import replace
from fractions import Fraction as F
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
import platform
import sys
import traceback

import numpy as np
import yaml

from adc_research.platform.amplifier import StaticCubicTruthConfig
from adc_research.platform.dual_path_settling import DualPathSettlingState
from adc_research.platform.two_phase_dual_path import TwoPhasePath, TwoPhaseDualPathConfig, process
from adc_research.platform.stage import process as stage
from adc_research.platform.backend_sar import convert as sar
from adc_research.platform.quantizer import convert as quantizer
from adc_research.calibration.fixed_adaptive_two_stage import FixedTwoStageAdaptiveState
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState
from adc_research.calibration.fixed_four_lane_window import FixedFourLaneWindowConfig, FourLaneConversion, correct_fixed_four_lane_window
from adc_research.evaluation.observations import digital_sample
from experiments.exp_057_static_two_stage_million.common import truth, input_tags
from experiments.exp_060_static_auxiliary_preflight.run import fixed_setup, voltage_fields, score_fields, inverse_config, check_physical, write, emit

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = Path(__file__).with_name('protocol.json')


def cases(p, background):
    result = []
    for model in background['cases']:
        for variant in ('nominal_zero', 'stage1_only', 'stage2_only'):
            result.append({**model, 'model': model['name'], 'variant': variant,
                'name': model['name']+'_'+variant,
                'offsets1': p['offsets']['stage1'] if variant == 'stage1_only' else ['0']*8,
                'offsets2': p['offsets']['stage2'] if variant == 'stage2_only' else ['0']*8})
    return result


def applied(case):
    base = truth(case)
    return replace(base,
        stage1=replace(base.stage1, threshold_offsets=tuple(float(F(v)) for v in case['offsets1'])),
        stage2=replace(base.stage2, threshold_offsets=tuple(float(F(v)) for v in case['offsets2'])))


def plant(x, d1, d2, case, pipeline, index=0):
    zero = TwoPhasePath(0.0, 0.0)
    phases = TwoPhaseDualPathConfig(zero, zero, zero, auxiliary_truth=StaticCubicTruthConfig(*case['stage1']))
    return process(x, pipeline, phases, DualPathSettlingState(), sample_index=index,
        dither_symbols=(d1, d2), nonidealities=applied(case))


def record(x, d1, d2, case, pipeline, cfg, index=0, xr=None):
    value = plant(x, d1, d2, case, pipeline, index); check_physical(value)
    sample = digital_sample(value.pipeline)
    row = {'case': case['name'], 'x': x, 'd': [d1, d2], 'v': voltage_fields(value),
        'word': [sample.stage1_symbol, sample.stage2_symbol, sample.backend_centered_code],
        'unit': score_fields(sample, cfg.cascade)}
    if xr is not None: row['x_rational'] = str(xr)
    if case['stage1'][1] == case['stage2'][1] == 0:
        row['inverse_export'] = score_fields(sample, inverse_config(cfg, case))
    return row


def hashes():
    paths = []
    for name in ('src/adc_research', 'rtl', 'experiments/exp_057_static_two_stage_million',
                 'experiments/exp_058_static_fixed_preflight', 'experiments/exp_059_static_fixed_million',
                 'experiments/exp_060_static_auxiliary_preflight', 'experiments/exp_061_static_auxiliary_million',
                 'experiments/exp_062_same_input_background', 'experiments/exp_063_static_comparator_preflight'):
        paths.extend(p for p in (ROOT/name).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    paths += [ROOT/'tests/test_static_comparator_offsets.py', ROOT/'configs/architectures/gu_behavioral_v1.yaml',
              ROOT/'configs/nonidealities/gu_gate_d_static_v0_1.yaml']
    return {str(p.relative_to(ROOT)).replace('\\', '/'): sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def grid(out, p, cc, pipeline, cfg):
    count = 0
    with gzip.open(out/'grid.jsonl.gz', 'wt', encoding='utf-8') as f:
        for case in cc:
            for i in range(p['grid']['points']):
                x = F(p['grid']['low'])+F(2*i+1, 2*p['grid']['points'])*(F(p['grid']['high'])-F(p['grid']['low']))
                for d1, d2 in p['grid']['dither_pairs']:
                    emit(f, {**record(float(x), d1, d2, case, pipeline, cfg, xr=x), 'i': i}); count += 1
    return count


def boundary(out, cc, pipeline, cfg):
    counts = {'first': 0, 'working_endpoint': 0, 'example': 0, 'node': 0, 'direct': 0}
    with gzip.open(out/'boundaries.jsonl.gz', 'wt', encoding='utf-8') as f:
        for case in cc:
            for j in range(8):
                t = F(2*j-7, 8)+F(case['offsets1'][j])
                for x in (t-F(1, 2**36), t, t+F(1, 2**36)):
                    for d1 in (-1, 1):
                        for d2 in (-1, 1):
                            emit(f, {**record(float(x), d1, d2, case, pipeline, cfg, xr=x), 'kind': 'first'}); counts['first'] += 1
                t2 = F(2*j-7, 8)+F(case['offsets2'][j])
                for m in (t2-F(1, 2**36), t2, t2+F(1, 2**36)):
                    for d2 in (-1, 1):
                        value = stage(float(m), float(m), d2, pipeline.stage2, nonidealities=applied(case).stage2)
                        backend = sar(value.residue, pipeline.backend)
                        assert not (value.overload_low or value.overload_high or backend.overload_low or backend.overload_high)
                        emit(f, {'case': case['name'], 'kind': 'node', 'm': float(m), 'm_rational': str(m),
                            'd2': d2, 'q2': value.quantizer.symbol, 'z2': 4*value.residue_preamp,
                            'r2': value.residue, 'be': backend.centered_code}); counts['node'] += 1
            for kind, xx in (('working_endpoint', (F(-41, 50), F(41, 50))), ('example', (F(251, 2000), F(1, 2400)))):
                for x in xx:
                    for d1 in (-1, 1):
                        for d2 in (-1, 1):
                            emit(f, {**record(float(x), d1, d2, case, pipeline, cfg, xr=x), 'kind': kind}); counts[kind] += 1
            for bank in (1, 2):
                offsets = tuple(float(F(v)) for v in case['offsets'+str(bank)])
                config = pipeline.stage1.quantizer if bank == 1 else pipeline.stage2.quantizer
                for j, nominal in enumerate(config.thresholds):
                    t = nominal+offsets[j]
                    for label, x in (('lower', math.nextafter(t, -math.inf)), ('equal', t), ('upper', math.nextafter(t, math.inf))):
                        q = quantizer(x, config, threshold_offsets=offsets)
                        emit(f, {'case': case['name'], 'kind': 'direct', 'bank': bank, 'j': j,
                            'position': label, 'x': x, 'threshold': t, 'q': q.symbol}); counts['direct'] += 1
    return counts


def short(out, p, cc, pipeline, cfg, tone):
    paths = windows = conversions = observations = 0
    with gzip.open(out/'short.jsonl.gz', 'wt', encoding='utf-8') as f:
        for case in cc:
            for seed in p['short']['seeds']:
                for method in p['short']['methods']:
                    state = FixedTwoStageAdaptiveState(FixedGatedLmsState.unity(cfg.stage1_lms), FixedGatedLmsState.unity(cfg.stage2_lms))
                    wcfg = FixedFourLaneWindowConfig(cfg, selection='point_products' if method['selected'] == 4 else 'all_products')
                    for w in range(p['short']['windows']):
                        before = list(state.stage1.accumulator_codes+state.stage2.accumulator_codes)
                        rows = []; physical = []
                        for j in range(120):
                            idx = 120*w+j; x = float(tone[idx % len(tone)]); d1, d2 = input_tags(seed, idx)[1]
                            value = plant(x, d1, d2, case, pipeline, idx); check_physical(value)
                            sample = digital_sample(value.pipeline); rows.append(FourLaneConversion(idx, idx % 4, sample))
                            physical.append({'x': x, 'd': [d1, d2], 'v': voltage_fields(value),
                                'word': [sample.stage1_symbol, sample.stage2_symbol, sample.backend_centered_code]})
                        value = correct_fixed_four_lane_window(rows, state, wcfg)
                        assert not any(v.saturated_low or v.saturated_high for v in value.calibrations)
                        updates = (value.stage1_update, value.stage2_update)
                        assert all(u.requested_deltas == u.applied_deltas for u in updates)
                        gm = []; bm = []
                        for j, cal in enumerate(value.calibrations):
                            local = (value.stage1_learning_outputs_scaled[j], value.stage2_learning_outputs_scaled[j])
                            raw = (cal.stage1_raw_scaled, 8*physical[j]['word'][2])
                            gm.append(sum(int(abs(local[b]) >= updates[b].thresholds_scaled[h]) << (4*b+h) for b in (0, 1) for h in range(4)))
                            bm.append(sum(int(abs(raw[b]) > (1024 if b == 0 else 256)*h) << (4*b+h) for b in (0, 1) for h in range(4)))
                        emit(f, {'case': case['name'], 'seed': seed, 'method': method['name'], 'window': w,
                            'before': before, 'after': list(value.state.stage1.accumulator_codes+value.state.stage2.accumulator_codes),
                            'coefficients': [list(u.coefficient_codes_before) for u in updates],
                            'products_scaled': [list(u.selected_product_sums) for u in updates],
                            'gate_counts': [list(u.selected_gate_counts) for u in updates],
                            'requests': [list(u.requested_deltas) for u in updates],
                            'output_scaled': [v.unclipped_output_scaled for v in value.calibrations],
                            'raw1_scaled': [v.stage1_raw_scaled for v in value.calibrations],
                            'y1_scaled': value.stage1_learning_outputs_scaled, 'y2_scaled': value.stage2_learning_outputs_scaled,
                            'gates': gm, 'basis': bm, 'values': physical})
                        state = value.state; windows += 1; conversions += 120; observations += method['selected']
                    paths += 1
                    print('generated', case['name'], seed, method['name'], flush=True)
    return {'paths': paths, 'windows': windows, 'conversions': conversions, 'observations_per_bank': observations, 'single_bank_commits': 2*windows}


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--run-id', required=True); arg = parser.parse_args()
    if not arg.run_id.replace('_', '').replace('-', '').isalnum(): raise ValueError('simple run id required')
    out = ROOT/'artifacts/runs/EXP_063'/arg.run_id; out.mkdir(parents=True, exist_ok=False)
    p = json.loads(PROTOCOL.read_text(encoding='utf-8'))
    source = json.loads((ROOT/p['source_protocol']).read_text(encoding='utf-8'))
    background = json.loads((ROOT/p['background_protocol']).read_text(encoding='utf-8'))
    cc = cases(p, background)
    original = yaml.safe_load((ROOT/p['offset_source']).read_text(encoding='utf-8'))
    for bank in ('stage1', 'stage2'):
        assert [float(F(v)) for v in p['offsets'][bank]] == original['effects']['flash_threshold_offsets'][bank]
    nominal = ROOT/p['nominal_record']; manifest = json.loads((nominal/'delivery_hashes.json').read_text(encoding='utf-8'))
    assert sha256((nominal/'tone.bin').read_bytes()).hexdigest() == manifest['tone.bin']
    for filename, data in (('protocol.json', p), ('source_protocol.json', source), ('background_protocol.json', background), ('cases.json', cc), ('offset_source.json', original)):
        write(out/filename, data)
    (out/'tone.bin').write_bytes((nominal/'tone.bin').read_bytes()); tone = np.fromfile(out/'tone.bin', dtype='<f8')
    frozen = hashes(); write(out/'source_hashes.json', frozen)
    write(out/'environment.json', {'python': sys.version, 'executable': sys.executable, 'platform': platform.platform()})
    try:
        pipeline, cfg = fixed_setup(source)
        counts = {'grid': grid(out, p, cc, pipeline, cfg), 'boundaries': boundary(out, cc, pipeline, cfg)}
        print('fixed records complete', counts, flush=True)
        counts['short'] = short(out, p, cc, pipeline, cfg, tone)
        assert hashes() == frozen
        write(out/'run_summary.json', {'status': 'complete', 'counts': counts, 'source_hashes_unchanged': True})
    except Exception:
        write(out/'run_failure.json', {'traceback': traceback.format_exc()}); raise


if __name__ == '__main__': main()
