"""Coupled continuous root curves and separately frozen integer diagnostics."""
import argparse
from dataclasses import replace
from fractions import Fraction as F
import json
from pathlib import Path

from adc_research.calibration.fixed_four_lane_window import FixedFourLaneWindowConfig,FourLaneConversion,correct_fixed_four_lane_window
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.coupled_root_curve import build_front_curve,certify_local_curve,curve_coefficients
from adc_research.theory.gated_correlation_roots import scan_two_slope_roots,stage_correlations
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_042_correlation_roots.run import digest,stage_rows,write,quantized_reference,fixed_correlation_mean,offline_score
from experiments.exp_046_coupled_root_curves.probe import parameters

ROOT=Path(__file__).resolve().parents[2]
FIT=11520
PARTITIONS={'fit':(0,11520),'training_suffix':(11520,15360),'online_sine':(15360,19200)}


def integer_diagnostics(samples,coefficients,cfg):
    state,cascade,exported=quantized_reference(coefficients,cfg)
    legal=all(0<=z<=bank_cfg.maximum_accumulator_code for bank,bank_cfg in
              ((state.stage2,cfg.stage2_lms),(state.stage1,cfg.stage1_lms)) for z in bank.accumulator_codes)
    result={'quantized_state_legal':legal,'exported_coefficients':exported,
            'export_distance_to_continuous_seed':max(abs(a-b) for a,b in zip(exported,coefficients))}
    if not legal:return result,cascade
    steps=tuple(120*s for s in (*cfg.stage2_lms.step_sizes,*cfg.stage1_lms.step_sizes))
    def requested(mean):
        values=tuple(-step*m*2**22 for step,m in zip(steps,mean))
        return tuple(round_fraction(v.numerator,v.denominator,'nearest_even') for v in values)
    mean=fixed_correlation_mean(samples,cascade,cfg)
    phases=[]
    for w in range(96):
        window=samples[w*120:(w+1)*120]
        phases.append(requested(fixed_correlation_mean(window,cascade,cfg)))
        if w in (0,95):
            initial=replace(state,stage2=replace(state.stage2,sample_count=w*120),
                                  stage1=replace(state.stage1,sample_count=w*120))
            rows=tuple(FourLaneConversion(w*120+i,i%4,s) for i,s in enumerate(window))
            actual=correct_fixed_four_lane_window(rows,initial,FixedFourLaneWindowConfig(cfg))
            assert phases[-1]==(*actual.stage2_update.requested_deltas,*actual.stage1_update.requested_deltas)
    virtual=requested(mean)
    result.update(integer_fit_correlations=mean,virtual_120_mean_request=virtual,
                  virtual_mean_stops=not any(virtual),frozen_window_requests=tuple(phases),
                  frozen_windows_with_nonzero_request=sum(any(r) for r in phases),
                  maximum_actual_window_request_q22=max(abs(v) for r in phases for v in r),
                  maximum_virtual_mean_request_q22=max(map(abs,virtual)),
                  actual_updater_window_checks=2)
    return result,cascade


def run(source,previous,output):
    originals={}
    for folder in (source,previous):
        path=folder/'summary.json'
        originals[path]=digest(path)
        summary=json.loads(path.read_text())
        for name,expected in summary['source_sha256'].items():
            assert digest(ROOT/name)==expected,name
            originals[ROOT/name]=expected
    previous_summary=json.loads((previous/'summary.json').read_text())
    verify_path=previous/'verification.json'
    verify=json.loads(verify_path.read_text())
    originals[verify_path]=digest(verify_path)
    for name,expected in verify['extra_source_sha256'].items():
        assert digest(ROOT/name)==expected,name
        originals[ROOT/name]=expected
    source_cases={c['name']:c for c in json.loads((source/'summary.json').read_text())['cases']}
    output.mkdir(parents=True,exist_ok=False)
    cfg=_config()
    case_summaries=[]
    for case in previous_summary['cases']:
        name=case['name']
        prior_path=previous/(name+'.json')
        assert digest(prior_path)==case['output_sha256']
        originals[prior_path]=digest(prior_path)
        path=source/name/'analog_digital_records.jsonl'
        assert digest(path)==source_cases[name]['physical']['raw_record_sha256']
        originals[path]=digest(path)
        lines=tuple(json.loads(line) for line in path.read_text().splitlines())
        samples=tuple(Sample(**line['sample']) for line in lines)
        fitting=samples[:FIT]
        back_rows=stage_rows(fitting,2)
        probes=[]
        candidates=[]
        for segment_index,segment in enumerate(case['certified_results']):
            if segment['status']!='certified_root_segment_in_seed_masks':continue
            direction,intercept=tuple(map(F,segment['direction'])),tuple(map(F,segment['intercept']))
            back_interval=(*map(F,segment['third_parameter_interval'][:2]),*segment['third_parameter_interval'][2:])
            for h in parameters(segment):
                k2=tuple(a*h+b for a,b in zip(direction,intercept))
                assert stage_correlations(back_rows,k2,F(32))==(F(0),)*4
                front_rows=stage_rows(fitting,1,k2)
                scan=scan_two_slope_roots(front_rows,F(128))
                assert scan.complete_on_declared_domain
                probes.append({'backend_segment':segment_index,'parameter':h,'status':scan.status,
                               'low_front_roots':len(scan.roots),'zero_intervals':scan.zero_intervals})
                for front_index,root in enumerate(scan.roots):
                    point_correlations=stage_correlations(front_rows,root.coefficients,F(128))
                    model=build_front_curve(fitting,direction,intercept,h,root.coefficients)
                    certificate=certify_local_curve(model,back_interval)
                    checks=[]
                    if certificate['status']=='certified_front_root_curve':
                        lo,hi=certificate['parameter_interval']
                        for q in (lo,(lo+hi)/2,hi):
                            back=tuple(a*q+b for a,b in zip(direction,intercept))
                            front=curve_coefficients(model,q)
                            c2=stage_correlations(back_rows,back,F(32))
                            c1=stage_correlations(stage_rows(fitting,1,back),front,F(128))
                            assert c2==(F(0),)*4 and c1[:2]==(F(0),)*2
                            if certificate['front_all_four_zero']:assert c1==(F(0),)*4
                            checks.append({'parameter':q,'all_eight_correlations':(*c2,*c1)})
                    coefficients=(*k2,*root.coefficients)
                    integer,cascade=integer_diagnostics(fitting,coefficients,cfg)
                    # Targets enter only this independent offline scoring section.
                    targets=tuple(line['ideal_code_offline_only'] for line in lines)
                    scores={label:offline_score(samples[a:b],targets[a:b],cascade,spectrum=label=='online_sine')
                            for label,(a,b) in PARTITIONS.items()}
                    small_model={key:value for key,value in model.items() if key not in ('frames','gate_constraints')}
                    small_model['weighted_digital_frames']=len(model.get('frames',()))
                    entry={'backend_segment':segment_index,'front_root':front_index,'seed_parameter':h,
                           'seed_coefficients':coefficients,'front_seed_correlations':point_correlations,
                           'curve_model':small_model,'certificate':certificate,'exact_curve_checks':checks,
                           'all_eight_zero_on_certified_curve':certificate.get('front_all_four_zero',False) and certificate['status']=='certified_front_root_curve',
                           'integer_diagnostics':integer,'offline_frozen_scores':scores}
                    candidates.append(entry)
                    print(name,segment_index,len(candidates),certificate['status'],
                          entry['all_eight_zero_on_certified_curve'],integer.get('virtual_mean_stops'),flush=True)
        target=output/(name+'.json')
        write(target,{'front_parameter_probes':probes,'candidates':candidates,'global_joint_search_complete':False})
        case_summaries.append({'name':name,'parameter_probes':len(probes),'front_root_seeds':len(candidates),
                 'certified_all_eight_zero_curves':sum(c['all_eight_zero_on_certified_curve'] for c in candidates),
                 'integer_virtual_mean_stops':sum(c['integer_diagnostics'].get('virtual_mean_stops',False) for c in candidates),
                 'all_actual_frozen_windows_stop':sum(c['integer_diagnostics'].get('frozen_windows_with_nonzero_request',1)==0 for c in candidates),
                 'output_sha256':digest(target)})
    for path,expected in originals.items():assert digest(path)==expected,str(path)
    dependencies=('src/adc_research/theory/coupled_root_curve.py','src/adc_research/theory/gated_correlation_roots.py',
                  'experiments/exp_046_coupled_root_curves/run.py','experiments/exp_046_coupled_root_curves/probe.py',
                  'tests/test_coupled_root_curve.py')
    write(output/'summary.json',{'scope':'local continuous coupled low-front root curves plus separately frozen integer requests and offline scores',
          'free_coordinates':'backend first3, front first2','fixed_coordinates':'backend fourth=1, front third/fourth=1',
          'parameter_probe_rule':'three interior quartiles and unity if strictly inside each backend segment',
          'neighborhood_initial_radius':'1/1024 clipped to half distance from backend segment ends',
          'neighborhood_max_halvings':60,'interval_modes':('symmetric','right','left'),
          'virtual_mean_request_scope':'pooled fit mean scaled to 120 conversions; not an actual window',
          'window_request_scope':'96 separate windows all frozen at the same exported seed; no chronological feedback replay',
          'new_training':False,'new_physical_samples':0,'cadence_used':False,'online_algorithm_changed':False,
          'global_joint_search_complete':False,'integer_or_time_varying_convergence_certified':False,
          'source_package_unchanged':True,
          'source_evidence_sha256':{str(path.relative_to(ROOT)).replace('\\','/'):d for path,d in originals.items()},
          'source_sha256':{name:digest(ROOT/name) for name in dependencies},'cases':case_summaries})


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('source',type=Path);p.add_argument('previous',type=Path);p.add_argument('output',type=Path)
    args=p.parse_args()
    run(args.source.resolve(),args.previous.resolve(),args.output.resolve())
