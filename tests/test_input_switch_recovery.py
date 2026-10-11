"""Finite recovery rule: stability, paired closeness and support are separate."""
import unittest
import numpy as np
from experiments.exp_066_input_switch_tracking_long.analyze import recovery


class InputSwitchRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.p={'tracking':{'group_blocks':8,'minimum_groups':3,'pair_sndr_group_mean_gap_db':1.,'pair_coefficient_group_mean_gap':.005},
                'input':{'samples_per_block':30720}}
        self.a={'group_sndr_means_db':[20.,20.,20.,20.],
                'group_effective_state_means':np.ones((4,8)).tolist(),
                'intervals':[{'end_block_exclusive':24,'passed':True},{'end_block_exclusive':32,'passed':True}]}
        self.support=np.zeros((32,8),dtype=int); self.support[:,0]=1

    def test_equal_poor_paths_can_pass_without_benefit_claim(self):
        r=recovery(self.a,self.a,self.support,self.support,self.p)
        self.assertEqual(r['first_satisfying_post_conversion'],24*30720)
        self.assertFalse(r['general_recovery_proved'])
        self.assertEqual(r['intervals'][0]['unsupported_coordinates'],list(range(1,8)))

    def test_support_from_either_path_requires_pair_state_closeness(self):
        b=dict(self.a,group_effective_state_means=(np.ones((4,8))+.006).tolist())
        r=recovery(self.a,b,self.support,np.zeros_like(self.support),self.p)
        self.assertIsNone(r['first_satisfying_post_conversion'])

    def test_first_passing_interval_does_not_hide_later_failure(self):
        b=dict(self.a,group_sndr_means_db=[20.,20.,20.,22.])
        r=recovery(self.a,b,self.support,self.support,self.p)
        self.assertEqual(r['first_satisfying_post_conversion'],24*30720)
        self.assertEqual(r['later_failing_intervals'],1)


if __name__=='__main__':unittest.main()
