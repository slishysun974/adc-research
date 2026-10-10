"""Final reconstruction, evidence audit, regression and documentation links."""
from fractions import Fraction as F
import json
from pathlib import Path
import re
import sys
import unittest
from urllib.parse import unquote

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.coupled_root_curve import build_front_curve,certify_interval
from experiments.exp_042_correlation_roots.run import digest,write

ROOT=Path(__file__).resolve().parents[2]
DOCS=('docs/STATUS.md','docs/DECISIONS.md','docs/README.md','docs/theory/README.md',
      'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
      'docs/theory/COUPLED_MEAN_ROOT_CURVES_AND_INTEGER_REQUESTS_V1.md',
      'docs/reports/experiments/README.md','docs/reports/experiments/EXP_046_COUPLED_ROOT_CURVES_V1.md',
      'docs/reports/RESEARCH_STATUS_PLAIN_2026-10-09.md',
      'docs/stages/02_end_to_end_theory/README.md','docs/stages/03_gu_baseline/README.md',
      'experiments/README.md','experiments/exp_046_coupled_root_curves/README.md')


def main(source,backend_source,folder):
    summary=json.loads((folder/'summary.json').read_text())
    fingerprints={**summary['source_sha256'],**summary['source_evidence_sha256']}
    for name,expected in fingerprints.items():assert digest(ROOT/name)==expected,name
    backend_cases={c['name']:c for c in json.loads((backend_source/'summary.json').read_text())['cases']}
    curves=points=windows=updater_checks=0
    for case in summary['cases']:
        path=folder/(case['name']+'.json')
        assert digest(path)==case['output_sha256']
        data=json.loads(path.read_text())
        samples=tuple(Sample(**json.loads(line)['sample']) for line in
                      (source/case['name']/'analog_digital_records.jsonl').read_text().splitlines()[:11520])
        for candidate in data['candidates']:
            segment=backend_cases[case['name']]['certified_results'][candidate['backend_segment']]
            direction=tuple(map(F,segment['direction']))
            intercept=tuple(map(F,segment['intercept']))
            h=F(candidate['seed_parameter'])
            front=tuple(map(F,candidate['seed_coefficients'][4:]))
            model=build_front_curve(samples,direction,intercept,h,front)
            assert model['status']=='constructed' and model['front_all_four_correlations_identically_zero']
            for field in ('denominator','numerator_u','numerator_v'):
                assert model[field]==tuple(map(F,candidate['curve_model'][field]))
            lo,hi=map(F,candidate['certificate']['parameter_interval'])
            back_lo,back_hi=map(F,segment['third_parameter_interval'][:2])
            assert back_lo<lo<hi<back_hi
            assert certify_interval(model,lo,hi)
            assert candidate['all_eight_zero_on_certified_curve']
            for check in candidate['exact_curve_checks']:
                assert all(F(x)==0 for x in check['all_eight_correlations'])
            integer=candidate['integer_diagnostics']
            assert integer['quantized_state_legal'] and not integer['virtual_mean_stops']
            assert len(integer['frozen_window_requests'])==96
            assert all(any(request) for request in integer['frozen_window_requests'])
            curves+=1
            points+=len(candidate['exact_curve_checks'])
            windows+=len(integer['frozen_window_requests'])
            updater_checks+=integer['actual_updater_window_checks']
    boxes=json.loads((folder/'integer_curve_boxes.json').read_text())
    assert boxes['source_script_sha256']==digest(ROOT/'experiments/exp_046_coupled_root_curves/integer_curve_boxes.py')
    assert len(boxes['curves'])==curves
    combinations=0
    for box in boxes['curves']:
        assert box['status']=='completed' and box['undefined_branch'] is None
        assert not box['enclosure_may_include_illegal_initial_states']
        assert box['no_integer_mean_fixed_state_on_legal_quantized_curve']
        assert not box['possible_fixed_code_combinations']
        assert all(not c['possible_fixed_state'] for c in box['tested_combinations'])
        combinations+=len(box['tested_combinations'])
    assert combinations==boxes['total_tested_code_combinations']==60
    stability=json.loads((folder/'transverse_stability.json').read_text())
    assert stability['source_script_sha256']==digest(ROOT/'experiments/exp_046_coupled_root_curves/transverse_stability.py')
    assert len(stability['candidates'])==curves
    assert all(r['front_plane_schur_stable'] and r['relative_front_plane_regular'] and
               r['higher_front_gates_all_closed'] for r in stability['candidates'])
    pair=json.loads((folder/'periodic255_reset.json').read_text())['candidates'][4:6]
    assert pair[0]['seed_coefficients'][:4]==pair[1]['seed_coefficients'][:4]
    gap=pair[0]['offline_frozen_scores']['online_sine']['spectrum_float']['sndr_db']-pair[1]['offline_frozen_scores']['online_sine']['spectrum_float']['sndr_db']
    assert 16.97<gap<16.98
    links=0
    missing=[]
    for name in DOCS:
        path=ROOT/name
        for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
            if '://' in target or target.startswith('#'):continue
            clean=unquote(target.split('#',1)[0]).strip('<>')
            if not (path.parent/clean).resolve().exists():missing.append((name,target))
            links+=1
    assert not missing,missing
    sys.path.insert(0,str(ROOT/'tests'))
    result=unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.discover(str(ROOT/'tests')))
    if not result.wasSuccessful():raise SystemExit(1)
    for name,expected in fingerprints.items():assert digest(ROOT/name)==expected,name
    extras=('experiments/exp_046_coupled_root_curves/finalize.py',
            'experiments/exp_046_coupled_root_curves/integer_curve_boxes.py',
            'experiments/exp_046_coupled_root_curves/transverse_stability.py',
            'experiments/exp_046_coupled_root_curves/plot_results.py',
            'tests/test_front_plane_stability.py','tests/test_coupled_curve_quantization.py')
    verification={'source_and_output_sha256_checks_passed':True,
        'reconstructed_all_eight_zero_curve_certificates':curves,'exact_curve_points':points,
        'export_code_combinations':combinations,'no_integer_mean_fixed_states_on_certified_curves':True,
        'frozen_window_requests_checked':windows,'original_updater_window_checks':updater_checks,
        'front_plane_schur_stable_seeds':len(stability['candidates']),
        'front_plane_infinity_contraction_seeds':sum(r['front_plane_contracts'] for r in stability['candidates']),
        'same_backend_two_front_roots_sndr_gap_float_db':gap,
        'regression':{'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)},
        'checked_local_document_links':links,'missing_local_links':missing,
        'extra_source_sha256':{name:digest(ROOT/name) for name in extras},
        'supplementary_result_sha256':{name:digest(folder/name) for name in ('integer_curve_boxes.json','transverse_stability.json')},
        'figure_sha256':digest(folder/'coupled_roots_and_scores.png'),'figure_visually_inspected':True,
        'global_joint_search_complete':False,'integer_or_time_varying_convergence_certified':False,
        'new_training':False,'cadence_used':False,'online_algorithm_changed':False}
    write(folder/'verification.json',verification)
    print(json.dumps({'curves':curves,'curve_points':points,'code_combinations':combinations,
                      'window_requests':windows,'front_stable_seeds':len(stability['candidates']),
                      'tests':result.testsRun,'local_links':links,'sndr_gap_db':gap},indent=2))


if __name__=='__main__':main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve(),Path(sys.argv[3]).resolve())
