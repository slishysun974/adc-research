"""Post-run archive and document/link checks; no learner/source mutations."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import re
import shutil
from .verify import ROOT, load, sources, digest
from experiments.exp_057_static_two_stage_million.common import write

DOCS = ['docs/README.md','docs/STATUS.md','docs/DECISIONS.md',
        'docs/RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md',
        'docs/reports/experiments/README.md','docs/reports/experiments/EXP_069_GU_LEARNING_RATE_V1.md',
        'docs/reports/GU_ALGORITHM_EVALUATION_V1.md','docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
        'docs/theory/README.md','docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md',
        'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
        'docs/theory/MILLION_SAMPLE_SCALAR_MEAN_NOISE_AND_QUANTIZATION_V1.md',
        'docs/stages/03_gu_baseline/README.md','docs/stages/04_new_algorithm/README.md']


def deliver(folder, preflight):
    p,_,_=load(folder)
    short=json.loads((preflight/'verification.json').read_text())
    verify=json.loads((folder/'verification.json').read_text())
    result=json.loads((folder/'summary.json').read_text())
    assert short['passed'] and verify['passed']
    assert result['new_paths']==p['budget']['new_paths']==90
    assert verify['all_output_codes_replayed']==result['new_output_codes']==p['budget']['new_output_codes']
    assert verify['all_bank_pair_commits_replayed']==p['budget']['new_bank_pair_commits']
    assert len(result['groups'])==24 and not result['rate_selected']
    analysis=json.loads((folder/'analysis.json').read_text())
    terminal=[]
    for row in analysis['paths']:
        checks=row['convergence']['intervals'];suffix=0
        for item in reversed(checks):
            if not item['passed']:break
            suffix+=1
        terminal.append({key:row[key] for key in ('case','rate','method','seed')} | {
            'last_interval_passed':bool(checks[-1]['passed']),
            'terminal_passing_intervals':suffix,
            'terminal_first_end_block':checks[len(checks)-suffix]['end_block_exclusive'] if suffix else None})
    write(folder/'terminal_criterion.json',{'paths':terminal,
        'last_interval_passing_paths':sum(r['last_interval_passed'] for r in terminal),
        'suffix_is_finite_descriptor_not_convergence_proof':True})
    sources(preflight);sources(folder)
    archived={}
    for directory, entries in ((preflight, {'exp069_preflight_run.log':'run.log','exp069_preflight_verify.log':'verification.log'}),
            (folder, {'exp069_background_run.log':'run.log','exp069_background_verify.log':'verification.log',
                      'exp069_analysis.log':'analysis.log','exp069_regression.log':'regression.log'})):
        dest=directory/'logs';dest.mkdir(exist_ok=True)
        for original,name in entries.items():
            src=ROOT/'tmp'/original;target=dest/name
            shutil.copyfile(src,target);assert digest(src)==digest(target)
            archived[str(target.relative_to(ROOT))]=digest(target)
    assert 'Ran 499 tests' in (folder/'logs/regression.log').read_text(encoding='utf-8')
    assert (folder/'logs/regression.log').read_text(encoding='utf-8').rstrip().endswith('OK')
    missing=[]
    for relative in DOCS:
        file=ROOT/relative
        for link in re.findall(r'\]\(([^)]+)\)',file.read_text(encoding='utf-8')):
            if '://' in link or link.startswith('#'):continue
            target=link.split('#')[0]
            if target and not (file.parent/target).exists():missing.append((relative,link))
    assert not missing,missing
    write(folder/'accepted_preflight.json',short)
    write(folder/'delivery_validation.json',{
        'passed':True,'preflight_paths':24,'new_long_paths':90,'reused_base_paths':30,
        'all_output_codes_replayed':verify['all_output_codes_replayed'],
        'all_bank_pair_commits_replayed':verify['all_bank_pair_commits_replayed'],
        'new_learning_observations_per_stage':result['new_learning_observations_per_stage'],
        'independent_scored_blocks':result['independent_blocks_checked'],
        'regression_tests':499,'source_and_data_unchanged':True,'missing_links':missing,
        'archived_logs':archived,'documents':{name:digest(ROOT/name) for name in DOCS},
        'post_run_validator_sha256':digest(Path(__file__)),
        'theoretical_convergence_proved':False,'chip_fidelity_proved':False,'rate_selected':False})
    files={f.name:digest(f) for f in folder.iterdir() if f.is_file() and f.name!='delivery_hashes.json'}
    write(folder/'delivery_hashes.json',files)
    print(json.dumps({'delivery_passed':True,'files_hashed':len(files),'docs':len(DOCS),'logs':len(archived)}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);parser.add_argument('preflight',type=Path)
    args=parser.parse_args();deliver(args.folder.resolve(),args.preflight.resolve())
