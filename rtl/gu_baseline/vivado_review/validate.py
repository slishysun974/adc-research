"""Require actual XSim markers, not merely Vivado's process exit code."""
import argparse
import hashlib
import json
from pathlib import Path

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('run', type=Path)
    parser.add_argument('--snapshot-only', action='store_true', help='verify portable frozen copies without accessing the original repository')
    args = parser.parse_args()
    root = args.run.resolve()
    original = (root / 'logs/vivado.log').read_text(errors='replace')
    def log(name, fallback=None):
        for suffix in ('_repaired', ''):
            path = root / f'logs/{name}{suffix}_simulate.log'
            if path.exists():
                text = path.read_text(errors='replace')
                assert 'Fatal:' not in text, path
                return text
        if fallback:
            assert fallback in original, fallback
            return original
        raise AssertionError(f'Missing log: {name}')
    arithmetic = 'exact arithmetic: 173872 deltas, 869360 saturation probes, 173872 disabled probes passed'
    checks = {
        'exact_arithmetic': arithmetic in log('arithmetic', arithmetic),
        'bank_thresholds': 'REVIEW_BANK_PASS cases=22' in log('bank', 'REVIEW_BANK_PASS cases=22'),
        'all_eight_states': '8263 sequential oracle vectors passed' in log('online'),
        'rtl_outputs_reset_idle': 'REVIEW_COST_PASS vectors=8391 idle_cycles=8391 reset_replay=128' in log('cost_rtl'),
        'netlist_outputs_reset_idle': 'REVIEW_COST_PASS vectors=8391 idle_cycles=8391 reset_replay=128' in log('cost_netlist'),
    }
    negative = (root / 'logs/negative_simulate.log').read_text(errors='replace')
    checks['negative_control_rejected'] = 'Fatal: cost output mismatch pass=0 row=0' in negative and 'REVIEW_COST_PASS' not in negative
    for name in ('utilization.rpt', 'timing_synth.rpt', 'check_timing.rpt'):
        checks[name] = (root / 'reports' / name).is_file()
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    source_root = Path(manifest['repository'])
    frozen = {rel: digest for rel,digest in manifest['source_sha256'].items() if not rel.startswith('rtl/gu_baseline/vivado_review/')}
    checks['frozen_rtl_and_bench_snapshots_match'] = all(hashlib.sha256((root / 'sources' / Path(rel).name).read_bytes()).hexdigest() == digest for rel,digest in frozen.items())
    if not args.snapshot_only:
        checks['original_rtl_and_benches_unchanged'] = all(hashlib.sha256((source_root / rel).read_bytes()).hexdigest() == digest for rel,digest in frozen.items())
    result = {'checks': checks, 'passed': all(checks.values()), 'scope': 'finite digital functional checks; no physical timing or ADC performance validation'}
    (root / 'validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    if not result['passed']:
        raise SystemExit(1)

if __name__ == '__main__':
    main()
