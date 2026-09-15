from __future__ import annotations

import unittest

import numpy as np

from adc_research.causal import (
    InterventionFactor,
    exact_shapley,
    metric_loss_values,
    run_factorial_interventions,
)
from adc_research.metrics import spectrum_metrics
from adc_research.pipeline import MismatchRealization, PipelineConfig, simulate


class PipelineBaselineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.n_samples = 4096
        self.tone_bin = 31
        self.base = PipelineConfig(amplitude=0.9, seed=17)
        self.realization = MismatchRealization.sample(self.base, self.n_samples)

    def test_nominal_simulation_is_well_formed(self) -> None:
        result = simulate(self.base, self.n_samples, self.tone_bin, self.realization)
        self.assertEqual(result.output_signal.shape, (self.n_samples,))
        self.assertGreater(np.unique(result.stage1_code).size, 2)
        self.assertEqual(result.threshold_crossing_rate, 0.0)
        self.assertLess(result.overload_rate, 0.01)

    def test_nonidealities_change_output_and_events(self) -> None:
        ideal = simulate(self.base, self.n_samples, self.tone_bin, self.realization)
        impaired_config = PipelineConfig(
            amplitude=0.9,
            gain_error=0.02,
            cdac_mismatch_lsb=0.1,
            comparator_offset_lsb=0.08,
            seed=17,
        )
        impaired = simulate(impaired_config, self.n_samples, self.tone_bin, self.realization)
        self.assertFalse(np.array_equal(ideal.output_signal, impaired.output_signal))
        self.assertGreater(impaired.threshold_crossing_rate + impaired.overload_rate, 0.0)

    def test_spectral_metrics_are_finite(self) -> None:
        result = simulate(self.base, self.n_samples, self.tone_bin, self.realization)
        metrics = spectrum_metrics(result.output_signal, self.tone_bin)
        self.assertTrue(np.isfinite(metrics.sfdr_db))
        self.assertTrue(np.isfinite(metrics.sndr_db))
        self.assertGreater(metrics.sfdr_db, metrics.sndr_db)

    def test_shapley_values_sum_to_total_loss(self) -> None:
        factors = [
            InterventionFactor("gain_error", 0.015),
            InterventionFactor("cdac_mismatch_lsb", 0.08),
            InterventionFactor("comparator_offset_lsb", 0.06),
        ]
        results = run_factorial_interventions(
            self.base,
            factors,
            self.n_samples,
            self.tone_bin,
            self.realization,
        )
        losses = metric_loss_values(results, "sfdr_db")
        names = [factor.name for factor in factors]
        shapley = exact_shapley(losses, names)
        self.assertAlmostEqual(sum(shapley.values()), losses[frozenset(names)], places=10)


if __name__ == "__main__":
    unittest.main()

