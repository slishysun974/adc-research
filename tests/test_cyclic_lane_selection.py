from fractions import Fraction as F
import unittest

from adc_research.theory.cyclic_lane_selection import (
    FOUR_LANE_OFFSETS, cyclic_indices, cyclic_lane_moments, lag_covariance_sum,
)
from adc_research.theory.lane_phase_statistics import lane_phase_moments
from adc_research.theory.selection_output_response import vector_moments
from adc_research.theory.static_fixed_contract import readout


class CyclicLaneSelectionTests(unittest.TestCase):
    def test_declared_offsets_have_minimal_maximum_circular_slot_gap(self):
        self.assertEqual(cyclic_indices(0),(0,61,30,91))
        for base in range(30):
            positions=sorted(cyclic_indices(base))
            gaps=[b-a for a,b in zip(positions,positions[1:]+[positions[0]+120])]
            self.assertEqual(sorted(gaps),[29,30,30,31])
            self.assertEqual([i%4 for i in cyclic_indices(base)],[0,1,2,3])
        # All gaps <=30 would force four exact30 gaps; that repeats two lanes.
        for start in range(4):
            self.assertEqual(len({(start+30*l)%4 for l in range(4)}),2)

    def test_zero_offsets_match_original_shared_phase_statistics(self):
        products=[(p-l,(p+1)*(l+1)) for p in range(5) for l in range(4)]
        a=cyclic_lane_moments(products,(0,)*4); b=lane_phase_moments(products)
        self.assertEqual(a.selected_mean,b.full_mean)
        self.assertEqual(a.covariance,b.shared_covariance)

    def test_uniform_base_mean_and_covariance_match_independent_enumeration(self):
        products=[(p-l,p*p+3*l) for p in range(7) for l in range(4)]
        shifts=(0,3,1,5)
        a=cyclic_lane_moments(products,shifts)
        direct=[tuple(sum(F(products[4*((r+shifts[l])%7)+l][j]) for l in range(4))/4
                      for j in range(2)) for r in range(7)]
        self.assertEqual((a.selected_mean,a.covariance),vector_moments(direct))
        self.assertEqual(a.selected_mean,a.full_mean)

    def test_cross_lag_identity_matches_exact_phase_enumeration(self):
        products=[(p-l,(p+1)*(l+1)) for p in range(5) for l in range(4)]
        for shifts in ((0,0,0,0),(0,1,2,3),(4,2,0,1)):
            self.assertEqual(cyclic_lane_moments(products,shifts).covariance,
                             lag_covariance_sum(products,shifts))

    def test_common_offset_translation_preserves_entire_ideal_distribution(self):
        products=[(p-l,(p+1)*(l+1)) for p in range(5) for l in range(4)]
        a=cyclic_lane_moments(products,(0,1,2,3))
        b=cyclic_lane_moments(products,(2,3,4,0))
        self.assertEqual(a.selected_mean,b.selected_mean)
        self.assertEqual(a.covariance,b.covariance)
        self.assertEqual(sorted(a.phase_means),sorted(b.phase_means))

    def test_legal_digital_in_phase_control_staggering_removes_noise(self):
        k=(F(1),)*8
        products=[]
        for p in range(30):
            for lane in range(4):
                z=readout(0,0,F(45 if p%2 else 15),1,1,k,data_q3=True)
                products.append((16*z.y2,))
        a=cyclic_lane_moments(products); b=cyclic_lane_moments(products,(0,)*4)
        self.assertGreater(b.covariance[0][0],0)
        self.assertEqual(a.covariance[0][0],0)

    def test_legal_digital_cancellation_control_staggering_increases_noise(self):
        k=(F(1),)*8
        products=[]
        for p in range(30):
            for lane in range(4):
                z=readout(0,0,F(45 if (p+FOUR_LANE_OFFSETS[lane])%2 else 15),1,1,k,data_q3=True)
                products.append((16*z.y2,))
        a=cyclic_lane_moments(products); b=cyclic_lane_moments(products,(0,)*4)
        self.assertEqual(b.covariance[0][0],0)
        # These offsets do not universally preserve lane cancellation.
        self.assertGreater(a.covariance[0][0],0)

    def test_rotation_coverage_on_frozen_record_is_not_a_time_varying_guarantee(self):
        for lane,offset in enumerate(FOUR_LANE_OFFSETS):
            self.assertEqual(sorted((w+offset)%30 for w in range(30)),list(range(30)))
        # Actual rotating choices can track a moving peak at every window.
        selected=[]; full=[]
        for w in range(30):
            values=[int(p==(w+FOUR_LANE_OFFSETS[l])%30) for p in range(30) for l in range(4)]
            selected.append(F(sum(values[i] for i in cyclic_indices(w)),4))
            full.append(F(sum(values),120))
        self.assertEqual(sum(selected),30)
        self.assertEqual(sum(full),1)

    def test_lane_constant_products_have_zero_selection_variance(self):
        result=cyclic_lane_moments([(l,l*l) for p in range(30) for l in range(4)])
        self.assertEqual(result.covariance,((0,0),(0,0)))

    def test_invalid_bases_offsets_shapes_and_float_products_rejected(self):
        for base in (-1,30,True):
            with self.assertRaises(ValueError): cyclic_indices(base)
        with self.assertRaises(ValueError): cyclic_indices(0,(0,30),30)
        with self.assertRaises(ValueError): cyclic_lane_moments(((1,),)*3)
        with self.assertRaises(TypeError): cyclic_lane_moments(((1.0,),)*120)


if __name__=='__main__':
    unittest.main()
