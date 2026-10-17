"""Independent exact tests of fixed-history translation partitions."""
from itertools import product
import unittest

from adc_research.theory.quantized_mean_dynamics import (
    export_code, propagate_export_itineraries,
)


def contains(box,state): return all(lo<=z<=hi for (lo,hi),z in zip(box,state))


class ExportItinerariesTests(unittest.TestCase):
    def test_all_81_initial_states_match_four_direct_windows(self):
        box=((8,16),(8,16))
        def request(window,codes):
            return ((1 if codes[0]%2==0 else -2)+(window%2),
                    -1 if codes[1]%2==0 else 2)
        result=propagate_export_itineraries(box,4,request,guard_bits=2,maximum=63,
                                         max_branches=512,max_cells_per_window=512,max_total_requests=256)
        self.assertEqual(result['status'],'complete')
        for initial in product(range(8,17),repeat=2):
            state=initial;itinerary=[]
            for window in range(4):
                codes=tuple(export_code(z,2) for z in state);itinerary.append(codes)
                state=tuple(z+d for z,d in zip(state,request(window,codes)))
                matches=[branch for branch in result['history'][window]['after_branches']
                         if contains(branch['initial'],initial)]
                self.assertEqual(len(matches),1)
                self.assertEqual(matches[0]['itinerary'],tuple(itinerary))
                self.assertEqual(state,tuple(z+d for z,d in zip(initial,matches[0]['offset'])))
                self.assertTrue(contains(matches[0]['current'],state))

    def test_shared_itinerary_keeps_two_initial_states_distance(self):
        result=propagate_export_itineraries(((101,103),)*8,3,
            lambda window,codes:(1,)*8,guard_bits=8,maximum=1023)
        self.assertEqual(result['status'],'complete')
        self.assertEqual(len(result['branches']),1)
        self.assertEqual(result['branches'][0]['current'],((104,106),)*8)
        self.assertEqual(result['branches'][0]['offset'],(3,)*8)
        self.assertEqual(result['initial_state_count'],3**8)

    def test_moving_requests_need_window_history_even_at_the_same_state(self):
        result=propagate_export_itineraries(((20,20),),2,
            lambda window,codes:(1 if window==0 else -1,),guard_bits=8,maximum=255)
        self.assertEqual(result['branches'][0]['current'],((20,20),))
        self.assertFalse(result['periodic_extension_certified'])
        self.assertNotEqual(result['history'][0]['actions'][0]['request'],
                            result['history'][1]['actions'][0]['request'])

    def test_colliding_final_states_do_not_merge_distinct_initial_histories(self):
        # Two initial points have different export codes, but map to the same final point.
        result=propagate_export_itineraries(((2,3),),1,
            lambda window,codes:(1 if codes[0]==2 else 0,),guard_bits=0,maximum=15)
        self.assertEqual(len(result['branches']),2)
        self.assertEqual([branch['current'] for branch in result['branches']], [((3,3),)]*2)
        self.assertEqual(sum(branch['initial'][0][1]-branch['initial'][0][0]+1
                             for branch in result['branches']),2)

    def test_cell_budget_stops_before_any_incomplete_window_requests(self):
        calls=[]
        def request(window,codes): calls.append((window,codes));return (1,)
        result=propagate_export_itineraries(((12,20),),3,request,guard_bits=3,maximum=63,
                                         max_cells_per_window=1)
        self.assertEqual(result['status'],'cell_budget')
        self.assertEqual(result['certified_windows'],1)
        self.assertEqual(result['stop']['window'],1)
        self.assertEqual(calls,[(0,(2,))])

    def test_request_and_branch_budgets_preserve_only_a_complete_prefix(self):
        result=propagate_export_itineraries(((12,20),),3,lambda window,codes:(1,),
            guard_bits=3,maximum=63,max_total_requests=1)
        self.assertEqual((result['status'],result['certified_windows']),('request_budget',1))
        result=propagate_export_itineraries(((12,20),),3,lambda window,codes:(1,),
            guard_bits=3,maximum=63,max_branches=1)
        self.assertEqual((result['status'],result['certified_windows']),('branch_budget',1))

    def test_possible_saturation_does_not_get_a_translation_certificate(self):
        result=propagate_export_itineraries(((13,15),),2,lambda window,codes:(2,),
                                          guard_bits=4,maximum=15)
        self.assertEqual(result['status'],'saturation_possible')
        self.assertEqual(result['certified_windows'],0)
        self.assertEqual(result['branches'][0]['current'],((13,15),))
        self.assertTrue(result['stop']['unsafe_images'])

    def test_zero_time_and_invalid_full_state_contracts(self):
        result=propagate_export_itineraries(((2,4),),0,lambda window,codes:(0,))
        self.assertEqual((result['status'],result['certified_windows']),('complete',0))
        for vector in ((0,0),(True,),(0.5,)):
            with self.assertRaises((TypeError,ValueError)):
                propagate_export_itineraries(((2,4),),1,lambda window,codes:vector)
        with self.assertRaises(ValueError):
            propagate_export_itineraries(((2,4),),-1,lambda window,codes:(0,))


if __name__=='__main__': unittest.main()
