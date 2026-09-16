from __future__ import annotations

import math
import unittest
from pathlib import Path

import yaml

from adc_research.platform.pipeline import process
from adc_research.platform.presets import (
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
)
from adc_research.theory.static_spectrum import (
    continuous_tone_metrics,
    predict_continuous_tone,
    predict_finite_coherent_tone,
)
from adc_research.theory.static_transfer import (
    StaticTransferPrediction,
    TransferSegment,
    build_gu_theory_config,
    predict_static_transfer,
)


ROOT = Path(__file__).resolve().parents[1]


def read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def two_level_transfer() -> StaticTransferPrediction:
    common = {
        "stage1_symbol": 0,
        "stage2_symbol": 0,
        "backend_centered_code": 0,
        "unclipped_output_code": 0,
        "correctable": True,
        "stage1_pwl_slice": None,
        "stage2_pwl_slice": None,
    }
    return StaticTransferPrediction(
        input_range=(-1.0, 1.0),
        output_range=(0, 1),
        segments=(
            TransferSegment(
                input_lower=-1.0,
                input_upper=0.0,
                output_code=0,
                **common,
            ),
            TransferSegment(
                input_lower=0.0,
                input_upper=1.0,
                output_code=1,
                **common,
            ),
        ),
        code_widths=(1.0, 1.0),
        dnl_lsb=(0.0, 0.0),
        transition_inl_lsb=(0.0, 0.0, 0.0),
        missing_codes=(),
        negative_step_count=0,
        uncorrectable_input_width=0.0,
    )


class ContinuousStaticSpectrumTests(unittest.TestCase):
    def test_two_level_square_wave_coefficients_are_exact(self) -> None:
        result = predict_continuous_tone(
            two_level_transfer(),
            amplitude_peak=0.9,
            harmonic_orders=(0, 1, 2, 3),
        )

        self.assertEqual(len(result.phase_intervals), 2)
        self.assertAlmostEqual(
            sum(interval.width for interval in result.phase_intervals),
            2 * math.pi,
            places=13,
        )
        self.assertAlmostEqual(result.coefficient(0).real, 0.5, places=14)
        self.assertAlmostEqual(result.coefficient(0).imag, 0.0, places=14)
        self.assertAlmostEqual(result.coefficient(1).real, 0.0, places=14)
        self.assertAlmostEqual(result.coefficient(1).imag, -1 / math.pi, places=14)
        self.assertAlmostEqual(abs(result.coefficient(2)), 0.0, places=14)
        self.assertAlmostEqual(result.coefficient(3).imag, -1 / (3 * math.pi), places=14)
        self.assertAlmostEqual(result.total_ac_power, 0.25, places=14)
        self.assertEqual(result.correctable_phase_fraction, 1.0)
        metrics = continuous_tone_metrics(result, harmonic_orders=(2, 3))
        self.assertAlmostEqual(
            metrics.harmonic_power,
            2 / (9 * math.pi**2),
            places=14,
        )


class GuStaticSpectrumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.architecture = read_yaml(
            ROOT / "configs" / "architectures" / "gu_behavioral_v1.yaml"
        )
        cls.nonidealities = read_yaml(
            ROOT
            / "configs"
            / "nonidealities"
            / "gu_gate_d_static_v0_1.yaml"
        )

    def test_finite_ideal_prediction_matches_platform_code_for_code(self) -> None:
        transfer = predict_static_transfer(
            build_gu_theory_config(self.architecture)
        )
        predicted = predict_finite_coherent_tone(
            transfer,
            sample_rate_hz=3.0e9,
            sample_count=4096,
            fundamental_bin=37,
            amplitude_peak=0.999,
            full_scale_peak=2048.0,
        )
        platform = build_gu_static_hypothesis_a(self.architecture)
        observed = tuple(
            process(value, platform, sample_index=index).reconstruction.output_code
            for index, value in enumerate(predicted.input_values)
        )

        self.assertEqual(predicted.output_codes, observed)
        self.assertGreater(predicted.spectrum.metrics.sndr_db, 72.0)
        self.assertLess(predicted.spectrum.metrics.sndr_db, 75.0)

    def test_coprime_tone_bins_have_identical_memoryless_metrics(self) -> None:
        transfer = predict_static_transfer(
            build_gu_theory_config(self.architecture)
        )
        common = {
            "sample_rate_hz": 3.0e9,
            "sample_count": 4096,
            "amplitude_peak": 0.901,
            "full_scale_peak": 2048.0,
        }
        low = predict_finite_coherent_tone(
            transfer, fundamental_bin=37, **common
        ).spectrum.metrics
        high = predict_finite_coherent_tone(
            transfer, fundamental_bin=997, **common
        ).spectrum.metrics

        for name in ("sndr_db", "snr_db", "thd_db", "sfdr_dbc", "enob_bits"):
            # The phase sets are mathematically identical permutations.  The
            # small tolerance admits libm argument-reduction differences at
            # quantizer boundaries without hiding a spectral-model error.
            self.assertAlmostEqual(
                getattr(low, name), getattr(high, name), delta=1e-3
            )

    def test_combined_static_effects_match_platform_on_coherent_holdout(self) -> None:
        enabled = (
            "flash_threshold_offsets",
            "cdac_code_level_mismatch",
            "linear_interstage_gain",
            "static_pwl_truth",
        )
        transfer = predict_static_transfer(
            build_gu_theory_config(
                self.architecture,
                nonidealities=self.nonidealities,
                enabled_effects=enabled,
            )
        )
        predicted = predict_finite_coherent_tone(
            transfer,
            sample_rate_hz=3.0e9,
            sample_count=4096,
            fundamental_bin=211,
            amplitude_peak=0.873,
            full_scale_peak=2048.0,
        )
        platform = build_gu_static_hypothesis_a(self.architecture)
        applied = build_gu_gate_d_nonidealities(
            self.nonidealities,
            enabled_effects=enabled,
        )
        observed = tuple(
            process(
                value,
                platform,
                sample_index=index,
                nonidealities=applied,
            ).reconstruction.output_code
            for index, value in enumerate(predicted.input_values)
        )

        self.assertEqual(predicted.output_codes, observed)


if __name__ == "__main__":
    unittest.main()
