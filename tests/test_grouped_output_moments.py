from fractions import Fraction as F
from itertools import product
import unittest

from adc_research.theory.grouped_output_moments import nested_moments, subset_loss_shift


class GroupedOutputMomentsTests(unittest.TestCase):
    def test_between_blocks_can_hold_all_output_variance_and_covariance(self):
        result = nested_moments((0,0,0,0),(0,0,1,1),(0,0,2,2),(0,0,2,2))
        self.assertEqual(result.output_variance,1)
        self.assertEqual(result.within_block_output_variance,0)
        self.assertEqual(result.between_block_output_variance,1)
        self.assertEqual(result.target_output_covariance,1)
        self.assertEqual(result.between_block_covariance,1)

    def test_unequal_counts_and_negative_covariance(self):
        result = nested_moments((0,0,0),(0,0,1),(2,1,0),(0,1,2))
        self.assertEqual(result.output_variance,F(2,3))
        self.assertEqual(result.within_block_output_variance,F(1,6))
        self.assertEqual(result.between_block_output_variance,F(1,2))
        self.assertEqual(result.within_block_covariance,-F(1,6))
        self.assertEqual(result.between_block_covariance,-F(1,2))

    def test_pure_observation_composition_and_missing_support(self):
        result = subset_loss_shift((0,0,0,1),(0,0,0,0),(0,0,0,1),(0,))
        self.assertEqual(result.observation_composition,-F(1,4))
        self.assertEqual(result.conditional_loss_change,0)
        self.assertEqual(result.full_mass_of_unseen_observations,F(1,4))

    def test_same_observation_conditional_change(self):
        result = subset_loss_shift((0,0),(0,0),(0,1),(0,))
        self.assertEqual(result.observation_composition,0)
        self.assertEqual(result.conditional_loss_change,-F(1,2))

    def test_every_nonempty_subset_retains_exact_loss_and_moment_identities(self):
        obs,blocks,t,y = (0,0,1,1),(0,1,0,1),(F(1,3),1,2,F(7,3)),(0,2,1,3)
        for mask in product((0,1),repeat=4):
            if not any(mask): continue
            idx = tuple(i for i,b in enumerate(mask) if b)
            result = subset_loss_shift(obs,t,y,idx)
            self.assertEqual(result.subset_loss-result.full_loss,
                             result.observation_composition+result.conditional_loss_change)
        moment = nested_moments(obs,blocks,t,y)
        self.assertEqual(moment.output_variance,
                         moment.within_block_output_variance+moment.between_block_output_variance)

    def test_partition_labels_do_not_add_online_information_or_depend_on_order(self):
        args = ((0,1,0,1),(0,0,1,1),(0,1,2,3),(1,0,3,2))
        first = nested_moments(*args)
        second = nested_moments(*(tuple(reversed(row)) for row in args))
        self.assertEqual(first,second)
        shifted = subset_loss_shift(args[0],args[2],args[3],tuple(range(4)))
        self.assertEqual((shifted.observation_composition,shifted.conditional_loss_change),(0,0))

    def test_invalid_records_and_subset_rejected(self):
        with self.assertRaises(ValueError): nested_moments((),(),(),())
        for selected in ((),(0,0),(2,),(-1,)):
            with self.assertRaises(ValueError): subset_loss_shift((0,),(0,),(0,),selected)
