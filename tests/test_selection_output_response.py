from fractions import Fraction as F
from itertools import product
import unittest

from adc_research.theory.lane_phase_statistics import lane_phase_moments
from adc_research.theory.selection_output_response import (
    affine_loss_comparison, bilinear_loss_terms, finite_output_loss_comparison,
    output_gram, vector_moments, weighted_covariance_difference,
)
from adc_research.theory.static_fixed_contract import commit, export, readout


class SelectionOutputResponseTests(unittest.TestCase):
    def test_affine_weight_matches_all_independent_choices_and_shared_choices(self):
        products = [(F(p-l), F((p+1)*(l+1))) for p in range(3) for l in range(4)]
        moments = lane_phase_moments(products)
        features = ((F(2), F(-1)), (F(1), F(3)))
        scales = (F(1,7), F(2,11))
        def loss(choices):
            total = F(0)
            for choice in choices:
                u = tuple(-scales[i]*sum(products[4*p+l][i] for l,p in enumerate(choice))/4
                          for i in range(2))
                total += sum((e+sum(x*y for x,y in zip(row,u)))**2
                             for row,e in zip(features, (F(3),F(-5))))/2
            return total/len(choices)
        independent = list(product(range(3), repeat=4))
        shared = [(p,)*4 for p in range(3)]
        predicted = weighted_covariance_difference(output_gram(features),
            moments.independent_covariance, moments.shared_covariance, scales)
        self.assertEqual(predicted, loss(independent)-loss(shared))

    def test_same_indefinite_covariance_difference_has_opposite_output_weights(self):
        first, second = ((2,0),(0,1)), ((1,0),(0,2))
        self.assertEqual(weighted_covariance_difference(((1,0),(0,0)),first,second,(1,1)), 1)
        self.assertEqual(weighted_covariance_difference(((0,0),(0,1)),first,second,(1,1)), -1)

    def test_effective_bias_target_cross_and_tight_box_endpoints(self):
        features = ((F(1),F(2)),(F(-1),F(3)))
        ref, updates = (F(1),F(-2)), ((F(2),F(0)),(F(-1),F(1)))
        outputs, targets, radii = (F(7),F(-3)),(F(6),F(-5)),(F(1,2),F(2))
        result = affine_loss_comparison(features, outputs, ref, updates, targets, radii)
        atoms = [tuple(z+sum(x*(a-b) for x,a,b in zip(row,u,ref))
                       for row,z in zip(features,outputs)) for u in updates]
        shift,center,lo,hi = finite_output_loss_comparison(atoms, outputs, targets, radii)
        self.assertEqual(shift, result.mean_output_difference)
        self.assertEqual((center,lo,hi), (result.mse_difference_at_centers,result.lower,result.upper))
        corners = []
        for signs in product((-1,1),repeat=2):
            t = tuple(x+s*r for x,s,r in zip(targets,signs,radii))
            corners.append(finite_output_loss_comparison(atoms,outputs,t)[1])
        self.assertEqual((min(corners),max(corners)),(lo,hi))

    def test_equal_raw_mean_is_not_equal_exported_mean(self):
        # Raw mean zero at an even export tie: opposite one-unit requests
        # straddle the boundary; the deterministic zero request stays even.
        acc = (1024*4096+2048,)
        means = (F(-1),F(1))
        raw_steps = (F(1,1<<22),)
        selected = [export(commit(acc,(m,),1,raw_steps)[1])[0] for m in means]
        full = export(commit(acc,(F(0),),1,raw_steps)[1])[0]
        self.assertEqual(sum(means),0)
        self.assertEqual(selected,[1025,1024])
        self.assertEqual(F(sum(selected),2)-full,F(1,2))

    def test_saturation_can_change_mean_even_before_export(self):
        selected = [commit((0,),(m,),1,(F(1,1<<22),))[1][0] for m in (-1,1)]
        self.assertEqual(selected,[1,0])
        self.assertEqual(F(sum(selected),2),F(1,2))

    def test_joint_digital_output_drift_and_loss_depend_on_target(self):
        old = readout(0,0,F(32),1,1,(F(1),)*8,data_q3=False)
        h = F(1,4096)
        triples, new_outputs = [], []
        for t in (-h,h):
            k = (1+t,1,1,1,1+t,1,1,1)
            new = readout(0,0,F(32),1,1,tuple(map(F,k)),data_q3=False)
            triples.append((48*t,32*t,t))
            self.assertEqual(new.output-old.output,48*t+32*t*t)
            new_outputs.append((new.output,))
        self.assertEqual(sum(z[0]-old.output for z in new_outputs)/2,32*h*h)
        for error in (F(0),F(-40)):
            terms = bilinear_loss_terms(triples,error)
            direct = finite_output_loss_comparison(new_outputs,(old.output,), (old.output-error,))[1]
            self.assertEqual(sum(terms),direct)
            self.assertEqual(direct>0,error==0)

    def test_joint_fourth_moment_not_determined_by_mean_and_covariance(self):
        first = [(F(-1),F(-1))]*4+[(F(1),F(1))]*4
        second = [(F(-2),F(-2)),(F(2),F(2))]+[(F(0),F(0))]*6
        self.assertEqual(vector_moments(first),vector_moments(second))
        a = bilinear_loss_terms([(F(0),b,c) for b,c in first], F(0))
        b = bilinear_loss_terms([(F(0),b,c) for b,c in second], F(0))
        self.assertEqual(sum(a),1)
        self.assertEqual(sum(b),4)

    def test_integer_output_atoms_need_no_affine_or_segment_assumption(self):
        outputs = ((F(1),F(-2)),(F(3),F(4)))
        shift,center,lo,hi = finite_output_loss_comparison(outputs,(F(0),F(2)),
                                                         (F(2),F(1)),(F(1),F(2)))
        self.assertEqual(shift,(F(2),F(-1)))
        self.assertEqual(center,F(5,2))
        self.assertEqual((lo,hi),(F(-3,2),F(13,2)))


if __name__ == '__main__':
    unittest.main()
