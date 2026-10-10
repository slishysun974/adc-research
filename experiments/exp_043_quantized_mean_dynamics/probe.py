"""Development probe; formal provenance/phase checks are in run.py."""
from collections import Counter
from fractions import Fraction as F
import json
from pathlib import Path

from adc_research.calibration.fixed_point import round_fraction
from adc_research.theory.quantized_mean_dynamics import (
    FixedStageRow, FrozenStageMean, certify_rectangle, export_cell, export_code,
)
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_042_correlation_roots.run import plain


def main():
    source = Path('artifacts/runs/EXP_039/window_v1')
    cfg = _config()
    for case in json.loads((source/'summary.json').read_text())['cases']:
        name = case['name']
        rows = [json.loads(line)['sample'] for line in
                (source/name/'analog_digital_records.jsonl').read_text().splitlines()[:11520]]
        counts = Counter((8*r['backend_centered_code'],128*r['stage2_dither_symbol']) for r in rows)
        model = FrozenStageMean(tuple(FixedStageRow(raw,d,count) for (raw,d),count in counts.items()),
                                width_scaled=256, steps=cfg.stage2_lms.step_sizes)
        prior = json.loads((Path('artifacts/runs/EXP_042/roots_v4')/(name+'.json')).read_text())
        scan = prior['stage2_scan']
        if scan['roots']:
            coefficients = tuple(F(x) for x in scan['roots'][0]['coefficients'][:2])
        else:
            t=F(16,15)
            coefficients=tuple(F(p)*t+F(q) for p,q in zip(scan['coefficient_line_slopes'],scan['coefficient_line_intercepts']))
        initial=tuple(round_fraction(k.numerator*2**22,k.denominator,'nearest_even') for k in coefficients)
        center=tuple(export_code(z) for z in initial)
        result = {'name':name,'center':center,'initial_request':model.request(center)}
        attempts=[]
        for radii in [(r,r) for r in (1,2,4,8,16)]+[(r,m*r) for r in (1,2,4,8) for m in (2,4,8,16)]:
            bounds=tuple((export_cell(c-r)[0],export_cell(c+r)[1]) for c,r in zip(center,radii))
            certificate=certify_rectangle(model,bounds)
            attempts.append({'radii':radii,'invariant':certificate['invariant'],
                             'violations':len(certificate['violating_codes']),
                             'fixed':certificate['fixed_state_cells'],
                             'high_zero':certificate['all_clamped_requests_zero'],
                             'high_closed':certificate['all_clamped_gates_closed']})
            if certificate['invariant']:
                break
        result['attempts']=attempts
        print(json.dumps(plain(result)),flush=True)


if __name__=='__main__':
    main()
