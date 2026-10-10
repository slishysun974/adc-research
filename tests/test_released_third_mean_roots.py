from fractions import Fraction as F
from itertools import product
import unittest
from adc_research.theory.gated_correlation_roots import WeightedStageRow,stage_correlations
from adc_research.theory.released_third_mean_roots import analyze_seed,_parameter_interval


class ReleasedThirdMeanRootTests(unittest.TestCase):
    def rows(self,targets,dither):
        return tuple(WeightedStageRow(F(t)+d,F(d)) for t,d in product(targets,(-dither,dither)))

    def test_three_active_rows_have_an_exact_point_root(self):
        rows=self.rows((F(-5,2),F(-3,2),F(-1,2),F(1,2),F(3,2),F(5,2)),F(1,4))
        result=analyze_seed(rows,(F(1),F(1),F(11,10),F(1)),F(1))
        self.assertEqual(result['status'],'certified_point_root_in_seed_masks')
        self.assertEqual(result['proposed_coefficients'],(F(1),)*4)
        self.assertTrue(result['all_four_correlations_zero'])

    def test_readout_changes_along_an_exact_zero_correlation_segment(self):
        rows=self.rows((F(-3,2),F(-1,2),F(1,2),F(3,2)),F(1))
        result=analyze_seed(rows,(F(1),)*4,F(1))
        self.assertEqual(result['status'],'certified_root_segment_in_seed_masks')
        self.assertTrue(result['nonunique_root_segment'])
        self.assertTrue(result['all_four_correlations_zero_on_segment'])
        self.assertGreater(result['readout_varying_conversions'],0)
        lo,hi,_,_=result['third_parameter_interval']
        for h in ((lo+hi)/2,(lo*2+hi)/3):
            coefficients=tuple(a*h+b for a,b in zip(result['direction'],result['intercept']))
            self.assertEqual(stage_correlations(rows,coefficients,F(1)),(F(0),)*4)

    def test_identically_closed_high_row_without_high_basis_is_reported(self):
        rows=self.rows((F(-3,2),F(-1,2),F(1,2),F(3,2)),F(1,4))
        result=analyze_seed(rows,(F(1),)*4,F(1))
        self.assertEqual(result['third_parameter_interval'],(F(0),F(2),False,False))
        self.assertEqual(result['readout_varying_conversions'],0)

    def test_open_closed_halfspaces_and_singleton_boundary(self):
        self.assertEqual(_parameter_interval(((F(1),F(-1),True),(F(-1),F(1),True))),
                         (F(1),F(1),True,True))
        self.assertIsNone(_parameter_interval(((F(1),F(-1),False),(F(-1),F(1),True))))
        self.assertIsNone(_parameter_interval(((F(0),F(0),False),)))

    def test_float_seed_is_rejected(self):
        rows=self.rows((F(1,2),F(3,2)),F(1,4))
        with self.assertRaises(TypeError):analyze_seed(rows,(1.0,)*4,F(1))


if __name__=='__main__':
    unittest.main()
