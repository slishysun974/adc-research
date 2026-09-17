from __future__ import annotations

import math
import unittest
from pathlib import Path

import yaml

from adc_research.platform.dual_path_settling import (
    DualPathSettlingConfig,
    DualPathSettlingState,
    process as process_dual_path,
)
from adc_research.platform.finite_settling import (
    FiniteSettlingConfig,
    SettlingState,
    process as process_reduced,
)
from adc_research.platform.pipeline import process as process_static
from adc_research.platform.presets import (
    build_gu_gate_d_nonidealities,
    build_gu_static_hypothesis_a,
)
from adc_research.theory.finite_settling import (
    DualPathPeriodicSettlingConfig,
    first_order_residual_factor,
    predict_periodic_dual_path_settling,
    predict_periodic_settling,
    PeriodicSettlingConfig,
)
from adc_research.theory.static_transfer import (
    build_gu_theory_config,
    predict_static_transfer,
)


ROOT = Path(__file__).resolve().parents[1]


class DualPathSettlingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.architecture = yaml.safe_load(
            (ROOT / "configs/architectures/gu_behavioral_v1.yaml").read_text(
                encoding="utf-8"
            )
        )
        cls.nonidealities = yaml.safe_load(
            (ROOT / "configs/nonidealities/gu_gate_d_static_v0_1.yaml").read_text(
                encoding="utf-8"
            )
        )

    def test_distinct_paper_anchor_factors_split_flash_decision(self) -> None:
        main = first_order_residual_factor(11e9, 100e-12)
        auxiliary = first_order_residual_factor(7e9, 80e-12)
        platform = build_gu_static_hypothesis_a(self.architecture)
        dual = process_dual_path(
            0.03175,
            platform,
            DualPathSettlingConfig(main, auxiliary, main),
            DualPathSettlingState(),
        )
        reduced = process_reduced(
            0.03175,
            platform,
            FiniteSettlingConfig((main, main)),
            SettlingState(),
        )

        self.assertAlmostEqual(dual.stage1_main_target, 0.127)
        self.assertAlmostEqual(dual.pipeline.stage1.residue, 0.12687347517581357)
        self.assertAlmostEqual(dual.stage1_auxiliary_output, 0.12323554417942344)
        self.assertEqual(dual.pipeline.stage2.quantizer.symbol, 0)
        self.assertEqual(reduced.pipeline.stage2.quantizer.symbol, 1)
        self.assertEqual(dual.pipeline.stage2.main_input, reduced.pipeline.stage2.main_input)

    def test_matched_zero_memory_limit_recovers_frozen_static_chain(self) -> None:
        platform = build_gu_static_hypothesis_a(self.architecture)
        settling = DualPathSettlingConfig(0.0, 0.0, 0.0)
        state = DualPathSettlingState(0.73, -0.41, 0.22)
        for code in range(0, 4096, 11):
            value = -1 + (code + 0.5) / 2048
            dual = process_dual_path(value, platform, settling, state)
            frozen = process_static(value, platform)
            self.assertEqual(
                dual.pipeline.reconstruction.output_code,
                frozen.reconstruction.output_code,
            )
            self.assertEqual(
                dual.pipeline.stage2.quantizer.symbol,
                frozen.stage2.quantizer.symbol,
            )
            self.assertEqual(dual.stage1_auxiliary_output, frozen.stage1.residue)

    def test_cyclic_theory_matches_hidden_initial_state_platform(self) -> None:
        ratio = 1.03
        platform = build_gu_static_hypothesis_a(
            self.architecture, stage2_flash_auxiliary_gain_ratio=ratio
        )
        theory_config = build_gu_theory_config(
            self.architecture, stage2_flash_auxiliary_gain_ratio=ratio
        )
        main = first_order_residual_factor(11e9, 100e-12)
        auxiliary = first_order_residual_factor(7e9, 80e-12)
        platform_settling = DualPathSettlingConfig(main, auxiliary, main)
        theory_settling = DualPathPeriodicSettlingConfig(main, auxiliary, main)
        count = 2048
        values = tuple(
            0.901 * math.sin(2 * math.pi * 211 * n / count + 0.271828)
            for n in range(count)
        )
        predicted = predict_periodic_dual_path_settling(
            values, theory_config, theory_settling
        )

        state = DualPathSettlingState(0.73, -0.41, 0.22)
        for index, value in enumerate(values):
            state = process_dual_path(
                value,
                platform,
                platform_settling,
                state,
                sample_index=index,
            ).next_state

        observed = []
        for index, value in enumerate(values):
            result = process_dual_path(
                value,
                platform,
                platform_settling,
                state,
                sample_index=index,
            )
            observed.append(result)
            state = result.next_state
        self.assertEqual(
            predicted.stage2_symbols,
            tuple(item.pipeline.stage2.quantizer.symbol for item in observed),
        )
        self.assertEqual(
            predicted.output_codes,
            tuple(item.pipeline.reconstruction.output_code for item in observed),
        )
        self.assertEqual(
            predicted.correctable,
            tuple(item.pipeline.reconstruction.correctable for item in observed),
        )
        self.assertLess(
            max(
                abs(a - b)
                for a, b in zip(
                    predicted.stage1_auxiliary_outputs,
                    (item.stage1_auxiliary_output for item in observed),
                    strict=True,
                )
            ),
            1e-13,
        )
        self.assertLess(
            max(
                abs(a - b)
                for a, b in zip(
                    predicted.stage2_main_outputs,
                    (item.pipeline.stage2.residue for item in observed),
                    strict=True,
                )
            ),
            1e-13,
        )

        reduced = predict_periodic_settling(
            values, theory_config, PeriodicSettlingConfig((main, main))
        )
        self.assertGreater(
            sum(a != b for a, b in zip(predicted.stage2_symbols, reduced.stage2_symbols)),
            0,
        )

    def test_independent_static_auxiliary_boundaries_match_platform(self) -> None:
        ratio = 1.03
        enabled = ("static_pwl_truth",)
        platform = build_gu_static_hypothesis_a(
            self.architecture, stage2_flash_auxiliary_gain_ratio=ratio
        )
        applied = build_gu_gate_d_nonidealities(
            self.nonidealities, enabled_effects=enabled
        )
        theory_config = build_gu_theory_config(
            self.architecture,
            nonidealities=self.nonidealities,
            enabled_effects=enabled,
            stage2_flash_auxiliary_gain_ratio=ratio,
        )
        independent = predict_static_transfer(
            theory_config, independent_stage1_auxiliary=True
        )
        reduced = predict_static_transfer(theory_config)
        settling = DualPathSettlingConfig(0.0, 0.0, 0.0)
        state = DualPathSettlingState()
        differing_q2 = 0
        for index in range(4096):
            value = -1 + 2 * (index + 0.61803398875) / 4096
            observed = process_dual_path(
                value, platform, settling, state, nonidealities=applied
            )
            predicted = independent.segment_at(value)
            self.assertEqual(
                predicted.stage2_symbol, observed.pipeline.stage2.quantizer.symbol
            )
            self.assertEqual(
                predicted.output_code, observed.pipeline.reconstruction.output_code
            )
            self.assertEqual(
                predicted.correctable, observed.pipeline.reconstruction.correctable
            )
            differing_q2 += predicted.stage2_symbol != reduced.segment_at(value).stage2_symbol
        self.assertGreater(differing_q2, 0)

    def test_auxiliary_flash_threshold_uses_its_own_input_preimage(self) -> None:
        ratio = 1.03
        enabled = ("static_pwl_truth",)
        theory_config = build_gu_theory_config(
            self.architecture,
            nonidealities=self.nonidealities,
            enabled_effects=enabled,
            stage2_flash_auxiliary_gain_ratio=ratio,
        )
        prediction = predict_static_transfer(
            theory_config, independent_stage1_auxiliary=True
        )
        platform = build_gu_static_hypothesis_a(
            self.architecture, stage2_flash_auxiliary_gain_ratio=ratio
        )
        applied = build_gu_gate_d_nonidealities(
            self.nonidealities, enabled_effects=enabled
        )
        boundary = 0.125 / (4.0 * ratio)
        for offset, expected_q2 in ((-1e-9, 0), (1e-9, 1)):
            value = boundary + offset
            observed = process_dual_path(
                value,
                platform,
                DualPathSettlingConfig(0.0, 0.0, 0.0),
                DualPathSettlingState(),
                nonidealities=applied,
            )
            self.assertEqual(prediction.segment_at(value).stage2_symbol, expected_q2)
            self.assertEqual(observed.pipeline.stage2.quantizer.symbol, expected_q2)


if __name__ == "__main__":
    unittest.main()
