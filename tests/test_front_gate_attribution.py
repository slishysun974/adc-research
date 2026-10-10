from fractions import Fraction as F
import unittest

from adc_research.theory.front_gate_attribution import (
    compare_gate_masks, gate_sources, inner_second_gate, stage_gate_frames,
)
from adc_research.theory.gated_correlation_roots import WeightedStageRow, stage_correlations


class FrontGateAttributionTests(unittest.TestCase):
    def test_inner_gate_identity_and_negative_contribution_on_exact_grid(self):
        width = F(128)
        for k in (F(1, 5), F(1, 4), F(1, 2), F(1), F(3, 2)):
            for raw in map(F, (-128, -100, -64, -32, 0, 32, 64, 100, 128)):
                for d in (F(-64), F(64)):
                    frame = stage_gate_frames((WeightedStageRow(raw, d),), (k, F(1), F(1), F(1)), width)[0]
                    self.assertEqual(inner_second_gate(raw, d, k, width), frame.gates[1])
                    self.assertEqual(frame.basis[1], 0)
                    if frame.gates[1]:
                        self.assertLessEqual(d*frame.local, -abs(d)*width*k)
                    if k <= abs(d)/(2*width):
                        self.assertTrue(frame.gates[1])

    def test_boundary_opens_under_original_greater_equal_rule(self):
        self.assertTrue(inner_second_gate(F(-64), F(64), F(1), F(128)))
        self.assertFalse(inner_second_gate(F(-64)+F(1, 10000), F(64), F(1), F(128)))
        self.assertTrue(inner_second_gate(F(128), F(64), F(1, 4), F(128)))

    def test_weighted_groups_reconstruct_independent_stage_correlations(self):
        rows = (WeightedStageRow(F(-64), F(64), 3), WeightedStageRow(F(192), F(64), 2),
                WeightedStageRow(F(64), F(-64), 5))
        k = (F(1),)*4
        sources = gate_sources(stage_gate_frames(rows, k, F(128)))
        self.assertEqual(tuple(x['correlation'] for x in sources['gates']), stage_correlations(rows, k, F(128)))
        self.assertEqual(sources['gates'][1]['groups'][0]['count'], 8)
        self.assertEqual(sources['gates'][1]['groups'][0]['self_sensitivity'], 0)
        self.assertLess(sources['gates'][1]['groups'][0]['correlation'], 0)

    def test_cross_mask_orientation_and_alignment(self):
        rows = (WeightedStageRow(F(32), F(64), 2), WeightedStageRow(F(32), F(-64), 1))
        a = stage_gate_frames(rows, (F(1),)*4, F(128))
        b = stage_gate_frames(rows, (F(1, 4), F(7, 4), F(1), F(1)), F(128))
        comparison = compare_gate_masks(a, b)
        self.assertEqual(comparison['membership_counts'], {'neither': 0, 'left_only': 0, 'right_only': 3, 'both': 0})
        self.assertEqual(comparison['cross_mask_correlations'][0], (F(0), F(0)))
        self.assertEqual(comparison['cross_mask_correlations'][1], (F(-10240, 3), F(-11776, 3)))
        with self.assertRaises(ValueError):
            compare_gate_masks(a, tuple(reversed(b)))

    def test_invalid_inner_domain_and_float_rejected(self):
        with self.assertRaises(ValueError):
            inner_second_gate(F(129), F(64), F(1), F(128))
        with self.assertRaises(TypeError):
            inner_second_gate(F(0), F(64), 1.0, F(128))


if __name__ == '__main__':
    unittest.main()
