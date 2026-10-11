"""Independent exact controls of conditional target constraints."""
from fractions import Fraction as F
from itertools import product
import unittest

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.coupled_stationarity import coupled_moments
from adc_research.theory.static_fixed_contract import export, nearest_even, readout
from adc_research.theory.target_moment_bounds import (
    affine_target_interval, coupled_target_bounds, label_target_split,
    loss_change_interval,
)
from adc_research.theory.window_mean_map import analyze_window_mean


class TargetMomentBoundsTests(unittest.TestCase):
    def test_label_balance_needs_target_selection_and_gate_conditions(self):
        baseline = label_target_split(16, F(1, 2), 1, 1, 3, 3)
        self.assertEqual(baseline.value, 0)
        controls = (
            (label_target_split(16, F(1, 2), 1, 1, 5, 3), (16, 0, 0)),
            (label_target_split(16, F(1, 2), 2, 1, 3, 3), (0, 24, 0)),
            (label_target_split(16, F(1, 2), 1, 0, 3, 3), (0, 24, 0)),
            (label_target_split(16, F(3, 4), 1, 1, 3, 3), (0, 0, 24)),
        )
        for value, expected in controls:
            terms = (value.target_difference, value.selection_difference, value.probability_imbalance)
            self.assertEqual(terms, expected)
            self.assertEqual(value.value, sum(terms))

    def test_shared_target_cancels_uncertainty_and_box_extrema_are_sharp(self):
        coupled = affine_target_interval((0, 0), (16, -16), (2, 2), (8, 8), groups=(0, 0))
        self.assertEqual((coupled.lower, coupled.upper), (0, 0))
        separate = affine_target_interval((0, 0), (16, -16), (2, 2), (8, 8))
        self.assertEqual((separate.lower, separate.upper), (-48, 48))
        result = affine_target_interval((3, -2, 1), (-2, 1, 4), (0, 0, -1), (2, 2, 3),
                                        weights=(1, 2, 1), groups=('a', 'a', 'b'))
        values = [F(3-2*a+2*(-2+a)+1+4*b, 4) for a, b in product((0, 2), (-1, 3))]
        self.assertEqual((result.lower, result.upper), (min(values), max(values)))
        self.assertEqual(result.minimizing_targets[0], result.minimizing_targets[1])

    def test_static_exact_linear_inverse_has_zero_target_leakage(self):
        # Ungated scalar exact inverse, shared X across the two current tags.
        a, x, d = F(49, 50), F(4), F(16)
        raw = tuple(a*(x+s*d) for s in (-1, 1))
        y = tuple(r/a-s*d for r, s in zip(raw, (-1, 1)))
        self.assertEqual(y, (x, x))
        target = affine_target_interval((0, 0), (-d, d), (x, x), (x, x), groups=(0, 0))
        self.assertEqual(target.center, 0)
        self.assertEqual(sum(s*d*v for s, v in zip((-1, 1), y))/2, 0)

    def test_rear_label_segment_change_breaks_shared_local_target(self):
        samples = (Sample(0, 1, 0, 1, 1), Sample(0, 1, 0, 1, -1))
        k = (F(1),)*4+(F(1), F(3, 2), F(1), F(1))
        mean = analyze_window_mean(samples, k)
        self.assertEqual(tuple(r.selector1 for r in mean.rows), (0, 1))
        m = coupled_moments(mean, (2048,)*2, (2148,)*2)
        self.assertEqual(m.target_leakage[0], 96)  # tau+ =36, tau- =24
        bound = coupled_target_bounds(mean, (2048,)*2, (2148,)*2, (2148,)*2, groups=(0, 0))
        self.assertEqual(bound.leakage[0].center, 96)
        self.assertEqual(label_target_split(16, F(1, 2), 1, 1, 36, 24).value, 96)

    def test_quantization_and_export_keep_the_observable_residual(self):
        # floor(0.98*(4+/-16)) =19,-12; exact inverse differs from quantized inverse.
        samples = (Sample(0, 0, 19, 1, 1), Sample(0, 0, -12, 1, -1))
        k = (F(50, 49),)*4+(F(1),)*4
        mean = analyze_window_mean(samples, k)
        m = coupled_moments(mean, (2048,)*2, (1988,)*2)
        self.assertEqual(m.target_leakage[0], 0)
        self.assertEqual(m.correlations[0], F(-144, 49))
        front_rear = k[4:]+k[:4]
        continuous = [readout(0, 0, F(s.backend_centered_code), 1, s.stage2_dither_symbol,
                              front_rear, data_q3=False).output for s in samples]
        acc = tuple(nearest_even(v*(1 << 22)) for v in front_rear)
        exported = tuple(F(v, 1024) for v in export(acc))
        q3 = [readout(0, 0, F(s.backend_centered_code), 1, s.stage2_dither_symbol,
                      exported, data_q3=True) for s in samples]
        self.assertEqual(sum(16*s.stage2_dither_symbol*r.y2 for s, r in zip(samples, q3))/2, -3)
        integer = tuple(nearest_even(r.output) for r in q3)
        b = loss_change_interval(continuous, integer, (1988,)*2, (1988,)*2)
        direct = sum((z-1988)**2-(y-1988)**2 for y, z in zip(continuous, integer))/2
        self.assertEqual(b.center, direct)

    def test_history_independence_eliminates_leakage_but_not_output_gradient(self):
        # Scalar r=X+D+(1/2)H, independent balanced X,D,H. K=1 has C=0.
        triples = tuple(product((-1, 1), repeat=3))
        r = tuple(F(x+d)+F(h, 2) for x, d, h in triples)
        y = tuple(z-d for z, (_, d, _) in zip(r, triples))
        self.assertEqual(sum(d*x for x, d, _ in triples), 0)
        self.assertEqual(sum(d*z for z, (_, d, _) in zip(y, triples)), 0)
        g = affine_target_interval(tuple(z*j for z, j in zip(y, r)), tuple(-j for j in r),
                                   tuple(x for x, _, _ in triples), tuple(x for x, _, _ in triples))
        self.assertEqual(g.center, F(1, 4))

    def test_finite_loss_bounds_sign_ambiguity_and_integer_plateau(self):
        # Same old/new digital codes can improve or degrade for different allowed targets.
        b = loss_change_interval((10,), (11,), (9,), (12,))
        self.assertEqual((b.lower, b.upper), (-3, 3))
        for t in range(9, 13):
            value = (11-t)**2-(10-t)**2
            self.assertLessEqual(b.lower, value)
            self.assertLessEqual(value, b.upper)
        plateau = loss_change_interval((2052,)*4, (2052,)*4, (0,)*4, (4095,)*4)
        self.assertEqual((plateau.lower, plateau.upper), (0, 0))
        hidden = (1024*4096,)*8
        self.assertEqual(export(hidden), export(tuple(x+1 for x in hidden)))

    def test_coupled_component_endpoints_match_independent_offline_targets(self):
        samples = (Sample(0, 0, 17, 1, -1), Sample(0, 1, -7, -1, -1))
        mean = analyze_window_mean(samples, (F(1),)*8)
        b = coupled_target_bounds(mean, (2048,)*2, (2040, 2050), (2050, 2060),
                                  learning_weights=(1, 0))
        for i in range(8):
            for bound, field in ((b.half_gradient[i], 'output_cross_moment'), (b.leakage[i], 'target_leakage')):
                for targets, expected in ((bound.minimizing_targets, bound.lower),
                                          (bound.maximizing_targets, bound.upper)):
                    m = coupled_moments(mean, (2048,)*2, targets, learning_weights=(1, 0))
                    self.assertEqual(getattr(m, field)[i], expected)

    def test_invalid_assumptions_and_selector_boundary(self):
        with self.assertRaises(TypeError):
            loss_change_interval((1.0,), (2,), (0,), (3,))
        with self.assertRaises(ValueError):
            affine_target_interval((0, 0), (1, 1), (0, 1), (2, 2), groups=(0, 0))
        with self.assertRaises(ValueError):
            loss_change_interval((1,), (2,), (3,), (0,))
        with self.assertRaises(ValueError):
            label_target_split(16, 2, 1, 1, 0, 0)
        mean = analyze_window_mean((Sample(0, 1, 16, -1, 1),), (F(1),)*8)
        b = coupled_target_bounds(mean, (2048,), (2048,), (2048,))
        self.assertFalse(b.output_derivative_regular)


if __name__ == '__main__':
    unittest.main()
