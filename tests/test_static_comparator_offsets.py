from fractions import Fraction as F
import unittest

from adc_research.theory.static_auxiliary_mismatch import CubicTransfer, convert as nominal
from adc_research.theory.static_comparator_offsets import convert, flash, thresholds, safety, branch_shift
from adc_research.theory.static_fixed_contract import readout

ZERO = (F(0),)*8
E1 = tuple(F(v, 2000) for v in (3, -2, 1, -3, 2, -1, 3, -2))
E2 = tuple(F(v, 2000) for v in (-2, 3, -1, 2, -3, 1, -2, 3))


class ComparatorOffsetTests(unittest.TestCase):
    def test_effective_threshold_equality_and_neighbor(self):
        for offsets in (ZERO, E1, E2):
            for j, t in enumerate(thresholds(offsets)):
                self.assertEqual(flash(t-F(1, 2**36), offsets), j-4)
                self.assertEqual(flash(t, offsets), j-3)
                self.assertEqual(flash(t+F(1, 2**36), offsets), j-3)
        with self.assertRaises(ValueError): thresholds((F(0),)*7)
        with self.assertRaises(ValueError): thresholds((F(1),)+ZERO[1:])
        with self.assertRaises(ValueError): thresholds((F(1, 4),)*8)

    def test_zero_offsets_preserve_static_cascade(self):
        first, second = CubicTransfer(F(39, 40), F(-11, 200)), CubicTransfer(F(49, 50), F(-1, 25))
        for x in (F(-41, 50), F(-1, 8), F(0), F(251, 2000), F(41, 50)):
            for d1 in (-1, 1):
                for d2 in (-1, 1):
                    self.assertEqual(convert(x, d1, d2, first, second, ZERO, ZERO), nominal(x, d1, d2, first, first, second))

    def test_first_offset_preserves_ideal_final_code_but_changes_front_learning(self):
        ideal = CubicTransfer(F(1)); x = F(251, 2000)
        a = convert(x, 1, 1, ideal, ideal, ZERO, ZERO)
        b = convert(x, 1, 1, ideal, ideal, E1, ZERO)
        ra, rb = [readout(t.q1, t.q2, F(t.backend), 1, 1, (F(1),)*8, data_q3=True) for t in (a, b)]
        self.assertEqual((a.q1, b.q1), (1, 0))
        self.assertEqual((ra.output, rb.output), (F(2305), F(2305)))
        self.assertEqual((ra.y1, rb.y1), (F(-255), F(257)))
        self.assertEqual((ra.gates[0][2], rb.gates[0][2]), (False, True))
        self.assertTrue(rb.support[0][2])
        self.assertEqual(branch_shift(b.q1-a.q1, b.q2-a.q2, b.main1-a.main1), (b.z1-a.z1, b.z2-a.z2))

    def test_offset_vector_safety_does_not_reach_backend_fourth_basis(self):
        for first, second in ((CubicTransfer(F(1)), CubicTransfer(F(1))),
                (CubicTransfer(F(39, 40)), CubicTransfer(F(49, 50))),
                (CubicTransfer(F(39, 40), F(-11, 200)), CubicTransfer(F(49, 50), F(-1, 25)))):
            for e1, e2 in ((ZERO, ZERO), (E1, ZERO), (ZERO, E2)):
                bound = safety(first, second, e1, e2)
                self.assertLessEqual(bound.nominal_output_radius1, F(631, 1000))
                self.assertLessEqual(bound.nominal_output_radius2, F(631, 1000))
                self.assertLessEqual(bound.backend_magnitude, 81)
                self.assertLess(bound.backend_magnitude, 96)
                self.assertLess(bound.unit_front_raw_magnitude, 384)

    def test_second_offset_and_sar_floor_open_correct_inverse_third_gate(self):
        first, second = CubicTransfer(F(39, 40)), CubicTransfer(F(49, 50))
        a = convert(F(1, 2400), 1, -1, first, second, ZERO, ZERO)
        b = convert(F(1, 2400), 1, -1, first, second, ZERO, E2)
        k = (F(40, 39),)*4+(F(50, 49),)*4
        ra, rb = [readout(t.q1, t.q2, F(t.backend), 1, -1, k, data_q3=False) for t in (a, b)]
        continuous = readout(b.q1, b.q2, 128*b.main2, 1, -1, k, data_q3=False)
        self.assertEqual((a.q2, b.q2, b.backend), (0, 1, -80))
        self.assertFalse(ra.gates[1][2]); self.assertTrue(rb.gates[1][2])
        self.assertTrue(rb.support[1][2]); self.assertFalse(continuous.gates[1][2])
        self.assertEqual(rb.y2, F(-3216, 49))


if __name__ == '__main__': unittest.main()
