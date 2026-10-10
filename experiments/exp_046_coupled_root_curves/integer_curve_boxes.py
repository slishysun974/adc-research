"""Export-code boxes enclose quantized points on each certified joint curve.

Cartesian code combinations can be unreachable. A possible fixed combination
is inconclusive; rejecting every combination proves absence on the legal
quantized curve. The update examined here is the declared pooled mean map.
"""
from dataclasses import replace
from fractions import Fraction as F
from itertools import product
import json
from math import prod
from pathlib import Path
import sys

from adc_research.calibration.fixed_adaptive_two_stage import cascade_from_fixed_state
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.coupled_root_curve import interval_value,divide_intervals
from adc_research.theory.quantized_mean_dynamics import export_code,export_cell
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial
from experiments.exp_042_correlation_roots.run import digest,fixed_correlation_mean,write

ROOT=Path(__file__).resolve().parents[2]
MAX_COMBINATIONS=256


def state_bounds(curve,backend,cfg):
    model=curve['curve_model']
    h0=F(curve['seed_parameter'])
    low,high=map(F,curve['certificate']['parameter_interval'])
    back=[]
    for a,b in zip(map(F,backend['direction']),map(F,backend['intercept'])):
        back.append(tuple(sorted((a*low+b,a*high+b))))
    t=low-h0,high-h0
    denominator=interval_value(tuple(map(F,model['denominator'])),t)
    front=[divide_intervals(interval_value(tuple(map(F,model[name])),t),denominator)
           for name in ('numerator_u','numerator_v')]+[(F(1),F(1))]*2
    coefficient_intervals=tuple(back+front)
    maximum=cfg.stage2_lms.maximum_accumulator_code
    states=[]
    might_be_illegal=False
    for lo,hi in coefficient_intervals:
        endpoints=[]
        for k in (lo,hi):
            scaled=k*2**22
            endpoints.append(round_fraction(scaled.numerator,scaled.denominator,'nearest_even'))
        might_be_illegal|=endpoints[0]<0 or endpoints[1]>maximum
        states.append((max(0,endpoints[0]),min(maximum,endpoints[1])))
    return tuple(states),coefficient_intervals,might_be_illegal


def main(source,backend_source,folder):
    output=folder/'integer_curve_boxes.json'
    if output.exists():raise FileExistsError(output)
    summary=json.loads((folder/'summary.json').read_text())
    for name,expected in {**summary['source_sha256'],**summary['source_evidence_sha256']}.items():
        assert digest(ROOT/name)==expected,name
    cfg=_config()
    steps=tuple(120*s for s in (*cfg.stage2_lms.step_sizes,*cfg.stage1_lms.step_sizes))
    previous=json.loads((backend_source/'summary.json').read_text())
    previous_cases={case['name']:case for case in previous['cases']}
    records=[]
    total=0
    for case in summary['cases']:
        data_path=folder/(case['name']+'.json')
        assert digest(data_path)==case['output_sha256']
        data=json.loads(data_path.read_text())
        raw_path=source/case['name']/'analog_digital_records.jsonl'
        # First-stage coarse code is absent from both local learning outputs.
        # Neutralize it for histogram reuse; all other digital fields and weights stay.
        samples=tuple(Sample(0,s['stage2_symbol'],s['backend_centered_code'],s['stage1_dither_symbol'],s['stage2_dither_symbol'])
                      for s in (json.loads(line)['sample'] for line in raw_path.read_text().splitlines()[:11520]))
        for index,curve in enumerate(data['candidates']):
            if not curve['all_eight_zero_on_certified_curve']:continue
            backend=previous_cases[case['name']]['certified_results'][curve['backend_segment']]
            states,coefficients,might_illegal=state_bounds(curve,backend,cfg)
            ranges=tuple(range(export_code(lo),export_code(hi)+1) for lo,hi in states)
            combinations=prod(map(len,ranges))
            record={'name':case['name'],'candidate':index,'state_intervals_q22':states,
                    'coefficient_intervals':coefficients,'export_code_ranges':tuple((r.start,r.stop-1) for r in ranges),
                    'combinations':combinations,'enclosure_may_include_illegal_initial_states':might_illegal}
            if combinations>MAX_COMBINATIONS:
                record['status']='combination_budget_not_certified'
                records.append(record)
                continue
            fixed=[]
            tested=[]
            failed=None
            for codes in product(*ranges):
                intersections=tuple((max(lo,export_cell(c)[0]),min(hi,export_cell(c)[1]))
                                    for (lo,hi),c in zip(states,codes))
                if any(lo>hi for lo,hi in intersections):continue
                initial=_initial(cfg)
                initial=replace(initial,stage2=replace(initial.stage2,accumulator_codes=tuple(c*4096 for c in codes[:4])),
                                        stage1=replace(initial.stage1,accumulator_codes=tuple(c*4096 for c in codes[4:])))
                cascade=cascade_from_fixed_state(cfg.cascade,initial,cfg.stage1_lms,cfg.stage2_lms)
                try:
                    mean=fixed_correlation_mean(samples,cascade,cfg)
                except ValueError as error:
                    failed={'codes':codes,'reason':str(error)}
                    break
                requests=[]
                for step,m in zip(steps,mean):
                    v=-step*m*2**22
                    requests.append(round_fraction(v.numerator,v.denominator,'nearest_even'))
                possible_fixed=all(d==0 or (d<0 and lo==0) or (d>0 and hi==cfg.stage2_lms.maximum_accumulator_code)
                                   for d,(lo,hi) in zip(requests,intersections))
                tested.append({'codes':codes,'request':tuple(requests),'possible_fixed_state':possible_fixed})
                if possible_fixed:fixed.append(codes)
            total+=len(tested)
            record.update(status='undefined_possible_combination' if failed else 'completed',
                          undefined_branch=failed,possible_fixed_code_combinations=tuple(fixed),tested_combinations=tuple(tested),
                          no_integer_mean_fixed_state_on_legal_quantized_curve=failed is None and not fixed)
            records.append(record)
            print(case['name'],index,len(tested),len(fixed),flush=True)
    for name,expected in {**summary['source_sha256'],**summary['source_evidence_sha256']}.items():
        assert digest(ROOT/name)==expected,name
    write(output,{'scope':'legal nearest-Q22 initial states obtained from the certified continuous curves; pooled frozen mean map',
          'max_combinations_per_curve':MAX_COMBINATIONS,'total_tested_code_combinations':total,
          'no_curve_implies_physical_or_chronological_convergence':True,
          'source_script_sha256':digest(Path(__file__)),'curves':records})


if __name__=='__main__':
    main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve(),Path(sys.argv[3]).resolve())
