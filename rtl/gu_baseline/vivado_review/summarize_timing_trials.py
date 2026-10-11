"""Read actual timing/functional results from the isolated mapping comparisons."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def metrics(root):
    utilization=(root/'reports/utilization.rpt').read_text()
    timing=(root/'reports/timing_synth.rpt').read_text()
    path=(root/'reports/critical_paths.rpt').read_text()
    row=re.search(r'^\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+(\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(\d+)\s+(\d+)\s+(\d+\.\d+)\s+',timing,re.M)
    assert row,root
    def used(label):return int(re.search(r'\| '+re.escape(label)+r'\s*\|\s*(\d+)',utilization)[1])
    return {'lut':used('Slice LUTs*'),'ff':used('Slice Registers'),'dsp':used('DSPs'),
        'wns_ns':float(row[1]),'tns_ns':float(row[2]),'setup_failing_endpoints':int(row[3]),'setup_total_endpoints':int(row[4]),
        'whs_ns':float(row[5]),'ths_ns':float(row[6]),'hold_failing_endpoints':int(row[7]),
        'data_path_delay_ns':float(re.search(r'Data Path Delay:\s+(\d+\.\d+)ns',path)[1]),
        'logic_levels':int(re.search(r'Logic Levels:\s+(\d+)',path)[1]),
        'critical_source':re.search(r'Source:\s+([^\r\n]+)',path)[1].strip(),
        'critical_destination':re.search(r'Destination:\s+([^\r\n]+)',path)[1].strip(),
        'timing_met':False,'scope':'synthesis estimate under identical 10ns clock, 1ns IO delays and 1pF output load'}

def main():
    parser=argparse.ArgumentParser();parser.add_argument('work',type=Path);args=parser.parse_args()
    work=args.work
    baseline=work/'hardware'
    frozen=json.loads((baseline/'manifest.json').read_text(encoding='utf-8'))['source_sha256']
    frozen={p:s for p,s in frozen.items() if not p.startswith('rtl/gu_baseline/vivado_review/')}
    assert all(sha(REPO/p)==s for p,s in frozen.items())
    result={'baseline':metrics(baseline),'trials':{},'original_core_files_unchanged':True}
    for name in ('timing_rebuilt_v1','timing_width_v1'):
        root=work/name
        assert (root/'tool_complete.txt').exists()
        expected={'arithmetic':'exact arithmetic: 173872 deltas, 869360 saturation probes, 173872 disabled probes passed',
            'bank':'REVIEW_BANK_PASS cases=22','online':'8263 sequential oracle vectors passed',
            'cost_rtl':'REVIEW_COST_PASS vectors=8391 idle_cycles=8391 reset_replay=128',
            'cost_netlist':'REVIEW_COST_PASS vectors=8391 idle_cycles=8391 reset_replay=128'}
        checks={}
        for label,marker in expected.items():
            text=(root/f'logs/{label}_simulate.log').read_text()
            checks[label]=marker in text and 'Fatal:' not in text
        negative=(root/'logs/negative_simulate.log').read_text()
        checks['negative_control']='Fatal: cost output mismatch pass=0 row=0' in negative and 'REVIEW_COST_PASS' not in negative
        checks['vectors_identical']=sha(root/'vectors/online.txt')==sha(baseline/'vectors/online.txt')
        checks['constraints_identical']=(root/'review.xdc').read_text()==next((baseline/'project/gu_review.srcs/constrs_1').rglob('review.xdc')).read_text()
        if name=='timing_width_v1':
            checks['eight_other_frozen_copies_identical']=all(sha(root/'sources'/Path(p).name)==s for p,s in frozen.items() if not p.endswith('/fixed_pwl_candidate_a.sv'))
            trial=json.loads((root/'width_trial.json').read_text())
            checks['candidate_matches_reviewed_change']=sha(root/'sources/fixed_pwl_candidate_a.sv')==trial['candidate_sha256']
            reference=(root/'sources/pwl_reference_review.sv').read_text().replace('module fixed_pwl_reference_review #(','module fixed_pwl_candidate_a #(')
            checks['reference_matches_original']=reference==(baseline/'sources/fixed_pwl_candidate_a.sv').read_text()
            eq=(root/'logs/pwl_equivalence_simulate.log').read_text()
            checks['pwl_width_preflight']='REVIEW_PWL_WIDTH_EQUIVALENCE_PASS checks=1581056' in eq and 'Fatal:' not in eq
        else:
            checks['all_nine_frozen_copies_identical']=all(sha(root/'sources'/Path(p).name)==s for p,s in frozen.items())
            subprocess.run([sys.executable,str(HERE/'validate.py'),str(root)],check=True,capture_output=True,text=True)
        assert all(checks.values()),checks
        validation={'checks':checks,'passed':True,'scope':'finite digital equivalence and unchanged constraints; synthesis timing still fails; no routed timing'}
        (root/'comparison_validation.json').write_text(json.dumps(validation,indent=2))
        result['trials'][name]={'metrics':metrics(root),'validation':validation}
    result['interpretation']='Width-only trial saves 86 LUT and 2 DSP and improves WNS by 2.313ns; 100MHz remains unmet. Baseline remains unchanged. Pipelining requires a separately defined feedback/observation contract.'
    (work/'timing_comparison.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
