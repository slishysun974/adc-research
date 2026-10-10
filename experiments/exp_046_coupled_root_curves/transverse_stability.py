"""Local front-plane mean stability, with closure and gate validity checked.

If det(I-M)<0, the characteristic polynomial is negative at 1 and positive
for large positive arguments, proving a real eigenvalue greater than one.
An infinity norm below one separately certifies contraction in this plane.
Neither result removes the neutral joint-curve direction.
"""
from fractions import Fraction as F
import json
from pathlib import Path
import sys

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.gated_correlation_roots import stage_basis,stage_correlations
from adc_research.theory.released_third_mean_roots import affine_correlations
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_042_correlation_roots.run import digest,stage_rows,write

ROOT=Path(__file__).resolve().parents[2]


def analyze_front_plane(rows,coefficients,steps,width=F(128)):
    matrix,constant,masks=affine_correlations(rows,coefficients,width)
    regular=True
    radii=[min(k,2-k)/2 for k in coefficients[:2]]
    for row,gates in zip(rows,masks):
        basis=stage_basis(row.raw,width)
        y=sum((k*p for k,p in zip(coefficients,basis)),F(0))-row.dither
        for i in range(1,4):
            margin=abs(abs(y)-width*sum(coefficients[:i],F(0)))
            sign=(y>0)-(y<0)
            identity=all(sign*basis[j]==width*int(j<i) for j in range(2))
            if margin==0:
                if not identity:regular=False
            else:
                lipschitz=sum(abs(p) for p in basis[:2])+width*min(i,2)
                if lipschitz:radii.append(margin/(2*lipschitz))
    closed=all(not g[2] and not g[3] for g in masks)
    m=tuple(tuple(F(i==j)-steps[i]*matrix[i][j] for j in range(2)) for i in range(2))
    norm=max(sum(abs(v) for v in row) for row in m)
    at_one=(1-m[0][0])*(1-m[1][1])-m[0][1]*m[1][0]
    trace=m[0][0]+m[1][1]
    determinant=m[0][0]*m[1][1]-m[0][1]*m[1][0]
    at_minus_one=1+trace+determinant
    determinant_gap=1-determinant
    return {'relative_front_plane_regular':regular,'higher_front_gates_all_closed':closed,
            'protected_front_coefficient_radius':min(radii) if regular else F(0),
            'transfer_matrix':m,'infinity_norm':norm,'characteristic_polynomial_at_one':at_one,
            'characteristic_polynomial_at_minus_one':at_minus_one,'one_minus_determinant':determinant_gap,
            'front_plane_schur_stable':regular and closed and at_one>0 and at_minus_one>0 and determinant_gap>0,
            'front_plane_contracts':regular and closed and norm<1,
            'front_plane_has_real_expanding_eigenvalue':regular and closed and at_one<0}


def main(source,folder):
    summary=json.loads((folder/'summary.json').read_text())
    for name,expected in {**summary['source_sha256'],**summary['source_evidence_sha256']}.items():
        assert digest(ROOT/name)==expected,name
    cfg=_config()
    steps=tuple(120*s for s in cfg.stage1_lms.step_sizes[:2])
    results=[]
    for case in summary['cases']:
        data=json.loads((folder/(case['name']+'.json')).read_text())
        samples=tuple(Sample(**json.loads(line)['sample']) for line in
                      (source/case['name']/'analog_digital_records.jsonl').read_text().splitlines()[:11520])
        for index,curve in enumerate(data['candidates']):
            coefficients=tuple(map(F,curve['seed_coefficients']))
            rows=stage_rows(samples,1,coefficients[:4])
            assert stage_correlations(rows,coefficients[4:],F(128))==(F(0),)*4
            result=analyze_front_plane(rows,coefficients[4:],steps)
            result.update(name=case['name'],candidate=index,parameter=F(curve['seed_parameter']))
            results.append(result)
            print(case['name'],index,result['front_plane_schur_stable'],result['front_plane_contracts'],flush=True)
    write(folder/'transverse_stability.json',{'scope':'fixed backend at an exact root, front first two slopes only; continuous pooled mean',
          'joint_strict_contraction_certified':False,'time_varying_or_integer_stability_certified':False,
          'source_script_sha256':digest(Path(__file__)),'candidates':results})


if __name__=='__main__':main(Path(sys.argv[1]).resolve(),Path(sys.argv[2]).resolve())
