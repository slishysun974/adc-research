"""Every digital transition independently replayed; original core at probes."""
import argparse
from dataclasses import replace
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import traceback
import numpy as np

from adc_research.theory.static_fixed_contract import readout, export, commit, nearest_even
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.fixed_four_lane_window import _bank, FourLaneConversion
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState
from adc_research.evaluation.observations import digital_sample
from experiments.exp_060_static_auxiliary_preflight.run import fixed_setup, plant, check_physical
from experiments.exp_062_same_input_background.verify import digital, round_ratio, tags, physical_words
from experiments.exp_057_static_two_stage_million.common import write

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    hasher = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4*1024*1024), b''):
            hasher.update(chunk)
    return hasher.hexdigest()


def load(folder):
    return [json.loads((folder/name).read_text(encoding='utf-8-sig')) for name in
            ('protocol.json', 'source_protocol.json', 'architecture_protocol.json')]


def sources(folder):
    for item in json.loads((folder/'source_hashes.json').read_text(encoding='utf-8-sig')):
        assert digest(Path(item['Path'])).upper() == item['Hash'], item['Path']
    p = load(folder)[0]
    for name, expected in json.loads((folder/'data_hashes.json').read_text(encoding='utf-8-sig')).items():
        assert digest(ROOT/p['source_folder']/name) == expected, name


def paths(meta, p):
    rates = {r['name']: r for r in p['rate_scales']}
    methods = {m['name']: m for m in p['methods']}
    return [(name, rates[name.split('_', 1)[0]], methods[name.split('_', 1)[1]]) for name in meta['Paths']]


def states_for(folder, stem, meta):
    return [np.memmap(folder/(stem+'_'+name+'_q22.bin'), dtype='<i4', mode='r',
                      shape=(meta['Windows']+1, 8)) for name in meta['Paths']]


def verify(folder):
    p, src, arch = load(folder)
    source = ROOT/p['source_folder']; n = p['input']['samples_per_block']; bw = n//120
    tone = np.fromfile(folder/'tone.bin', dtype='<f8')
    assert np.array_equal(tone, np.fromfile(source/'tone.bin', dtype='<f8'))
    pipeline, cfg = fixed_setup(arch)
    controls = 0
    for den in (2, 4, 125, 250, 500, 4096):
        for num in range(-128, 129):
            assert int(round_ratio(np.array(num, dtype=np.int64), den)) == nearest_even(F(num, den))
            controls += 1
    conversions = commits = probe_readouts = core_commits = platform_probes = base_codes = base_states = 0
    streams = 0; maximum_voltage = 0.0
    for case in src['cases']:
        for seed in p['seeds']:
            stem = f"{case['name']}_{seed}"
            if not (folder/(stem+'.json')).exists():
                continue
            meta = json.loads((folder/(stem+'.json')).read_text(encoding='utf-8-sig'))
            nw = meta['Windows']; preflight = nw == p['preflight']['windows']; desc = paths(meta, p)
            count = nw*120
            words = np.memmap(source/(stem+'_words.bin'), dtype='i1', mode='r', shape=(src['budget']['windows_per_path'],120,4))
            output = np.memmap(folder/(stem+'_outputs.bin'), dtype='<i2', mode='r', shape=(nw,120,len(desc)))
            reference = np.memmap(source/(stem+'_outputs.bin'), dtype='<i2', mode='r', shape=(src['budget']['windows_per_path'],120,3))
            state = states_for(folder, stem, meta)
            assert (folder/(stem+'_outputs.bin')).stat().st_size == count*len(desc)*2
            for st in state:
                assert np.array_equal(st[0], np.full(8, 1 << 22))
            requested_clips = np.zeros(len(desc), dtype=np.int64)
            for block, start in enumerate(range(0, nw, bw)):
                stop = min(start+bw, nw); part = words[start:stop]
                indices = np.arange(start*120, stop*120); dd1, dd2 = tags(seed, indices)
                assert np.array_equal(part[:,:,3].ravel(), (dd1 > 0)+2*(dd2 > 0))
                # Independent physical vector formula for each source word used.
                native = physical_words(tone[indices % n], dd1, dd2, case)
                for h, actual in enumerate(native):
                    assert np.array_equal(part[:,:,h].ravel(), actual)
                unit = digital(part, np.full((stop-start,8), 1 << 22, dtype=np.int64))[0]
                assert np.array_equal(unit, reference[start:stop,:,0])
                for h, (name, rate, method) in enumerate(desc):
                    acc = np.asarray(state[h][start:stop], dtype=np.int64)
                    after = np.asarray(state[h][start+1:stop+1], dtype=np.int64)
                    y, gates, basis, products = digital(part, acc)
                    assert np.array_equal(y, output[start:stop,:,h]), (stem, name, block, 'output')
                    sums = products[:,:method['selected']].sum(axis=1)
                    factors = np.array([-2,-6,-12,-24,-32,-96,-192,-384], dtype=np.int64)
                    requests = round_ratio(sums*factors*method['multiplier']*rate['numerator'], 125*rate['denominator'])
                    unclipped = acc+requests
                    requested_clips[h] += np.count_nonzero((unclipped < 0)|(unclipped > 2047*4096))
                    assert np.array_equal(np.clip(unclipped,0,2047*4096), after), (stem, name, block, 'commit')
                    for key, span in (('All',120),('Selected',method['selected'])):
                        saved = meta['Blocks'][block][key][h]
                        for field, actual in (('Gates',gates[:,:span].sum(axis=(0,1))),
                                              ('Basis',basis[:,:span].sum(axis=(0,1))),
                                              ('Both',(gates[:,:span]&basis[:,:span]).sum(axis=(0,1))),
                                              ('Correlations',products[:,:span].sum(axis=(0,1)))):
                            assert np.array_equal(saved[field], actual), (stem,name,block,field)
                    for field, actual in (('ZeroRequest',(requests==0).sum(axis=0)),
                                          ('NonzeroSumZero',((requests==0)&(sums!=0)).sum(axis=0)),
                                          ('HiddenChanged',(acc!=after).sum(axis=0)),
                                          ('ExportChanged',(round_ratio(acc,4096)!=round_ratio(after,4096)).sum(axis=0))):
                        assert np.array_equal(meta['Blocks'][block][field][h],actual), (stem,name,block,field)
                    if rate['name'] == 'base':
                        original = np.memmap(source/(stem+'_'+method['name']+'_q22.bin'),dtype='<f8',mode='r',shape=(src['budget']['windows_per_path']+1,8))
                        assert np.array_equal(state[h][start:stop+1], original[start:stop+1]*(1 << 22))
                        assert np.array_equal(y, reference[start:stop,:,1+h%2])
                        base_codes += 120*(stop-start); base_states += 8*(stop-start)
                    conversions += 120*(stop-start); commits += stop-start
            assert np.array_equal(requested_clips,meta['CoefficientClips'])
            assert np.array_equal(np.count_nonzero((output<0)|(output>4095),axis=(0,1)),meta['OutputClips'])
            keep = set(range(nw)) if preflight else {b*bw+j for b in p['verification']['long_probe_blocks'] for j in range(4)} | set(range(nw-4,nw))
            for w in sorted(keep):
                conversions_core = []
                local_values = [[[],[]] for _ in desc]
                independent_sums = np.zeros((len(desc),8), dtype=np.int64)
                old = [tuple(int(v) for v in st[w]) for st in state]
                ks = [tuple(F(v,1024) for v in export(a)) for a in old]
                cascades = [replace(cfg.cascade,
                    stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=export(a)[:4]),
                    stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=export(a)[4:])) for a in old]
                for j, digital_word in enumerate(words[w]):
                    q1,q2,be,bits = map(int,digital_word); d1,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
                    if preflight:
                        original = plant(float(tone[(w*120+j)%n]),d1,d2,case,pipeline,w*120+j)
                        check_physical(original); sample = digital_sample(original.pipeline)
                        assert (sample.stage1_symbol,sample.stage2_symbol,sample.backend_centered_code)==(q1,q2,be)
                        platform_probes += 1
                    else:
                        from adc_research.calibration.observation import DigitalCalibrationSample
                        sample = DigitalCalibrationSample(q1,q2,be,d1,d2)
                    conversions_core.append(FourLaneConversion(w*120+j,j%4,sample))
                    for h, (name, rate, method) in enumerate(desc):
                        rd = readout(q1,q2,F(be),d1,d2,ks[h],data_q3=True)
                        core = correct_two_stage_fixed_observed(sample,cascades[h])
                        assert core.unclipped_output_scaled == 8*rd.output
                        assert core.stage1_raw_scaled == 8*rd.raw1
                        assert nearest_even(rd.output)==output[w,j,h]
                        for bank, y in enumerate((rd.y1,rd.y2)):
                            local_values[h][bank].append((512*d1 if bank==0 else 128*d2,int(8*y)))
                            if j < method['selected']:
                                for coord, gate in enumerate(rd.gates[bank]):
                                    independent_sums[h,4*bank+coord] += int((64*d1 if bank==0 else 16*d2)*y*gate)
                        probe_readouts += 1
                for h, (name, rate, method) in enumerate(desc):
                    ratio = F(rate['numerator'],rate['denominator'])
                    steps = tuple(mu*ratio for mu in cfg.stage1_lms.step_sizes+cfg.stage2_lms.step_sizes)
                    requests, expected = commit(old[h],tuple(F(int(v)) for v in independent_sums[h]),method['multiplier'],steps)
                    assert expected == tuple(int(v) for v in state[h][w+1])
                    for bank, bcfg in enumerate((cfg.stage1_lms,cfg.stage2_lms)):
                        updated_cfg = replace(bcfg,step_sizes=tuple(mu*ratio for mu in bcfg.step_sizes))
                        bs = FixedGatedLmsState(old[h][4*bank:4*bank+4],(0,)*4,(0,)*4,(0,)*4,w*120)
                        core = _bank(bs,updated_cfg,conversions_core,local_values[h][bank],tuple(j<method['selected'] for j in range(120)),method['multiplier'])
                        assert core.requested_deltas == requests[4*bank:4*bank+4]
                        assert core.state.accumulator_codes == expected[4*bank:4*bank+4]
                        core_commits += 1
            streams += 1
            print('verified',stem,'paths',len(desc),'all windows',nw,flush=True)
    assert streams == (3 if preflight else 15)
    sources(folder)
    result = {'passed':True,'streams':streams,'paths':streams*(8 if preflight else 6),
        'rounding_controls':controls,'all_output_codes_replayed':conversions,
        'all_bank_pair_commits_replayed':commits,'rational_and_original_core_readouts':probe_readouts,
        'original_fixed_bank_commits':core_commits,'original_platform_probe_conversions':platform_probes,
        'base_prefix_output_codes_exact':base_codes,'base_prefix_q22_components_exact':base_states,
        'original_data_hashes_unchanged':True,'source_hashes_unchanged':True,
        'all_counters_replayed':True,'full_long_original_platform_replay':False}
    write(folder/'verification.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);folder=parser.parse_args().folder.resolve()
    try: verify(folder)
    except Exception:
        write(folder/'verification_failure.json',{'traceback':traceback.format_exc()});raise
