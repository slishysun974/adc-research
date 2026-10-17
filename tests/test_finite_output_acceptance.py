import unittest
from fractions import Fraction as F

from adc_research.theory.finite_output_acceptance import (
    benefit, group_scores, intervals, recovery,
)


def score(mse, residual=None, db=50):
    return {'mse_codes_squared': F(mse),
            'residual_power': F(mse if residual is None else residual),
            'sndr_db': F(db)}


class FiniteOutputAcceptanceTests(unittest.TestCase):
    def test_inclusive_margin_and_loss_guard(self):
        unit = score(10)
        self.assertTrue(benefit(score(9), unit))
        self.assertFalse(benefit(score(F(901, 100)), unit))
        self.assertFalse(benefit(score(9, 9, 49), unit))

    def test_similarly_bad_paths_are_not_recovery(self):
        self.assertFalse(recovery(score(11), score(11), score(10)))
        self.assertTrue(recovery(score(F(44, 5)), score(8), score(10)))
        self.assertFalse(recovery(score(F(881, 100)), score(8), score(10)))

    def test_zero_reference_has_no_positive_benefit(self):
        self.assertFalse(benefit(score(0), score(0)))
        self.assertFalse(recovery(score(0), score(0), score(0)))

    def test_first_pass_does_not_certify_terminal_or_forever(self):
        result = intervals([True, True, True, False, True, True, True])
        self.assertEqual(result['first_pass_block'], 24)
        self.assertEqual(result['later_violations'], 3)
        self.assertTrue(result['terminal_pass'])
        self.assertEqual(result['terminal_good_conversions'], 737280)
        self.assertFalse(result['asymptotic_convergence_proved'])

    def test_power_means_are_not_mean_ratios(self):
        group = group_scores([score(1), score(17)], size=2)[0]
        unit = group_scores([score(2), score(18)], size=2)[0]
        self.assertTrue(benefit(group, unit))
        self.assertEqual(group['mse_codes_squared']/unit['mse_codes_squared'], F(9, 10))
        self.assertNotEqual(F(9, 10), (F(1, 2)+F(17, 18))/2)

    def test_invalid_and_incomplete_scores_rejected(self):
        for rows in ([], [score(1)], [dict(score(1), sndr_db=float('nan'))]*8):
            with self.assertRaises(ValueError):
                group_scores(rows)
        with self.assertRaises(ValueError):
            intervals([True, True])


if __name__ == '__main__':
    unittest.main()
