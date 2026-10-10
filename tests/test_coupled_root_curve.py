from fractions import Fraction as F
from itertools import product
import unittest
from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.coupled_root_curve import build_front_curve,certify_local_curve,curve_coefficients,certify_interval,multiply,add,value,divide_intervals
from adc_research.theory.gated_correlation_roots import stage_correlations
from experiments.exp_042_correlation_roots.run import stage_rows


def fixture():
    samples=[]
    for local1,d1,d2 in product((80,150),(-1,1),(-1,1)):
        q2=1 if local1==150 or d1==1 else 0
        local2=local1+64*d1-128*q2
        samples.append(Sample(0,q2,local2+16*d2,d1,d2))
    return tuple(samples)


class CoupledRootCurveTests(unittest.TestCase):
    def test_rational_curve_satisfies_independent_front_equations(self):
        samples=fixture()
        direction=(F(0),F(0),F(1),F(0))
        intercept=(F(1),F(1),F(0),F(1))
        model=build_front_curve(samples,direction,intercept,F(1),(F(1),)*4)
        certificate=certify_local_curve(model,(F(1,2),F(3,2),False,False))
        self.assertEqual(certificate['status'],'certified_front_root_curve')
        self.assertTrue(certificate['front_all_four_zero'])
        lo,hi=certificate['parameter_interval']
        for h in (lo,(3*lo+hi)/4,(lo+hi)/2,(lo+3*hi)/4,hi):
            back=tuple(a*h+b for a,b in zip(direction,intercept))
            rows=stage_rows(samples,1,back)
            self.assertEqual(stage_correlations(rows,curve_coefficients(model,h),F(128)),(F(0),)*4)

    def test_polynomial_cramer_identity(self):
        self.assertEqual(add(multiply((F(1),F(1)),(F(1),F(-1))),(F(-1),F(0),F(1))),(F(0),))
        self.assertEqual(value((F(2),F(3),F(4)),F(1,2)),F(9,2))

    def test_interval_division_handles_negative_denominator_and_zero(self):
        self.assertEqual(divide_intervals((F(1),F(2)),(F(-4),F(-2))),(F(-1),F(-1,4)))
        with self.assertRaises(ValueError):divide_intervals((F(1),F(2)),(F(-1),F(1)))

    def test_large_interval_rejects_a_changing_basis_frame(self):
        model=build_front_curve(fixture(),(F(0),F(0),F(1),F(0)),(F(1),F(1),F(0),F(1)),F(1),(F(1),)*4)
        self.assertFalse(certify_interval(model,F(-10),F(10)))

    def test_singular_front_matrix_is_explicit(self):
        samples=(Sample(0,0,16,1,1),Sample(0,0,-16,-1,-1))
        model=build_front_curve(samples,(F(0),F(0),F(1),F(0)),(F(1),F(1),F(0),F(1)),F(1),(F(1),)*4)
        self.assertEqual(model['status'],'singular_front_low_matrix')

    def test_float_and_nonunity_front_high_slopes_are_rejected(self):
        with self.assertRaises(TypeError):build_front_curve(fixture(),(0.0,)*4,(F(1),)*4,F(1),(F(1),)*4)
        with self.assertRaises(ValueError):build_front_curve(fixture(),(F(0),)*4,(F(1),)*4,F(1),(F(1),F(1),F(3,2),F(1)))


if __name__=='__main__':unittest.main()
