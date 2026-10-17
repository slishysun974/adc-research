"""NG-37 exact finite initial-state partitions on four old development windows."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys

from adc_research.theory.quantized_mean_dynamics import propagate_export_itineraries
from adc_research.theory.static_fixed_contract import readout, export, commit, saturated_integer
from adc_research.calibration.fixed_gated_lms import (
    FixedGatedLmsConfig, FixedGatedLmsState, exported_coefficient_codes,
    adaptive_lower_thresholds_scaled,
)
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.observation import DigitalCalibrationSample
from .check_quantized_phase_sets import configuration, steps, selected_tasks, DOCUMENTS

ROOT=Path(__file__).resolve().parents[2]
OLD=ROOT/'artifacts/runs/EXP_071/final_preflight_v1'
PREVIOUS=ROOT/'artifacts/research/quantized_phase_sets_20261012_v2'
MAXIMUM=2047*4096

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path): return json.loads(path.read_text(encoding='utf-8'))
def write(path,data): path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def check_hashes(manifest):
    for name,value in manifest.items(): assert digest(ROOT/name)==value,name

def old_prefix_matches():
    name='src/adc_research/theory/quantized_mean_dynamics.py'
    expected=load(PREVIOUS/'execution_hashes.json')[name]
    prefix=(ROOT/name).read_text(encoding='utf-8').split('\ndef propagate_export_itineraries(')[0].rstrip('\n')
    assert any(hashlib.sha256((prefix+'\n'*n).replace('\n',eol).encode()).hexdigest()==expected
               for n in (1,2,3) for eol in ('\n','\r\n'))
    return expected

def prepare(folder):
    folder.mkdir(parents=True,exist_ok=False)
    used=load(PREVIOUS/'original_data_hashes.json')
    old_delivery=load(OLD/'delivery_hashes.json')
    for task in selected_tasks():
        name=task['stem']+'_outputs.bin'
        used[(OLD/name).relative_to(ROOT).as_posix()]=old_delivery[name]
    prior_delivery=load(PREVIOUS/'delivery_hashes.json')
    for name in ('results.json','protocol.json','execution_hashes.json'):
        used[(PREVIOUS/name).relative_to(ROOT).as_posix()]=prior_delivery[name]
    check_hashes(used)
    previous_source=old_prefix_matches()
    sources={Path(module.__file__).resolve().relative_to(ROOT).as_posix():digest(Path(module.__file__).resolve())
             for module in tuple(sys.modules.values()) if getattr(module,'__file__',None)
             and Path(module.__file__).resolve().is_relative_to(ROOT)
             and Path(module.__file__).suffix=='.py'}
    for name in ('tests/test_export_itineraries.py','tests/test_quantized_phase_sets.py'):
        sources[name]=digest(ROOT/name)
    write(folder/'protocol.json',{
        'version':'NG37-fixed-history-export-itineraries-v1','date':'2026-10-12',
        'authority':'User continues original D129 task2 after D134. No new algorithm design or long matrix.',
        'question':'Can a finite normal window sequence exactly partition all initial states by export itineraries? Does a shared itinerary preserve initial distance, and where do fixed branch budgets stop?',
        'history':'Literal original windows0..3,global slots0..479 of final development preflight. Fixed seed202610711, cases509/1009,original main tasks,base/quarter and point30/full120. Do not repeat or wrap this prefix, generate later words, or claim source/PRNG closure.',
        'initial_sets':'Each original unit initial eight-state vector plus independent radius1 or2048 Q22 LSB. Radius2048 is the full even-code unit export cell. Sixteen finite partitions on eight original paths.',
        'caps':{'windows_per_partition':4,'cells_per_window':128,'branches':128,
                'unique_requests_per_partition':64,'cached_evaluations_per_original_path':80,
                'all_rational_evaluations':640,'rational_readouts':76800,
                'formal_probes':160,'formal_readouts':19200},
        'stop':'All before-window cell/branch/request caps checked before computing that incomplete window. Preserve only certified complete prefixes; no adaptive budget increase. Possible coefficient saturation stops translation proof. Any undefined readout is an execution failure and retained.',
        'objects':'Keep disjoint initial rectangles and cumulative offsets for each full eight-coordinate itinerary. Never merge different initial histories because their final rectangles overlap. Exact initial-cardinality conservation,not a sample count.',
        'controls':{'new_exact_tests':8,'targeted_plus_full_invocations':2,
            'complete_small_state_transitions_per_invocation':324,
            'coverage':'All81 initial states,four windows; shared eight-dimensional itinerary,history-dependent requests,final-state collisions,three budget stops,saturation stop and invalid contracts'},
        'reuse_budget':{'old_words':960,'old_state_vectors':40,'old_saved_integer_codes':3840,
                       'original_actual_transitions':32},
        'formal_probes':'Original actual centers plus lexicographically first/last current code-cell intersection at every completed phase. Deduplicate same original path/window/code. Full120 readout/threshold/gate checks and once-rounded complete requests.',
        'report':'All16 partitions and stops,all32 saved point transitions/codes,exact disjoint initial volume per phase,finite output-code envelopes at completed phases,noncontraction witnesses inside nonsingleton unsaturated branches. No target MSE/FFT or new performance score.',
        'fixed_state_history_control':'At the SAME unit eight coefficients evaluate each of the four old windows. Retain all equality/difference outcomes; varying requests reject one deterministic coefficient-only map for this allowed finite history,not a stochastic average model.',
        'old_ng36_source_prefix_sha256':previous_source,
        'new_adc_conversions':0,'new_online_learning':0,'new_online_outputs':0,
        'new_performance_scores':0,'new_fft':0,'future_holdout_read':False,
    })
    write(folder/'original_data_hashes.json',used);write(folder/'execution_hashes.json',sources)
    write(folder/'environment.json',{'python':sys.version,'platform':sys.platform})
    for name in DOCUMENTS:
        target=folder/'documents_before'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,target)
    # Preserve the exact original NG36 module, recovered from its verified prefix.
    prefix=(ROOT/'src/adc_research/theory/quantized_mean_dynamics.py').read_text().split('\ndef propagate_export_itineraries(')[0]
    (folder/'previous_module_prefix.txt').write_text(prefix,encoding='utf-8')
    print(f'Frozen:16 partitions/four windows; 19 old files/{len(sources)} sources; fixed stop budgets.')


def run(folder):
    check_hashes(load(folder/'original_data_hashes.json'));check_hashes(load(folder/'execution_hashes.json'))
    old_prefix_matches()
    counts={'old_words_read':0,'old_state_vectors_read':0,'old_saved_integer_codes_read':0,
        'rational_evaluations':0,'rational_readouts':0,'formal_probes':0,'formal_readouts':0,
        'saved_point_transitions_verified':0,'saved_integer_codes_verified':0,
        'new_adc_conversions':0,'new_online_learning':0,'new_online_outputs':0,
        'new_performance_scores':0,'new_fft':0}
    partitions=[];history_controls=[];formal_provenance=[]
    for task in selected_tasks():
        with (ROOT/task['word_file']).open('rb') as handle: raw=handle.read(480*4)
        assert len(raw)==480*4
        words=tuple(struct.unpack('4b',raw[i:i+4]) for i in range(0,len(raw),4))
        windows=tuple(words[120*j:120*(j+1)] for j in range(4));counts['old_words_read']+=480
        word_hashes=[hashlib.sha256(raw[480*j:480*(j+1)]).hexdigest() for j in range(4)]
        with (OLD/(task['stem']+'_outputs.bin')).open('rb') as handle: saved=handle.read(4*120*4*2)
        saved=struct.unpack('<1920h',saved);counts['old_saved_integer_codes_read']+=1920
        for path_index,desc in enumerate(task['paths']):
            with (OLD/(task['stem']+'_'+desc['name']+'_q22.bin')).open('rb') as handle: raw_states=handle.read(5*32)
            states=tuple(struct.unpack('<8i',raw_states[i:i+32]) for i in range(0,len(raw_states),32))
            assert len(states)==5;counts['old_state_vectors_read']+=5
            cache={};probed=set();rate_steps=steps(desc['num'],desc['den'])
            lms=tuple(FixedGatedLmsConfig(width,ss) for width,ss in
                      zip((1024,256),(rate_steps[:4],rate_steps[4:])))

            def evaluate(window,codes):
                key=(window,tuple(codes))
                if key in cache: return cache[key]
                assert len(cache)<80 and counts['rational_evaluations']<640
                coefficients=tuple(F(code,1024) for code in codes)
                records=[];products=[F(0)]*8;output=[];equalities=0
                for index,(q1,q2,be,bits) in enumerate(windows[window]):
                    d1,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
                    result=readout(q1,q2,F(be),d1,d2,coefficients,data_q3=True)
                    records.append((DigitalCalibrationSample(q1,q2,be,d1,d2),result))
                    output.append(saturated_integer(result.output))
                    if index<desc['selected']:
                        equalities+=sum(abs(y)==t for y,ts in zip((result.y1,result.y2),result.thresholds) for t in ts[1:])
                        for bank,(d,y,gates) in enumerate(zip((64*d1,16*d2),(result.y1,result.y2),result.gates)):
                            for i,g in enumerate(gates):products[4*bank+i]+=d*y*g
                delta,_=commit((0,)*8,tuple(products),desc['multiplier'],rate_steps)
                value={'request':delta,'output':tuple(output),'products':tuple(products),
                       'records':records,'equalities':equalities}
                cache[key]=value;counts['rational_evaluations']+=1;counts['rational_readouts']+=120
                return value

            def formal_probe(window,codes,representative):
                key=(window,tuple(codes))
                if key in probed:return
                assert counts['formal_probes']<160
                value=evaluate(window,codes);formal_codes=[]
                for bank in range(2):
                    state=FixedGatedLmsState(tuple(representative[4*bank:4*bank+4]),(0,)*4,(0,)*4,(0,)*4)
                    formal_codes.extend(exported_coefficient_codes(state,lms[bank]))
                assert tuple(formal_codes)==tuple(codes)
                cfg=configuration(formal_codes)
                thresholds=tuple(adaptive_lower_thresholds_scaled(tuple(formal_codes[4*b:4*b+4]),lms[b]) for b in range(2))
                sums=[0]*8
                for index,(observed,rational) in enumerate(value['records']):
                    core=correct_two_stage_fixed_observed(observed,cfg)
                    yy=(core.stage1_pwl.corrected_code_scaled-core.stage1_dither_scaled,
                        core.stage2_pwl.corrected_code_scaled-core.stage2_dither_scaled)
                    assert tuple(F(y,8) for y in yy)==(rational.y1,rational.y2)
                    assert core.unclipped_output_scaled==8*rational.output
                    assert round_fraction(core.output_scaled,8,'nearest_even')==value['output'][index]
                    for bank,(y,d,ts) in enumerate(zip(yy,(core.stage1_dither_scaled,core.stage2_dither_scaled),thresholds)):
                        gates=tuple(i==0 or abs(y)>=t for i,t in enumerate(ts))
                        assert gates==rational.gates[bank]
                        assert tuple(F(t,8) for t in ts)==rational.thresholds[bank]
                        if index<desc['selected']:
                            for i,g in enumerate(gates):sums[4*bank+i]+=d*y*g
                assert tuple(F(s,64) for s in sums)==value['products']
                delta=tuple(round_fraction(-mu.numerator*desc['multiplier']*s*(1<<22),mu.denominator*64,'nearest_even')
                            for mu,s in zip(rate_steps,sums))
                assert delta==value['request']
                counts['formal_probes']+=1;counts['formal_readouts']+=120;probed.add(key)
                formal_provenance.append({'case':task['case'],'path':desc['name'],'window':window,'codes':codes,
                                          'hidden_representative':representative})

            for window in range(4):
                codes=export(states[window]);value=evaluate(window,codes)
                after=tuple(a+d for a,d in zip(states[window],value['request']))
                assert after==states[window+1]
                expected=tuple(saved[(window*120+i)*4+path_index] for i in range(120))
                assert value['output']==expected
                counts['saved_point_transitions_verified']+=1;counts['saved_integer_codes_verified']+=120
                formal_probe(window,codes,states[window])
            unit_requests=[evaluate(window,(1024,)*8)['request'] for window in range(4)]
            history_controls.append({'case':task['case'],'path':desc['name'],'word_window_sha256':word_hashes,
                'unit_requests':unit_requests,'same_unit_request_w0_w1':unit_requests[0]==unit_requests[1],
                'same_unit_request_w0_w2':unit_requests[0]==unit_requests[2],
                'tag_bit_mismatches_w0_w2':sum(a[3]!=b[3] for a,b in zip(windows[0],windows[2]))})
            for radius in (1,2048):
                initial=tuple((value-radius,value+radius) for value in states[0])
                result=propagate_export_itineraries(initial,4,
                    lambda window,codes:evaluate(window,codes)['request'],max_cells_per_window=128,
                    max_branches=128,max_total_requests=64)
                widths=[];witnesses=[]
                for frame in result['history']:
                    window=frame['window'];actions=frame['actions']
                    options={action['codes']:evaluate(window,action['codes'])['output'] for action in actions}
                    lower=tuple(min(values[i] for values in options.values()) for i in range(120))
                    upper=tuple(max(values[i] for values in options.values()) for i in range(120))
                    center=evaluate(window,export(states[window]))['output']
                    assert all(lo<=value<=hi for lo,value,hi in zip(lower,center,upper))
                    widths.append({'window':window,'maximum_integer_code_width':max(b-a for a,b in zip(lower,upper)),
                                   'lower':lower,'upper':upper})
                    for action in (min(actions,key=lambda a:a['codes']),max(actions,key=lambda a:a['codes'])):
                        formal_probe(window,action['codes'],tuple(lo for lo,hi in action['before']))
                    assert any(all(lo<=value<=hi for (lo,hi),value in zip(branch['current'],states[window+1]))
                               for branch in frame['after_branches'])
                for branch in result['branches']:
                    lo=tuple(a for a,b in branch['initial']);hi=tuple(b for a,b in branch['initial'])
                    if lo!=hi:
                        endlo=tuple(a+d for a,d in zip(lo,branch['offset']))
                        endhi=tuple(b+d for b,d in zip(hi,branch['offset']))
                        start_distance=max(b-a for a,b in zip(lo,hi))
                        end_distance=max(b-a for a,b in zip(endlo,endhi))
                        assert start_distance==end_distance
                        witnesses.append({'initial_low':lo,'initial_high':hi,'final_low':endlo,'final_high':endhi,
                                          'distance':start_distance,'itinerary':branch['itinerary']})
                        break
                item={'case':task['case'],'path':desc['name'],'radius_q22':radius,
                      'partition':result,'output_envelopes':widths,'translation_distance_witness':witnesses}
                partitions.append(item)
                print(task['case'],desc['name'],'radius',radius,result['status'],
                      'certified',result['certified_windows'],'branches',len(result['branches']),flush=True)
                write(folder/'progress.json',{'completed_partitions':len(partitions),'counts':counts})
    assert len(partitions)==16 and counts['old_words_read']==960 and counts['old_state_vectors_read']==40
    assert counts['saved_point_transitions_verified']==32 and counts['saved_integer_codes_verified']==3840
    check_hashes(load(folder/'original_data_hashes.json'));check_hashes(load(folder/'execution_hashes.json'))
    output={'mathematical_status':'Exact fixed finite history partition; no future invariance or periodic source certificate.',
            'partitions':partitions,'history_controls':history_controls,'formal_provenance':formal_provenance,'counts':counts,
            'future_holdout_read':False,'new_algorithm_designed':False}
    write(folder/'results.json',output)
    print(json.dumps(counts),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','run'))
    parser.add_argument('--output',required=True,type=Path);args=parser.parse_args()
    (prepare if args.action=='prepare' else run)(args.output.resolve())
