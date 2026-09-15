import math
import unittest
from pathlib import Path

import numpy as np
import yaml

from adc_research.metrics.spectral import (
    analyze_coherent_tone,
    folded_bin,
)
from adc_research.metrics.static import code_density_metrics
from adc_research.platform.pipeline import process
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stimulus import (
    CoherentSineConfig,
    UniformRampConfig,
    coherent_sine,
    uniform_ramp,
)


ROOT = Path(__file__).resolve().parents[1]


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class CodeDensityMetricTests(unittest.TestCase):
    def test_uniform_histogram_has_zero_dnl_and_inl(self) -> None:
        result = code_density_metrics(
            [code for code in range(8) for _ in range(4)],
            minimum_code=0,
            maximum_code=7,
        )
        self.assertEqual(result.histogram, (4,) * 8)
        self.assertEqual(result.missing_codes, ())
        self.assertTrue(all(value == 0.0 for value in result.dnl_lsb))
        self.assertTrue(all(value == 0.0 for value in result.transition_inl_lsb))

    def test_missing_code_and_double_width_code_are_visible(self) -> None:
        result = code_density_metrics(
            [0, 1, 3, 3],
            minimum_code=0,
            maximum_code=3,
        )
        self.assertEqual(result.dnl_lsb, (0.0, 0.0, -1.0, 1.0))
        self.assertEqual(result.transition_inl_lsb, (0.0, 0.0, 0.0, -1.0, 0.0))
        self.assertEqual(result.missing_codes, (2,))


class SpectralMetricTests(unittest.TestCase):
    def test_harmonic_alias_bin_is_folded_into_first_nyquist_zone(self) -> None:
        self.assertEqual(folded_bin(2, 1800, 4096), 496)

    def test_known_second_harmonic_has_expected_thd_and_sfdr(self) -> None:
        sample_count = 4096
        tone_bin = 37
        index = np.arange(sample_count)
        values = np.sin(2 * np.pi * tone_bin * index / sample_count)
        values += 0.01 * np.sin(4 * np.pi * tone_bin * index / sample_count)
        result = analyze_coherent_tone(
            values,
            sample_rate_hz=1.0,
            fundamental_bin=tone_bin,
            harmonic_orders=(2,),
        )
        self.assertAlmostEqual(result.metrics.thd_db, -40.0, places=9)
        self.assertAlmostEqual(result.metrics.sfdr_dbc, 40.0, places=9)
        self.assertAlmostEqual(result.metrics.sndr_db, 40.0, places=9)
        self.assertTrue(math.isinf(result.metrics.snr_db) or result.metrics.snr_db > 250)
        self.assertEqual(result.metrics.worst_spur_bin, 2 * tone_bin)


class PlatformMetricIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        architecture = read_yaml(
            ROOT / "configs" / "architectures" / "gu_behavioral_v1.yaml"
        )
        cls.pipeline = build_gu_static_hypothesis_a(architecture)

    def test_ideal_pipeline_uniform_ramp_has_zero_dnl_and_inl(self) -> None:
        stimulus = uniform_ramp(
            UniformRampConfig(code_count=4096, samples_per_code=2)
        )
        codes = [
            process(value, self.pipeline, sample_index=index).reconstruction.output_code
            for index, value in enumerate(stimulus)
        ]
        result = code_density_metrics(codes, minimum_code=0, maximum_code=4095)
        self.assertEqual(result.missing_codes, ())
        self.assertEqual(result.minimum_dnl_lsb, 0.0)
        self.assertEqual(result.maximum_dnl_lsb, 0.0)
        self.assertEqual(result.minimum_inl_lsb, 0.0)
        self.assertEqual(result.maximum_inl_lsb, 0.0)

    def test_ideal_pipeline_coherent_sine_is_near_twelve_bit_limit(self) -> None:
        tone = CoherentSineConfig(
            sample_rate_hz=3.0e9,
            sample_count=16384,
            tone_bin=997,
            amplitude_peak=0.999,
        )
        stimulus = coherent_sine(tone)
        codes = [
            process(value, self.pipeline, sample_index=index).reconstruction.output_code
            for index, value in enumerate(stimulus)
        ]
        result = analyze_coherent_tone(
            codes,
            sample_rate_hz=tone.sample_rate_hz,
            fundamental_bin=tone.tone_bin,
            full_scale_peak=2048.0,
        )
        self.assertGreater(result.metrics.sndr_db, 72.0)
        self.assertLess(result.metrics.sndr_db, 75.0)
        self.assertGreater(result.metrics.enob_bits, 11.6)
        self.assertLess(result.metrics.enob_bits, 12.2)
        self.assertLess(abs(result.metrics.fundamental_dbfs), 0.02)


if __name__ == "__main__":
    unittest.main()
