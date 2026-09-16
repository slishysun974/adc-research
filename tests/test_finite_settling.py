from __future__ import annotations

import math
import unittest
from pathlib import Path

import numpy as np
import yaml

from adc_research.platform.finite_settling import (
    FiniteSettlingConfig,
    SettlingState,
    process,
)
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stimulus import (
    CoherentSineConfig,
    coherent_sine,
)
from adc_research.theory.finite_settling import (
    PeriodicSettlingConfig,
    equivalent_settling_bits,
    first_order_residual_factor,
    periodic_first_order_response,
    predict_periodic_settling,
)
from adc_research.theory.static_spectrum import predict_finite_coherent_tone
from adc_research.theory.static_transfer import (
    build_gu_theory_config,
    predict_static_transfer,
)


ROOT = Path(__file__).resolve().parents[1]


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class FirstOrderSettlingTheoryTests(unittest.TestCase):
    def test_paper_anchor_is_consistent_with_ten_bit_settling(self) -> None:
        residual = first_order_residual_factor(11.0e9, 100.0e-12)
        self.assertAlmostEqual(residual, math.exp(-2.2 * math.pi), places=15)
        self.assertAlmostEqual(equivalent_settling_bits(residual), 9.9712, places=4)
        self.assertLess(abs(residual / (2.0**-10) - 1.0), 0.03)

    def test_periodic_solution_closes_cycle_and_has_static_limit(self) -> None:
        targets = (0.2, -0.4, 0.8, -0.1)
        self.assertEqual(periodic_first_order_response(targets, 0.0), targets)
        rho = 0.25
        response = periodic_first_order_response(targets, rho)
        previous = response[-1]
        replay = []
        for target in targets:
            previous = (1.0 - rho) * target + rho * previous
            replay.append(previous)
        for predicted, observed in zip(response, replay, strict=True):
            self.assertAlmostEqual(predicted, observed, places=15)

    def test_periodic_solution_has_expected_one_pole_frequency_response(self) -> None:
        sample_count = 256
        tone_bin = 19
        rho = 0.2
        indices = np.arange(sample_count)
        targets = np.sin(2 * math.pi * tone_bin * indices / sample_count)
        response = periodic_first_order_response(targets, rho)
        input_spectrum = np.fft.rfft(targets) / sample_count
        output_spectrum = np.fft.rfft(response) / sample_count
        omega = 2 * math.pi * tone_bin / sample_count
        expected = (1 - rho) / (1 - rho * np.exp(-1j * omega))
        observed = output_spectrum[tone_bin] / input_spectrum[tone_bin]
        self.assertAlmostEqual(observed.real, expected.real, places=14)
        self.assertAlmostEqual(observed.imag, expected.imag, places=14)


class GuFiniteSettlingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.architecture = read_yaml(
            ROOT / "configs" / "architectures" / "gu_behavioral_v1.yaml"
        )
        cls.theory_config = build_gu_theory_config(cls.architecture)
        cls.platform_config = build_gu_static_hypothesis_a(cls.architecture)
        cls.values = tuple(
            float(value)
            for value in coherent_sine(
                CoherentSineConfig(
                    sample_rate_hz=3.0e9,
                    sample_count=4096,
                    tone_bin=211,
                    amplitude_peak=0.901,
                    phase_radians=0.2718281828459045,
                )
            )
        )

    def test_zero_residual_factor_recovers_static_spectrum_codes(self) -> None:
        dynamic = predict_periodic_settling(
            self.values,
            self.theory_config,
            PeriodicSettlingConfig((0.0, 0.0)),
        )
        static_transfer = predict_static_transfer(self.theory_config)
        static = predict_finite_coherent_tone(
            static_transfer,
            sample_rate_hz=3.0e9,
            sample_count=4096,
            fundamental_bin=211,
            amplitude_peak=0.901,
            phase_radians=0.2718281828459045,
        )
        self.assertEqual(dynamic.output_codes, static.output_codes)

    def test_periodic_theory_matches_warmed_sample_platform(self) -> None:
        rho = first_order_residual_factor(11.0e9, 100.0e-12)
        theory = predict_periodic_settling(
            self.values,
            self.theory_config,
            PeriodicSettlingConfig((rho, rho)),
        )
        state = SettlingState(0.73, -0.41)
        platform_settling = FiniteSettlingConfig((rho, rho))
        for sample_index, value in enumerate(self.values):
            state = process(
                value,
                self.platform_config,
                platform_settling,
                state,
                sample_index=sample_index,
            ).next_state

        observed_codes = []
        observed_stage1 = []
        observed_stage2 = []
        for sample_index, value in enumerate(self.values):
            result = process(
                value,
                self.platform_config,
                platform_settling,
                state,
                sample_index=sample_index,
            )
            state = result.next_state
            observed_codes.append(result.pipeline.reconstruction.output_code)
            observed_stage1.append(result.pipeline.stage1.residue)
            observed_stage2.append(result.pipeline.stage2.residue)

        self.assertEqual(theory.output_codes, tuple(observed_codes))
        self.assertLess(
            max(abs(a - b) for a, b in zip(theory.stage1_residues, observed_stage1)),
            1e-14,
        )
        self.assertLess(
            max(abs(a - b) for a, b in zip(theory.stage2_residues, observed_stage2)),
            1e-14,
        )


if __name__ == "__main__":
    unittest.main()
