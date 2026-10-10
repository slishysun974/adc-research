"""Predeclared third-slope slices, not a global three-parameter search."""
from fractions import Fraction as F
import json
from pathlib import Path
from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.gated_correlation_roots import scan_two_slope_roots,stage_correlations
from experiments.exp_042_correlation_roots.run import stage_rows,plain


def main():
    source=Path('artifacts/runs/EXP_039/window_v1')
    for case in json.loads((source/'summary.json').read_text())['cases']:
        path=source/case['name']/'analog_digital_records.jsonl'
        samples=tuple(Sample(**json.loads(line)['sample']) for line in path.read_text().splitlines()[:11520])
        rows=stage_rows(samples,2)
        result=[]
        for high in (F(3,4),F(7,8),F(1),F(9,8),F(5,4)):
            scan=scan_two_slope_roots(rows,32,(high,F(1)))
            result.append({'third':high,'status':scan.status,'roots':[
                {'coefficients':root.coefficients,'correlations':stage_correlations(rows,root.coefficients,32)} for root in scan.roots]})
        print(case['name'],json.dumps(plain(result)),flush=True)


if __name__=='__main__':
    main()
