from fractions import Fraction as F
from itertools import product
import unittest

from adc_research.theory.quantized_mean_dynamics import (
    FixedStageRow, FrozenStageMean, accelerated_orbit, certify_rectangle,
    export_cell, export_code, StageRequest,
)
from adc_research.evaluation.gated_target_diagnostics import decompose_target_correlation


class QuantizedMeanDynamicsTests(unittest.TestCase):
    def test_tie_parity_and_complete_integer_preimages(self):
        for guard in (0, 1, 3, 12):
            for code in range(1, 6):
                lo, hi = export_cell(code, guard)
                self.assertEqual(export_code(lo, guard), code)
                self.assertEqual(export_code(hi, guard), code)
                self.assertNotEqual(export_code(lo-1, guard), code)
                self.assertNotEqual(export_code(hi+1, guard), code)
        self.assertEqual(export_cell(2, 3), (12, 20))
        self.assertEqual(export_cell(3, 3), (21, 27))

    def test_weighted_pooled_request_equals_repeated_actual_window(self):
        rows = (FixedStageRow(-24, -8, 2), FixedStageRow(15, 8, 1))
        kw = dict(width_scaled=8, steps=(F(1, 1024),)*4, window_size=3,
                  coefficient_bits=3, accumulator_bits=6, fixed_high=(8, 8))
        weighted = FrozenStageMean(rows, **kw)
        expanded = FrozenStageMean((rows[0].__class__(-24,-8),)*2+(FixedStageRow(15,8),), **kw)
        self.assertEqual(weighted.request((8,8)), expanded.request((8,8)))
        # Identity corrector gives local=-16,+7; all first-gate products add.
        self.assertEqual(weighted.request((8,8)).products[0], 312)

    def test_gate_equality_and_negative_full_scale_are_retained(self):
        model = FrozenStageMean((FixedStageRow(-32,-8),), width_scaled=8,
                                steps=(F(1,1000),)*4, coefficient_bits=3,
                                accumulator_bits=6, fixed_high=(8,8))
        self.assertEqual(model.request((8,8)).gates, (1,1,1,1))
        self.assertEqual(model.request((8,8)).products, (192,)*4)

    def test_q3_gate_moves_from_continuous_16_15_to_17_16(self):
        model=FrozenStageMean((FixedStageRow(376,128),FixedStageRow(-376,-128)),
                              width_scaled=256,steps=(F(1,1000),)*4)
        self.assertEqual(model.request((1024,1087)).gates[1],0)
        self.assertEqual(model.request((1024,1088)).gates[1],2)
        # 1088/1024=17/16 gives a product of 127.5 Q3 units;
        # nearest-even rounds it to 128, including the equality gate.
        self.assertEqual(F(1088,1024),F(17,16))
        self.assertEqual(F(16,15)-F(17,16),F(1,240))

    def test_cell_certificate_matches_every_small_integer_state(self):
        model = FrozenStageMean((FixedStageRow(12,8),FixedStageRow(-9,-8)),
                                width_scaled=8, steps=(F(1,1024),)*4,
                                coefficient_bits=3, accumulator_bits=6, fixed_high=(8,8))
        bounds=((50,75),(50,75))
        certificate=certify_rectangle(model,bounds)
        invariant=True
        fixed=False
        for state in product(*(range(lo,hi+1) for lo,hi in bounds)):
            after=model.transition(state)
            invariant &= all(lo <= z <= hi for z,(lo,hi) in zip(after,bounds))
            fixed |= after==state
        self.assertEqual(certificate['invariant'],invariant)
        self.assertEqual(bool(certificate['fixed_state_cells']),fixed)

    def test_outward_saturation_is_a_fixed_state(self):
        model=FrozenStageMean((FixedStageRow(0,8),),width_scaled=8,steps=(F(1),)*4,
                              coefficient_bits=3,accumulator_bits=6,fixed_high=(8,8))
        top=model.maximum
        certificate=certify_rectangle(model,((top,top),(top,top)))
        self.assertTrue(certificate['invariant'])
        self.assertTrue(certificate['fixed_state_cells'])

    def test_event_skipping_matches_every_small_direct_step(self):
        model=FrozenStageMean((FixedStageRow(8,8),),width_scaled=8,
                              steps=(F(1,4096),)*4,coefficient_bits=3,
                              accumulator_bits=10,fixed_high=(8,8))
        bounds=((1,model.maximum-1),)*2
        initial=(8*128+1,8*128)
        result=accelerated_orbit(model,initial,bounds,max_events=30)
        state=initial
        for event in result['events']:
            self.assertEqual(event['state'],state)
            for _ in range(event['constant_request_steps']):
                self.assertEqual(tuple(export_code(z,model.guard) for z in state),event['codes'])
                state=model.transition(state)
        self.assertEqual(result['last_state'],state)

    def test_full_state_cycle_not_just_exported_coefficient_repetition(self):
        # Hand-checkable map alternates +/-1 inside adjacent export cells.
        class Fixture:
            maximum=100
            guard=1
            def request(self,codes):
                class Request:
                    deltas=(1 if codes[0]<=2 else -1,0,0,0)
                return Request()
        result=accelerated_orbit(Fixture(),(4,10),((1,20),(1,20)),20)
        self.assertEqual(result['status'],'cycle')
        self.assertEqual(result['period'],2)
        # It records the first repeated event state, not the minimal transient.
        self.assertEqual(result['cycle_start'],2)

    def test_invariant_no_fixed_rectangle_certifies_a_nontrivial_cycle(self):
        class Fixture:
            maximum=100
            guard=1
            def request(self,codes):
                return StageRequest((0,)*4,(0,)*4,(1 if codes[0]==2 else -1,0,0,0),1)
        certificate=certify_rectangle(Fixture(),((5,6),(10,10)))
        self.assertTrue(certificate['invariant'])
        self.assertFalse(certificate['fixed_state_cells'])
        self.assertTrue(certificate['every_state_eventually_nontrivially_periodic'])

    def test_acceleration_rejects_missing_coordinates(self):
        model=FrozenStageMean((FixedStageRow(8,8),),width_scaled=8,steps=(F(1),)*4)
        with self.assertRaises(ValueError): accelerated_orbit(model,(1,),((1,10),)*2)

    def test_invalid_numeric_inputs_and_domain_are_rejected(self):
        with self.assertRaises(TypeError): export_cell(1.0)
        with self.assertRaises(ValueError): export_code(-1)
        with self.assertRaises(TypeError): FixedStageRow(1,True)
        with self.assertRaises(ValueError):
            FrozenStageMean((FixedStageRow(32,8),),width_scaled=8,steps=(F(1),)*4)

    def test_balanced_independent_target_can_leak_through_gate(self):
        # T=1, D=+/-1, y=T+D/4. The |y|>=1 gate selects D=+1.
        result=decompose_target_correlation(((F(1),F(-1),False,1),(F(1),F(1),True,1)))
        self.assertEqual(result['unconditional_target_correlation'],0)
        self.assertEqual(result['conditional_imbalance_part'],0)
        self.assertEqual(result['gate_covariance_part'],F(1,2))
        self.assertEqual(result['gated_target_correlation'],F(1,2))

    def test_predither_gate_and_conditional_balance_remove_signal_term(self):
        rows=tuple((F(t),F(d),t>=2,1) for t,d in product((1,2),(-1,1)))
        result=decompose_target_correlation(rows)
        self.assertEqual(result['gated_target_correlation'],0)
        self.assertEqual(result['gate_covariance_part'],0)

    def test_conditional_decomposition_matches_expanded_imbalance(self):
        rows=((F(1),F(1),True,3),(F(1),F(-1),False,1),(F(2),F(-1),True,2))
        result=decompose_target_correlation(rows)
        self.assertEqual(result['gated_target_correlation'],F(-1,6))
        self.assertEqual(result['conditional_imbalance_part']+result['gate_covariance_part'],F(-1,6))
        self.assertEqual(result,decompose_target_correlation(tuple((t,d,g,1) for t,d,g,c in rows for _ in range(c))))


if __name__=='__main__':
    unittest.main()
