from fractions import Fraction as F
import unittest

from adc_research.theory.static_auxiliary_mismatch import (
    CubicTransfer, convert, rear_reconstruction_error, linear_branch_difference,
)
from adc_research.theory.static_fixed_contract import readout


class StaticAuxiliaryMismatchTests(unittest.TestCase):
    def test_branch_change_preserves_ideal_output_but_changes_rear_gate(self):
        unit = CubicTransfer(F(1))
        matched = convert(F(1, 2048), 1, 1, unit, unit, unit)
        changed = convert(F(1, 2048), 1, 1, unit, CubicTransfer(F(97, 100)), unit)
        self.assertEqual((matched.q2, matched.backend), (1, -47))
        self.assertEqual((changed.q2, changed.backend), (0, 81))
        left = readout(matched.q1, matched.q2, F(matched.backend), 1, 1,
                       (F(1),) * 8, data_q3=True)
        right = readout(changed.q1, changed.q2, F(changed.backend), 1, 1,
                        (F(1),) * 8, data_q3=True)
        self.assertEqual((left.output, right.output), (2049, 2049))
        self.assertEqual((left.y2, right.y2), (-63, 65))
        self.assertEqual((left.gates[1][2], right.gates[1][2]), (False, True))

    def test_arbitrary_rear_readout_identity(self):
        trace = convert(F(1, 2048), 1, -1, CubicTransfer(F(39, 40)),
                        CubicTransfer(F(97, 100)), CubicTransfer(F(49, 50)))
        for p2 in (F(trace.backend), F(3, 2) * trace.backend, F(7, 8)):
            raw1, error = rear_reconstruction_error(trace, -1, p2)
            self.assertEqual(raw1, 512 * trace.main1 + error)

    def test_linear_branch_formula_keeps_quantization_and_arithmetic(self):
        a2, k = F(49, 50), F(1045, 1024)
        m, d2 = F(65, 512), 1
        values = []
        for q in (0, 1):
            r = 4 * a2 * (m - F(q, 4) + F(d2, 32))
            c = (128 * (r + 1)).__floor__() - 128
            epsilon = c - 128 * r
            eta = F(q, 16)
            values.append((128 * q + k * c + eta - 16 * d2, epsilon, eta))
        difference = linear_branch_difference(1, k, a2,
            values[1][1] - values[0][1], values[1][2] - values[0][2])
        self.assertEqual(values[1][0] - values[0][0], difference)

    def test_out_of_domain_and_overload_are_rejected(self):
        unit = CubicTransfer(F(1))
        with self.assertRaises(ValueError):
            CubicTransfer(F(1), F(-1))
        with self.assertRaises(ValueError):
            convert(F(1), 1, 1, unit, unit, unit)
        with self.assertRaises(ValueError):
            convert(F(0), 1, 1, unit, unit, unit, F(2))


if __name__ == "__main__":
    unittest.main()
