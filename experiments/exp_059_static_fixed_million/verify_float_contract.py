"""Supplement v1 replay at exact gates: float layer follows ORIGINAL doubles.

The frozen v1 verifier used exact-real Fraction gates for mode0 as well as
fixed modes. At a subtraction-rounding equality that is the wrong reference.
Retain v1, the failure log, all run hashes/data, and the three exact fixed
references; adapt ONLY the mode0 expected readout through original observe.
"""
import argparse
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path

from adc_research.calibration.adaptive_two_stage import TwoStageAdaptiveState, observe
from adc_research.calibration.gated_lms import GatedLmsState, adaptive_lower_thresholds
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.theory.static_fixed_contract import Readout
from experiments.exp_057_static_two_stage_million.common import setup, write
from experiments.exp_059_static_fixed_million import verify as v1


def run(folder):
    source=json.loads((folder/'source_protocol.json').read_text(encoding='utf-8-sig'))
    _,cfg=setup(source)
    original=v1.readout
    counter={'float_samples':0,'exact_real_gate_disagreements':0}

    def reference(q1,q2,backend,d1,d2,k,*,data_q3):
        rational=original(q1,q2,backend,d1,d2,k,data_q3=data_q3)
        if data_q3:return rational
        state=TwoStageAdaptiveState(GatedLmsState(tuple(map(float,k[:4])),(0,)*4),
                                   GatedLmsState(tuple(map(float,k[4:])),(0,)*4))
        result=observe(DigitalCalibrationSample(q1,q2,int(backend),d1,d2),state,cfg)
        ys=(result.stage1_local_learning_output,result.stage2_local_learning_output)
        thresholds=(adaptive_lower_thresholds(state.stage1.coefficients,128),
                    adaptive_lower_thresholds(state.stage2.coefficients,32))
        gates=tuple(tuple(j==0 or abs(y)>=ts[j] for j in range(4)) for y,ts in zip(ys,thresholds))
        raw=result.calibration.stage1_raw_code
        support=tuple(tuple(abs(r)>j*width for j in range(4)) for r,width in ((raw,128),(int(backend),32)))
        counter['float_samples']+=1
        counter['exact_real_gate_disagreements']+=sum(a!=b for aa,bb in zip(gates,rational.gates) for a,b in zip(aa,bb))
        return Readout(F.from_float(raw),F.from_float(ys[0]),F.from_float(ys[1]),
                       F.from_float(result.calibration.unclipped_output_code),
                       tuple(tuple(F.from_float(t) for t in ts) for ts in thresholds),gates,support)

    helper=Path(__file__)
    before=sha256(helper.read_bytes()).hexdigest()
    v1.readout=reference
    try:v1.verify(folder)
    finally:v1.readout=original
    assert sha256(helper.read_bytes()).hexdigest()==before
    write(folder/'float_contract_verification.json',{'passed':True,**counter,
        'supplement_source':str(helper),'supplement_sha256':before,'frozen_run_sources_changed':False,
        'fixed_layer_reference_changed':False,'run_reexecuted':False,
        'reason':'Exact-real mode0 gate was not the declared original double subtraction/gate contract.'})
    print(json.dumps(counter),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path)
    run(parser.parse_args().folder.resolve())
