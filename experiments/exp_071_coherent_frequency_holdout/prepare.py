"""Freeze EXP071 final implementation and data roles before generation."""
import argparse
from pathlib import Path
import platform
import shutil
import time
import traceback

import numpy as np

from experiments.exp_069_gu_learning_rate.check_normal_loss_limits import ROOT,load,write,digest,relative,verify_hashes

HERE=Path(__file__).resolve().parent
DEPENDENCIES=[f'experiments/exp_{n}/{"Kernel.cs"}' for n in (
    '057_static_two_stage_million','059_static_fixed_million','061_static_auxiliary_million',
    '062_same_input_background','069_gu_learning_rate','070_gu_learning_rate_switch')]


def check(folder):
    for name in ('source_hashes.json','data_hashes.json'):
        verify_hashes(load(folder/name))


def source_manifest():
    files=list((ROOT/'src').rglob('*.py'))
    files += [p for p in HERE.iterdir() if p.suffix in ('.py','.cs','.ps1','.json')]
    files += [ROOT/n for n in DEPENDENCIES]
    files += [ROOT/n for n in (
        'configs/architectures/gu_behavioral_v1.yaml',
        'experiments/exp_057_static_two_stage_million/common.py',
        'experiments/exp_060_static_auxiliary_preflight/run.py',
        'experiments/exp_062_same_input_background/verify.py',
        'experiments/exp_062_same_input_background/analyze.py',
        'experiments/exp_069_gu_learning_rate/check_normal_loss_limits.py',
        'experiments/exp_070_gu_learning_rate_switch/analyze.py')]
    return {relative(p):digest(p) for p in sorted(set(files))}


def prepare(folder,preflight,accepted=None):
    assert folder.parent==ROOT/'artifacts/runs/EXP_071','direct EXP071 run folder required'
    folder.mkdir(parents=True,exist_ok=False)
    p=load(HERE/'protocol.json');e=load(HERE/'execution_contract_v1.json')
    boundary=ROOT/e['accepted_boundary'];old=ROOT/'artifacts/runs/EXP_071/preflight_v2_diagnostic'
    assert load(boundary/'verification.json')['boundary_preflight_accepted']
    sources=source_manifest()
    if not preflight:
        assert accepted is not None
        check(accepted);v=load(accepted/'verification.json')
        assert v['passed'] and v['preflight'] and v['long_ready']
        assert load(accepted/'source_hashes.json')==sources,'final sources changed after preflight'
        assert not v['confirmation_opened']
    write(folder/'source_hashes.json',sources)
    for source,name in ((HERE/'protocol.json','protocol.json'),(HERE/'execution_contract_v1.json','execution_contract_v1.json'),
                        (HERE/'boundary_contract_v2.json','boundary_contract_v2.json'),(ROOT/p['source_architecture_protocol'],'architecture_protocol.json')):
        shutil.copyfile(source,folder/name)
    # Full prior deliveries remain immutable; no used confirmation data exists yet.
    data={}
    for parent in (old,boundary):
        manifest=load(parent/'delivery_hashes.json')
        data.update({relative(parent/name):value for name,value in manifest.items()})
        data[relative(parent/'delivery_hashes.json')]=digest(parent/'delivery_hashes.json')
    if accepted:
        for name,value in load(accepted/'delivery_hashes.json').items():data[relative(accepted/name)]=value
        data[relative(accepted/'delivery_hashes.json')]=digest(accepted/'delivery_hashes.json')
    origin=ROOT/p['input']['original_tone_file']
    assert digest(origin)==p['input']['original_tone_sha256']
    data[relative(origin)]=digest(origin)
    verify_hashes(data)
    write(folder/'data_hashes.json',data)
    free=shutil.disk_usage(folder).free
    assert free>=2*(1<<30),'2GiB raw/metadata reserve required'
    write(folder/'resource_assessment.json',{'free_bytes_before_sources':free,'raw_design_bytes':p['storage_design']['raw_total_bytes_excluding_tables_metadata_probes_logs'],
        'reserved_bytes':2*(1<<30),'long_source_learning_rough_estimate_seconds':None if preflight else load(accepted/'timing.json')['source_and_learner_seconds']*128*20/4,
        'estimate_is_not_hardware_throughput':True})
    write(folder/'environment.json',{'python':platform.python_version(),'numpy':np.__version__,'platform':platform.platform()})
    base=np.fromfile(origin,dtype='<f8');assert len(base)==30720
    cases=[c for c in p['cases'] if c['role']=='development'] if preflight else p['cases']
    if preflight:cases=cases+[{'name':'old127_control','role':'mechanism','tone_bin':127},{'name':'ideal509','role':'mechanism','tone_bin':509,'ideal':True}]
    tables={}
    for c in cases:
        assert c['tone_bin'] not in p['future_algorithm_reservation']['tone_bins']
        name=c['name']+'_tone.bin';idx=(c['tone_bin']*pow(127,-1,len(base))*np.arange(len(base)))%len(base)
        base[idx].astype('<f8').tofile(folder/name);tables[name]=digest(folder/name)
    data.update({relative(folder/name):value for name,value in tables.items()});write(folder/'data_hashes.json',data)
    seeds=[p['preflight_seed']] if preflight else p['seeds']
    specs=[{'name':r['name']+'_'+m['name'],'rate':r['name'],'method':m['name'],'variant':'fresh',
            'num':r['numerator'],'den':r['denominator'],'selected':m['selected'],'multiplier':m['multiplier'],'initial':[1<<22]*8}
           for r in p['rate_scales'] for m in p['methods']]
    source_tasks=[];tasks=[]
    for c in cases:
        for seed in seeds:
            stem=c['name']+'_'+str(seed)
            source_tasks.append({'stem':stem,'case':c['name'],'role':c['role'],'tone_bin':c['tone_bin'],'seed':seed,
                'tone_file':relative(folder/(c['name']+'_tone.bin')),'windows':32 if preflight else 32768,'ideal':c.get('ideal',False)})
            if c.get('ideal',False):continue
            task={'stem':stem,'case':c['name'],'role':c['role'],'tone_bin':c['tone_bin'],'seed':seed,'word_file':relative(folder/(stem+'_words.bin')),
                  'word_start':0,'global_start':0,'windows':32 if preflight else 32768,'paths':specs,'kind':'main'}
            tasks.append(task)
            if preflight and c['name']=='dev_509':
                tasks.append(dict(task,stem=stem+'_split_a',windows=16,kind='restart'))
                tasks.append(dict(task,stem=stem+'_split_b',windows=16,word_start=16,global_start=1920,kind='restart',resume_task=stem+'_split_a'))
    controls=[]
    if preflight:
        for model in ('both_smooth','ideal'):
            controls.append({'name':model+'_endpoint','word_file':relative(old/(model+'_endpoint_words.bin')),'codes':[1024]*8,'limit':-1,'kind':'endpoint'})
        for c in ('dev_509','dev_1009','old127_control'):
            for h,k in enumerate(p['balanced_permutation_control_budget']['fixed_coefficient_states_q1_10']):
                controls.append({'name':c+'_fixed_'+str(h),'word_file':relative(folder/(c+'_'+str(seeds[0])+'_words.bin')),'codes':k,'limit':120,'kind':'mixed'})
    write(folder/'runplan.json',{'preflight':preflight,'sources':source_tasks,'tasks':tasks,'fixed_controls':controls,
        'accepted_final_preflight':None if preflight else relative(accepted),'confirmation_opened_by_this_run':not preflight,
        'future_reservation_opened':False})
    docs=['docs/STATUS.md','docs/DECISIONS.md','docs/RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md',
        'docs/reports/GU_ALGORITHM_EVALUATION_V1.md','docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
        'docs/reports/experiments/EXP_071_COHERENT_FREQUENCY_PREFLIGHT_V1.md','docs/reports/experiments/README.md',
        'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md','docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
        'docs/theory/README.md','experiments/exp_071_coherent_frequency_holdout/README.md']
    for name in docs:
        target=folder/'documents_before'/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
    check(folder)
    write(folder/'freeze_complete.json',{'preflight':preflight,'sources':len(sources),'prior_and_input_files':len(data),'tables':tables,
        'planned_source_conversions':sum(s['windows']*120 for s in source_tasks),'planned_online_outputs':sum(t['windows']*120*len(t['paths']) for t in tasks),
        'future_conditions_generated':False,'confirmation_tables_generated':not preflight})
    print('prepared final', 'preflight' if preflight else 'long','sources',len(source_tasks),'tasks',len(tasks),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);parser.add_argument('--preflight',action='store_true');parser.add_argument('--accepted',type=Path)
    a=parser.parse_args()
    try:prepare(a.folder.resolve(),a.preflight,a.accepted.resolve() if a.accepted else None)
    except Exception:
        if a.folder.exists():write(a.folder/'prepare_failure.json',{'traceback':traceback.format_exc()})
        raise
