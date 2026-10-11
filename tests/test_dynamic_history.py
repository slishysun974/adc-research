"""Exact limits, current-dither correlation and analog history boundaries."""

from fractions import Fraction as F
import unittest

from adc_research.theory.dynamic_history import (
    convert, expanded, phase, scalar_current_correlation, unroll,
)


class DynamicHistoryTests(unittest.TestCase):
    def test_exact_convolution_and_history_difference(self):
        targets = [F((7*j) % 19 - 9, 20) for j in range(24)]
        a, r, b = F(1, 25), F(1, 10), F(1, 100)
        first, second = F(1, 2), F(-1, 2)
        for n, target in enumerate(targets, 1):
            self.assertEqual(phase(first, target, a, r, b)[1],
                             expanded(first, target, a, r, b))
            first = phase(first, target, a, r, b)[1]
            second = phase(second, target, a, r, b)[1]
            self.assertEqual(first, unroll(targets[:n], F(1, 2), a, r, b))
            self.assertEqual(first - second, (a*r)**n)

    def test_reset_is_memoryless_but_not_fully_settled(self):
        self.assertEqual(phase(F(1, 2), F(1, 4), F(1, 25), 0)[1], F(6, 25))
        self.assertEqual(phase(F(-1, 2), F(1, 4), F(1, 25), 0)[1], F(6, 25))
        self.assertNotEqual(F(6, 25), F(1, 4))
        self.assertEqual(phase(F(9), F(1, 4), 0, 1)[1], F(1, 4))

    def test_current_dither_root_from_balanced_enumeration(self):
        a, rho = F(39, 40), F(1, 25)
        for tracking in (0, F(1, 10), 1):
            for inverse in (1/a, 1/(a*(1-rho))):
                products = []
                for x in (F(-1, 5), F(1, 5)):
                    for old in (F(-1, 3), F(1, 3)):
                        for d in (F(-1, 32), F(1, 32)):
                            r = phase(old, a*(x+d), rho, tracking)[1]
                            products.append(d*(inverse*r-d))
                self.assertEqual(sum(products)/len(products),
                    scalar_current_correlation(a, inverse, rho, F(1, 1024)))
        self.assertLess(scalar_current_correlation(a, 1/a, rho, F(1, 1024)), 0)

    def test_auxiliary_history_can_change_current_branch(self):
        case = {bank: (F(1), F(0)) for bank in ('stage1', 'auxiliary', 'stage2')}
        # Same present x/tags and main history; only past auxiliary differs.
        x = F(-1, 2048)
        low = convert(x, 1, 1, case, (F(1, 500), F(1, 25), F(1, 500)), 1,
                      (F(0), F(0), F(0)))
        high = convert(x, 1, 1, case, (F(1, 500), F(1, 25), F(1, 500)), 1,
                       (F(0), F(1, 2), F(0)))
        self.assertEqual(low.q2, 0)
        self.assertEqual(high.q2, 1)
        self.assertEqual(low.outputs[0], high.outputs[0])
        self.assertEqual(high.nominal[1] - low.nominal[1], -1)

    def test_unselected_conversion_changes_later_physical_word(self):
        case = {bank: (F(1), F(0)) for bank in ('stage1', 'auxiliary', 'stage2')}
        factors = (F(1, 500), F(1, 25), F(1, 500))
        previous = (F(0),) * 3
        before = convert(F(-1, 2048), 1, 1, case, factors, 1, previous)
        # Skip any intermediate actual conversion: the future uses wrong state.
        intermediate = convert(F(31, 256), 1, 1, case, factors, 1, before.outputs)
        full = convert(F(-1, 2048), 1, 1, case, factors, 1, intermediate.outputs)
        skipped = convert(F(-1, 2048), 1, 1, case, factors, 1, before.outputs)
        self.assertNotEqual(full.outputs, skipped.outputs)
        self.assertNotEqual((full.q2, full.backend), (skipped.q2, skipped.backend))


if __name__ == '__main__':
    unittest.main()
