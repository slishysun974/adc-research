from __future__ import annotations

import math
import unittest
from pathlib import Path

import yaml

from adc_research.platform.backend_sar import SarConfig, convert as convert_sar
from adc_research.platform.cdac import CdacConfig
from adc_research.platform.pipeline import StaticPipelineConfig, process
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.quantizer import QuantizerConfig
from adc_research.platform.reconstruct import ReconstructionConfig
from adc_research.platform.stage import StaticStageConfig


class PlatformGateCTests(unittest.TestCase):
    @staticmethod
    def make_config(
        *,
        dither_preamp_amplitude: float = 1 / 32,
        dither_code_copies: tuple[int, int] = (64, 16),
        auxiliary_gain_ratios: tuple[float, float] = (1.0, 1.0),
    ) -> StaticPipelineConfig:
        symbols = tuple(range(-4, 5))
        thresholds = tuple((symbol + 0.5) / 4 for symbol in range(-4, 4))
        stage = StaticStageConfig(
            quantizer=QuantizerConfig(thresholds, symbols),
            cdac=CdacConfig(
                nominal_levels={symbol: symbol / 4 for symbol in symbols},
                dither_levels={
                    -1: -dither_preamp_amplitude,
                    1: dither_preamp_amplitude,
                },
            ),
            nominal_interstage_gain=4,
        )
        reconstruction = ReconstructionConfig(
            front_stage_weights=(512, 128),
            backend_weight=1,
            output_offset=2048,
            output_range=(0, 4095),
            dither_code_copies=(
                {-1: -dither_code_copies[0], 1: dither_code_copies[0]},
                {-1: -dither_code_copies[1], 1: dither_code_copies[1]},
            ),
        )
        return StaticPipelineConfig(
            stage1=stage,
            stage2=stage,
            backend=SarConfig(bits=8, channels=4),
            reconstruction=reconstruction,
            auxiliary_gain_ratios=auxiliary_gain_ratios,
        )

    def test_backend_sar_has_midrise_endpoint_and_ti_channel_semantics(self) -> None:
        config = SarConfig(bits=8, channels=4)
        cases = (
            (-1.0, 0, -128, False, False),
            (0.0, 128, 0, False, False),
            (1.0 - 1e-12, 255, 127, False, False),
            (-1.01, 0, -128, True, False),
            (1.0, 255, 127, False, True),
        )
        for sample_index, (value, raw, centered, low, high) in enumerate(cases):
            result = convert_sar(value, config, sample_index=sample_index)
            self.assertEqual(result.raw_code, raw)
            self.assertEqual(result.centered_code, centered)
            self.assertEqual(result.channel_index, sample_index % 4)
            self.assertEqual(result.overload_low, low)
            self.assertEqual(result.overload_high, high)

    def test_named_hypothesis_yaml_resolves_to_gate_c_configuration(self) -> None:
        root = Path(__file__).resolve().parents[1]
        path = root / "configs" / "architectures" / "gu_static_hypothesis_a_v0_1.yaml"
        assumption = yaml.safe_load(path.read_text(encoding="utf-8"))
        config = build_gu_static_hypothesis_a(assumption)
        self.assertEqual(config.backend.bits, 8)
        self.assertEqual(config.backend.channels, 4)
        self.assertEqual(config.reconstruction.front_stage_weights, (512, 128))
        self.assertEqual(
            config.reconstruction.dither_code_copies,
            ({-1: -64, 1: 64}, {-1: -16, 1: 16}),
        )

    def test_complete_trace_obeys_both_residue_equations(self) -> None:
        config = self.make_config()
        value = 0.314159
        result = process(value, config, sample_index=6, dither_symbols=(1, -1))

        q1, q2 = result.reconstruction.stage_symbols
        self.assertAlmostEqual(
            result.stage1.residue,
            4 * (value - q1 / 4 + 1 / 32),
        )
        self.assertAlmostEqual(
            result.stage2.residue,
            4 * (result.stage1.residue - q2 / 4 - 1 / 32),
        )
        self.assertEqual(result.backend.channel_index, 2)
        self.assertEqual(result.reconstruction.digital_dither_copy, 64 - 16)
        self.assertTrue(result.reconstruction.correctable)

    def test_exhaustive_code_centers_form_monotone_no_missing_code_transfer(self) -> None:
        config = self.make_config()
        actual = []
        for expected in range(4096):
            value = -1 + (expected + 0.5) / 2048
            result = process(value, config, sample_index=expected)
            actual.append(result.reconstruction.output_code)
            self.assertTrue(result.reconstruction.correctable)

        self.assertEqual(actual, list(range(4096)))

    def test_two_dithers_and_auxiliary_gain_mismatch_reconstruct_exactly(self) -> None:
        for ratio in (0.97, 1.03):
            config = self.make_config(auxiliary_gain_ratios=(1.0, ratio))
            for expected in range(4096):
                value = -1 + (expected + 0.5) / 2048
                for dither_symbols in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
                    result = process(
                        value,
                        config,
                        sample_index=expected,
                        dither_symbols=dither_symbols,
                    )
                    self.assertEqual(result.reconstruction.output_code, expected)
                    self.assertTrue(result.reconstruction.correctable)

    def test_auxiliary_coordinate_overrange_does_not_mean_signal_loss(self) -> None:
        # This is a generic platform-semantics test, not a claim that Gu's
        # reported inter-stage mismatch applies to the stage-1 input flash.
        config = self.make_config(auxiliary_gain_ratios=(1.03, 1.03))
        result = process(
            -1 + 0.5 / 2048,
            config,
            dither_symbols=(-1, -1),
        )
        self.assertTrue(result.stage1.quantizer.overload_low)
        self.assertFalse(result.stage1.main_input_overload_low)
        self.assertTrue(result.reconstruction.correctable)

    def test_alternative_peak_to_peak_dither_interpretation_is_configurable(self) -> None:
        config = self.make_config(
            dither_preamp_amplitude=1 / 64,
            dither_code_copies=(32, 8),
        )
        for expected in range(4096):
            value = -1 + (expected + 0.5) / 2048
            result = process(value, config, dither_symbols=(1, -1))
            self.assertEqual(result.reconstruction.output_code, expected)

    def test_out_of_range_input_is_clipped_but_not_marked_correctable(self) -> None:
        config = self.make_config()
        low = process(-1.01, config)
        high = process(1.01, config)
        self.assertEqual(low.reconstruction.output_code, 0)
        self.assertEqual(high.reconstruction.output_code, 4095)
        self.assertFalse(low.reconstruction.correctable)
        self.assertFalse(high.reconstruction.correctable)
        self.assertTrue(low.stage1.quantizer.overload_low)
        self.assertTrue(high.stage1.quantizer.overload_high)

    def test_repeated_conversion_is_bit_reproducible(self) -> None:
        config = self.make_config(auxiliary_gain_ratios=(1.03, 0.97))
        first = process(0.271828, config, sample_index=17, dither_symbols=(-1, 1))
        second = process(0.271828, config, sample_index=17, dither_symbols=(-1, 1))
        self.assertEqual(first, second)

    def test_output_code_matches_independent_uniform_quantizer_away_from_centers(self) -> None:
        config = self.make_config()
        for index in range(1, 8192, 17):
            value = -1 + index / 4096
            expected = min(max(math.floor(2048 * (value + 1)), 0), 4095)
            result = process(value, config)
            self.assertEqual(result.reconstruction.output_code, expected)


if __name__ == "__main__":
    unittest.main()
