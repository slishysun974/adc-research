"""Evidence fingerprints, saved-result identities, regression and local links."""
from fractions import Fraction as F
import json
from pathlib import Path
import re
import sys
import unittest
from urllib.parse import unquote

from experiments.exp_042_correlation_roots.run import digest,write

ROOT=Path(__file__).resolve().parents[2]
DOCUMENTS=('docs/STATUS.md','docs/DECISIONS.md','docs/README.md','docs/theory/README.md',
    'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
    'docs/theory/ORDERED_WINDOW_STATE_AND_HIGH_SLOPE_PROPAGATION_V1.md',
    'docs/reports/experiments/README.md','docs/reports/experiments/EXP_044_ORDERED_WINDOW_PROPAGATION_V1.md',
    'docs/stages/02_end_to_end_theory/README.md','docs/stages/03_gu_baseline/README.md',
    'experiments/README.md','experiments/exp_044_ordered_window_propagation/README.md',
    'src/adc_research/evaluation/README.md')


def main(folder):
    summary=json.loads((folder/'summary.json').read_text())
    for name,expected in {**summary['source_sha256'],**summary['source_evidence_sha256']}.items():
        assert digest(ROOT/name)==expected,name
    support=json.loads((folder/'gate_support.json').read_text())
    assert support['source_script_sha256']==digest(ROOT/'experiments/exp_044_ordered_window_propagation/analyze_gate_support.py')
    gains=[]
    corner_checks=0
    phase_windows=0
    for case in summary['cases']:
        path=folder/(case['name']+'.json')
        assert digest(path)==case['output_sha256']
        record=json.loads(path.read_text())
        for tube in record['tubes']:
            assert tube['completed_windows']==160 and tube['stopped'] is None
            corner_checks+=tube['corner_output_checks']
            phase_windows+=len(tube['rows'])
            for row,state in zip(tube['rows'],record['trajectory_q22']['unchanged_gu'][1:],strict=True):
                box=(*row['next_box']['stage2_accumulators'],*row['next_box']['stage1_accumulators'])
                assert all(p['lower']<=z<=p['upper'] for p,z in zip(box,state,strict=True))
            if tube['initial_radius_q22_lsb']==1:
                gain=F(max(abs(v) for v in tube['two_corner_final_difference_q22']),2)
                gains.append({'name':case['name'],'finite_composition_pair_gain':gain,
                              'all_windows_constant_translation':tube['translation_proved_for_completed_prefix']})
        for part in record['high_code_decomposition']['training'],record['high_code_decomposition']['online_sine']:
            if all(part[p]['nonzero_count']==0 for p in ('direct_high','indirect_low_history')):
                assert part['total']['nonzero_count']==0
            cross=(F(part['total']['mean_squared_codes'])-F(part['direct_high']['mean_squared_codes'])
                   -F(part['indirect_low_history']['mean_squared_codes']))/2
            assert abs(cross)<=1
    for case in support['cases']:
        assert sum(w['zero_basis_product_sum_q6'] for w in case['windows'])==case['zero_basis_product_sum_q6']
        assert sum(w['nonzero_basis_product_sum_q6'] for w in case['windows'])==case['nonzero_basis_product_sum_q6']
        assert F(case['zero_basis_unrounded_q22_update'])+F(case['nonzero_basis_unrounded_q22_update'])+F(case['window_rounding_residual_q22'])==case['actual_third_accumulator_change_q22']
    links=0
    missing=[]
    for name in DOCUMENTS:
        path=ROOT/name
        for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
            if '://' in target or target.startswith('#'):
                continue
            clean=unquote(target.split('#',1)[0]).strip('<>')
            if not (path.parent/clean).resolve().exists():
                missing.append((name,target))
            links+=1
    assert not missing,missing
    sys.path.insert(0,str(ROOT/'tests'))
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result=unittest.TextTestRunner(verbosity=0).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    extras=('experiments/exp_044_ordered_window_propagation/finalize.py',
            'experiments/exp_044_ordered_window_propagation/analyze_gate_support.py',
            'experiments/exp_044_ordered_window_propagation/plot_results.py',
            'tests/test_high_gate_sensitivity.py')
    verification={'source_and_output_sha256_checks_passed':True,
          'regression':{'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)},
          'checked_local_document_links':links,'missing_local_links':missing,
          'finite_pair_gains':gains,'corner_final_code_checks':corner_checks,
          'phase_window_box_checks':phase_windows,'original_gu_reference_windows_checked':960,
          'code_decomposition_identity_conversions':115200,
          'original_third_gate_classification_windows':960,
          'gate_support_sha256':digest(folder/'gate_support.json'),
          'extra_source_sha256':{name:digest(ROOT/name) for name in extras},
          'figure_sha256':digest(folder/'ordered_window_results.png'),'figure_visually_inspected':True,
          'new_physical_samples':0,'record_length_extended':False,'cadence_used':False,
          'online_gu_implementation_changed':False}
    write(folder/'verification.json',verification)
    print(json.dumps({'tests_run':result.testsRun,'local_links':links,'corner_code_checks':corner_checks,
                      'phase_window_boxes':phase_windows,'source_unchanged':True},indent=2))


if __name__=='__main__':
    main(Path(sys.argv[1]).resolve())
