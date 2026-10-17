"""Hand examples and analytic margins for the new offline contract."""

from fractions import Fraction as F
import unittest

from adc_research.theory.static_fixed_contract import (
    nearest_even, export, pwl, readout, commit,
    local_error_bounds, gate_error_bounds, protected,
    output_range_bound, saturated_integer, saturation_loss_change,
)


class StaticFixedContractTests(unittest.TestCase):
    def test_signed_ties_and_export_cell_endpoints(self):
        self.assertEqual([nearest_even(F(v,2)) for v in (-5,-3,-1,1,3,5)],[-2,-2,0,0,2,2])
        a=1024*4096+2048
        self.assertEqual(export((a-1,a,a+1)),(1024,1024,1025))
        self.assertEqual(export((1025*4096+2048,)),(1026,))

    def test_complete_unity_word_has_third_readout_and_gate_support(self):
        # Exact plant witness X=1/8, D1=D2=-1 is derived in the document.
        r=readout(1,-2,F(-80),-1,-1,(F(1),)*8,data_q3=True)
        self.assertEqual((r.raw1,r.y1,r.y2,r.output),(-320,-256,-64,2304))
        self.assertTrue(r.gates[0][2] and r.gates[1][2])
        self.assertTrue(r.support[0][2] and r.support[1][2])
        self.assertFalse(r.support[0][3] or r.support[1][3])

    def test_offset_and_product_rounding_do_not_equal_rounding_total(self):
        # Rear: offset32*(1026/1024)=32.0625 ->32; local64*.5/1024=.03125 ->0.
        # Together32.09375 would round32.125. Separate rounding is required.
        k=(F(1026,1024),F(64,1024),F(1),F(1))
        self.assertEqual(pwl(F(65,2),32,k,True),F(32))
        self.assertEqual(pwl(F(65,2),32,k,False),F(1027,32))

    def test_compression_margin_protects_only_declared_inverse_state(self):
        a1,a2=F(39,40),F(49,50)
        e1,e2=local_error_bounds(320*a1+1/a2,80*a2+1,1/a1)
        t1,t2=gate_error_bounds()
        margin1=256/a1-256-1/(a1*a2)
        margin2=63/a2-64
        self.assertGreater(margin1,e1+t1[2])
        self.assertGreater(margin2,e2+t2[2])
        self.assertFalse(protected(F(0),e2,t2[2]))
        self.assertFalse(protected(e2+t2[2],e2,t2[2]))

    def test_nonzero_hidden_update_can_leave_export_unchanged(self):
        a=(1<<22,)*8
        # Chosen arithmetic control: exact one-LSB request, not training step.
        requests,after=commit(a,(F(-1),)*8,1,(F(1,1<<22),)*8)
        self.assertEqual(requests,(1,)*8)
        self.assertNotEqual(after,a)
        self.assertEqual(export(after),export(a))
        requests,after=commit((0,)*8,(F(3),)*8,1,(F(1,1<<23),)*8)
        self.assertEqual(requests,(-2,)*8)
        self.assertEqual(after,(0,)*8)

    def test_zero_mean_hidden_request_need_not_give_zero_mean_export_change(self):
        center = 1024*4096
        starts, requests = (center+2048, center), (1, -1)
        hidden = sum(requests)/2
        effective = [F(export((a+r,))[0]-export((a,))[0], 1024)
                     for a, r in zip(starts, requests)]
        self.assertEqual(hidden, 0)
        self.assertEqual(effective, [F(1, 1024), F(0)])
        self.assertEqual(sum(effective)/2, F(1, 2048))

    def test_unprotected_second_gate_changes_without_its_basis_support(self):
        source=(F(4097,4096),)*8
        before=readout(0,0,F(16),1,-1,source,data_q3=False)
        after=readout(0,0,F(16),1,-1,(F(1),)*8,data_q3=True)
        self.assertEqual(abs(before.y2)-before.thresholds[1][1],F(-1,256))
        self.assertFalse(before.gates[1][1])
        self.assertTrue(after.gates[1][1])
        self.assertFalse(after.support[1][1])

    def test_q3_range_bound_keeps_two_rear_rounding_terms(self):
        bound = output_range_bound(3, 2, 79, 1228, 1228)
        self.assertEqual(bound.front_raw_radius, F(93917, 256))
        self.assertEqual(bound.output_radius, F(133694215, 65536))
        self.assertTrue(bound.no_saturation)
        self.assertFalse(output_range_bound(3, 2, 79, 1280, 1280).no_saturation)

    def test_range_bound_covers_extreme_words_and_segment_boundaries(self):
        from itertools import product
        banks = ((1024,)*8, (1228,)*8, (0,1228,0,1228)*2)
        for codes in banks:
            bound = output_range_bound(3, 2, 79, max(codes[:4]), max(codes[4:]))
            for q1,q2,be,d1,d2 in product((-3,3),(-2,2),(-79,-32,0,31,32,78,79),(-1,1),(-1,1)):
                rd=readout(q1,q2,F(be),d1,d2,tuple(F(k,1024) for k in codes),data_q3=True)
                self.assertLessEqual(abs(rd.raw1),bound.front_raw_radius)
                self.assertLessEqual(abs(rd.output-2048),bound.output_radius)
                self.assertEqual(nearest_even(rd.output),saturated_integer(rd.output))

    def test_legal_slopes_alone_do_not_certify_output_range(self):
        codes=(2047,)*8
        bound=output_range_bound(3,2,79,2047,2047)
        self.assertTrue(bound.front_domain_safe)
        self.assertFalse(bound.no_saturation)
        rd=readout(3,2,F(79),-1,-1,tuple(F(k,1024) for k in codes),data_q3=True)
        self.assertGreater(rd.output,4095)

    def test_saturation_mse_projection_requires_target_inside_range(self):
        for y in (F(-5), F(-1,8), F(4095)+F(1,8), F(4100)):
            for t in (F(0),F(2048),F(4095)):
                self.assertLessEqual(saturation_loss_change(y,t),0)
        self.assertEqual(saturation_loss_change(F(4096),F(4096)),1)
        # Q3 saturation can occur even when both final integer codes equal4095.
        self.assertEqual(saturated_integer(F(32761,8)),4095)
        self.assertEqual(saturation_loss_change(F(32761,8),F(4095)),0)

    def test_round_then_integer_clip_matches_saturate_then_round(self):
        for j in range(-16,16):
            for offset in (0,4095):
                y=F(offset)+F(j,8)
                self.assertEqual(saturated_integer(y),min(4095,max(0,nearest_even(y))))

    def test_range_and_saturation_reject_invalid_contract(self):
        for args in ((3,2,128,1228,1228),(3,2,79,-1,1228),(5,2,79,1228,1228)):
            with self.assertRaises(ValueError):output_range_bound(*args)
        with self.assertRaises(ValueError):saturated_integer(F(0),1,0)


if __name__=="__main__":
    unittest.main()
