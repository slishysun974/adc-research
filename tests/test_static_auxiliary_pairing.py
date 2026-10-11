from fractions import Fraction as F
import unittest

import numpy as np

from adc_research.theory.static_auxiliary_mismatch import CubicTransfer, convert
from adc_research.theory.static_fixed_contract import readout, export, commit
from experiments.exp_061_static_auxiliary_million.analyze import crossed, local, online_replay, raw_fields


def record(trace):
    return np.array([[trace.q1,trace.q2,trace.backend,trace.z1,trace.main1,
                      trace.auxiliary1,trace.z2,trace.main2]],dtype=float).T


class StaticAuxiliaryPairingTests(unittest.TestCase):
    def test_ideal_resistance_and_nonzero_state_interaction_hand_example(self):
        one=CubicTransfer(F(1));a=convert(F(1,2048),1,1,one,one,one)
        b=convert(F(1,2048),1,1,one,CubicTransfer(F(97,100)),one)
        r0,r1=record(a),record(b);tags=np.array([[1,1]]);x=np.array([1/2048])
        result=crossed(raw_fields(r0),raw_fields(r1),r0,r1,tags,x,np.ones(8),np.array([1]*4+[1.25]*4))
        self.assertEqual(result['continuous']['term_mean'],[0,-11.75,32])
        self.assertEqual(result['continuous']['actual_mse'],410.0625)
        self.assertEqual(result['same_state_correlation_gate_term'][6],1040)
        self.assertEqual(result['same_state_correlation_readout_term'][4],2048)

    def test_online_vector_replay_against_fraction_windows_and_signed_rounding(self):
        one=CubicTransfer(F(1));tags=np.array([[-1,-1],[-1,1],[1,-1],[1,1]]*60)
        traces=[convert(F((i%31)-15,40),int(d1),int(d2),one,CubicTransfer(F(103,100)),one)
                for i,(d1,d2) in enumerate(tags)]
        r=np.concatenate([record(t) for t in traces],axis=1);raw=raw_fields(r)
        hidden=np.array([4194304+137*i for i in range(8)])/4194304
        steps=tuple(F(n,d) for d in (262144000,16384000) for n in (1,3,6,12))
        for selected,multiplier in ((4,30),(120,1)):
            acc=tuple(int(v*4194304) for v in hidden);expected=[]
            for start in (0,120):
                k=tuple(F(v,1024) for v in export(acc));sums=[F(0)]*8
                for i in range(start,start+120):
                    q1,q2,c3=map(int,r[:3,i]);d1,d2=map(int,tags[i])
                    y=readout(q1,q2,F(c3),d1,d2,k,data_q3=True);expected.append(float(y.output))
                    if i-start<selected:
                        for bank,value in enumerate((y.y1,y.y2)):
                            for j,g in enumerate(y.gates[bank]):sums[4*bank+j]+=(64*d1 if bank==0 else 16*d2)*value*g
                _,acc=commit(acc,tuple(sums),multiplier,steps)
            actual=online_replay(raw,tags,hidden,{'selected':selected,'multiplier':multiplier})
            self.assertTrue(np.array_equal(actual,expected))

    def test_gate_and_readout_support_remain_separate(self):
        one=CubicTransfer(F(1));trace=convert(F(1,2048),1,1,one,CubicTransfer(F(97,100)),one)
        _,_,g,b,_=local(raw_fields(record(trace)),np.array([[1,1]]),np.ones(8))
        self.assertTrue(g[0,6] and b[0,6]);self.assertFalse(g[0,7] or b[0,7])


if __name__=='__main__':unittest.main()
