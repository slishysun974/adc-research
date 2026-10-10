"""Frozen-record integer trapping, true window witnesses, and gate selection."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from fractions import Fraction as F
import json
from pathlib import Path

from adc_research.calibration.fixed_four_lane_window import (
    FixedFourLaneWindowConfig, FourLaneConversion, correct_fixed_four_lane_window,
)
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.fixed_pwl import correct_fixed
from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.evaluation.gated_target_diagnostics import decompose_target_correlation
from adc_research.theory.constrained_mean_root import weighted_cascade_mean
from adc_research.theory.gated_correlation_roots import WeightedStageRow, stage_correlations
from adc_research.theory.quantized_mean_dynamics import (
    FixedStageRow, FrozenStageMean, accelerated_orbit, certify_rectangle, export_cell, export_code,
)
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial
from experiments.exp_042_correlation_roots.run import digest, histogram, write


ROOT=Path(__file__).resolve().parents[2]
FIT=96*120
RADII=(1,2,4,8,16)
MAX_EVENTS=20000


def fixed_rows(samples):
    counts=Counter((8*s.backend_centered_code,128*s.stage2_dither_symbol) for s in samples)
    return tuple(FixedStageRow(raw,dither,count) for (raw,dither),count in sorted(counts.items()))


def make_model(samples,cfg):
    return FrozenStageMean(fixed_rows(samples),width_scaled=256,steps=cfg.stage2_lms.step_sizes)


def reference_products(rows,codes,cfg):
    """Independent existing integer PWL path, not the new formula."""
    pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=tuple(codes)+(1024,1024))
    from adc_research.calibration.fixed_gated_lms import adaptive_lower_thresholds_scaled
    thresholds=adaptive_lower_thresholds_scaled(pwl.coefficient_codes,cfg.stage2_lms)
    sums,counts=[0]*4,[0]*4
    for row in rows:
        local=correct_fixed(row.raw_scaled,pwl).corrected_code_scaled-row.dither_scaled
        for i,threshold in enumerate(thresholds):
            if i==0 or abs(local)>=threshold:
                sums[i]+=row.count*row.dither_scaled*local
                counts[i]+=row.count
    return tuple(sums),tuple(counts)


def phase_analysis(samples,model,certificate,center,cfg):
    phases=tuple(make_model(samples[i:i+120],cfg) for i in range(0,FIT,120))
    requests=tuple(p.request(center) for p in phases)
    assert tuple(sum(r.products[i] for r in requests) for i in range(4))==model.request(center).products
    phase_requests=tuple(r.deltas for r in requests)
    rounded_average=tuple(F(sum(r[i] for r in phase_requests),96) for i in range(4))
    witness=None
    for phase,p in enumerate(phases):
        for cell in certificate['cells']:
            if not any(pair[0]==bound[0] or pair[1]==bound[1] for pair,bound in
                       zip(cell['intersection'],certificate['bounds'])):
                continue
            request=p.request(cell['codes'])
            for endpoint in (0,1):
                state=tuple(pair[endpoint] for pair in cell['intersection'])
                after=p.transition(state)
                if any(not lo<=z<=hi for z,(lo,hi) in zip(after,certificate['bounds'])):
                    witness={'phase':phase,'codes':cell['codes'],'state':state,
                             'request':request,'after_low2':after}
                    # Compare this exact witness to the untouched actual updater.
                    initial=_initial(cfg)
                    initial=replace(initial,
                        stage2=replace(initial.stage2,accumulator_codes=(*state,2**22,2**22),sample_count=phase*120),
                        stage1=replace(initial.stage1,sample_count=phase*120))
                    window=tuple(FourLaneConversion(phase*120+i,i%4,s)
                                 for i,s in enumerate(samples[phase*120:(phase+1)*120]))
                    actual=correct_fixed_four_lane_window(window,initial,FixedFourLaneWindowConfig(cfg))
                    assert actual.stage2_update.requested_deltas==request.deltas
                    assert actual.state.stage2.accumulator_codes[:2]==after
                    witness['actual_four_lane_updater_verified']=True
                    witness['actual_after_all4']=actual.state.stage2.accumulator_codes
                    break
            if witness:
                break
        if witness:
            break
    return {'anchor_phase_requests':phase_requests,'anchor_pooled_request':model.request(center).deltas,
            'average_of_once_rounded_phase_requests':rounded_average,
            'all_96_windows_stop_at_anchor':all(not any(r) for r in phase_requests),
            'phase_rectangle_counterexample':witness,
            'phase_rectangle_certified':False}


def front_decomposition(samples,ideals,coefficients):
    # Ideals are used only here, after the digital dynamics have been computed.
    mean=weighted_cascade_mean(histogram(samples),coefficients)
    lookup={sample:row for (sample,count),row in zip(histogram(samples),mean.base.rows)}
    output=[]
    for i in range(4):
        records=[]
        errors=F(0)
        for sample,ideal in zip(samples,ideals,strict=True):
            row=lookup[sample]
            target=F(ideal-2048-512*sample.stage1_symbol)
            records.append((target,row.dither1,row.gates1[i],1))
            if row.gates1[i]:
                errors+=row.dither1*(row.local1-target)
        result=decompose_target_correlation(records)
        result['continuous_error_correlation']=errors/len(samples)
        result['learning_correlation']=mean.mean_products[4+i]
        assert result['gated_target_correlation']+result['continuous_error_correlation']==result['learning_correlation']
        assert result['conditional_imbalance_part']+result['gate_covariance_part']==result['gated_target_correlation']
        output.append(result)
    return output


def verify_event_orbit(model,orbit):
    checks=0
    for event in orbit['events']:
        state=event['state']
        delta=event['deltas']
        steps=event['constant_request_steps']
        # Validate first and last source states, and exact endpoint image.
        last=tuple(z+(steps-1)*d for z,d in zip(state,delta))
        assert tuple(export_code(z,model.guard) for z in last)==event['codes']
        after=tuple(z+steps*d for z,d in zip(state,delta))
        assert model.transition(last)==after
        assert tuple(export_code(z,model.guard) for z in state)==event['codes']
        checks+=1
    if orbit['status']=='cycle':
        first=orbit['events'][orbit['cycle_event_start']]
        assert first['state']==orbit['last_state']
        assert orbit['period']>1
        state=first['state']
        states=set()
        for _ in range(orbit['period']):
            assert state not in states
            states.add(state)
            state=model.transition(state)
        assert state==first['state']
        orbit['cycle_period_verified_by_every_integer_step']=True
        orbit['cycle_distinct_integer_states']=len(states)
        orbit['cycle_bounds_q22']=tuple((min(z[i] for z in states),max(z[i] for z in states)) for i in range(2))
        orbit['cycle_export_code_ranges']=tuple((min(export_code(z[i],model.guard) for z in states),
                                                max(export_code(z[i],model.guard) for z in states)) for i in range(2))
    return checks


def jump_directions(scan,model,cfg):
    if scan['roots']:
        return None
    point=F(16,15)
    cuts=[F(b['parameter']) for b in scan['boundaries']]
    distance=min([abs(t-point) for t in cuts if t!=point]+[F(1,65536)])
    epsilon=distance/2
    rows=tuple(WeightedStageRow(F(r.raw_scaled,8),F(r.dither_scaled,8),r.count) for r in model.rows)
    output=[]
    for side,t in (('left',point-epsilon),('right',point+epsilon)):
        coefficients=tuple(F(p)*t+F(q) for p,q in zip(scan['coefficient_line_slopes'],scan['coefficient_line_intercepts']))+(F(1),F(1))
        correlations=stage_correlations(rows,coefficients,32)
        assert correlations[0]==0
        delta_v=-120*cfg.stage2_lms.step_sizes[1]*correlations[1]
        after=(coefficients[0],coefficients[1]+delta_v,F(1),F(1))
        next_primary=F(scan['primary_coefficients'][1])*delta_v
        assert stage_correlations(rows,after,32)[0]==next_primary
        output.append({'side':side,'parameter':t,'correlations':correlations,
                       'clamped_low2_unrounded_delta':(F(0),delta_v),
                       'primary_correlation_after_step':next_primary,
                       'primary_zero_line_is_preserved':next_primary==0})
    assert output[0]['clamped_low2_unrounded_delta'][1]>0
    assert output[1]['clamped_low2_unrounded_delta'][1]<0
    return output


def q3_gate_shift(model,cfg,center):
    rows=(FixedStageRow(376,128),FixedStageRow(-376,-128))
    probe=FrozenStageMean(rows,width_scaled=256,steps=cfg.stage2_lms.step_sizes)
    observations=[]
    for code in (1087,1088,1092):
        request=probe.request((center[0],code))
        assert reference_products(rows,(center[0],code),cfg)==(request.products,request.gates)
        assert request.gates[1]==(0 if code==1087 else 2)
        observations.append({'second_export_code':code,'second_gate_count':request.gates[1]})
    return {'row_family_raw_and_dither_codes':((47,16),(-47,-16)),
            'matching_fit_conversions':sum(r.count for r in model.rows if (r.raw_scaled,r.dither_scaled) in ((376,128),(-376,-128))),
            'continuous_second_coefficient_threshold':F(16,15),
            'q3_export_code_threshold':1088,'q3_exported_slope_threshold':F(17,16),
            'threshold_shift':F(-1,240),'observations':observations}


def run(source,roots,output):
    originals={}
    for folder in (source,roots):
        summary_path=folder/'summary.json'
        summary=json.loads(summary_path.read_text())
        originals[summary_path]=digest(summary_path)
        for name,expected in summary['source_sha256'].items():
            path=ROOT/name
            assert digest(path)==expected,name
            originals[path]=expected
    output.mkdir(parents=True,exist_ok=False)
    cfg=_config()
    summaries=[]
    comparisons=events=identities=0
    source_summary=json.loads((source/'summary.json').read_text())
    root_summary=json.loads((roots/'summary.json').read_text())
    root_hashes={c['name']:c['output_sha256'] for c in root_summary['cases']}
    for case in source_summary['cases']:
        name=case['name']
        path=source/name/'analog_digital_records.jsonl'
        assert digest(path)==case['physical']['raw_record_sha256']
        originals[path]=digest(path)
        prior_path=roots/(name+'.json')
        assert digest(prior_path)==root_hashes[name]
        originals[prior_path]=digest(prior_path)
        prior=json.loads(prior_path.read_text())
        lines=[json.loads(line) for line in path.read_text().splitlines()[:FIT]]
        samples=tuple(Sample(**line['sample']) for line in lines)
        model=make_model(samples,cfg)
        scan=prior['stage2_scan']
        if scan['roots']:
            coefficients=tuple(F(x) for x in scan['roots'][0]['coefficients'][:2])
            anchor_kind='first stage2 root (all cases have at most one)'
        else:
            coefficients=tuple(F(p)*F(16,15)+F(q) for p,q in
                               zip(scan['coefficient_line_slopes'],scan['coefficient_line_intercepts']))
            anchor_kind='primary zero line at the previously reported 16/15 jump'
        assert len(scan['roots'])<=1
        initial=tuple(round_fraction(k.numerator*2**22,k.denominator,'nearest_even') for k in coefficients)
        center=tuple(export_code(z) for z in initial)
        attempts=[]
        for radius in RADII:
            bounds=tuple((export_cell(c-radius)[0],export_cell(c+radius)[1]) for c in center)
            certificate=certify_rectangle(model,bounds)
            attempts.append({'radius_q1_10_codes':radius,'invariant':certificate['invariant'],
                             'violating_cells':len(certificate['violating_codes']),
                             'fixed_state_cells':certificate['fixed_state_cells']})
            if certificate['invariant']:
                break
        orbit=None
        if certificate['invariant']:
            orbit=accelerated_orbit(model,initial,bounds,MAX_EVENTS)
            events+=verify_event_orbit(model,orbit)
        phases=phase_analysis(samples,model,certificate,center,cfg)
        # Validate every code pair used by the rectangle search and the orbit.
        for codes,request in model.cache.items():
            reference=reference_products(model.rows,codes,cfg)
            assert reference==(request.products,request.gates)
            comparisons+=1
        # Full root, when unique and available; otherwise a declared front-unit diagnostic.
        if len(prior['candidates'])==1:
            diagnostic=tuple(F(x) for x in prior['candidates'][0]['coefficients'])
            diagnostic_kind='unique full low4 root'
        else:
            diagnostic=(*coefficients,F(1),F(1),*(F(1),)*4)
            diagnostic_kind='stage2 anchor with unit front coefficients; not a full root'
        ideals=tuple(line['ideal_code_offline_only'] for line in lines)
        decomposition=front_decomposition(samples,ideals,diagnostic)
        identities+=8
        directions=jump_directions(scan,model,cfg)
        gate_shift=q3_gate_shift(model,cfg,center)
        target=output/(name+'.json')
        write(target,{'anchor_kind':anchor_kind,'continuous_stage2_anchor':coefficients,
                     'initial_q22':initial,'initial_export_codes':center,'search_attempts':attempts,
                     'continuous_jump_side_directions':directions,
                     'q3_gate_threshold_shift':gate_shift,
                     'pooled_rectangle_certificate':certificate,'pooled_orbit':orbit,'phase_analysis':phases,
                     'offline_front_diagnostic_kind':diagnostic_kind,'offline_front_coefficients':diagnostic,
                     'offline_front_signal_decomposition':decomposition})
        brief={'name':name,'center_export_codes':center,'attempts':attempts,
               'certified_bounds_q22':bounds,'invariant_pooled_rectangle':certificate['invariant'],
               'has_pooled_fixed_state_in_examined_rectangle':bool(certificate['fixed_state_cells']),
               'eventually_nontrivially_periodic_pooled_low2':certificate['every_state_eventually_nontrivially_periodic'],
               'high_gates_all_closed':certificate['all_clamped_gates_closed'],
               'high_requests_all_zero':certificate['all_clamped_requests_zero'],
               'unclamped_stage2_has_same_pooled_invariant_set':certificate['invariant'] and certificate['all_clamped_requests_zero'],
               'orbit_status':None if orbit is None else orbit['status'],
               'orbit_period':None if orbit is None else orbit.get('period'),
               'actual_phase_rectangle_counterexample_found':phases['phase_rectangle_counterexample'] is not None,
               'initial_pooled_request':model.request(center).deltas,
               'offline_signal_decomposition':decomposition,'output_sha256':digest(target)}
        summaries.append(brief)
        print(name,brief['invariant_pooled_rectangle'],brief['orbit_status'],brief['orbit_period'],flush=True)
    for path,expected in originals.items():
        assert digest(path)==expected,str(path)
    dependencies=('src/adc_research/theory/quantized_mean_dynamics.py',
                  'src/adc_research/evaluation/gated_target_diagnostics.py',
                  'experiments/exp_043_quantized_mean_dynamics/run.py',
                  'tests/test_quantized_mean_dynamics.py')
    write(output/'summary.json',{'scope':'exact fixed empirical stage2 pooled mean; actual-window counterexamples; offline conditional gate bias',
          'phase_varying_gu_convergence_certified':False,'new_training_samples':0,'cadence_used':False,
          'online_algorithm_changed':False,'physical_guarantee':False,
          'mean_window_scale':120,'fit_rows_per_case':FIT,'fixed_high_export_codes':[1024,1024],
          'rectangle_search_radii_q1_10_codes':RADII,'event_limit':MAX_EVENTS,
          'source_package_unchanged':True,
          'source_evidence_sha256':{str(path.relative_to(ROOT)).replace('\\','/'):expected for path,expected in originals.items()},
          'source_sha256':{name:digest(ROOT/name) for name in dependencies},
          'verification':{'independent_fixed_pwl_code_pairs':comparisons,'exact_event_segments':events,
                          'offline_decomposition_identities':identities},'cases':summaries})


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('roots',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    run(args.source.resolve(),args.roots.resolve(),args.output.resolve())
