"""Original two-phase platform and original shared-window Gu, short scope only."""

import argparse
from dataclasses import asdict
import gzip
from hashlib import sha256
import json
from pathlib import Path
import platform
import shutil
import sys
import traceback

import numpy as np

from adc_research.calibration.fixed_adaptive_two_stage import FixedTwoStageAdaptiveState
from adc_research.calibration.fixed_four_lane_window import (
    FourLaneConversion, FixedFourLaneWindowConfig, correct_fixed_four_lane_window,
)
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.evaluation.observations import digital_sample
from adc_research.platform.amplifier import StaticCubicTruthConfig
from adc_research.platform.dual_path_settling import DualPathSettlingState
from adc_research.platform.two_phase_dual_path import TwoPhasePath, TwoPhaseDualPathConfig, process
from experiments.exp_057_static_two_stage_million.common import word, truth, write
from experiments.exp_060_static_auxiliary_preflight.run import fixed_setup, check_physical

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def sources():
    paths = set()
    for dirname in ('src/adc_research', 'rtl'):
        paths.update(p for p in (ROOT/dirname).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    for dirname in (ROOT/'experiments').iterdir():
        if dirname.is_dir() and any(dirname.name.startswith(f'exp_{n:03d}_') for n in range(55, 68)):
            paths.update(p for p in dirname.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    paths.update([ROOT/'configs/architectures/gu_behavioral_v1.yaml', ROOT/'tests/test_dynamic_history.py'])
    return {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(paths)}


def phases_config(case, phase):
    return TwoPhaseDualPathConfig(*(TwoPhasePath(a, phase['tracking']) for a in phase['amplification']),
        auxiliary_truth=StaticCubicTruthConfig(*case['auxiliary']))


def initial(cfg):
    return FixedTwoStageAdaptiveState(FixedGatedLmsState.unity(cfg.stage1_lms),
                                      FixedGatedLmsState.unity(cfg.stage2_lms))


def integer_code(cal):
    result = round_fraction(cal.unclipped_output_scaled, 8, 'nearest_even')
    if not 0 <= result <= 4095 or cal.saturated_low or cal.saturated_high:
        raise ValueError('output clip in short preflight')
    return result


def emit(stream, row):
    stream.write(json.dumps(row, separators=(',', ':'), allow_nan=False)+'\n')


def run(folder):
    p = json.loads((HERE/'protocol.json').read_text(encoding='utf-8'))
    src = json.loads((ROOT/p['source_protocol']).read_text(encoding='utf-8-sig'))
    frozen = sources()
    write(folder/'source_hashes.json', frozen)
    shutil.copyfile(HERE/'protocol.json', folder/'protocol.json')
    shutil.copyfile(ROOT/p['source_protocol'], folder/'source_protocol.json')
    ref = ROOT/p['static_reference']
    assert json.loads((ref/'verification.json').read_text(encoding='utf-8-sig'))['passed']
    old_hashes = {v['Path']: v['Hash'].lower() for v in json.loads((ref/'source_hashes.json').read_text(encoding='utf-8-sig'))}
    for path, expected in old_hashes.items():
        assert digest(Path(path)) == expected, f'old source changed: {path}'
    reference_files = ['tone.bin', 'verification.json', 'source_hashes.json']
    for c in p['cases']:
        stem = f"{c['name']}_{p['seed']}"
        reference_files += [stem+'_words.bin', stem+'_outputs.bin']
        reference_files += [stem+'_'+m['name']+'_q22.bin' for m in p['methods']]
    (folder/'reference').mkdir()
    for name in reference_files:
        shutil.copyfile(ref/name, folder/'reference'/name)
    write(folder/'reference_hashes.json', {name:digest(ref/name) for name in reference_files})
    tone = np.fromfile(folder/'reference/tone.bin', dtype='<f8')
    assert len(tone) == p['input']['samples_per_period']
    pipeline, cfg = fixed_setup(src)
    write(folder/'environment.json', {'python':sys.version, 'executable':sys.executable,
                                      'platform':platform.platform(), 'numpy':np.__version__})
    count = codes = commits = 0
    for case in p['cases']:
        for ph in p['phases']:
            name = case['name']+'_'+ph['name']
            phases = phases_config(case, ph)
            analog = DualPathSettlingState(*p['initial_analog_outputs'])
            states = [initial(cfg) for _ in p['methods']]
            wcfg = [FixedFourLaneWindowConfig(cfg, selection=m['selection']) for m in p['methods']]
            with gzip.open(folder/(name+'_records.jsonl.gz'), 'wt', encoding='utf-8') as records, \
                 gzip.open(folder/(name+'_windows.jsonl.gz'), 'wt', encoding='utf-8') as windows:
                for w in range(p['budget']['windows']):
                    if w == p['controls']['checkpoint_window']:
                        write(folder/(name+'_checkpoint.json'), {'global_conversion':120*w,
                            'analog':analog.as_tuple(), 'digital':[asdict(s) for s in states]})
                    rows, raw_rows = [], []
                    for n in range(120*w, 120*(w+1)):
                        d1,d2 = tuple(-1 if word(p['seed'],stream,n)>>63 == 0 else 1 for stream in (2,3))
                        x = float(tone[n % len(tone)])
                        before = analog.as_tuple()
                        result = process(x, pipeline, phases, analog, sample_index=n,
                                         dither_symbols=(d1,d2), nonidealities=truth(case))
                        check_physical(result)
                        analog = result.next_state
                        sample = digital_sample(result.pipeline)
                        rows.append(FourLaneConversion(n, n%4, sample))
                        raw_rows.append({'n':n, 'x':x, 'd':[d1,d2], 'before':before,
                            'starts':result.tracking_starts, 'targets':result.static_targets,
                            'outputs':analog.as_tuple(), 'nominal':[4*result.pipeline.stage1.residue_preamp,
                                4*result.pipeline.stage2.residue_preamp],
                            'word':[sample.stage1_symbol,sample.stage2_symbol,sample.backend_centered_code],
                            'unit':integer_code(correct_two_stage_fixed_observed(sample,cfg.cascade))})
                    results = [correct_fixed_four_lane_window(rows, st, wc) for st,wc in zip(states,wcfg)]
                    for index, result in enumerate(results):
                        for bank in (result.stage1_update,result.stage2_update):
                            if bank.requested_deltas != bank.applied_deltas:
                                raise ValueError('coefficient saturation')
                        for row,cal in zip(raw_rows,result.calibrations):
                            row.setdefault('online', []).append(integer_code(cal))
                    for row in raw_rows:
                        emit(records,row)
                    emit(windows, {'w':w, 'before':[asdict(st) for st in states],
                        'updates':[[asdict(r.stage1_update),asdict(r.stage2_update)] for r in results],
                        'after':[asdict(r.state) for r in results]})
                    states = [r.state for r in results]
                    count += 120; codes += 240; commits += 2
            print(f'{name}: all3840 physical conversions, both32-window paths saved', flush=True)
    assert sources() == frozen
    write(folder/'summary.json', {'completed':True, 'physical_conversions':count,
        'online_codes':codes, 'unit_codes':count, 'two_bank_commits':commits,
        'source_hashes_unchanged':True, 'physical_overloads':0,'coefficient_saturations':0,'output_clips':0})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('folder',type=Path)
    out = parser.parse_args().folder.resolve()
    out.mkdir(parents=True, exist_ok=False)
    try:
        run(out)
    except Exception:
        write(out/'failure.json', {'passed':False,'traceback':traceback.format_exc()})
        raise
