"""Local-root fingerprints, exact digital Gram ranks, regression and links."""
from fractions import Fraction as F
import json
from pathlib import Path
import re
import sys
import unittest
from urllib.parse import unquote

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.gated_correlation_roots import stage_basis
from adc_research.theory.window_excitation import exact_nullspace
from experiments.exp_042_correlation_roots.run import digest,stage_rows,write

ROOT=Path(__file__).resolve().parents[2]
DOCS=('docs/STATUS.md','docs/DECISIONS.md','docs/README.md','docs/theory/README.md',
      'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
      'docs/theory/RELEASED_THIRD_ROOT_SEGMENTS_V1.md',
      'docs/reports/experiments/README.md','docs/reports/experiments/EXP_045_RELEASED_THIRD_ROOTS_V1.md',
      'docs/stages/02_end_to_end_theory/README.md','docs/stages/03_gu_baseline/README.md',
      'experiments/README.md','experiments/exp_045_released_third_roots/README.md')


def main(folder):
    summary=json.loads((folder/'summary.json').read_text())
    for name,expected in {**summary['source_sha256'],**summary['source_evidence_sha256']}.items():
        assert digest(ROOT/name)==expected,name
    helper='experiments/exp_042_correlation_roots/run.py'
    frozen_helper=json.loads((ROOT/'artifacts/runs/EXP_042/roots_v4/summary.json').read_text())['source_sha256'][helper]
    assert digest(ROOT/helper)==frozen_helper
    gram_ranks=[]
    segments=checks=0
    for case in summary['cases']:
        assert digest(folder/(case['name']+'.json'))==case['output_sha256']
        path=ROOT/'artifacts/runs/EXP_039/window_v1'/case['name']/'analog_digital_records.jsonl'
        samples=tuple(Sample(**json.loads(line)['sample']) for line in path.read_text().splitlines()[:11520])
        rows=stage_rows(samples,2)
        gram=[[F(0)]*3 for _ in range(3)]
        for row in rows:
            basis=stage_basis(row.raw,F(32))
            for i in range(3):
                for j in range(3):
                    gram[i][j]+=row.count*basis[i]*basis[j]/11520
        gram_ranks.append({'name':case['name'],'rank':3-len(exact_nullspace(gram))})
        for result in case['certified_results']:
            if result['status']=='certified_root_segment_in_seed_masks':
                segments+=1
                assert result['all_four_correlations_zero_on_segment']
                assert result['gate_counts'][2:]==[0,0]
                assert result['readout_varying_conversions']>0
                checks+=result['direct_rational_check_points']
    assert segments==5
    links=0
    missing=[]
    for name in DOCS:
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
    result=unittest.TextTestRunner(verbosity=0).run(unittest.defaultTestLoader.discover(str(ROOT/'tests')))
    if not result.wasSuccessful():
        raise SystemExit(1)
    verification={'source_and_output_sha256_checks_passed':True,
        'regression':{'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)},
        'certified_distinct_segments':segments,'direct_rational_segment_points':checks,
        'digital_readout_gram_rank_first3':gram_ranks,
        'gram_scope':'sensitivity of continuous digital PWL output, not physical observability or a known correct target',
        'checked_local_document_links':links,'missing_local_links':missing,
        'extra_source_sha256':{helper:frozen_helper,
            'experiments/exp_045_released_third_roots/finalize.py':digest(Path(__file__)),
            'experiments/exp_045_released_third_roots/plot_segments.py':digest(ROOT/'experiments/exp_045_released_third_roots/plot_segments.py')},
        'figure_sha256':digest(folder/'released_third_segments.png'),'figure_visually_inspected':True,
        'global_three_parameter_search_complete':False,'front_stage_equilibrium_certified':False,
        'new_training':False,'cadence_used':False,'online_algorithm_changed':False}
    write(folder/'verification.json',verification)
    print(json.dumps({'tests':result.testsRun,'local_links':links,'root_segments':segments,
                      'rational_check_points':checks,'digital_gram_ranks':[r['rank'] for r in gram_ranks]},indent=2))


if __name__=='__main__':
    main(Path(sys.argv[1]).resolve())
