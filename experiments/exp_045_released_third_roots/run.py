"""Slice-generated seeds and exact local released-third correlation roots."""
import argparse
from fractions import Fraction as F
import json
from pathlib import Path

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.gated_correlation_roots import scan_two_slope_roots,stage_correlations
from adc_research.theory.released_third_mean_roots import analyze_seed
from experiments.exp_042_correlation_roots.run import digest,stage_rows,write

ROOT=Path(__file__).resolve().parents[2]
HIGH_GRID=(F(3,4),F(7,8),F(1),F(9,8),F(5,4))


def key(result):
    if result['status']=='certified_point_root_in_seed_masks':
        return ('point',tuple(result['proposed_coefficients']))
    return ('segment',tuple(result['direction']),tuple(result['intercept']),tuple(result['third_parameter_interval']))


def run(source,previous,output):
    originals={}
    for folder in (source,previous):
        path=folder/'summary.json'
        originals[path]=digest(path)
        summary=json.loads(path.read_text())
        for name,expected in summary['source_sha256'].items():
            assert digest(ROOT/name)==expected,name
            originals[ROOT/name]=expected
    source_summary=json.loads((source/'summary.json').read_text())
    output.mkdir(parents=True,exist_ok=False)
    cases=[]
    for case in source_summary['cases']:
        name=case['name']
        path=source/name/'analog_digital_records.jsonl'
        assert digest(path)==case['physical']['raw_record_sha256']
        originals[path]=digest(path)
        samples=tuple(Sample(**json.loads(line)['sample']) for line in path.read_text().splitlines()[:11520])
        rows=stage_rows(samples,2)
        scans=[]
        analyses=[]
        unique={}
        for high in HIGH_GRID:
            scan=scan_two_slope_roots(rows,F(32),(high,F(1)))
            assert scan.complete_on_declared_domain
            scans.append({'third':high,'status':scan.status,'roots':scan.roots,
                          'zero_intervals':scan.zero_intervals,'cell_count':len(scan.cells),
                          'boundary_count':len(scan.boundaries)})
            for root in scan.roots:
                assert stage_correlations(rows,root.coefficients,F(32))[:2]==(F(0),)*2
                analysis=analyze_seed(rows,root.coefficients)
                analyses.append(analysis)
                if analysis['status'] in ('certified_point_root_in_seed_masks','certified_root_segment_in_seed_masks'):
                    unique.setdefault(key(analysis),analysis)
        target=output/(name+'.json')
        results=tuple(unique.values())
        write(target,{'slices':scans,'seed_analyses':analyses,'distinct_certified_results':results,
                      'global_three_parameter_search_complete':False})
        brief={'name':name,'slice_root_counts':tuple(len(s['roots']) for s in scans),
               'distinct_certified_points':sum(r['status']=='certified_point_root_in_seed_masks' for r in results),
               'distinct_certified_segments':sum(r['status']=='certified_root_segment_in_seed_masks' and r['nonunique_root_segment'] for r in results),
               'all_four_zero_segments':sum(r.get('all_four_correlations_zero_on_segment',False) and r['nonunique_root_segment'] for r in results),
               'readout_varying_segments':sum(r.get('nonunique_root_segment',False) and r['readout_varying_conversions']>0 for r in results),
               'seed_proposal_statuses':tuple(r['status'] for r in analyses),
               'certified_results':results,'output_sha256':digest(target)}
        cases.append(brief)
        print(name,brief['distinct_certified_points'],brief['distinct_certified_segments'],brief['seed_proposal_statuses'],flush=True)
    for path,expected in originals.items():
        assert digest(path)==expected,str(path)
    dependencies=('src/adc_research/theory/released_third_mean_roots.py',
                  'src/adc_research/theory/gated_correlation_roots.py',
                  'src/adc_research/theory/window_excitation.py',
                  'experiments/exp_045_released_third_roots/run.py','tests/test_released_third_mean_roots.py')
    write(output/'summary.json',{'scope':'fixed fourth=1, local three-slope root certificates from predeclared exact slices',
          'third_slice_grid':HIGH_GRID,'fit_conversions_per_case':11520,'third_is_free_in_certified_results':True,
          'global_three_parameter_search_complete':False,'front_stage_equilibrium_certified':False,
          'integer_or_time_varying_convergence_certified':False,'new_physical_samples':0,
          'new_training':False,'cadence_used':False,'online_algorithm_changed':False,'source_package_unchanged':True,
          'source_evidence_sha256':{str(path.relative_to(ROOT)).replace('\\','/'):value for path,value in originals.items()},
          'source_sha256':{name:digest(ROOT/name) for name in dependencies},'cases':cases})


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('source',type=Path)
    parser.add_argument('previous',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    run(args.source.resolve(),args.previous.resolve(),args.output.resolve())
