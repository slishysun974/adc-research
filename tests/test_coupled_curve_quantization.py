from fractions import Fraction as F
import unittest
from adc_research.theory.coupled_root_curve import build_front_curve,certify_local_curve,curve_coefficients
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_042_correlation_roots.run import quantized_reference
from experiments.exp_046_coupled_root_curves.integer_curve_boxes import state_bounds
from test_coupled_root_curve import fixture


class CoupledCurveQuantizationTests(unittest.TestCase):
    def test_exact_runtime_initial_states_are_inside_curve_axis_enclosures(self):
        direction=(F(0),F(0),F(1),F(0))
        intercept=(F(1),F(1),F(0),F(1))
        model=build_front_curve(fixture(),direction,intercept,F(1),(F(1),)*4)
        certificate=certify_local_curve(model,(F(1,2),F(3,2),False,False))
        curve={'curve_model':model,'seed_parameter':F(1),'certificate':certificate}
        cfg=_config()
        bounds,_,illegal=state_bounds(curve,{'direction':direction,'intercept':intercept},cfg)
        self.assertFalse(illegal)
        lo,hi=certificate['parameter_interval']
        for i in range(51):
            h=lo+(hi-lo)*F(i,50)
            back=tuple(a*h+b for a,b in zip(direction,intercept))
            state,_,_=quantized_reference((*back,*curve_coefficients(model,h)),cfg)
            values=(*state.stage2.accumulator_codes,*state.stage1.accumulator_codes)
            self.assertTrue(all(a<=z<=b for z,(a,b) in zip(values,bounds)))


if __name__=='__main__':unittest.main()
