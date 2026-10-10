"""Independent limits and histories for the offline two-phase ADC candidate."""

from pathlib import Path
import unittest
import yaml

from adc_research.platform.amplifier import StaticCubicTruthConfig
from adc_research.platform.dual_path_settling import (
    DualPathSettlingConfig, DualPathSettlingState, process as old_process,
)
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.two_phase_dual_path import TwoPhasePath, TwoPhaseDualPathConfig, process


class TwoPhaseDualPathTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1]
        self.pipeline = build_gu_static_hypothesis_a(yaml.safe_load(
            (root/"configs/architectures/gu_behavioral_v1.yaml").read_text()))

    def test_general_recurrence_and_memory_difference(self):
        path = TwoPhasePath(0.03, 0.1, 0.02)
        start, output = path.advance(0.7, 0.5)
        self.assertAlmostEqual(start, 0.088)
        self.assertAlmostEqual(output, (1-0.03)*0.5+0.03*(1-0.1)*0.02+0.003*0.7)
        _, alternate = path.advance(-0.7, 0.5)
        self.assertAlmostEqual(output-alternate, 1.4*path.memory_factor)

    def test_tracking_reset_removes_prior_history(self):
        path = TwoPhasePath(0.03, 0.0, 0.01)
        self.assertEqual(path.advance(-10.0, 0.4), path.advance(10.0, 0.4))
        self.assertEqual(path.memory_factor, 0.0)

    def test_direct_hold_limit_matches_existing_platform(self):
        cfg = TwoPhaseDualPathConfig(TwoPhasePath(0.001, 1), TwoPhasePath(0.03, 1), TwoPhasePath(0.001, 1))
        old_cfg = DualPathSettlingConfig(0.001, 0.03, 0.001)
        old_state = state = DualPathSettlingState()
        for n in range(64):
            x = ((37*n) % 101-50)/71
            symbols = (1 if n % 2 else -1, 1 if n % 3 else -1)
            old = old_process(x, self.pipeline, old_cfg, old_state, sample_index=n, dither_symbols=symbols)
            new = process(x, self.pipeline, cfg, state, sample_index=n, dither_symbols=symbols)
            self.assertEqual(old.pipeline.backend.centered_code, new.pipeline.backend.centered_code)
            self.assertEqual(old.pipeline.stage2.quantizer.symbol, new.pipeline.stage2.quantizer.symbol)
            for a, b in zip(old.next_state.as_tuple(), new.next_state.as_tuple()):
                self.assertAlmostEqual(a, b, places=14)
            old_state, state = old.next_state, new.next_state

    def test_static_limit_and_independent_auxiliary_nonlinearity(self):
        cfg = TwoPhaseDualPathConfig(*(TwoPhasePath(0, 0) for _ in range(3)),
                                     auxiliary_truth=StaticCubicTruthConfig(1, 0.1))
        result = process(0.037, self.pipeline, cfg, DualPathSettlingState(0.8, -0.7, 0.6),
                         dither_symbols=(1, -1))
        self.assertEqual(result.next_state.as_tuple(), result.static_targets)
        self.assertNotEqual(result.static_targets[0], result.static_targets[1])
        expected = 4*result.pipeline.stage1.residue_preamp
        self.assertAlmostEqual(result.auxiliary_output, expected+0.1*expected**3)

    def test_invalid_phase_parameters_are_rejected(self):
        for parameters in ((1, 0), (-0.1, 0), (0.1, -0.1), (0.1, 1.1), (float("nan"), 0)):
            with self.assertRaises(ValueError):
                TwoPhasePath(*parameters)


if __name__ == "__main__":
    unittest.main()
