"""Exact path enumeration and extremal finite-record controls."""

from fractions import Fraction as F
from itertools import product
import unittest

from adc_research.theory.temporal_state_moments import (
    affine_temporal_covariance, partition_moments, stationary_group_factors,
)


class TemporalStateMomentsTests(unittest.TestCase):
    def test_transient_covariance_by_full_affine_path_enumeration(self):
        records = []
        for aa in product((F(1), F(1, 2)), repeat=4):
            record = [F(3, 4)]
            for a in aa:
                record.append(a*record[-1]+F(1, 4))
            records.append(record)
        means = [sum(z[i] for z in records)/16 for i in range(5)]
        covariance = [[sum((z[i]-means[i])*(z[j]-means[j]) for z in records)/16
                       for j in range(5)] for i in range(5)]
        predicted = affine_temporal_covariance(F(3, 4), [covariance[i][i] for i in range(5)])
        self.assertEqual(predicted, tuple(map(tuple, covariance)))
        weights = (F(0), F(-1, 2), F(-1, 2), F(1, 2), F(1, 2))
        contrast = [sum(a*b for a, b in zip(weights, z)) for z in records]
        cm = sum(contrast)/16
        self.assertEqual(sum((x-cm)**2 for x in contrast)/16,
                         sum(weights[i]*weights[j]*predicted[i][j] for i in range(5) for j in range(5)))

    def test_stationary_groups_by_direct_pair_sums(self):
        for r in (F(-1, 2), F(0), F(3, 4)):
            for n in (1, 2, 5):
                out = stationary_group_factors(r, n)
                vv = sum(r**abs(j-i) for i in range(n) for j in range(n))/F(n*n)
                cc = sum(r**(j-i) for i in range(n) for j in range(n, 2*n))/F(n*n)
                self.assertEqual(out['mean_variance_factor'], vv)
                self.assertEqual(out['adjacent_covariance_factor'], cc)
                self.assertEqual(out['adjacent_difference_variance_factor'], 2*(vv-cc))

    def test_positive_memory_and_negative_alternation_have_opposite_averaging_effect(self):
        self.assertEqual(stationary_group_factors(0, 10)['iid_variance_understatement_factor'], 1)
        self.assertGreater(stationary_group_factors(F(9, 10), 10)['iid_variance_understatement_factor'], 5)
        self.assertLess(stationary_group_factors(F(-1, 2), 10)['iid_variance_understatement_factor'], 1)

    def test_partition_with_unequal_counts_matches_direct_record(self):
        groups = ((-3, 1), (2, 4, 6))
        out = partition_moments([sum(g) for g in groups], [sum(x*x for x in g) for g in groups], [2, 3])
        self.assertEqual(out['mean'], 2)
        self.assertEqual(out['variance'], F(46, 5))
        self.assertEqual(out['within_variance']+out['between_variance'], out['variance'])

    def test_group_range_variance_bounds_are_sharp(self):
        for values, bound in (((0, 1, 2), F(2, 3)), ((0, 0, 2, 2), F(1))):
            out = partition_moments(values, [v*v for v in values], [1]*len(values))
            self.assertEqual(out['between_variance'], bound)
            r = max(values)-min(values)
            self.assertLessEqual(F(r*r, 2*len(values)), out['variance'])
            self.assertLessEqual(out['variance'], F(r*r, 4))

    def test_small_total_variance_can_hide_shifted_group_means(self):
        out = partition_moments((0, 20, 40), (0, 20, 80), (20, 20, 20))
        self.assertEqual(out['within_variance'], 0)
        self.assertEqual(out['between_variance'], F(2, 3))
        self.assertEqual(out['group_means'], (0, 1, 2))

    def test_export_of_mean_is_not_mean_of_exports(self):
        # Q22 integers near one Q1.10 midpoint; nearest-even at 2048 -> 0.
        hidden = (2047, 2049, 2049)
        exports = tuple(round(F(x, 4096)) for x in hidden)
        self.assertEqual(exports, (0, 1, 1))
        self.assertNotEqual(sum(exports)/F(3), round(sum(hidden)/F(3*4096)))
        self.assertLessEqual(abs(sum(exports)/F(3*1024)-sum(hidden)/F(3*2**22)), F(1, 2048))

    def test_degenerate_and_invalid_inputs(self):
        out = partition_moments((6, 6), (18, 18), (2, 2))
        self.assertEqual(out['variance'], 0)
        with self.assertRaises(ValueError):
            partition_moments((5,), (1,), (2,))
        with self.assertRaises(ValueError):
            stationary_group_factors(1, 3)
        with self.assertRaises(ValueError):
            affine_temporal_covariance(F(1, 2), [-1])
