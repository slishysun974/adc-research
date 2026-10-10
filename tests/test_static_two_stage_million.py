"""Meaningful implementation and offline-diagnostic checks for EXP-057."""

import json
import unittest

import numpy as np

from adc_research.calibration.adaptive_two_stage import TwoStageAdaptiveState,observe
from adc_research.calibration.gated_lms import GatedLmsState
from adc_research.platform.pipeline import process
from adc_research.evaluation.observations import digital_sample
from experiments.exp_057_static_two_stage_million.common import (
    PROTOCOL,setup,truth,plant_arrays,corrected_arrays,basis)
from experiments.exp_057_static_two_stage_million.analyze import projection


class StaticTwoStageMillionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol=json.loads(PROTOCOL.read_text(encoding="utf-8"))
        cls.pipeline,cls.cfg=setup(cls.protocol)
        cls.x=np.repeat(-.82+(np.arange(129)+.5)*(1.64/129),4)
        cls.tags=np.tile(np.array([[-1,-1],[-1,1],[1,-1],[1,1]]),(129,1))

    def test_scoring_generator_matches_original_pipeline_all_cases(self):
        for case in self.protocol["cases"]:
            raw=plant_arrays(self.x,self.tags[:,0],self.tags[:,1],case)
            ni=truth(case)
            for n,(x,tags) in enumerate(zip(self.x,self.tags)):
                original=process(float(x),self.pipeline,dither_symbols=tuple(tags),nonidealities=ni)
                self.assertEqual((raw[0][n],raw[1][n],raw[5][n]),
                    (original.stage1.quantizer.symbol,original.stage2.quantizer.symbol,original.backend.centered_code))
                self.assertAlmostEqual(raw[2][n],original.stage1.residue,places=14)
                self.assertAlmostEqual(raw[3][n],original.stage2.residue,places=14)

    def test_digital_only_vector_score_matches_original_cascade(self):
        case=self.protocol["cases"][-1]
        raw=plant_arrays(self.x,self.tags[:,0],self.tags[:,1],case)
        k=np.array([1.04,1.06,1,1,1.02,1.05,1,1])
        got=corrected_arrays(raw[0],raw[1],raw[5],self.tags[:,0],self.tags[:,1],k)
        state=TwoStageAdaptiveState(GatedLmsState(tuple(k[:4]),(0,)*4),GatedLmsState(tuple(k[4:]),(0,)*4))
        for n,x in enumerate(self.x):
            original=process(float(x),self.pipeline,dither_symbols=tuple(self.tags[n]),nonidealities=truth(case))
            obs=observe(digital_sample(original),state,self.cfg)
            self.assertAlmostEqual(got[0][n],obs.calibration.unclipped_output_code,places=10)
            self.assertAlmostEqual(got[1][n],obs.stage1_local_learning_output,places=11)
            self.assertAlmostEqual(got[2][n],obs.stage2_local_learning_output,places=11)

    def test_fixed_rear_projection_identity_with_nonzero_fit_residual(self):
        case=self.protocol["cases"][-1]
        raw=plant_arrays(self.x,self.tags[:,0],self.tags[:,1],case)
        k=np.array([1.005,1.08,1,1,1.012,1.018,1,1])
        audit=projection(k,raw[0],raw[1],raw[5],self.tags[:,0],self.tags[:,1],self.x)
        self.assertGreater(audit["fixed_rear_front_projection_mse"],0)
        self.assertGreater(audit["front_coefficient_excess_mse"],0)
        self.assertAlmostEqual(audit["actual_validation_mse"],audit["fixed_rear_front_projection_mse"]+
            audit["front_coefficient_excess_mse"]+audit["projection_cross_term"],places=9)
        self.assertLess(abs(audit["projection_cross_term"]),1e-9)

    def test_high_slope_can_affect_readout_without_high_gate(self):
        # Nominal high-dither backend R=80, Y=64, third gate threshold64.
        # With first two learned inverse slopes and unlearned third:
        # a=.98 yields R=78.4 and Y=63.706..., below third threshold65.306...
        k=np.array([1/.98,1/.98,1,1])
        raw=np.array([78.4])
        phi=basis(raw,32)
        y=float((phi@k)[0])-16
        self.assertGreater(phi[0,2],0)
        self.assertLess(y,32*(k[0]+k[1]))

    def test_correct_linear_inverse_has_no_third_gate_but_has_third_readout(self):
        case=self.protocol["cases"][2]  # both gains compressed, matched paths
        raw=plant_arrays(self.x,self.tags[:,0],self.tags[:,1],case)
        a1,a2=case["stage1"][0],case["stage2"][0]
        k=np.array([1/a1]*4+[1/a2]*4)
        _,y1,y2,r1=corrected_arrays(raw[0],raw[1],raw[4],self.tags[:,0],self.tags[:,1],k)
        self.assertLess(float(np.max(np.abs(y1))),256/a1)
        self.assertLess(float(np.max(np.abs(y2))),64/a2)
        self.assertGreater(int(np.count_nonzero(basis(r1,128)[:,2])),0)
        self.assertGreater(int(np.count_nonzero(basis(raw[4],32)[:,2])),0)
        np.testing.assert_allclose(y1,2048*(self.x-raw[0]/4),rtol=0,atol=1e-10)
        np.testing.assert_allclose(y2,512*(raw[2]-raw[1]/4),rtol=0,atol=1e-10)


if __name__=="__main__":unittest.main()
