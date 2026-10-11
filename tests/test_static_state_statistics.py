"""Finite identities with correlated states and nonorthogonal evaluation bases."""
from fractions import Fraction as F
import unittest
import numpy as np

from adc_research.theory.static_state_statistics import mean_covariance_loss, finite_increment_balance
from adc_research.theory.static_fixed_contract import readout
from experiments.exp_059_static_fixed_million.analyze import output
from experiments.exp_057_static_two_stage_million.common import setup, PROTOCOL
from adc_research.calibration.adaptive_two_stage import TwoStageAdaptiveState, observe
from adc_research.calibration.gated_lms import GatedLmsState, adaptive_lower_thresholds
from adc_research.calibration.observation import DigitalCalibrationSample
import json


class StaticStateStatisticsTests(unittest.TestCase):
    def test_correlated_nonstationary_states_still_obey_finite_loss_identity(self):
        phi=np.array([[1,2],[3,-1],[-2,4]],float)
        target=np.array([2,-3,1.])
        states=np.array([[0,1],[0,1],[2,4],[3,7]],float)
        result=mean_covariance_loss(phi,target,states)
        direct=np.mean([(phi@k-target)**2 for k in states])
        self.assertAlmostEqual(direct,result['average_continuous_mse'],places=12)
        self.assertGreater(abs(result['covariance'][0][1]),0)

    def test_hand_example_distinguishes_loss_of_mean_from_mean_loss(self):
        result=mean_covariance_loss([[2]],[1],[[0],[2]])
        self.assertEqual(result['mean_state_mse'],1)
        self.assertEqual(result['state_variance_mse'],4)
        self.assertEqual(result['average_continuous_mse'],5)

    def test_finite_second_moment_balance_keeps_nonzero_boundary(self):
        states=np.array([[1,2],[2,-1],[4,3],[5,6]],float)
        result=finite_increment_balance(states,[1,1])
        self.assertLess(result['maximum_balance_error'],1e-12)
        self.assertGreater(np.max(np.abs(result['second_moment_boundary'])),0)
        np.testing.assert_allclose(result['mean_increment'],result['mean_boundary'],rtol=0,atol=1e-14)

    def test_same_mean_does_not_remove_state_noise(self):
        result=mean_covariance_loss([[1]],[1],[[0],[2]])
        self.assertEqual(result['mean_state_mse'],0)
        self.assertEqual(result['average_continuous_mse'],1)

    def test_vector_q3_evaluation_matches_independent_rational_at_rounding_ties(self):
        k=np.array([1025,1043,1067,1101,1026,64,1024,1024])/1024
        be=np.array([-80,-65,-64,-33,-32,-1,0,1,32,33,64,65,80])
        q1=np.zeros(len(be),dtype=int);q2=q1.copy();tags=np.ones(len(be),dtype=int)
        raw=(q1,q2,None,None,None,be)
        actual=output(raw,tags,-tags,k,True)
        expected=[float(readout(0,0,F(int(b)),1,-1,tuple(F.from_float(v) for v in k),data_q3=True).output) for b in be]
        np.testing.assert_array_equal(actual,expected)

    def test_exact_real_gate_equality_need_not_match_original_double_subtraction(self):
        # Actual EXP-059 float probe: exact rear local magnitude equals third
        # threshold; original subtraction rounds one ULP inward and closes it.
        k=(1.0001884765625,1.000233642578125,1.,1.,.99996875,.999759765625,1.,1.)
        exact=readout(1,1,F(-80),1,-1,tuple(map(F.from_float,k)),data_q3=False)
        self.assertTrue(exact.gates[1][2])
        _,cfg=setup(json.loads(PROTOCOL.read_text(encoding='utf-8')))
        state=TwoStageAdaptiveState(GatedLmsState(k[:4],(0,)*4),GatedLmsState(k[4:],(0,)*4))
        actual=observe(DigitalCalibrationSample(1,1,-80,1,-1),state,cfg)
        threshold=adaptive_lower_thresholds(k[4:],32)[2]
        self.assertLess(abs(actual.stage2_local_learning_output),threshold)
        self.assertLess(threshold-abs(actual.stage2_local_learning_output),2e-14)


if __name__=='__main__':unittest.main()
