from fractions import Fraction as F
from itertools import product
import unittest
from adc_research.theory.gated_correlation_roots import WeightedStageRow,stage_correlations
from experiments.exp_046_coupled_root_curves.transverse_stability import analyze_front_plane


class FrontPlaneStabilityTests(unittest.TestCase):
    def test_stable_closed_front_plane_from_balanced_digital_rows(self):
        rows=tuple(WeightedStageRow(F(t)+d,F(d),2 if abs(t)<1 else 1) for t,d in product((F(-3,2),F(-1,2),F(1,2),F(3,2)),(F(-1,4),F(1,4))))
        result=analyze_front_plane(rows,(F(1),)*4,(F(1,100),F(1,100)),F(1))
        self.assertTrue(result['front_plane_contracts'])
        self.assertTrue(result['front_plane_schur_stable'])
        self.assertFalse(result['front_plane_has_real_expanding_eigenvalue'])
        self.assertGreater(result['protected_front_coefficient_radius'],0)

    def test_open_high_gate_prevents_claim_of_closed_plane(self):
        rows=(WeightedStageRow(F(3),F(1)),)
        result=analyze_front_plane(rows,(F(1),)*4,(F(1,100),F(1,100)),F(1))
        self.assertFalse(result['higher_front_gates_all_closed'])
        self.assertFalse(result['front_plane_contracts'])
        self.assertFalse(result['front_plane_schur_stable'])

    def test_variable_equality_gate_rejects_relative_regularity(self):
        rows=(WeightedStageRow(F(1,2),F(-1,2)),)
        result=analyze_front_plane(rows,(F(1),)*4,(F(1,100),F(1,100)),F(1))
        self.assertFalse(result['relative_front_plane_regular'])
        self.assertEqual(result['protected_front_coefficient_radius'],0)

    def test_exact_root_with_closed_high_gates_has_an_expanding_eigenvalue(self):
        rows=(WeightedStageRow(F(1,4),F(-1,4)),WeightedStageRow(F(3,4),F(1,4)),
              WeightedStageRow(F(21,16),F(1,4),30),WeightedStageRow(F(13,8),F(-1,4),17))
        self.assertEqual(stage_correlations(rows,(F(1),)*4,F(1)),(F(0),)*4)
        result=analyze_front_plane(rows,(F(1),)*4,(F(1,100),F(1,100)),F(1))
        self.assertTrue(result['front_plane_has_real_expanding_eigenvalue'])
        self.assertFalse(result['front_plane_schur_stable'])
        self.assertFalse(result['front_plane_contracts'])
        self.assertLess(result['characteristic_polynomial_at_one'],0)


if __name__=='__main__':unittest.main()
