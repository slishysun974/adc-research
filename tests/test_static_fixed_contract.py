"""Hand examples and analytic margins for the new offline contract."""

from fractions import Fraction as F
import unittest

from adc_research.theory.static_fixed_contract import (
    nearest_even, export, pwl, readout, commit,
    local_error_bounds, gate_error_bounds, protected,
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


if __name__=="__main__":
    unittest.main()
