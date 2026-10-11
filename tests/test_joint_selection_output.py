from fractions import Fraction as F
from itertools import product
import unittest

from adc_research.theory.joint_selection_output import (
    four_grid_loss, output_moments, mix_output_moments, moments_loss_comparison,
)
from adc_research.theory.static_fixed_contract import readout, nearest_even


class JointSelectionOutputTests(unittest.TestCase):
    def test_loss_cross_remains_when_output_interaction_is_zero(self):
        positive = four_grid_loss((0,), (1,), (1,), (2,), (0,))
        negative = four_grid_loss((0,), (1,), (-1,), (0,), (0,))
        self.assertEqual(positive.output_interaction, (0,))
        self.assertEqual((positive.front_loss, positive.rear_loss,
                          positive.loss_interaction, positive.joint_loss), (1, 1, 2, 4))
        self.assertEqual(negative.loss_interaction, -2)
        self.assertEqual(negative.joint_loss, 0)

    def test_legal_integer_joint_control_matches_direct_loss(self):
        old = (F(1),)*8
        new = (F(3,4),)+(F(1),)*3+(F(3,2),)+(F(1),)*3
        grids = []
        for k in (old, new[:4]+old[4:], old[:4]+new[4:], new):
            grids.append((nearest_even(readout(0, 0, F(16), -1, -1,
                                                k, data_q3=True).output),))
        self.assertEqual(tuple(z[0] for z in grids), (2144, 2136, 2152, 2142))
        for target in (2144, 2141):
            result = four_grid_loss(*grids, (target,))
            self.assertEqual(result.output_interaction, (-2,))
            self.assertEqual(result.joint_loss, (2142-target)**2-(2144-target)**2)
            self.assertEqual(result.loss_interaction,
                             result.joint_loss-result.front_loss-result.rear_loss)

    def test_arbitrary_finite_integer_grids_include_all_cross_terms(self):
        old, front, rear, joint = (1, -2), (3, -1), (0, 2), (4, 0)
        for targets in product((-3, 2, 5), repeat=2):
            result = four_grid_loss(old, front, rear, joint, targets)
            direct = sum(F((a-t)**2-(b-t)**2) for a,b,t in zip(joint,old,targets))/2
            self.assertEqual(result.joint_loss, direct)

    def test_rounding_creates_output_interaction_from_additive_continuous_grids(self):
        continuous = (F(1,5), F(3,5), F(3,5), F(1))
        result = four_grid_loss(*[(nearest_even(x),) for x in continuous], (0,))
        self.assertEqual(continuous[3]-continuous[1]-continuous[2]+continuous[0], 0)
        self.assertEqual(result.output_interaction, (-1,))
        self.assertEqual(result.joint_loss, 1)

    def test_legal_front_segment_boundary_is_retained(self):
        old = (F(1),)*8
        new = (F(1), F(3,4), F(1), F(1), F(1025,1024), F(1), F(1), F(1))
        grids = [(nearest_even(readout(0, 1, F(16), 1, 1, k, data_q3=True).output),)
                 for k in (old, new[:4]+old[4:], old[:4]+new[4:], new)]
        self.assertEqual(readout(0, 1, F(16), 1, 1, old, data_q3=True).raw1, 128)
        result = four_grid_loss(*grids, (2112,))
        self.assertEqual(result.joint_loss, (grids[3][0]-2112)**2-(grids[0][0]-2112)**2)

    def test_mixture_moments_match_nonuniform_integer_atom_enumeration(self):
        atoms = ((1, -2), (4, 3), (-1, 6))
        mixture = mix_output_moments(
            [output_moments((row,)) for row in atoms], (F(1,2), F(1,3), F(1,6)))
        repeated = [atoms[0]]*3+[atoms[1]]*2+[atoms[2]]
        self.assertEqual(mixture, output_moments(repeated))
        ref, target = (2, 0), (3, -1)
        result = moments_loss_comparison(mixture, ref, target)
        direct = sum(sum(F((z-t)**2-(r-t)**2) for z,r,t in zip(row,ref,target))/2
                     for row in repeated)/6
        self.assertEqual(result.center, direct)
        self.assertEqual(result.center, result.target_cross+result.mean_square+result.variance)

    def test_target_box_endpoints_are_tight_for_joint_integer_outputs(self):
        m = output_moments(((2, -1), (4, 3)))
        ref, target, radius = (1, 2), (3, -2), (F(1,2), F(2))
        result = moments_loss_comparison(m, ref, target, radius)
        values = [moments_loss_comparison(m, ref, tuple(t+s*r for t,s,r in
                    zip(target, signs, radius))).center for signs in product((-1,1), repeat=2)]
        self.assertEqual((min(values),max(values)), (result.lower,result.upper))

    def test_same_mean_different_joint_output_variance_changes_loss(self):
        a, b = output_moments(((0,), (2,))), output_moments(((-1,), (3,)))
        self.assertEqual(a.mean, b.mean)
        self.assertEqual(moments_loss_comparison(a, (1,), (1,)).center, 1)
        self.assertEqual(moments_loss_comparison(b, (1,), (1,)).center, 4)

    def test_deterministic_joint_law_has_zero_variance(self):
        result = moments_loss_comparison(output_moments(((3, -1),)), (2, 0), (1, 2))
        self.assertEqual(result.variance, 0)
        self.assertEqual(result.center, 4)

    def test_invalid_shapes_probabilities_and_moments_rejected(self):
        with self.assertRaises(ValueError): four_grid_loss((), (), (), (), ())
        with self.assertRaises(ValueError): output_moments(((1,), (1,2)))
        m = output_moments(((1,),))
        with self.assertRaises(ValueError): mix_output_moments((m,), (F(1,2),))
        with self.assertRaises(ValueError): moments_loss_comparison(m, (1,), (1,), (-1,))


if __name__ == '__main__':
    unittest.main()
