"""Conditional full-chain envelopes versus an independent sample-wise platform."""

from __future__ import annotations

import unittest
from dataclasses import replace
from math import pi, sin
from pathlib import Path

import numpy as np
import yaml

from adc_research.calibration.gu_baseline import build_gu_two_stage_baseline
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.calibration.two_stage import correct_two_stage_observed
from adc_research.evaluation.full_chain_code_envelope import bound_static_gu_codes
from adc_research.evaluation.observations import digital_sample
from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.platform.dual_path_settling import (
    DualPathSettlingConfig,
    DualPathSettlingState,
    process as process_dual_path,
)
from adc_research.platform.backend_sar import convert as convert_sar
from adc_research.platform.cdac import CdacMismatch
from adc_research.platform.pipeline import StaticPipelineNonidealities, process
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stage import StaticStageNonidealities
from adc_research.theory.static_observation_reachability import (
    ClosedInterval,
    StaticCandidateArchitecture,
    propagate_static_observations,
)
from adc_research.theory.finite_record_bounds import bound_finite_coherent_tone


ROOT = Path(__file__).resolve().parents[1]


def gain_four(interval: ClosedInterval) -> ClosedInterval:
    return ClosedInterval(4 * interval.lower, 4 * interval.upper)


class StaticObservationReachabilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        architecture = yaml.safe_load(
            (ROOT / "configs/architectures/gu_behavioral_v1.yaml").read_text(
                encoding="utf-8"
            )
        )
        front = architecture["front_stage_template"]
        bounds = tuple(ClosedInterval(value, value) for value in front["thresholds"])
        cls.geometry = StaticCandidateArchitecture(
            stage1_thresholds=bounds,
            stage2_thresholds=bounds,
            stage1_symbols=tuple(front["output_symbols"]),
            stage2_symbols=tuple(front["output_symbols"]),
            stage1_dac_levels=tuple(front["dac_levels"]),
            stage2_dac_levels=tuple(front["dac_levels"]),
            front_nominal_range=(-1.0, 1.0),
            backend_range=(-1.0, 1.0),
            backend_bits=8,
        )
        cls.platform = build_gu_static_hypothesis_a(architecture)
        cls.calibration = build_gu_two_stage_baseline(
            cls.platform, architecture["pwl_implications"]
        )

    def _bound(self, input_voltage, auxiliary=gain_four, geometry=None,
               stage2_transfer=gain_four):
        observations = propagate_static_observations(
            input_voltage,
            ClosedInterval(0.0, 0.0),
            ClosedInterval(0.0, 0.0),
            geometry or self.geometry,
            gain_four,
            auxiliary,
            stage2_transfer,
        )
        codes = bound_static_gu_codes(
            observations, self.calibration,
            stage1_dither_symbol=None,
            stage2_dither_symbol=None,
        )
        return observations, codes

    def _actual_code(self, raw) -> int:
        corrected = correct_two_stage_observed(digital_sample(raw), self.calibration)
        return min(max(round(corrected.unclipped_output_code), 0), 4095)

    def test_independent_auxiliary_threshold_crossing_retains_both_branches(self) -> None:
        observations, codes = self._bound(
            ClosedInterval(-0.2, -0.2),
            auxiliary=lambda _: ClosedInterval(0.1, 0.15),
            stage2_transfer=lambda interval: ClosedInterval(
                4.1 * interval.lower, 4.1 * interval.upper
            ),
        )
        self.assertEqual({item.stage1_symbol for item in observations.outcomes}, {-1})
        self.assertEqual({item.stage2_symbol for item in observations.outcomes}, {0, 1})
        self.assertEqual(codes.observation_count, 2)
        self.assertEqual((codes.lower_output_code, codes.upper_output_code), (1637, 1640))
        settling = DualPathSettlingConfig(0.0, 0.0, 0.0)
        nonidealities = StaticPipelineNonidealities(
            stage2=StaticStageNonidealities(actual_interstage_gain=4.1)
        )
        for auxiliary_ratio in (0.5, 0.75):
            platform = replace(
                self.platform, auxiliary_gain_ratios=(1.0, auxiliary_ratio)
            )
            raw = process_dual_path(
                -0.2, platform, settling, DualPathSettlingState(),
                nonidealities=nonidealities,
            ).pipeline
            self.assertIn(
                (raw.stage1.quantizer.symbol, raw.stage2.quantizer.symbol,
                 raw.backend.centered_code),
                {(item.stage1_symbol, item.stage2_symbol,
                  item.backend_centered_code) for item in observations.outcomes},
            )
            self.assertLessEqual(codes.lower_output_code, self._actual_code(raw))
            self.assertLessEqual(self._actual_code(raw), codes.upper_output_code)
        self.assertFalse(codes.physical_overload_possible)

    def test_first_stage_decision_boundary_is_propagated(self) -> None:
        observations, codes = self._bound(ClosedInterval(-0.126, -0.124))
        self.assertEqual({item.stage1_symbol for item in observations.outcomes}, {-1, 0})
        for value in np.linspace(-0.126, -0.124, 101):
            raw = process(float(value), self.platform)
            outcome = (
                raw.stage1.quantizer.symbol,
                raw.stage2.quantizer.symbol,
                raw.backend.centered_code,
            )
            self.assertIn(outcome, {
                (item.stage1_symbol, item.stage2_symbol,
                 item.backend_centered_code) for item in observations.outcomes
            })
            self.assertLessEqual(codes.lower_output_code, self._actual_code(raw))
            self.assertLessEqual(self._actual_code(raw), codes.upper_output_code)

    def test_uncertain_flash_threshold_covers_both_actual_offsets(self) -> None:
        thresholds = list(self.geometry.stage1_thresholds)
        thresholds[3] = ClosedInterval(-0.126, -0.124)
        geometry = replace(self.geometry, stage1_thresholds=tuple(thresholds))
        observations, codes = self._bound(
            ClosedInterval(-0.125, -0.125), geometry=geometry
        )
        self.assertEqual({item.stage1_symbol for item in observations.outcomes}, {-1, 0})
        for offset in (-0.001, 0.001):
            offsets = (0.0, 0.0, 0.0, offset, 0.0, 0.0, 0.0, 0.0)
            raw = process(
                -0.125,
                self.platform,
                nonidealities=StaticPipelineNonidealities(
                    stage1=StaticStageNonidealities(threshold_offsets=offsets)
                ),
            )
            self.assertLessEqual(codes.lower_output_code, self._actual_code(raw))
            self.assertLessEqual(self._actual_code(raw), codes.upper_output_code)

    def test_cdac_levels_and_sar_threshold_shift_are_both_propagated(self) -> None:
        dac_radius = 0.001
        sar_radius = 0.001
        step = (self.geometry.backend_range[1] - self.geometry.backend_range[0]) / 256
        sar_thresholds = tuple(
            ClosedInterval(-1 + index * step - sar_radius,
                           -1 + index * step + sar_radius)
            for index in range(1, 256)
        )
        geometry = replace(
            self.geometry,
            stage1_dac_levels=tuple(
                ClosedInterval(level.lower - dac_radius, level.upper + dac_radius)
                for level in self.geometry.stage1_dac_levels
            ),
            stage2_dac_levels=tuple(
                ClosedInterval(level.lower - dac_radius, level.upper + dac_radius)
                for level in self.geometry.stage2_dac_levels
            ),
            backend_thresholds=sar_thresholds,
        )
        observations, codes = self._bound(ClosedInterval(-0.2, -0.2), geometry=geometry)
        possible = {
            (item.stage1_symbol, item.stage2_symbol, item.backend_centered_code)
            for item in observations.outcomes
        }
        self.assertGreater(len(possible), 1)
        self.assertLess(codes.lower_output_code, codes.upper_output_code)
        for cdac1_error in (-dac_radius, dac_radius):
            for cdac2_error in (-dac_radius, dac_radius):
                nonidealities = StaticPipelineNonidealities(
                    stage1=StaticStageNonidealities(cdac_mismatch=CdacMismatch(
                        {symbol: cdac1_error for symbol in self.geometry.stage1_symbols}
                    )),
                    stage2=StaticStageNonidealities(cdac_mismatch=CdacMismatch(
                        {symbol: cdac2_error for symbol in self.geometry.stage2_symbols}
                    )),
                )
                raw = process(-0.2, self.platform, nonidealities=nonidealities)
                for sar_shift in (-sar_radius, sar_radius):
                    # Shifting every SAR threshold by sar_shift is exactly
                    # the nominal uniform quantizer at v-sar_shift.
                    shifted = convert_sar(raw.stage2.residue - sar_shift,
                                          self.platform.backend)
                    triple = (
                        raw.stage1.quantizer.symbol,
                        raw.stage2.quantizer.symbol,
                        shifted.centered_code,
                    )
                    self.assertIn(triple, possible)
                    observed = DigitalCalibrationSample(*triple, None, None)
                    corrected = correct_two_stage_observed(observed, self.calibration)
                    code = min(max(round(corrected.unclipped_output_code), 0), 4095)
                    self.assertLessEqual(codes.lower_output_code, code)
                    self.assertLessEqual(code, codes.upper_output_code)

    def test_uncertain_sar_threshold_at_equality_retains_both_codes(self) -> None:
        step = 2 / 256
        thresholds = [
            ClosedInterval(-1 + index * step, -1 + index * step)
            for index in range(1, 256)
        ]
        thresholds[127] = ClosedInterval(-0.001, 0.001)
        geometry = replace(self.geometry, backend_thresholds=tuple(thresholds))
        observations, codes = self._bound(ClosedInterval(0.0, 0.0), geometry=geometry)
        self.assertEqual(
            {item.backend_centered_code for item in observations.outcomes}, {-1, 0}
        )
        self.assertEqual((codes.lower_output_code, codes.upper_output_code),
                         (2047, 2048))
        for shift in (-0.001, 0.001):
            actual = convert_sar(-shift, self.platform.backend).centered_code
            self.assertIn(actual, {-1, 0})

        thresholds[127] = ClosedInterval(-0.01, 0.01)
        with self.assertRaisesRegex(ValueError, "backend threshold intervals"):
            replace(self.geometry, backend_thresholds=tuple(thresholds))

    def test_full_record_bounds_cover_two_independent_auxiliary_curves(self) -> None:
        def auxiliary_range(interval: ClosedInterval) -> ClosedInterval:
            corners = (
                0.98 * 4 * interval.lower, 1.02 * 4 * interval.lower,
                0.98 * 4 * interval.upper, 1.02 * 4 * interval.upper,
            )
            return ClosedInterval(min(corners), max(corners))

        stage2_transfer = lambda interval: ClosedInterval(
            4.1 * interval.lower, 4.1 * interval.upper
        )
        settling = DualPathSettlingConfig(0.0, 0.0, 0.0)
        nonidealities = StaticPipelineNonidealities(
            stage2=StaticStageNonidealities(actual_interstage_gain=4.1)
        )
        records = {ratio: [] for ratio in (0.98, 1.02)}
        lower_codes = []
        upper_codes = []
        for index in range(128):
            value = 0.6 * sin(2 * pi * 3 * index / 128)
            _, envelope = self._bound(
                ClosedInterval(value, value), auxiliary=auxiliary_range,
                stage2_transfer=stage2_transfer,
            )
            self.assertFalse(envelope.physical_overload_possible)
            lower_codes.append(envelope.lower_output_code)
            upper_codes.append(envelope.upper_output_code)
            for ratio in records:
                platform = replace(
                    self.platform, auxiliary_gain_ratios=(1.0, ratio)
                )
                raw = process_dual_path(
                    value, platform, settling, DualPathSettlingState(),
                    sample_index=index, nonidealities=nonidealities,
                ).pipeline
                code = self._actual_code(raw)
                self.assertLessEqual(envelope.lower_output_code, code)
                self.assertLessEqual(code, envelope.upper_output_code)
                records[ratio].append(code)

        bound = bound_finite_coherent_tone(
            records[0.98], lower_codes, upper_codes, fundamental_bin=3
        )
        for codes in records.values():
            scored = analyze_coherent_tone(
                codes, sample_rate_hz=3e9, fundamental_bin=3
            ).metrics
            self.assertLessEqual(bound.sndr_db.lower, scored.sndr_db)
            self.assertLessEqual(scored.sndr_db, bound.sndr_db.upper)
            self.assertLessEqual(bound.sfdr_dbc.lower, scored.sfdr_dbc)
            self.assertLessEqual(scored.sfdr_dbc, bound.sfdr_dbc.upper)

    def test_invalid_envelopes_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ClosedInterval(1.0, 0.0)
        thresholds = list(self.geometry.stage1_thresholds)
        thresholds[3] = ClosedInterval(-0.5, 0.5)
        with self.assertRaises(ValueError):
            replace(self.geometry, stage1_thresholds=tuple(thresholds))
        with self.assertRaises(TypeError):
            self._bound(ClosedInterval(0.0, 0.0), auxiliary=lambda _: (0.0, 0.0))

    def test_auxiliary_outside_nominal_domain_is_separate_from_main_overload(self) -> None:
        observations = propagate_static_observations(
            ClosedInterval(0.0, 0.0),
            ClosedInterval(0.0, 0.0),
            ClosedInterval(0.0, 0.0),
            self.geometry,
            gain_four,
            lambda _: ClosedInterval(1.1, 1.1),
            lambda _: ClosedInterval(-0.01, -0.01),
        )
        self.assertTrue(observations.stage2_aux_outside_nominal_range_possible)
        self.assertFalse(observations.stage1_main_overload_possible)
        self.assertFalse(observations.backend_overload_possible)
        codes = bound_static_gu_codes(
            observations, self.calibration,
            stage1_dither_symbol=None,
            stage2_dither_symbol=None,
        )
        self.assertFalse(codes.physical_overload_possible)

        outside_digital_domain = propagate_static_observations(
            ClosedInterval(0.0, 0.0),
            ClosedInterval(0.0, 0.0),
            ClosedInterval(0.0, 0.0),
            self.geometry,
            gain_four,
            lambda _: ClosedInterval(1.1, 1.1),
            lambda _: ClosedInterval(0.0, 0.0),
        )
        with self.assertRaisesRegex(ValueError, "outside candidate Gu correction domain"):
            bound_static_gu_codes(
                outside_digital_domain, self.calibration,
                stage1_dither_symbol=None, stage2_dither_symbol=None,
            )


if __name__ == "__main__":
    unittest.main()
