"""Frozen NG-36 integer-cell controls and limited old development replay.

No analog generation, online trajectory, target, FFT or holdout evaluation.
"""
import argparse
from dataclasses import replace
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys

from adc_research.theory.quantized_mean_dynamics import export_cell, certify_phase_unions
from adc_research.theory.static_fixed_contract import readout, export, commit
from adc_research.calibration.fixed_gated_lms import (
    FixedGatedLmsConfig, FixedGatedLmsState, exported_coefficient_codes,
    adaptive_lower_thresholds_scaled,
)
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.fixed_pwl import (
    FixedPwlArithmetic, FixedPwlConfig, FixedTwoStageConfig,
    correct_two_stage_fixed_observed,
)
from adc_research.calibration.observation import DigitalCalibrationSample


ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'artifacts/runs/EXP_071/final_preflight_v1'
MAXIMUM=2047*4096
FACTORS=(2,6,12,24,32,96,192,384)
DOCUMENTS=(
    'docs/STATUS.md','docs/DECISIONS.md','docs/README.md',
    'docs/RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md',
    'docs/theory/README.md','docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
    'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md',
    'docs/theory/QUANTIZED_MEAN_DYNAMICS_AND_GATE_SELECTION_V1.md',
    'docs/theory/WINDOW_MEAN_AND_GATE_MARGIN_CONDITIONS_V1.md',
    'docs/reports/GU_ALGORITHM_EVALUATION_V1.md',
    'docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
)


def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path): return json.loads(path.read_text(encoding='utf-8'))
def write(path,data): path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def check_hashes(manifest):
    for name,value in manifest.items(): assert digest(ROOT/name)==value,name


def verify_old_prefix():
    name='src/adc_research/theory/quantized_mean_dynamics.py'
    expected=load(OLD/'source_hashes.json')[name]
    prefix=(ROOT/name).read_text(encoding='utf-8').split('\ndef _box(')[0].rstrip('\n')
    candidates=[(prefix+'\n'*n).replace('\n',eol).encode('utf-8')
                for n in (1,2,3) for eol in ('\n','\r\n')]
    assert any(hashlib.sha256(value).hexdigest()==expected for value in candidates)
    return expected


def selected_tasks():
    return [task for task in load(OLD/'runplan.json')['tasks']
            if task['kind']=='main' and task['case'] in ('dev_509','dev_1009')]


def prepare(folder):
    folder.mkdir(parents=True,exist_ok=False)
    manifest=load(OLD/'delivery_hashes.json')
    names=['runplan.json','protocol.json','verification.json','source_hashes.json']
    for task in selected_tasks():
        names.append(Path(task['word_file']).name)
        names.extend(task['stem']+'_'+desc['name']+'_q22.bin' for desc in task['paths'])
    used={}
    for name in names:
        assert digest(OLD/name)==manifest[name],name
        used[(OLD/name).relative_to(ROOT).as_posix()]=manifest[name]
    assert load(OLD/'verification.json')['passed'] and load(OLD/'runplan.json')['preflight']
    old_prefix=verify_old_prefix()
    sources={Path(module.__file__).resolve().relative_to(ROOT).as_posix():digest(Path(module.__file__).resolve())
             for module in tuple(sys.modules.values()) if getattr(module,'__file__',None)
             and Path(module.__file__).resolve().is_relative_to(ROOT)
             and Path(module.__file__).suffix=='.py'}
    sources['tests/test_quantized_phase_sets.py']=digest(ROOT/'tests/test_quantized_phase_sets.py')
    sources['tests/test_quantized_mean_dynamics.py']=digest(ROOT/'tests/test_quantized_mean_dynamics.py')
    write(folder/'protocol.json',{
        'version':'NG36-quantized-phase-union-v1','date':'2026-10-12',
        'authority':'User continues D133 original conditional theory; no new algorithm design. D129 task2 bounded exact controls.',
        'question':'Can exact exported-cell translations certify finite phase unions despite gate equality? Which old unit-cell candidates fail whole-cell inclusion?',
        'positive_digital_fixture':'All four d1,d2 signs,q1=q2=0,backend=64*d1+16*d2. Unit codes1024. Rear third gate equality is retained; all eight request sums are zero. Full interior unit export cell is invariant only for this repeated declared digital window.',
        'negative_digital_fixture':'Four repeated q1=q2=0,backend80,d1=d2=+1. Retain all eight requests. A nonzero request invalidates the same full interior cell.',
        'precision_contract':'Original Q22,Q1.10,Q3,nearest-even,>= gates,120 slots,simultaneous commit,saturation[0,2047*4096]. point30 multiplier30 and full120 multiplier1; original and1/4 steps.',
        'finite_cover':'Closed integer rectangle unions; enumerate only intersecting export-code cells, exact translate/saturate each full vector and subtract next phase union. No eight-state lattice enumeration or derivative/protected-margin assumption.',
        'unit_tests':9,'targeted_and_full_invocations':2,
        'unit_enumeration_per_invocation':{'cut_point_membership':5625,'small_state_transitions':121},
        'generic_checker_caps':{'cells_per_call':256,'requests_per_call':512,'uncovered_fragments':4096},
        'development_reuse':{'cases':['dev_509','dev_1009'],'seed':202610711,
            'paths':8,'old_windows_per_path':[0,1],'window_conditions':16,
            'source_word_prefix_per_case':240,'state_vectors_per_path':3,
            'candidate':'Full eight-dimensional export cell of actual old window-start state. Test the repeated SAME frozen window; no assertion of future-window coverage.',
            'formal_hidden_probes':'Actual old state,all cell lower endpoints,all cell upper endpoints; same exported code verified by original state export.',
            'readout_caps':{'rational':992,'formal':2976},'full_cell_checks':16},
        'fixtures_budget':{'rational_readouts':8,'formal_readouts':24,'full_cell_checks':2},
        'prediction':'Rational and formal products,readouts,thresholds,gates and requests agree with saved next states. Nonzero requests cannot keep a full interior cell invariant; retain any all-zero cases and every witness.',
        'guard_and_cycle_limits':'All allowed future phase windows/request vectors must be covered. A finite union certificate does not certify future sources. Eventual periodicity additionally requires a closed deterministic augmented phase/input/PRNG state; exported-code repetition alone is insufficient.',
        'stop':'No new periods/frequencies,larger covers,score-selected states,new source,new FFT,new Gu update or long trajectory. Original failure retained if budgets or consistency fail.',
        'old_quantized_source_prefix_sha256':old_prefix,
        'new_adc_conversions':0,'new_online_learning':0,'new_online_outputs':0,
        'new_performance_scores':0,'new_fft':0,
    })
    write(folder/'original_data_hashes.json',used)
    write(folder/'execution_hashes.json',sources)
    write(folder/'environment.json',{'python':sys.version,'platform':sys.platform})
    for name in DOCUMENTS:
        target=folder/'documents_before'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,target)
    print(f'Frozen:9 exact tests,16 old windows,18 full-cell checks; {len(used)} old files/{len(sources)} sources.')


def steps(num=1,den=1):
    # The old vector replay divides Q3 D*Y by64 BEFORE applying factor/125.
    # readout products here are already physical code^2, so no further64.
    return tuple(F(factor*num,125*(1<<22)*den) for factor in FACTORS)


def configuration(codes):
    arithmetic=FixedPwlArithmetic()
    banks=tuple(FixedPwlConfig(width,tuple(bank),tuple(value/1024 for value in bank),
                              arithmetic,(False,)*4)
                for width,bank in zip((1024,256),(codes[:4],codes[4:])))
    return FixedTwoStageConfig(*banks,4096,1024,8,16384,(0,32760),
                              ({-1:-512,1:512},{-1:-128,1:128}),3)


def analyze_window(words,before,desc,counts):
    codes=export(before)
    coefficients=tuple(F(value,1024) for value in codes)
    selected=words[:desc['selected']]
    products=[F(0)]*8
    records=[]
    equalities=0
    for q1,q2,be,bits in selected:
        d1,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
        result=readout(q1,q2,F(be),d1,d2,coefficients,data_q3=True)
        values=(result.y1,result.y2)
        for bank,(d,y,gates) in enumerate(zip((64*d1,16*d2),values,result.gates)):
            for i,g in enumerate(gates): products[4*bank+i]+=d*y*g
        equalities+=sum(abs(y)==t for y,ts in zip(values,result.thresholds) for t in ts[1:])
        records.append((DigitalCalibrationSample(q1,q2,be,d1,d2),result))
    counts['rational_readouts']+=len(selected)
    rate_steps=steps(desc['num'],desc['den'])
    delta,after=commit(before,tuple(products),desc['multiplier'],rate_steps)
    cell=tuple((max(0,export_cell(code)[0]),min(MAXIMUM,export_cell(code)[1])) for code in codes)
    probes=(before,tuple(lo for lo,hi in cell),tuple(hi for lo,hi in cell))
    lms=tuple(FixedGatedLmsConfig(width,bank_steps) for width,bank_steps in
              zip((1024,256),(rate_steps[:4],rate_steps[4:])))
    for probe in probes:
        formal_codes=[]
        for bank in range(2):
            state=FixedGatedLmsState(tuple(probe[4*bank:4*bank+4]),(0,)*4,(0,)*4,(0,)*4)
            formal_codes.extend(exported_coefficient_codes(state,lms[bank]))
        assert tuple(formal_codes)==codes
        config=configuration(formal_codes)
        thresholds=tuple(adaptive_lower_thresholds_scaled(tuple(formal_codes[4*b:4*b+4]),lms[b]) for b in range(2))
        sums=[0]*8
        for observed,rational in records:
            formal=correct_two_stage_fixed_observed(observed,config)
            yy=(formal.stage1_pwl.corrected_code_scaled-formal.stage1_dither_scaled,
                formal.stage2_pwl.corrected_code_scaled-formal.stage2_dither_scaled)
            assert tuple(F(value,8) for value in yy)==(rational.y1,rational.y2)
            assert formal.unclipped_output_scaled==8*rational.output
            for bank,(y,d,ts) in enumerate(zip(yy,(formal.stage1_dither_scaled,formal.stage2_dither_scaled),thresholds)):
                gates=tuple(i==0 or abs(y)>=t for i,t in enumerate(ts))
                assert gates==rational.gates[bank]
                assert tuple(F(t,8) for t in ts)==rational.thresholds[bank]
                for i,g in enumerate(gates): sums[4*bank+i]+=d*y*g
        assert tuple(F(value,64) for value in sums)==tuple(products)
        formal_delta=tuple(round_fraction(-mu.numerator*desc['multiplier']*value*(1<<22),
                                         mu.denominator*64,'nearest_even')
                           for mu,value in zip(rate_steps,sums))
        assert formal_delta==delta
        counts['formal_readouts']+=len(records)
        counts['formal_full_request_vectors']+=1
    certificate=certify_phase_unions(((cell,),),lambda phase,c: (delta,),max_cells=1,max_requests=1)
    assert certificate['invariant']==(not any(delta))
    assert certificate['cell_count']==certificate['request_count']==1
    counts['full_cell_checks']+=1
    return {'codes':codes,'cell':cell,'request':delta,'point_after':after,
            'gate_equalities':equalities,'invariant_for_repeated_window':certificate['invariant'],
            'image':certificate['cells'][0]['requests'][0]['image'],
            'uncovered_witness':certificate['cells'][0]['requests'][0]['uncovered_witness']}


def run(folder):
    check_hashes(load(folder/'original_data_hashes.json'));check_hashes(load(folder/'execution_hashes.json'))
    verify_old_prefix()
    counts={'old_source_words_read':0,'old_state_vectors_read':0,'rational_readouts':0,
            'formal_readouts':0,'formal_full_request_vectors':0,'full_cell_checks':0,
            'new_adc_conversions':0,'new_online_learning':0,'new_online_outputs':0,
            'new_performance_scores':0,'new_fft':0}
    descriptor={'selected':4,'multiplier':30,'num':1,'den':1}
    fixtures=[]
    balanced=tuple((0,0,64*d1+16*d2,int(d1>0)+2*int(d2>0)) for d1 in (-1,1) for d2 in (-1,1))
    for label,words in (('balanced',balanced),('unbalanced',((0,0,80,3),)*4)):
        item=analyze_window(words,(4194304,)*8,descriptor,counts)
        item['name']=label;fixtures.append(item)
    assert fixtures[0]['invariant_for_repeated_window'] and fixtures[0]['gate_equalities']==4
    assert not fixtures[1]['invariant_for_repeated_window']
    rows=[]
    for task in selected_tasks():
        with (ROOT/task['word_file']).open('rb') as handle: raw=handle.read(240*4)
        words=tuple(struct.unpack('4b',raw[i:i+4]) for i in range(0,len(raw),4))
        assert len(words)==240;counts['old_source_words_read']+=240
        for desc in task['paths']:
            path=OLD/(task['stem']+'_'+desc['name']+'_q22.bin')
            with path.open('rb') as handle: raw=handle.read(3*8*4)
            states=tuple(struct.unpack('<8i',raw[i:i+32]) for i in range(0,len(raw),32))
            assert len(states)==3;counts['old_state_vectors_read']+=3
            for window in (0,1):
                item=analyze_window(words[120*window:120*(window+1)],states[window],desc,counts)
                write(folder/'progress.json',{'case':task['case'],'path':desc['name'],
                    'window':window,'counts':counts,'calculated_after':item['point_after'],
                    'saved_after':states[window+1],'completed_previous_window_rows':len(rows)})
                assert item['point_after']==states[window+1],(task['case'],desc['name'],window)
                item.update({'case':task['case'],'path':desc['name'],'window':window})
                rows.append(item)
    assert len(rows)==16 and counts['rational_readouts']==1000 and counts['formal_readouts']==3000
    assert counts['full_cell_checks']==18 and counts['formal_full_request_vectors']==54
    check_hashes(load(folder/'original_data_hashes.json'));check_hashes(load(folder/'execution_hashes.json'))
    output={'mathematical_status':'Exact conditional finite-union inclusion; no actual future Gu invariant or source-period certificate.',
            'fixtures':fixtures,'positive_full_cell_integer_states':4097**8,'development':rows,
            'development_single_full_cell_invariant':sum(row['invariant_for_repeated_window'] for row in rows),
            'counts':counts,'future_holdout_read':False,'new_algorithm_designed':False}
    write(folder/'results.json',output)
    print(f'Positive full cell contains {4097**8} integer states; old single-cell inclusions {output["development_single_full_cell_invariant"]}/16; requests match all16 saved next states; rational1000/formal3000.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','run'))
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    (prepare if args.action=='prepare' else run)(args.output.resolve())
