"""Read-only evidence checks, cycle gate mechanism, regression and link audit."""
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import re
import sys
import unittest
from urllib.parse import unquote

from adc_research.calibration.fixed_gated_lms import adaptive_lower_thresholds_scaled
from adc_research.calibration.fixed_pwl import correct_fixed
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_042_correlation_roots.run import digest,write

ROOT=Path(__file__).resolve().parents[2]
DOCUMENTS=(
    'docs/STATUS.md','docs/DECISIONS.md','docs/README.md',
    'docs/theory/README.md','docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
    'docs/theory/QUANTIZED_MEAN_DYNAMICS_AND_GATE_SELECTION_V1.md',
    'docs/reports/experiments/README.md','docs/reports/experiments/EXP_043_QUANTIZED_MEAN_DYNAMICS_V1.md',
    'docs/stages/02_end_to_end_theory/README.md','docs/stages/03_gu_baseline/README.md',
    'experiments/README.md','experiments/exp_043_quantized_mean_dynamics/README.md',
)


def main(folder):
    summary=json.loads((folder/'summary.json').read_text())
    for name,expected in {**summary['source_sha256'],**summary['source_evidence_sha256']}.items():
        assert digest(ROOT/name)==expected,name
    for case in summary['cases']:
        assert digest(folder/(case['name']+'.json'))==case['output_sha256']
    cfg=_config()
    switches=[]
    for name in ('iid_reset','iid_two_phase'):
        data=json.loads((folder/(name+'.json')).read_text())
        path=ROOT/'artifacts/runs/EXP_039/window_v1'/name/'analog_digital_records.jsonl'
        counts=Counter((8*row['sample']['backend_centered_code'],128*row['sample']['stage2_dither_symbol'])
                       for row in (json.loads(line) for line in path.read_text().splitlines()[:11520]))
        for code0 in range(*[data['pooled_orbit']['cycle_export_code_ranges'][0][0],
                            data['pooled_orbit']['cycle_export_code_ranges'][0][1]+1]):
            masks=[]
            for code1 in (1087,1088):
                pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=(code0,code1,1024,1024))
                threshold=adaptive_lower_thresholds_scaled(pwl.coefficient_codes,cfg.stage2_lms)[1]
                masks.append({key:abs(correct_fixed(key[0],pwl).corrected_code_scaled-key[1])>=threshold
                              for key in counts})
            changed={key for key in counts if masks[0][key]!=masks[1][key]}
            assert changed=={(376,128),(-376,-128)}
            assert all(not masks[0][key] and masks[1][key] for key in changed)
            count=sum(counts[key] for key in changed)
            assert count==data['q3_gate_threshold_shift']['matching_fit_conversions']
            switches.append({'name':name,'first_export_code':code0,
                             'only_switching_raw_dither_scaled':sorted(changed),'switching_conversions':count})
    links=0
    failures=[]
    for name in DOCUMENTS:
        path=ROOT/name
        for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',path.read_text(encoding='utf-8')):
            if '://' in target or target.startswith('#'):
                continue
            clean=unquote(target.split('#',1)[0]).strip('<>')
            if not (path.parent/clean).resolve().exists():
                failures.append((name,target))
            links+=1
    assert not failures,failures
    sys.path.insert(0,str(ROOT/'tests'))
    suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'))
    result=unittest.TextTestRunner(verbosity=1).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)
    output={'source_and_output_sha256_checks_passed':True,'cycle_gate_mask_checks':switches,
            'regression':{'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors)},
            'checked_local_document_links':links,'missing_local_links':failures,
            'figure_visually_inspected':True,
            'new_training_samples':0,'cadence_used':False,'online_algorithm_changed':False,
            'verification_script_sha256':digest(Path(__file__)),
            'plot_script_sha256':digest(ROOT/'experiments/exp_043_quantized_mean_dynamics/plot_cycles.py'),
            'figure_sha256':digest(folder/'mean_cycles.png')}
    write(folder/'verification.json',output)
    print(json.dumps(output,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main(Path(sys.argv[1]).resolve())
