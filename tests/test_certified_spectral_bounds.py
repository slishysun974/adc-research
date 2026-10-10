"""Analytic powers, exhaustive records, and numerical-certificate boundaries."""

from __future__ import annotations

from fractions import Fraction as F
import itertools
import math
import unittest

from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.theory.certified_spectral_bounds import (
    RationalInterval, _sqrt_point, _twiddles,
    bound_certified_coherent_tone, certified_phase, certified_pi, certified_power_db,
)


def as_float(value):
    return -math.inf if value == "-inf" else math.inf if value == "+inf" else float(value)


class CertifiedSpectralBoundsTests(unittest.TestCase):
    def assert_contains(self, interval, value):
        # Floating scoring is an independent consistency check, not the
        # mathematical justification of the rational certificate.
        self.assertLessEqual(as_float(interval.lower), value + 1e-11)
        self.assertLessEqual(value, as_float(interval.upper) + 1e-11)

    def test_rational_rounding_and_signed_square(self):
        result = RationalInterval(F(-1, 3), F(2, 3)).rounded(32)
        self.assertLessEqual(result.lower, F(-1, 3))
        self.assertGreaterEqual(result.upper, F(2, 3))
        self.assertLessEqual(result.upper-result.lower, F(1)+F(2, 2**32))
        self.assertEqual(RationalInterval(F(-3), F(2)).square(),
                         RationalInterval(F(0), F(9)))
        self.assertEqual(RationalInterval(F(-3), F(-2)).square(),
                         RationalInterval(F(4), F(9)))

    def test_pi_contains_independent_decimal_bracket(self):
        # Two known decimal bounds, distinct from the Machin evaluation.
        prefix = "31415926535897932384626433832795028841971693993751058209749445923078164062862089986280348253421170679"
        low = F(int(prefix), 10**(len(prefix)-1))
        high = low + F(1, 10**(len(prefix)-1))
        for bits in (32, 72, 128, 256):
            result = certified_pi(bits)
            self.assertLessEqual(result.lower, low)
            self.assertGreaterEqual(result.upper, high)
            self.assertLessEqual(result.upper-result.lower, F(2, 2**bits))

    def test_twiddles_cover_exact_algebraic_roots(self):
        for size in (8, 12):
            table = _twiddles(size, 72)
            scale = 1 << 72
            self.assertEqual(table[0], (scale, scale, 0, 0))
            self.assertEqual(table[size//4], (0, 0, scale, scale))
            self.assertEqual(table[size//2], (-scale, -scale, 0, 0))
            self.assertEqual(table[3*size//4], (0, 0, -scale, -scale))
        # sin(pi/4)^2 = cos(pi/4)^2 = 1/2.
        cl, cu, sl, su = _twiddles(8, 72)[1]
        for low, high in ((cl, cu), (sl, su)):
            self.assertLessEqual(F(low, 1 << 72)**2, F(1, 2))
            self.assertGreaterEqual(F(high, 1 << 72)**2, F(1, 2))
        # cos(pi/3)=1/2, sin(pi/3)^2=3/4.
        cl, cu, sl, su = _twiddles(12, 72)[2]
        self.assertLessEqual(F(cl, 1 << 72), F(1, 2))
        self.assertGreaterEqual(F(cu, 1 << 72), F(1, 2))
        self.assertLessEqual(F(sl, 1 << 72)**2, F(3, 4))
        self.assertGreaterEqual(F(su, 1 << 72)**2, F(3, 4))

    def test_square_roots_are_proved_by_integer_squaring(self):
        for value in (F(0), F(4), F(2), F(1, 3), F(10**100, 7), F(1, 10**100)):
            result = _sqrt_point(value, 72)
            self.assertLessEqual(result.lower**2, value)
            self.assertGreaterEqual(result.upper**2, value)
            self.assertLessEqual(result.upper-result.lower, F(1, 2**72))
        self.assertEqual(_sqrt_point(F(4), 72), RationalInterval.point(2))

    def test_public_phase_is_periodic_and_rejects_float_indices(self):
        self.assertEqual(certified_phase(1, 8), certified_phase(9, 8))
        self.assertEqual(certified_phase(-1, 8), certified_phase(7, 8))
        self.assertEqual(certified_phase(1, 4),
                         (RationalInterval.point(0), RationalInterval.point(1)))
        with self.assertRaises(TypeError):
            certified_phase(1.0, 8)
        with self.assertRaises(ValueError):
            certified_phase(1, 0)
        with self.assertRaises(TypeError):
            RationalInterval.point(0.1)

    def test_decibels_contain_exact_powers_of_ten(self):
        for exponent in (-100, -3, -1, 0, 1, 3, 100):
            result = certified_power_db(F(10)**exponent)
            self.assertLessEqual(result.lower, 10*exponent)
            self.assertGreaterEqual(result.upper, 10*exponent)
            self.assertLess(result.upper-result.lower, F(1, 10**15))
        # Negative ln numerator requires considering all denominator corners.
        result = certified_power_db(F(1, 2))
        self.assert_contains(result, -10*math.log10(2))

    def test_exact_nyquist_spur_has_single_sided_weight(self):
        codes = (11, 13, 11, 5, 11, 13, 11, 5)
        # DC=10; fundamental k=2 has power 8, Nyquist power 1.
        result = bound_certified_coherent_tone(codes, codes, fundamental_bin=2)
        self.assertEqual(result.midpoint_bin_power[2], RationalInterval.point(8))
        self.assertEqual(result.midpoint_bin_power[4], RationalInterval.point(1))
        for ratio in (result.sndr_power_ratio, result.sfdr_power_ratio):
            self.assertLessEqual(ratio.lower, 8)
            self.assertGreaterEqual(ratio.upper, 8)
        self.assert_contains(result.sndr_db, 10*math.log10(8))
        self.assert_contains(result.sfdr_dbc, 10*math.log10(8))

    def test_non_power_of_two_record_matches_independent_scoring(self):
        codes = (14, 17, 12, 6, 3, 9)
        result = bound_certified_coherent_tone(codes, codes, fundamental_bin=1)
        score = analyze_coherent_tone(codes, sample_rate_hz=6,
                                     fundamental_bin=1, harmonic_orders=()).metrics
        self.assert_contains(result.sndr_db, score.sndr_db)
        self.assert_contains(result.sfdr_dbc, score.sfdr_dbc)
        self.assertLess(result.sndr_db.upper-result.sndr_db.lower, F(1, 10**14))

    def test_every_exhaustive_integer_history_is_covered(self):
        lower = [107, 103, 101, 99, 95, 97, 97, 101]
        upper = lower.copy()
        indices = (0, 3, 6)
        for index in indices:
            upper[index] += 2
        result = bound_certified_coherent_tone(lower, upper, fundamental_bin=1)
        self.assertTrue(result.fundamental_guaranteed_nonzero)
        for choices in itertools.product(range(3), repeat=3):
            codes = lower.copy()
            for index, offset in zip(indices, choices):
                codes[index] += offset
            score = analyze_coherent_tone(codes, sample_rate_hz=8,
                                         fundamental_bin=1, harmonic_orders=()).metrics
            self.assert_contains(result.sndr_db, score.sndr_db)
            self.assert_contains(result.sfdr_dbc, score.sfdr_dbc)
            spectrum = analyze_coherent_tone(codes, sample_rate_hz=8,
                                            fundamental_bin=1, harmonic_orders=()).rms_power
            for bounds, power in zip(result.binwise_record_power, spectrum):
                self.assert_contains(bounds, power)

    def test_exact_pure_tone_and_unresolved_fundamental(self):
        codes = (12, 10, 8, 10)
        result = bound_certified_coherent_tone(codes, codes, fundamental_bin=1)
        self.assertEqual(result.sndr_db.lower, "+inf")
        self.assertEqual(result.sndr_db.upper, "+inf")
        self.assertEqual(result.sfdr_dbc.lower, "+inf")
        wide = bound_certified_coherent_tone((0, 0, 0, 0), (4, 4, 4, 4), fundamental_bin=1)
        self.assertFalse(wide.fundamental_guaranteed_nonzero)
        self.assertEqual(wide.sndr_db.lower, "-inf")
        self.assertEqual(wide.sndr_db.upper, "+inf")
        with self.assertRaisesRegex(ValueError, "no fundamental"):
            bound_certified_coherent_tone((10,)*4, (10,)*4, fundamental_bin=1)

    def test_constant_integer_offset_does_not_change_certificate(self):
        lower = (7, 3, 1, -1, -5, -3, -3, 1)
        upper = tuple(x+1 for x in lower)
        original = bound_certified_coherent_tone(lower, upper, fundamental_bin=1)
        shifted = bound_certified_coherent_tone(tuple(x+10**80 for x in lower),
                                              tuple(x+10**80 for x in upper), fundamental_bin=1)
        self.assertEqual(original, shifted)

    def test_precision_change_preserves_analytic_value(self):
        codes = (12, 9, 10, 9)
        coarse = bound_certified_coherent_tone(codes, codes, fundamental_bin=1, bits=32)
        fine = bound_certified_coherent_tone(codes, codes, fundamental_bin=1, bits=96)
        for result in (coarse, fine):
            self.assertLessEqual(result.sndr_power_ratio.lower, F(1, 2))
            self.assertGreaterEqual(result.sndr_power_ratio.upper, F(1, 2))
        self.assertLess(fine.sndr_db.upper-fine.sndr_db.lower,
                        coarse.sndr_db.upper-coarse.sndr_db.lower)

    def test_invalid_source_and_protocol_inputs_are_rejected(self):
        codes = (12, 10, 8, 10)
        for invalid in ((12.0, 10, 8, 10), (True, 10, 8, 10), (F(12), 10, 8, 10)):
            with self.assertRaises(TypeError):
                bound_certified_coherent_tone(invalid, codes, fundamental_bin=1)
        for lower, upper, tone in ((codes, codes[:-1], 1), (codes[:3], codes[:3], 1),
                                   (codes, codes, 0), (codes, codes, 2),
                                   ((13, 10, 8, 10), codes, 1)):
            with self.assertRaises(ValueError):
                bound_certified_coherent_tone(lower, upper, fundamental_bin=tone)
        with self.assertRaises(TypeError):
            certified_power_db(2.0)
        with self.assertRaises(ValueError):
            certified_power_db(F(0))
        with self.assertRaises(ValueError):
            bound_certified_coherent_tone(codes, codes, fundamental_bin=1, bits=16)


if __name__ == "__main__":
    unittest.main()
