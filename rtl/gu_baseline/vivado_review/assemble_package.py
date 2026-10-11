"""Assemble a portable review packet; compiled caches and huge WDBs stay local."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]

def copy_file(source,target):
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,target)

def copy_tree(source,target):
    if source.exists(): shutil.copytree(source,target)

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('work',type=Path)
    parser.add_argument('destination',type=Path)
    args=parser.parse_args()
    work,dest=args.work.resolve(),args.destination.resolve()
    if dest.exists(): raise SystemExit('Refusing to overwrite a delivered packet')
    dest.mkdir(parents=True)
    for source,name in [('ADC_Circuit_Review_v2.pptx','ADC_Circuit_Review.pptx'),
                        ('ADC_Circuit_Review.pdf','ADC_Circuit_Review.pdf'),
                        ('Reproduction_Guide.pdf','Reproduction_Guide.pdf')]:
        copy_file(work/'output'/source,dest/name)
    copy_file(HERE/'REPRODUCE.md',dest/'REPRODUCE.md')
    baseline=work/'hardware'
    hardware=dest/'hardware'
    for directory in ('sources','vectors','reports','netlists','checkpoints','schematics','logs'):
        copy_tree(baseline/directory,hardware/directory)
    for name in ('manifest.json','integration_revisions.json','project_paths_verified.txt'):
        copy_file(baseline/name,hardware/name)
    for name in ('build.tcl','rebuild.ps1','export_schematics.tcl','inspect_local.tcl','short_demo.tcl','show_states.tcl','validate.py','review_protocol.json'):
        copy_file(HERE/name,hardware/name)
    for name in ('gu_review.xpr',): copy_file(baseline/'project'/name,hardware/'project'/name)
    for directory in ('gu_review.srcs','gu_review.runs'):
        copy_tree(baseline/'project'/directory,hardware/'project'/directory)
    constraints=list((hardware/'project/gu_review.srcs/constrs_1').rglob('review.xdc'))
    assert len(constraints)==1
    copy_file(constraints[0],hardware/'review.xdc')
    assert 'set_input_transition' not in (hardware/'review.xdc').read_text()
    for name in ('arithmetic.vcd','bank.vcd','online_repaired.vcd','cost_rtl_repaired.vcd','cost_netlist_repaired.vcd'):
        copy_file(baseline/'sim'/name,hardware/'sim'/name)
    copy_tree(baseline/'sim/waves',hardware/'sim/waves')
    # Keep only already reviewed Simulink sources/summaries and current figures.
    behavior=dest/'behavior'
    for p in (REPO/'simulink_adc').iterdir():
        if p.is_file() and (p.suffix in ('.slx','.m','.py','.ps1','.md','.json') or p.name in ('signal_flow.png','stage_detail.png','learning_detail.png','digital_detail.png')):
            copy_file(p,behavior/p.name)
    copy_tree(REPO/'simulink_adc/blocks',behavior/'blocks')
    for p in (REPO/'simulink_adc/performance_figures').glob('reduced_*'):
        copy_file(p,behavior/'performance_figures'/p.name)
    # Reports retain exact original project-relative source locations in prose.
    report=(REPO/'docs/reports/CIRCUIT_REVIEW_VIVADO_RESULTS_2026-10-11.md').read_text(encoding='utf-8')
    report=re.sub(r'\[([^\]]+)\]\((?!https?://)([^)]+)\)',lambda m:m[1]+'（原项目路径：`'+m[2]+'`）',report)
    (dest/'RESEARCH_RESULTS.md').write_text(report,encoding='utf-8')
    for rel in ('docs/stages/03_gu_baseline/DIGITAL_BUS_AND_DUAL_PATH_SOURCE_AUDIT_V1.md',
                'docs/stages/03_gu_baseline/CANDIDATE_A_EXACT_UPDATE_ARITHMETIC_V1.md',
                'docs/stages/03_gu_baseline/DIGITAL_INTERFACE_CANDIDATE_A_V1.md'):
        copy_file(REPO/rel,dest/'notes'/Path(rel).name)
    for name in ('figure_provenance.json','rtl_state_trace.svg','rtl_state_trace.png','behavior_metrics.svg','behavior_metrics.png'):
        copy_file(work/'assets'/name,dest/'figures'/name)
    for trial in ('timing_rebuilt_v1','timing_width_v1'):
        source=work/trial
        if not (source/'tool_complete.txt').exists(): raise SystemExit('Unfinished timing trial: '+trial)
        for directory in ('sources','vectors','reports','netlists','logs','checkpoints'):
            copy_tree(source/directory,dest/'timing_trials'/trial/directory)
        copy_file(source/'project/gu_review.xpr',dest/'timing_trials'/trial/'project/gu_review.xpr')
        for directory in ('gu_review.srcs','gu_review.runs'):
            copy_tree(source/'project'/directory,dest/'timing_trials'/trial/'project'/directory)
        for name in ('build.tcl','manifest.json','review_protocol.json','width_trial.json','validation.json','comparison_validation.json'):
            if (source/name).exists(): copy_file(source/name,dest/'timing_trials'/trial/name)
    for name in ('prepare_width_trial.py','tb_review_pwl_equivalence.sv','build.tcl'):
        copy_file(HERE/name,dest/'timing_trials/scripts'/name)
    copy_file(work/'timing_comparison.json',dest/'timing_trials/timing_comparison.json')
    xpr=hardware/'project/gu_review.xpr'
    paths=[f.attrib['Path'] for f in ET.parse(xpr).iter('File')]
    actual=[]
    resolved_counts={}
    for project in [xpr,*sorted((dest/'timing_trials').glob('*/project/gu_review.xpr'))]:
        references=[]
        for file in ET.parse(project).iter('File'):
            value=file.attrib['Path']
            if value.startswith('$PPRDIR/'):
                references.append((project.parent/value[len('$PPRDIR/'):]).resolve())
            elif value.startswith('$PSRCDIR/'):
                references.append((project.parent/(project.stem+'.srcs')/value[len('$PSRCDIR/'):]).resolve())
            else:raise AssertionError('External source path: '+value)
        assert all(p.is_file() and p.is_relative_to(dest) for p in references)
        resolved_counts[project.relative_to(dest).as_posix()]=len(references)
        if project==xpr:actual=references
    assert len(actual)==12
    manifest=json.loads((hardware/'manifest.json').read_text(encoding='utf-8'))
    frozen={rel:sha for rel,sha in manifest['source_sha256'].items() if not rel.startswith('rtl/gu_baseline/vivado_review/')}
    assert len(frozen)==9
    assert all(digest(REPO/rel)==sha and digest(hardware/'sources'/Path(rel).name)==sha for rel,sha in frozen.items())
    assert digest(hardware/'vectors/online.txt')==manifest['vectors_sha256']
    assert len((hardware/'vectors/online.txt').read_text().splitlines())==8263
    subprocess.run([sys.executable,str(hardware/'validate.py'),str(hardware),'--snapshot-only'],check=True,capture_output=True,text=True)
    assert json.loads((hardware/'validation.json').read_text())['passed']
    metadata={'date':'2026-10-11','vivado':'2026.1 Build 6511674','part':'xc7a100tcsg324-1',
        'frozen_core_files':9,'resolved_project_sources_and_constraints':resolved_counts,
        'finite_functional_checks':'173872 deltas / 869360 saturation / 22 bank / 8263 eight-state / 8391 RTL and netlist outputs / negative control',
        'effective_constraints':json.loads((hardware/'review_protocol.json').read_text()),
        'timing_scope':'synthesized estimate; 100MHz failed; no place/route, board or analog transistor validation',
        'presentation_primary':'editable PPTX; PDF is exact static rendering',
        'new_installs':0,
        'source_sha256':{str(p.relative_to(dest)).replace('\\','/'):digest(p) for p in sorted(dest.rglob('*')) if p.is_file()}}
    (dest/'assembly_manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
    zip_path=dest/'ADC_Circuit_Review_Package.zip'
    with zipfile.ZipFile(zip_path,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(dest.rglob('*')):
            if p.is_file() and p!=zip_path: z.write(p,p.relative_to(dest).as_posix())
    with zipfile.ZipFile(zip_path) as z:
        assert z.testzip() is None
        archive_entries=len(z.namelist())
    receipt={'archive':str(zip_path),'archive_sha256':digest(zip_path),'archive_bytes':zip_path.stat().st_size,
        'archive_entries':archive_entries,'zip_crc_check':True,'relative_source_paths':True,'frozen_core_unchanged':True,
        'six_slide_and_one_page_visual_review':'final PPTX imported and rendered; final PDFs rendered with Poppler and all pages inspected',
        'presentation_font':'Microsoft YaHei; PDF guide font embedded','timing_passed':False}
    (dest/'delivery_validation.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
