"""Check finite-record bounds against the scoring code and enumerated records."""

from __future__ import annotations

import itertools
import math
import unittest

import numpy as np

from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.theory.finite_record_bounds import (
    bound_finite_coherent_sfdr_binwise,
    bound_finite_coherent_tone,
    code_uncertainty_budget_for_floors,
)


class FiniteRecordBoundsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sample_count = 32
        self.tone_bin = 3
        n = np.arange(self.sample_count)
        self.reference = np.rint(
            100
            + 40 * np.sin(2 * np.pi * self.tone_bin * n / self.sample_count)
            + 3 * np.sin(2 * np.pi * 5 * n / self.sample_count)
        )

    def score(self, codes: np.ndarray) -> tuple[float, float]:
        metrics = analyze_coherent_tone(
            codes, sample_rate_hz=1.0, fundamental_bin=self.tone_bin
        ).metrics
        return metrics.sndr_db, metrics.sfdr_dbc

    def test_zero_envelope_reproduces_score(self) -> None:
        result = bound_finite_coherent_tone(
            self.reference, self.reference, self.reference,
            fundamental_bin=self.tone_bin,
        )
        sndr, sfdr = self.score(self.reference)
        self.assertEqual(result.rms_code_uncertainty, 0.0)
        self.assertAlmostEqual(result.sndr_db.lower, sndr, places=10)
        self.assertAlmostEqual(result.sndr_db.upper, sndr, places=10)
        self.assertAlmostEqual(result.sfdr_dbc.lower, sfdr, places=10)
        self.assertAlmostEqual(result.sfdr_dbc.upper, sfdr, places=10)
        binwise = bound_finite_coherent_sfdr_binwise(
            self.reference, self.reference, fundamental_bin=self.tone_bin,
        )
        self.assertAlmostEqual(binwise.sfdr_dbc.lower, sfdr, places=10)
        self.assertAlmostEqual(binwise.sfdr_dbc.upper, sfdr, places=10)

    def test_every_enumerated_record_lies_inside_bounds(self) -> None:
        lower = self.reference.copy()
        upper = self.reference.copy()
        uncertain_indices = (2, 11, 19)
        lower[list(uncertain_indices)] -= 1
        upper[list(uncertain_indices)] += 1
        result = bound_finite_coherent_tone(
            self.reference, lower, upper, fundamental_bin=self.tone_bin
        )
        binwise = bound_finite_coherent_sfdr_binwise(
            lower, upper, fundamental_bin=self.tone_bin,
        )
        self.assertAlmostEqual(result.rms_code_uncertainty, math.sqrt(3 / 32))
        for shifts in itertools.product((-1, 0, 1), repeat=3):
            codes = self.reference.copy()
            codes[list(uncertain_indices)] += shifts
            sndr, sfdr = self.score(codes)
            self.assertLessEqual(result.sndr_db.lower, sndr + 1e-10)
            self.assertLessEqual(sndr, result.sndr_db.upper + 1e-10)
            self.assertLessEqual(result.sfdr_dbc.lower, sfdr + 1e-10)
            self.assertLessEqual(sfdr, result.sfdr_dbc.upper + 1e-10)
            self.assertLessEqual(binwise.sfdr_dbc.lower, sfdr + 1e-10)
            self.assertLessEqual(sfdr, binwise.sfdr_dbc.upper + 1e-10)

    def test_binwise_bound_handles_asymmetric_integer_envelopes(self) -> None:
        lower = self.reference.copy()
        upper = self.reference.copy()
        upper[[2, 11, 19]] += 1
        bounds = bound_finite_coherent_sfdr_binwise(
            lower, upper, fundamental_bin=self.tone_bin,
        )
        self.assertEqual(bounds.sum_code_halfwidths, 1.5)
        for shifts in itertools.product((0, 1), repeat=3):
            codes = self.reference.copy()
            codes[[2, 11, 19]] += shifts
            _, sfdr = self.score(codes)
            self.assertLessEqual(bounds.sfdr_dbc.lower, sfdr + 1e-10)
            self.assertLessEqual(sfdr, bounds.sfdr_dbc.upper + 1e-10)

    def test_binwise_bound_rejects_invalid_envelope(self) -> None:
        lower = self.reference.copy()
        upper = self.reference.copy()
        lower[0] += 1
        with self.assertRaisesRegex(ValueError, "lower code"):
            bound_finite_coherent_sfdr_binwise(
                lower, upper, fundamental_bin=self.tone_bin,
            )

    def test_rejects_an_envelope_that_excludes_reference(self) -> None:
        lower = self.reference.copy()
        upper = self.reference.copy()
        lower[0] += 1
        with self.assertRaises(ValueError):
            bound_finite_coherent_tone(
                self.reference, lower, upper, fundamental_bin=self.tone_bin
            )

    def test_unresolved_spur_gives_unbounded_upper_sfdr(self) -> None:
        lower = self.reference - 10
        upper = self.reference + 10
        result = bound_finite_coherent_tone(
            self.reference, lower, upper, fundamental_bin=self.tone_bin
        )
        self.assertTrue(math.isinf(result.sfdr_dbc.upper))

    def test_inverse_budget_agrees_with_forward_bound(self) -> None:
        lower = self.reference.copy()
        upper = self.reference.copy()
        lower[2] -= 1
        upper[2] += 1
        forward = bound_finite_coherent_tone(
            self.reference, lower, upper, fundamental_bin=self.tone_bin,
        )
        loose = code_uncertainty_budget_for_floors(
            self.reference, fundamental_bin=self.tone_bin,
            minimum_sndr_db=forward.sndr_db.lower - 0.01,
            minimum_sfdr_dbc=forward.sfdr_dbc.lower - 0.01,
        )
        tight = code_uncertainty_budget_for_floors(
            self.reference, fundamental_bin=self.tone_bin,
            minimum_sndr_db=forward.sndr_db.lower + 0.01,
            minimum_sfdr_dbc=forward.sfdr_dbc.lower + 0.01,
        )
        self.assertGreater(loose.joint_rms_budget, forward.rms_code_uncertainty)
        self.assertLess(tight.joint_rms_budget, forward.rms_code_uncertainty)
        self.assertEqual(loose.joint_rms_budget, min(
            loose.sndr_rms_budget, loose.sfdr_rms_budget,
        ))

    def test_budget_rejects_a_floor_above_reference(self) -> None:
        nominal = self.score(self.reference)
        with self.assertRaisesRegex(ValueError, "already falls below"):
            code_uncertainty_budget_for_floors(
                self.reference, fundamental_bin=self.tone_bin,
                minimum_sndr_db=nominal[0] + 1.0,
            )
        with self.assertRaisesRegex(ValueError, "at least one"):
            code_uncertainty_budget_for_floors(
                self.reference, fundamental_bin=self.tone_bin,
            )


if __name__ == "__main__":
    unittest.main()
