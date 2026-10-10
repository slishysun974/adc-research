"""Fixed rational parameters on existing backend segments; not global search."""
from fractions import Fraction as F
import json
from pathlib import Path
from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.gated_correlation_roots import scan_two_slope_roots,stage_correlations
from experiments.exp_042_correlation_roots.run import stage_rows,plain


def parameters(segment):
    low,high=map(F,segment['third_parameter_interval'][:2])
    values={(3*low+high)/4,(low+high)/2,(low+3*high)/4}
    if low<F(1)<high:values.add(F(1))
    return tuple(sorted(values))


def main():
    source=Path('artifacts/runs/EXP_039/window_v1')
    previous=json.loads(Path('artifacts/runs/EXP_045/local_v2/summary.json').read_text())
    for case in previous['cases']:
        if not case['certified_results']:continue
        samples=tuple(Sample(**json.loads(line)['sample']) for line in
                      (source/case['name']/'analog_digital_records.jsonl').read_text().splitlines()[:11520])
        for index,segment in enumerate(case['certified_results']):
            result=[]
            for h in parameters(segment):
                k2=tuple(F(a)*h+F(b) for a,b in zip(segment['direction'],segment['intercept']))
                rows=stage_rows(samples,1,k2)
                scan=scan_two_slope_roots(rows,F(128))
                result.append({'h':h,'status':scan.status,'roots':[{
                    'front':r.coefficients,'correlations':stage_correlations(rows,r.coefficients,F(128))}
                    for r in scan.roots]})
            print(case['name'],index,json.dumps(plain(result)),flush=True)


if __name__=='__main__':main()
