from __future__ import annotations

import math
import unittest

from adc_research.theory.static_sensitivity import moving_step_fourier_derivatives


class StaticSensitivityTests(unittest.TestCase):
    def test_two_level_threshold_matches_closed_form(self) -> None:
        for threshold in (0.2, 0.5):
            derivatives, rising, falling = moving_step_fourier_derivatives(
                input_boundary=threshold,
                input_boundary_derivative=1.0,
                code_jump_with_increasing_input=1.0,
                amplitude_peak=1.0,
                orders=(0, 1),
            )
            self.assertAlmostEqual(
                derivatives[0].real,
                -1 / (math.pi * math.sqrt(1 - threshold**2)),
                places=12,
            )
            self.assertAlmostEqual(derivatives[0].imag, 0.0, places=12)
            self.assertAlmostEqual(
                derivatives[1].imag,
                threshold / (math.pi * math.sqrt(1 - threshold**2)),
                places=12,
            )
            self.assertAlmostEqual(derivatives[1].real, 0.0, places=12)
            self.assertAlmostEqual(math.sin(rising), threshold, places=12)
            self.assertAlmostEqual(math.sin(falling), threshold, places=12)

    def test_sine_tangency_has_no_ordinary_boundary_derivative(self) -> None:
        with self.assertRaises(ValueError):
            moving_step_fourier_derivatives(
                input_boundary=1.0,
                input_boundary_derivative=1.0,
                code_jump_with_increasing_input=1.0,
                amplitude_peak=1.0,
            )


if __name__ == "__main__":
    unittest.main()
