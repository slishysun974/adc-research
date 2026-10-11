"""Counterexamples for hidden-state inheritance and finite paired loss."""
from fractions import Fraction as F
import unittest
import numpy as np

from adc_research.theory.static_fixed_contract import export, nearest_even
from experiments.exp_062_same_input_background.verify import tags
from experiments.exp_065_input_switch_tracking.analyze import mse_difference


class InputSwitchContractTests(unittest.TestCase):
    def test_equal_exports_can_split_after_same_one_LSB_request(self):
        # Hidden states on either side of the last value below an even tie.
        a=1024*4096+2047; b=a+1
        self.assertEqual(export((a,)),export((b,)))
        self.assertNotEqual(export((a+1,)),export((b+1,)))
        self.assertEqual(nearest_even(F(3,4)),1)

    def test_global_tag_is_part_of_reproducible_suffix(self):
        start=3932160; span=np.arange(120)
        original=tags(202610621,start+span)
        for a,b in zip(original,tags(202610621,start+span)):
            np.testing.assert_array_equal(a,b)
        self.assertTrue(any(np.any(a!=b) for a,b in zip(original,tags(202610621,span))))

    def test_output_change_power_does_not_determine_loss_sign(self):
        target=np.zeros(2); reference=np.ones(2)
        bad=mse_difference(np.full(2,3.),reference,target)
        good=mse_difference(np.full(2,-1.),reference,target)
        self.assertEqual(bad['output_change_power'],good['output_change_power'])
        self.assertEqual(bad['mse_difference'],8)
        self.assertEqual(good['mse_difference'],0)
        self.assertEqual(good['reference_error_cross'],-4)


if __name__=='__main__': unittest.main()
