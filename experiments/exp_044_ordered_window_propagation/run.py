"""Finite ordered-window replay, high-slope intervention, and sound state tubes."""

from __future__ import annotations

import argparse
from dataclasses import replace
from fractions import Fraction as F
import json
from pathlib import Path

from adc_research.calibration.fixed_adaptive_two_stage import cascade_from_fixed_state
from adc_research.calibration.fixed_four_lane_window import FixedFourLaneWindowConfig,FourLaneConversion,correct_fixed_four_lane_window
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.evaluation.fixed_online_state_bounds import FixedStateBox,IntegerInterval
from adc_research.evaluation.fixed_window_state_bounds import bound_frozen_window
from adc_research.metrics.spectral import analyze_coherent_tone
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial
from experiments.exp_039_four_lane_dynamic_loop.run import code as final_code
from experiments.exp_042_correlation_roots.run import digest,write


ROOT=Path(__file__).resolve().parents[2]
WINDOW=120
TRAINING_WINDOWS=128
TOTAL_WINDOWS=160
RADII=(1,2048)


def accumulators(state):
    return (*state.stage2.accumulator_codes,*state.stage1.accumulator_codes)


def intervals(box):
    return (*box.stage2_accumulators,*box.stage1_accumulators)


def clamp_high(state):
    return replace(state,
        stage2=replace(state.stage2,accumulator_codes=(*state.stage2.accumulator_codes[:2],2**22,2**22)),
        stage1=replace(state.stage1,accumulator_codes=(*state.stage1.accumulator_codes[:2],2**22,2**22)))


def advance(samples,state,cfg):
    start=state.stage1.sample_count
    rows=tuple(FourLaneConversion(start+i,(start+i)%4,s) for i,s in enumerate(samples))
    return correct_fixed_four_lane_window(rows,state,cfg)


def frozen_codes(samples,state,cfg):
    cascade=cascade_from_fixed_state(cfg.cascade,state,cfg.stage1_lms,cfg.stage2_lms)
    return tuple(final_code(correct_two_stage_fixed_observed(s,cascade)) for s in samples)


def difference_stats(values):
    values=tuple(values)
    return {'count':len(values),'nonzero_count':sum(v!=0 for v in values),
            'maximum_absolute_codes':max(map(abs,values),default=0),
            'mean_absolute_codes':F(sum(map(abs,values)),len(values)) if values else F(0),
            'mean_squared_codes':F(sum(v*v for v in values),len(values)) if values else F(0)}


def score(codes,ideals):
    errors=tuple(a-b for a,b in zip(codes,ideals,strict=True))
    metrics=analyze_coherent_tone(codes,sample_rate_hz=3e9,fundamental_bin=67,full_scale_peak=2048).metrics
    return {'mae_codes':F(sum(map(abs,errors)),len(errors)),
            'maximum_error_codes':max(map(abs,errors)),
            'sndr_db_float':metrics.sndr_db,'sfdr_dbc_float':metrics.sfdr_dbc}


def replay(windows,cfg,*,clamped=False,swap_training_pairs=False):
    state=_initial(cfg.adaptive)
    states=[state]
    results=[]
    codes=[]
    for index in range(TOTAL_WINDOWS):
        source_index=(index^1) if swap_training_pairs and index<TRAINING_WINDOWS else index
        result=advance(windows[source_index],state,cfg)
        state=clamp_high(result.state) if clamped else result.state
        states.append(state)
        results.append(result)
        codes.extend(final_code(c) for c in result.calibrations)
    return tuple(states),tuple(results),tuple(codes)


def check_saved_reference(states,results,codes,golden):
    for index,(result,after) in enumerate(zip(results,states[1:],strict=True)):
        row=golden['trajectory'][index]
        expected=(*row['coefficients_after']['stage2_q22'],*row['coefficients_after']['stage1_q22'])
        assert accumulators(after)==expected
        for bank in ('stage2','stage1'):
            update=getattr(result,bank+'_update')
            stored=row['products'][bank]
            for field in ('selected_product_sums','selected_gate_counts','requested_deltas','applied_deltas'):
                assert tuple(stored[field])==getattr(update,field)
    assert tuple(golden['online_sine_codes'])==codes[TRAINING_WINDOWS*WINDOW:]


def local_order_checks(windows,states,cfg):
    checks=[]
    for first in range(0,TRAINING_WINDOWS,2):
        start=states[first]
        reverse_a=advance(windows[first+1],start,cfg)
        reverse_b=advance(windows[first],reverse_a.state,cfg)
        forward=states[first+2]
        reverse=reverse_b.state
        difference=tuple(a-b for a,b in zip(accumulators(reverse),accumulators(forward),strict=True))
        # Same next digital window is scored without committing either state.
        probe=windows[first+2]
        probe_delta=tuple(a-b for a,b in zip(frozen_codes(probe,reverse,cfg.adaptive),
                                            frozen_codes(probe,forward,cfg.adaptive),strict=True))
        checks.append({'pair':(first,first+1),'reverse_minus_forward_q22':difference,
                       'same_next_window_code_difference':difference_stats(probe_delta)})
    return {'pairs':checks,'noncommuting_state_pairs':sum(any(c['reverse_minus_forward_q22']) for c in checks),
            'pairs_already_affecting_next_final_code':sum(c['same_next_window_code_difference']['nonzero_count']>0 for c in checks),
            'maximum_q22_commutator':max(abs(v) for c in checks for v in c['reverse_minus_forward_q22'])}


def high_decomposition(windows,free_states,free_codes,clamp_codes,cfg):
    shadow=[]
    for i,samples in enumerate(windows):
        shadow.extend(frozen_codes(samples,clamp_high(free_states[i]),cfg.adaptive))
    direct=tuple(a-b for a,b in zip(free_codes,shadow,strict=True))
    indirect=tuple(a-b for a,b in zip(shadow,clamp_codes,strict=True))
    total=tuple(a-b for a,b in zip(free_codes,clamp_codes,strict=True))
    assert all(a+b==c for a,b,c in zip(direct,indirect,total,strict=True))
    return {'identity_checked_conversions':len(total),
            'training':{'direct_high':difference_stats(direct[:15360]),'indirect_low_history':difference_stats(indirect[:15360]),
                        'total':difference_stats(total[:15360])},
            'online_sine':{'direct_high':difference_stats(direct[15360:]),'indirect_low_history':difference_stats(indirect[15360:]),
                           'total':difference_stats(total[15360:])}}


def tube(windows,center_states,center_results,center_codes,cfg,radius):
    unit=2**22
    initial_intervals=(IntegerInterval(unit-radius,unit+radius),)*4
    initial_box=FixedStateBox(initial_intervals,initial_intervals)
    box=initial_box
    corners=[replace(_initial(cfg.adaptive),
                stage1=replace(_initial(cfg.adaptive).stage1,accumulator_codes=(unit+sign*radius,)*4),
                stage2=replace(_initial(cfg.adaptive).stage2,accumulator_codes=(unit+sign*radius,)*4)) for sign in (-1,1)]
    rows=[]
    max_code_width=0
    stopped=None
    translation=True
    checks=0
    for i,samples in enumerate(windows):
        try:
            result=bound_frozen_window(samples,box,cfg)
        except (ValueError,KeyError) as error:
            stopped={'window':i,'reason':str(error),'scope':'abstract box has undefined candidate branch; not a concrete failure'}
            break
        before=box
        box=result.next_state_box
        assert all(p.lower<=z<=p.upper for p,z in zip(intervals(before),accumulators(center_states[i]),strict=True))
        assert all(p.lower<=z<=p.upper for p,z in zip(intervals(box),accumulators(center_states[i+1]),strict=True))
        current_codes=center_codes[i*WINDOW:(i+1)*WINDOW]
        assert all(p.lower<=z<=p.upper for p,z in zip(result.codes,current_codes,strict=True))
        for bank in ('stage2','stage1'):
            request=getattr(result,'requested_'+bank)
            actual=getattr(center_results[i],bank+'_update').requested_deltas
            assert all(p.lower<=z<=p.upper for p,z in zip(request,actual,strict=True))
        for corner_index,corner in enumerate(corners):
            actual=advance(samples,corner,cfg)
            corners[corner_index]=actual.state
            assert all(p.lower<=z<=p.upper for p,z in zip(intervals(box),accumulators(actual.state),strict=True))
            assert all(p.lower<=final_code(c)<=p.upper for p,c in zip(result.codes,actual.calibrations,strict=True))
            checks+=WINDOW
        widths=tuple(p.upper-p.lower for p in intervals(box))
        requests=(*result.requested_stage2,*result.requested_stage1)
        same_widths=widths==tuple(p.upper-p.lower for p in intervals(before))
        no_saturation=all(0<p.lower<=p.upper<cfg.adaptive.stage2_lms.maximum_accumulator_code for p in intervals(box))
        translation&=result.all_exported_coefficients_singleton and same_widths and no_saturation and all(p.lower==p.upper for p in requests)
        current_width=max(p.upper-p.lower for p in result.codes)
        max_code_width=max(max_code_width,current_width)
        rows.append({'window':i,'next_box':box,'widths_q22':widths,
                     'maximum_code_width':current_width,'exported_coefficients_singleton':result.all_exported_coefficients_singleton,
                     'uncertain_gate_counts':(*result.uncertain_gates_stage2,*result.uncertain_gates_stage1)})
    exact_difference=tuple(a-b for a,b in zip(accumulators(corners[1]),accumulators(corners[0]),strict=True))
    if translation:
        assert exact_difference==(2*radius,)*8
    return {'initial_radius_q22_lsb':radius,'initial_box':initial_box,'completed_windows':len(rows),
            'stopped':stopped,'rows':rows,'final_box':box,'maximum_final_code_interval_width':max_code_width,
            'translation_proved_for_completed_prefix':translation,
            'no_strict_contraction_for_completed_prefix':translation,
            'two_corner_final_difference_q22':exact_difference,'corner_output_checks':checks,
            'initial_equals_final_box':initial_box==box,
            'guarantee_scope':'given exact digital sequence and initial box, completed finite prefix only'}


def run(source,previous,output):
    original={}
    for folder in (source,previous):
        path=folder/'summary.json'
        original[path]=digest(path)
        summary=json.loads(path.read_text())
        for name,expected in summary['source_sha256'].items():
            assert digest(ROOT/name)==expected,name
            original[ROOT/name]=expected
    source_summary=json.loads((source/'summary.json').read_text())
    output.mkdir(parents=True,exist_ok=False)
    cfg=FixedFourLaneWindowConfig(_config())
    summaries=[]
    for case in source_summary['cases']:
        name=case['name']
        path=source/name/'analog_digital_records.jsonl'
        assert digest(path)==case['physical']['raw_record_sha256']
        original[path]=digest(path)
        golden_path=source/name/'all_products.json'
        expected=next(m['artifact_sha256'] for m in case['methods'] if m['method']=='all_products')
        assert digest(golden_path)==expected
        original[golden_path]=expected
        lines=tuple(json.loads(line) for line in path.read_text().splitlines())
        assert len(lines)==TOTAL_WINDOWS*WINDOW
        assert tuple(line['conversion_id'] for line in lines)==tuple(range(len(lines)))
        samples=tuple(Sample(**line['sample']) for line in lines)
        windows=tuple(samples[i:i+WINDOW] for i in range(0,len(samples),WINDOW))
        free_states,free_results,free_codes=replay(windows,cfg)
        check_saved_reference(free_states,free_results,free_codes,json.loads(golden_path.read_text()))
        clamp_states,clamp_results,clamp_codes=replay(windows,cfg,clamped=True)
        swap_states,swap_results,swap_codes=replay(windows,cfg,swap_training_pairs=True)
        order=local_order_checks(windows,free_states,cfg)
        decomposition=high_decomposition(windows,free_states,free_codes,clamp_codes,cfg)
        tubes=[]
        for radius in RADII:
            result=tube(windows,free_states,free_results,free_codes,cfg,radius)
            tubes.append(result)
            print(name,'tube',radius,result['completed_windows'],result['maximum_final_code_interval_width'],flush=True)
        ideals=tuple(line['ideal_code_offline_only'] for line in lines[15360:])
        scores={label:score(codes[15360:],ideals) for label,codes in
                (('unchanged_gu',free_codes),('clamped_high_control',clamp_codes),('swapped_training_windows_control',swap_codes))}
        high_requests=tuple(sum(getattr(result,bank+'_update').requested_deltas[i]!=0 for result in free_results)
                            for bank in ('stage2','stage1') for i in (2,3))
        target=output/(name+'.json')
        write(target,{'order_checks':order,'high_code_decomposition':decomposition,
                     'tubes':tubes,'scores':scores,'high_nonzero_request_windows':high_requests,
                     'trajectory_q22':{'unchanged_gu':tuple(map(accumulators,free_states)),
                                       'clamped_high_control':tuple(map(accumulators,clamp_states)),
                                       'swapped_training_windows_control':tuple(map(accumulators,swap_states))},
                     'online_sine_codes':{'unchanged_gu':free_codes[15360:],'clamped_high_control':clamp_codes[15360:],
                                          'swapped_training_windows_control':swap_codes[15360:]}})
        summaries.append({'name':name,'high_nonzero_request_windows':high_requests,
            'noncommuting_training_pairs':order['noncommuting_state_pairs'],
            'pairs_affecting_same_next_final_code':order['pairs_already_affecting_next_final_code'],
            'maximum_q22_commutator':order['maximum_q22_commutator'],
            'free_vs_clamp_online_code_difference':decomposition['online_sine'],
            'scores':scores,'tube_summary':tuple({k:t[k] for k in ('initial_radius_q22_lsb','completed_windows','stopped',
                     'maximum_final_code_interval_width','translation_proved_for_completed_prefix','corner_output_checks')} for t in tubes),
            'swap_minus_original_training_endpoint_q22':tuple(a-b for a,b in zip(accumulators(swap_states[128]),accumulators(free_states[128]))),
            'output_sha256':digest(target)})
    for path,expected in original.items():
        assert digest(path)==expected,str(path)
    dependencies=('src/adc_research/evaluation/fixed_window_state_bounds.py',
                  'src/adc_research/evaluation/fixed_online_state_bounds.py',
                  'experiments/exp_044_ordered_window_propagation/run.py','tests/test_fixed_window_state_bounds.py')
    write(output/'summary.json',{'scope':'actual finite digital window sequence, full eight-state Gu, exact interval enclosures and offline interventions',
          'source_conversions':115200,'new_physical_samples':0,'record_length_extended':False,
          'cadence_used':False,'online_gu_implementation_changed':False,'physical_guarantee':False,
          'infinite_horizon_stability_certified':False,'protocol':{'window':120,'training_windows':128,
          'online_sine_windows':32,'tube_initial_radii_q22_lsb':RADII,'initial_coefficients':'all unity',
          'high_control':'reset each bank coordinates 2 and 3 to unity after each commit; offline intervention',
          'order_control':'swap adjacent training windows; retain their digital tuples, sine order unchanged; no analog-history re-simulation'},
          'source_package_unchanged':True,'source_evidence_sha256':{str(path.relative_to(ROOT)).replace('\\','/'):expected for path,expected in original.items()},
          'source_sha256':{name:digest(ROOT/name) for name in dependencies},'cases':summaries})


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('previous',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    run(args.source.resolve(),args.previous.resolve(),args.output.resolve())
