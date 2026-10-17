"""Exact independent state/coverage controls for finite phase unions."""
from itertools import product
import unittest

from adc_research.theory.quantized_mean_dynamics import (
    export_code, integer_box_uncovered, subtract_integer_box, certify_phase_unions,
)


def contains(box, state):
    return all(lo <= value <= hi for (lo,hi),value in zip(box,state))


class QuantizedPhaseSetsTests(unittest.TestCase):
    def test_subtraction_matches_all_225_small_cuts(self):
        source = ((0,4),(0,4))
        intervals = tuple((lo,hi) for lo in range(5) for hi in range(lo,5))
        for cut in product(intervals,repeat=2):
            pieces = subtract_integer_box(source,cut)
            for state in product(range(5),repeat=2):
                memberships = sum(contains(piece,state) for piece in pieces)
                self.assertEqual(memberships,int(not contains(cut,state)))

    def test_all_corners_covered_still_leaves_a_union_hole(self):
        source = ((0,2),(0,2))
        corners = tuple(((x,x),(y,y)) for x,y in product((0,2),repeat=2))
        for state in product((0,2),repeat=2):
            self.assertTrue(any(contains(box,state) for box in corners))
        missing = integer_box_uncovered(source,corners)
        self.assertTrue(any(contains(box,(1,1)) for box in missing))

    def test_image_spanning_adjacent_rectangles_is_covered_exactly(self):
        phases = ((((12,20),),((21,27),)),)
        certificate = certify_phase_unions(phases,
            lambda phase,codes: ((1 if codes[0]==2 else -1,),),guard_bits=3,maximum=63)
        self.assertTrue(certificate['invariant'])
        self.assertEqual(certificate['cell_count'],2)
        self.assertEqual(certificate['cells'][0]['requests'][0]['image'],((13,21),))

    def test_two_phase_eight_coordinate_translation_closes_without_derivatives(self):
        phases = ((((21,27),)*8,), (((37,43),)*8,))
        certificate = certify_phase_unions(phases,
            lambda phase,codes: ((16 if phase==0 else -16,)*8,),guard_bits=3,maximum=63)
        self.assertTrue(certificate['invariant'])
        self.assertEqual((certificate['cell_count'],certificate['request_count']),(2,2))
        self.assertEqual(certificate['cells'][0]['requests'][0]['image'],phases[1][0])

    def test_phase_certificate_matches_every_small_integer_state(self):
        box = ((3,13),(3,13))
        def requests(phase,codes):
            return (tuple(1 if code<=2 else -1 for code in codes),)
        certificate = certify_phase_unions(((box,),),requests,guard_bits=2,maximum=31)
        all_inside = True
        for state in product(range(3,14),repeat=2):
            codes = tuple(export_code(z,2) for z in state)
            vector = requests(0,codes)[0]
            after = tuple(z+d for z,d in zip(state,vector))
            all_inside &= contains(box,after)
        self.assertEqual(certificate['invariant'],all_inside)
        self.assertTrue(all_inside)

    def test_saturation_image_retains_actual_endpoint_states(self):
        box = ((0,2),(13,15))
        certificate = certify_phase_unions(((box,),),lambda phase,codes: ((-20,20),),
                                          guard_bits=4,maximum=15)
        self.assertTrue(certificate['invariant'])
        for cell in certificate['cells']:
            image = cell['requests'][0]['image']
            self.assertEqual(image,((0,0),(15,15)))
        for state in product(range(3),range(13,16)):
            self.assertEqual(tuple(min(max(z+d,0),15) for z,d in zip(state,(-20,20))),(0,15))

    def test_every_allowed_request_is_required_not_just_the_mean(self):
        box = ((21,27),)
        zero = certify_phase_unions(((box,),),lambda phase,codes: ((0,),),guard_bits=3,maximum=63)
        varied = certify_phase_unions(((box,),),lambda phase,codes: ((-1,),(1,)),guard_bits=3,maximum=63)
        self.assertTrue(zero['invariant'])
        self.assertFalse(varied['invariant'])
        self.assertEqual(len(varied['violations']),2)

    def test_budget_rejects_before_request_work_and_limits_union_fragments(self):
        called = []
        def request(phase,codes): called.append(codes); return ((0,0),)
        with self.assertRaisesRegex(ValueError,'before evaluating'):
            certify_phase_unions(((((0,63),(0,63)),),),request,guard_bits=2,maximum=63,max_cells=4)
        self.assertEqual(called,[])
        with self.assertRaisesRegex(ValueError,'fragment budget'):
            integer_box_uncovered(((0,4),(0,4)),(((2,2),(2,2)),),max_fragments=1)

    def test_empty_partial_or_noninteger_contracts_are_rejected(self):
        box = ((21,27),)
        for requests in (lambda phase,codes: (),lambda phase,codes: ((0,0),),
                         lambda phase,codes: ((True,),),lambda phase,codes: ((0.0,),)):
            with self.assertRaises((TypeError,ValueError)):
                certify_phase_unions(((box,),),requests,guard_bits=3,maximum=63)
        for phases in ((),((),),((((7,3),),),),((((-1,3),),),)):
            with self.assertRaises(ValueError):
                certify_phase_unions(phases,lambda phase,codes: ((0,),),guard_bits=3,maximum=63)


if __name__ == '__main__': unittest.main()
