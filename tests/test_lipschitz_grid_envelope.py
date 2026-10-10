"""Finite analog scans become conditional continuous envelopes only with L."""

from __future__ import annotations

import unittest
from math import sin
from pathlib import Path

import numpy as np
import yaml

from adc_research.theory.lipschitz_grid_envelope import LipschitzGridEnvelope
from adc_research.theory.static_observation_reachability import (
    ClosedInterval,
    StaticCandidateArchitecture,
    propagate_static_observations,
)


ROOT = Path(__file__).resolve().parents[1]


class LipschitzGridEnvelopeTests(unittest.TestCase):
    def test_hidden_between_sample_peak_remains_possible(self) -> None:
        envelope = LipschitzGridEnvelope(
            (0.0, 1.0),
            (ClosedInterval(0.0, 0.0), ClosedInterval(0.0, 0.0)),
            slope_bound=1.0,
        )
        midpoint = envelope(ClosedInterval(0.5, 0.5))
        self.assertEqual(midpoint, ClosedInterval(-0.5, 0.5))
        self.assertGreaterEqual(envelope(ClosedInterval(0.0, 1.0)).upper, 0.5)

    def test_smooth_curve_is_covered_between_grid_points_and_across_cells(self) -> None:
        def truth(value: float) -> float:
            return value + 0.1 * sin(6 * value)

        grid = tuple(round(-1 + index / 10, 10) for index in range(21))
        measured = tuple(
            ClosedInterval(truth(x) - 0.002, truth(x) + 0.002)
            for x in grid
        )
        # |truth'| = |1 + 0.6 cos(6x)| <= 1.6. Use an external
        # certificate of 1.7 rather than a slope fitted from the grid.
        envelope = LipschitzGridEnvelope(grid, measured, slope_bound=1.7)
        for low, high in ((-0.93, -0.64), (0.01, 0.14), (0.75, 0.75), (-1, 1)):
            bound = envelope(ClosedInterval(low, high))
            for value in np.linspace(low, high, 101):
                actual = truth(float(value))
                self.assertLessEqual(bound.lower - 1e-12, actual)
                self.assertLessEqual(actual, bound.upper + 1e-12)

    def test_contradictory_or_incomplete_evidence_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "contradict"):
            LipschitzGridEnvelope(
                (0.0, 1.0, 2.0),
                (ClosedInterval(0, 0), ClosedInterval(0, 100), ClosedInterval(130, 130)),
                slope_bound=60.0,
            )
        with self.assertRaises(ValueError):
            LipschitzGridEnvelope(
                (0.0, 1.0), (ClosedInterval(0, 0), ClosedInterval(1, 1)),
                slope_bound=-1.0,
            )
        constant = LipschitzGridEnvelope(
            (0.0, 1.0), (ClosedInterval(2, 3), ClosedInterval(2.5, 3.5)),
            slope_bound=0.0,
        )
        self.assertEqual(constant(ClosedInterval(0.1, 0.9)), ClosedInterval(2.5, 3.0))
        with self.assertRaisesRegex(ValueError, "outside the measured input domain"):
            constant(ClosedInterval(-0.1, 0.5))

    def test_grid_envelopes_feed_independent_main_auxiliary_propagation(self) -> None:
        config = yaml.safe_load(
            (ROOT / "configs/architectures/gu_behavioral_v1.yaml").read_text(
                encoding="utf-8"
            )
        )
        front = config["front_stage_template"]
        thresholds = tuple(ClosedInterval(t, t) for t in front["thresholds"])
        geometry = StaticCandidateArchitecture(
            thresholds, thresholds,
            tuple(front["output_symbols"]), tuple(front["output_symbols"]),
            tuple(front["dac_levels"]), tuple(front["dac_levels"]),
            (-1.0, 1.0), (-1.0, 1.0), 8,
        )
        grid = tuple(round(-0.25 + 0.025 * index, 10) for index in range(21))
        pad = 1e-6
        main = LipschitzGridEnvelope(
            grid, tuple(ClosedInterval(4 * x - pad, 4 * x + pad) for x in grid),
            slope_bound=4.01,
        )
        auxiliary = LipschitzGridEnvelope(
            grid,
            tuple(ClosedInterval(min(2 * x, 3 * x) - pad,
                                 max(2 * x, 3 * x) + pad) for x in grid),
            slope_bound=3.01,
        )
        second_main = LipschitzGridEnvelope(
            grid, tuple(ClosedInterval(4.1 * x - pad, 4.1 * x + pad) for x in grid),
            slope_bound=4.11,
        )
        observations = propagate_static_observations(
            ClosedInterval(-0.2, -0.2),
            ClosedInterval(0, 0), ClosedInterval(0, 0),
            geometry, main, auxiliary, second_main,
        )
        triples = {
            (item.stage1_symbol, item.stage2_symbol, item.backend_centered_code)
            for item in observations.outcomes
        }
        self.assertIn((-1, 0, 104), triples)
        self.assertIn((-1, 1, -27), triples)
        self.assertFalse(observations.backend_overload_possible)


if __name__ == "__main__":
    unittest.main()
