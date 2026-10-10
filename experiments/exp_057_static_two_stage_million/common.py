"""Offline helpers for the frozen EXP-057 static cascade controls."""

from fractions import Fraction
import json
import math
from pathlib import Path

import numpy as np
import yaml

from adc_research.calibration.gu_baseline import build_gu_two_stage_baseline
from adc_research.calibration.gated_lms import GatedLmsConfig
from adc_research.calibration.adaptive_two_stage import TwoStageAdaptiveConfig
from adc_research.platform.amplifier import StaticCubicTruthConfig
from adc_research.platform.pipeline import StaticPipelineNonidealities
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stage import StaticStageNonidealities

ROOT=Path(__file__).resolve().parents[2]
PROTOCOL=Path(__file__).with_name("protocol.json")
MASK=(1<<64)-1


def write(path,data):
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")


def setup(protocol):
    arch=yaml.safe_load((ROOT/"configs/architectures/gu_behavioral_v1.yaml").read_text(encoding="utf-8"))
    pipeline=build_gu_static_hypothesis_a(arch)
    cascade=build_gu_two_stage_baseline(pipeline,arch["pwl_implications"])
    cfg=TwoStageAdaptiveConfig(cascade,
        GatedLmsConfig(128,tuple(n/protocol["steps"]["stage1_denominator"] for n in protocol["steps"]["numerators"])),
        GatedLmsConfig(32,tuple(n/protocol["steps"]["stage2_denominator"] for n in protocol["steps"]["numerators"])))
    return pipeline,cfg


def truth(case):
    return StaticPipelineNonidealities(*[
        StaticStageNonidealities(cubic_truth=StaticCubicTruthConfig(*case[bank]))
        for bank in ("stage1","stage2")])


def word(seed,stream,index):
    x=(seed^((stream*0xD1B54A32D192ED03)&MASK)^((index*0x9E3779B97F4A7C15)&MASK))&MASK
    x=((x^(x>>30))*0xBF58476D1CE4E5B9)&MASK
    x=((x^(x>>27))*0x94D049BB133111EB)&MASK
    return x^(x>>31)


def input_tags(seed,index):
    # Preserve native double multiplication order.
    x=-.82+1.64*(word(seed,1,index)>>11)*(1/9007199254740992)
    return x,tuple(-1 if word(seed,s,index)>>63==0 else 1 for s in (2,3))


def plant_arrays(x,d1,d2,case):
    """Offline vector generator, cross-checked against original platform."""
    thresholds=np.arange(-.875,1,.25)
    q1=np.searchsorted(thresholds,x,side="right")-4
    z1=4*(x-q1/4+d1/32)
    a1,b1=case["stage1"];a2,b2=case["stage2"]
    r1=a1*z1+b1*z1**3
    q2=np.searchsorted(thresholds,r1,side="right")-4
    z2=4*(r1-q2/4+d2/32)
    r2=a2*z2+b2*z2**3
    return q1,q2,r1,r2,128*r2,np.floor((r2+1)*128)-128


def basis(raw,width):
    mag=np.abs(raw)
    return np.sign(raw)[:,None]*np.clip(mag[:,None]-width*np.arange(4),0,width)


def corrected_arrays(q1,q2,backend,d1,d2,k):
    # Offline scoring, not a new production update interface.
    p2=basis(backend,32)@k[4:]
    raw1=128*q2+p2-16*d2
    if np.any(raw1< -512) or np.any(raw1>=512):raise ValueError("PWL input domain")
    p1=basis(raw1,128)@k[:4]
    return 512*q1+p1-64*d1+2048,p1-64*d1,p2-16*d2,raw1


def window_original_products(q1,q2,backend,d1,d2,k):
    output,y1,y2,raw1=corrected_arrays(q1,q2,backend,d1,d2,k)
    sums=np.zeros(8);gates=np.zeros(8,dtype=np.int64)
    for bank,(local,dd,width) in enumerate(((y1,64*d1,128),(y2,16*d2,32))):
        thresholds=np.concatenate(([0],width*np.cumsum(k[bank*4:bank*4+3])))
        for j in range(4):
            mask=np.ones(len(local),dtype=bool) if j==0 else np.abs(local)>=thresholds[j]
            sums[bank*4+j]=float(np.sum(dd*local*mask))
            gates[bank*4+j]=int(np.sum(mask))
    return output,sums,gates


def metrics(values,x,tone):
    # Sum residual bins directly: do not subtract large nearly equal powers.
    spectrum=np.fft.rfft(values-np.mean(values))/len(values)
    p=np.abs(spectrum)**2;p[1:-1]*=2
    signal=float(p[tone]);p[[0,tone]]=0
    residual=float(np.sum(p));spur=float(np.max(p))
    def db(den):return 10*math.log10(signal/den) if den>0 else "+inf"
    error=values-(2048*(x+1))
    return {"mse_codes_squared":float(np.mean(error**2)),"mae_codes":float(np.mean(np.abs(error))),
            "mean_error_codes":float(np.mean(error)),"sndr_db":db(residual),"sfdr_dbc":db(spur),
            "residual_power":residual,"worst_spur_bin":int(np.argmax(p)),
            "output_clips":int(np.count_nonzero((values<0)|(values>4095)))}
