"""Freeze provenance and exact boundary states before any EXP070 run."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import traceback
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')


def digest(path):
    h = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4*1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def relative(path):
    return path.relative_to(ROOT).as_posix()


def check(folder):
    for name in ('source_hashes.json', 'data_hashes.json'):
        for path, expected in read(folder/name).items():
            assert digest(ROOT/path) == expected, path


def prepare(folder, preflight, accepted):
    assert folder.is_relative_to(ROOT/'artifacts/runs/EXP_070')
    folder.mkdir(parents=True, exist_ok=False)
    p = read(Path(__file__).with_name('protocol.json'))
    write(folder/'protocol.json', p)
    contract = ROOT/p['sources']['accepted_contract']
    assert read(contract/'delivery_validation.json')['passed']
    for name, expected in read(contract/'original_source_hashes.json').items():
        assert digest(ROOT/name) == expected, name
    if not preflight:
        assert accepted is not None and read(accepted/'verification.json')['passed']
        assert read(accepted/'runplan.json')['preflight']
        check(accepted)
        assert digest(accepted/'protocol.json') == digest(folder/'protocol.json')
        write(folder/'accepted_preflight.json', read(accepted/'verification.json'))
    for name in ('architecture_protocol', 'model_protocol'):
        shutil.copyfile(ROOT/p[name], folder/(name+'.json'))
    seeds = p['seeds'][:1] if preflight else p['seeds']
    paths = {}
    files = {}
    for source_name in ('startup_base', 'startup_quarter', 'switch_base'):
        source = ROOT/p['sources'][source_name]
        assert read(source/'delivery_validation.json')['passed']
        manifest = read(source/'delivery_hashes.json')
        names = ['protocol.json', 'analysis.json', 'verification.json', 'delivery_validation.json']
        if source_name == 'startup_base':
            names += ['tone.bin']
        for case in p['cases']:
            for seed in seeds:
                stem = f'{case}_{seed}'
                if source_name == 'startup_base':
                    names += [stem+'_words.bin', stem+'_outputs.bin', stem+'_point30_q22.bin', stem+'_full120_q22.bin']
                elif source_name == 'startup_quarter':
                    names += [stem+'_outputs.bin', stem+'_quarter_point30_q22.bin', stem+'_quarter_full120_q22.bin']
                else:
                    for variant in p['variants']:
                        target = f'{case}_{variant}_{seed}'
                        names += [target+'.json', target+'_words.bin', target+'_outputs.bin',
                                  target+'_point30_q22.bin', target+'_full120_q22.bin']
        for name in names:
            actual = digest(source/name)
            assert actual == manifest[name], (source_name, name)
            files[relative(source/name)] = actual
        paths[source_name] = source
    files[relative(contract/'delivery_validation.json')] = digest(contract/'delivery_validation.json')
    write(folder/'data_hashes.json', files)
    shutil.copyfile(paths['startup_base']/'tone.bin', folder/'tone.bin')
    tasks = []

    def specs(case, seed, rates, variants, start):
        result = []
        for rate in rates:
            for variant in variants:
                for method in p['methods']:
                    if variant == 'fresh':
                        initial = [1 << 22]*8
                    else:
                        stem = f'{case}_{seed}'
                        source = paths['startup_base' if rate['name'] == 'base' else 'startup_quarter']
                        suffix = ('_' if rate['name'] == 'base' else '_quarter_')+method['name']+'_q22.bin'
                        dtype = '<f8' if rate['name'] == 'base' else '<i4'
                        state = np.memmap(source/(stem+suffix), dtype=dtype, mode='r', shape=(65537,8))
                        value = state[start]*(1 << 22) if rate['name'] == 'base' else state[start]
                        assert np.array_equal(value, np.rint(value))
                        initial = np.asarray(value, dtype=np.int64).tolist()
                    result.append({'name':rate['name']+'_'+variant+'_'+method['name'],
                        'rate':rate['name'],'variant':variant,'method':method['name'],
                        'num':rate['numerator'],'den':rate['denominator'],
                        'selected':method['selected'],'multiplier':method['multiplier'],'initial':initial})
        return result

    for case in p['cases']:
        for seed in seeds:
            stem = f'{case}_{seed}'
            rates = p['rates'] if preflight else p['rates'][1:]
            spec = specs(case,seed,rates,p['variants'],32768)
            word_file = relative(paths['switch_base']/f'{case}_carry_{seed}_words.bin')
            tasks.append({'stem':stem,'case':case,'seed':seed,'kind':'main','word_file':word_file,
                'word_start':0,'global_start':3932160,'windows':32 if preflight else 32768,'paths':spec})
            if preflight:
                tasks.append({'stem':stem+'_nochange','case':case,'seed':seed,'kind':'nochange',
                    'word_file':relative(paths['startup_base']/(stem+'_words.bin')),'word_start':32766,
                    'global_start':32766*120,'windows':34,'paths':specs(case,seed,p['rates'],['carry'],32766)})
                quarter = specs(case,seed,p['rates'][1:],p['variants'],32768)
                tasks.append({'stem':stem+'_split_a','case':case,'seed':seed,'kind':'restart',
                    'word_file':word_file,'word_start':0,'global_start':3932160,'windows':16,'paths':quarter})
                tasks.append({'stem':stem+'_split_b','case':case,'seed':seed,'kind':'restart',
                    'word_file':word_file,'word_start':16,'global_start':3932160+16*120,'windows':16,
                    'paths':quarter,'resume_task':stem+'_split_a'})
    write(folder/'runplan.json', {'preflight':preflight,'tasks':tasks})
    all_sources = []
    for directory in ('src','rtl','experiments/exp_057_static_two_stage_million',
        'experiments/exp_059_static_fixed_million','experiments/exp_060_static_auxiliary_preflight',
        'experiments/exp_061_static_auxiliary_million','experiments/exp_062_same_input_background',
        'experiments/exp_066_input_switch_tracking_long','experiments/exp_069_gu_learning_rate',
        'experiments/exp_070_gu_learning_rate_switch'):
        all_sources.extend(path for path in (ROOT/directory).rglob('*') if path.is_file()
            and path.suffix in ('.py','.cs','.ps1','.json','.md','.sv','.v') and '__pycache__' not in path.parts)
    all_sources.append(ROOT/'configs/architectures/gu_behavioral_v1.yaml')
    write(folder/'source_hashes.json', {relative(path):digest(path) for path in sorted(set(all_sources))})
    docs = ['docs/STATUS.md','docs/DECISIONS.md','docs/README.md',
        'docs/RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md',
        'docs/reports/GU_ALGORITHM_EVALUATION_V1.md','docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
        'docs/theory/README.md','docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md',
        'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
        'docs/theory/EXCITATION_AND_CONSTRAINED_STABILITY_V1.md',
        'docs/theory/MILLION_SAMPLE_SCALAR_MEAN_NOISE_AND_QUANTIZATION_V1.md',
        'docs/reports/experiments/README.md']
    for name in docs:
        target = folder/'documents_before'/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name,target)
    check(folder)
    print('prepared',len(tasks),'tasks; data files',len(files),'executable/source entries',len(all_sources),flush=True)


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path)
    parser.add_argument('--preflight',action='store_true');parser.add_argument('--accepted',type=Path)
    args=parser.parse_args();folder=args.folder.resolve()
    try:prepare(folder,args.preflight,args.accepted.resolve() if args.accepted else None)
    except Exception:
        if folder.exists():write(folder/'prepare_failure.json',{'traceback':traceback.format_exc()})
        raise
