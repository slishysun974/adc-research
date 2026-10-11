from collections import Counter
from fractions import Fraction as F
from itertools import product
import unittest

from adc_research.theory.selection_probability_contract import (
    bounded_rejection_law, conditional_lane_mean, expectation_shift_bound,
    modulo_law, residue_counts, total_variation, weighted_moments,
)
from adc_research.theory.static_fixed_contract import readout
from adc_research.calibration.window_phase_selection import xorshift32


class SelectionProbabilityContractTests(unittest.TestCase):
    def test_residue_formula_matches_direct_intervals_and_binary_widths(self):
        for start,stop,p in ((0,32,30),(1,256,30),(7,81,9),(0,8,2)):
            counts=Counter(x%p for x in range(start,stop))
            self.assertEqual(residue_counts(stop,p,start),tuple(counts[i] for i in range(p)))
        self.assertEqual(modulo_law(5),(F(1,16),)*2+(F(1,32),)*28)
        self.assertEqual(total_variation(modulo_law(5),(F(1,30),)*30),F(7,120))

    def test_nonzero32bit_state_counts_do_not_assume_generator_period(self):
        counts=residue_counts(1<<32,30,1)
        self.assertEqual(counts[1:16],(143165577,)*15)
        self.assertEqual((counts[0],)+counts[16:],(143165576,)*15)
        self.assertEqual(total_variation(modulo_law(32,exclude_zero=True),(F(1,30),)*30),
                         F(15,2*((1<<32)-1)))

    def test_existing_xorshift_transform_has32_independent_binary_columns(self):
        # Independent GF(2) column reduction certifies invertibility of
        # this digital transition, without claiming a maximum period.
        pivots={}
        for i in range(32):
            column=xorshift32(1<<i)
            while column:
                bit=column.bit_length()-1
                if bit in pivots: column^=pivots[bit]
                else:
                    pivots[bit]=column
                    break
        self.assertEqual(len(pivots),32)

    def test_two_draw_capped_law_matches_all1024_input_pairs(self):
        counts=Counter(); draws=0
        for a,b in product(range(32),repeat=2):
            if a<30: selected,n=a,1
            elif b<30: selected,n=b,2
            else: selected,n=0,2
            counts[selected]+=1; draws+=n
        law=bounded_rejection_law(attempts=2)
        self.assertEqual(law.probabilities,tuple(F(counts[i],1024) for i in range(30)))
        self.assertEqual(law.expected_draws,F(draws,1024))
        self.assertEqual(law.deadline_failure_probability,F(1,256))

    def test_four_draw_deadline_cost_and_fallback_bias(self):
        law=bounded_rejection_law()
        self.assertEqual(law.deadline_failure_probability,F(1,65536))
        self.assertEqual(law.expected_draws,F(4369,4096))
        self.assertEqual(total_variation(law.probabilities,(F(1,30),)*30),F(29,1966080))
        self.assertEqual(sum(law.probabilities),1)
        self.assertEqual(bounded_rejection_law(bits=5,phases=16).probabilities,(F(1,16),)*16)

    def test_uniform_global_phases_and_causal_choice_can_still_select_biased_words(self):
        selected=[]; full=[]
        for history_phase in range(30):
            rows=[]
            for phase in range(30):
                for lane in range(4):
                    backend=45 if phase==history_phase else 15
                    z=readout(0,0,F(backend),1,1,(F(1),)*8,data_q3=True)
                    rows.append((16*z.y2,))
            conditional=(tuple(F(int(r==history_phase)) for r in range(30)),)*4
            selected.append(conditional_lane_mean(rows,conditional)[0])
            full.append(sum(r[0] for r in rows)/120)
        self.assertEqual(full,[F(0)]*30)
        self.assertEqual(selected,[F(464)]*30)
        # The 30 histories are equiprobable and select each phase once;
        # each conditioned window nevertheless selects a large product.

    def test_lane_marginals_suffice_for_mean_without_independence(self):
        rows=[(F(p-l),F(p*l)) for p in range(3) for l in range(4)]
        self.assertEqual(conditional_lane_mean(rows,((F(1,3),)*3,)*4),
                         tuple(sum(r[i] for r in rows)/12 for i in range(2)))

    def test_weighted_moments_and_tv_bound_match_direct_small_atom_enumeration(self):
        rows=((F(0),F(2)),(F(3),F(-1)),(F(1),F(4)))
        p=(F(1,2),F(1,3),F(1,6)); q=(F(1,3),)*3
        mean,cov=weighted_moments(rows,p)
        duplicated=[rows[0]]*3+[rows[1]]*2+[rows[2]]
        m=tuple(sum(r[i] for r in duplicated)/6 for i in range(2))
        c=tuple(tuple(sum((r[i]-m[i])*(r[j]-m[j]) for r in duplicated)/6 for j in range(2)) for i in range(2))
        self.assertEqual((mean,cov),(m,c))
        shift,bound=expectation_shift_bound((F(2),F(-1),F(4)),p,q)
        self.assertLessEqual(abs(shift),bound)
        variation=total_variation(p,q)
        f=tuple(F(int(a>b)) for a,b in zip(p,q))
        self.assertEqual(expectation_shift_bound(f,p,q),(variation,variation))

    def test_bounded_binary_mapping_cannot_have_equal30_preimages(self):
        # Divisibility is the exact count obstruction, not a probabilistic
        # goodness-of-fit test of a finite pseudo-random trace.
        for bits in range(1,81): self.assertNotEqual((1<<bits)%30,0)

    def test_rejects_invalid_domains_and_inexact_probabilities(self):
        for args in ((0,30,4,0),(5,33,4,0),(5,30,0,0),(5,30,4,30)):
            with self.assertRaises(ValueError): bounded_rejection_law(*args)
        with self.assertRaises(TypeError): weighted_moments(((F(1),),),(1.0,))
        with self.assertRaises(ValueError): weighted_moments(((F(1),),),(F(1,2),))


if __name__=='__main__': unittest.main()
