from fractions import Fraction as F
import unittest

from adc_research.evaluation.front_target_projection import project_low_front_targets, decompose_front_target_bias
from adc_research.theory.gated_correlation_roots import WeightedStageRow, stage_basis


def fixture():
    actual = (F(11, 10), F(9, 10), F(1), F(1))
    record = []
    for raw in (F(-192), F(-64), F(64), F(192)):
        basis = stage_basis(raw, F(128))
        for d in (F(-64), F(64)):
            row = WeightedStageRow(raw, d, 2)
            # A constant offset is orthogonal to both odd basis columns.
            target = sum((k*p for k, p in zip(actual, basis)), F(0))-d+3
            record.append((row, target))
    return tuple(record), actual


class FrontTargetProjectionTests(unittest.TestCase):
    def test_exact_known_projection_with_nonzero_representation_residual(self):
        record, actual = fixture()
        projection = project_low_front_targets(record)
        self.assertEqual(projection['coefficients'], actual)
        self.assertEqual(projection['minimum_continuous_mse'], 9)
        self.assertEqual(projection['basis_error_orthogonality'], (0, 0))
        self.assertGreater(projection['basis_gram_determinant'], 0)

    def test_exact_bias_and_mse_identities_away_from_the_projection(self):
        record, actual = fixture()
        projection = project_low_front_targets(record)
        root = (F(1, 4), F(7, 4), F(1), F(1))
        result = decompose_front_target_bias(record, root, projection)
        self.assertGreater(result['continuous_mse'], 9)
        self.assertEqual(result['continuous_mse'], 9+result['excess_mse'])
        for gate in result['gates']:
            self.assertEqual(gate['gated_target_correlation']+gate['continuous_root_error_correlation'], gate['learning_correlation'])
            self.assertEqual(gate['conditional_imbalance_part']+gate['gate_covariance_part'], gate['gated_target_correlation'])
            self.assertEqual(gate['projection_residual_correlation']+gate['coefficient_bias_correlation'], gate['continuous_root_error_correlation'])

    def test_singular_basis_is_explicitly_rejected(self):
        record = ((WeightedStageRow(F(64), F(64)), F(0)),)
        with self.assertRaises(ValueError):
            project_low_front_targets(record)

    def test_changed_high_coefficient_is_not_the_same_projection_problem(self):
        record, actual = fixture()
        with self.assertRaises(ValueError):
            decompose_front_target_bias(record, (*actual[:2], F(3, 2), F(1)), project_low_front_targets(record))


if __name__ == '__main__':
    unittest.main()
