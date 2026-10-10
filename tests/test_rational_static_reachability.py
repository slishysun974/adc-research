"""Boundary and independent point checks of exact analog-to-code arithmetic."""
from __future__ import annotations

from dataclasses import replace
from fractions import Fraction as F
from itertools import product
from pathlib import Path
import tempfile
import unittest

from adc_research.calibration.fixed_adaptive_two_stage import (
    FixedTwoStageAdaptiveState, correct_and_update_fixed,
)
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.evaluation.fixed_online_state_bounds import FixedStateBox
from adc_research.evaluation.physical_scan_package import audit_scan_package
from adc_research.evaluation.static_online_reachability import (
    StaticAnalogFrame, propagate_rational_static_fixed_online_codes,
)
from adc_research.theory.rational_static_reachability import (
    propagate_rational_static_observations,
)
from adc_research.theory.static_observation_reachability import (
    ClosedInterval as I, StaticCandidateArchitecture,
)
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_036_physical_scan_intake.generate_fixture import generate_fixture


def point(value):
    return I(F(value), F(value))


def identity(query):
    return query


def geometry():
    return StaticCandidateArchitecture(
        (point(F(1, 8)),), (point(F(1, 8)),), (-1, 1), (-1, 1),
        (F(0), F(0)), (F(0), F(0)), (F(-1), F(1)), (F(-1), F(1)), 8,
    )


class RationalStaticReachabilityTests(unittest.TestCase):
    def test_distinguishes_below_equal_above_despite_equal_binary_floats(self):
        epsilon = F(1, 10**80)
        threshold = F(1, 8)
        self.assertEqual(float(threshold-epsilon), float(threshold+epsilon))
        expected = ((-1, -1, 15), (1, 1, 16), (1, 1, 16))
        for x, outcome in zip((threshold-epsilon, threshold, threshold+epsilon), expected):
            result = propagate_rational_static_observations(
                point(x), point(0), point(0), geometry(), identity, identity, identity,
            )
            self.assertEqual(len(result.outcomes), 1)
            actual = result.outcomes[0]
            self.assertEqual((actual.stage1_symbol, actual.stage2_symbol,
                              actual.backend_centered_code), outcome)

    def test_all_uniform_backend_boundaries_and_clipped_endpoints(self):
        epsilon = F(1, 10**80)
        for raw_boundary in range(257):
            threshold = F(-1) + F(raw_boundary, 128)
            for offset in (-epsilon, F(0), epsilon):
                x = threshold + offset
                result = propagate_rational_static_observations(
                    point(x), point(0), point(0), geometry(), identity, identity, identity,
                )
                # Point reference: enumerate the explicit 255 SAR thresholds.
                raw = sum(x >= F(-1)+F(k, 128) for k in range(1, 256))
                self.assertEqual(result.outcomes[0].backend_centered_code, raw-128)
                self.assertEqual(result.backend_overload_possible, x < -1 or x >= 1)

    def test_uncertain_cdac_dither_and_nonuniform_sar_cover_point_realizations(self):
        epsilon = F(1, 10**30)
        band = lambda x: I(x-epsilon, x+epsilon)
        backend = tuple(band(F(-1)+F(k, 4)+F(k*k, 1000)) for k in range(1, 8))
        architecture = StaticCandidateArchitecture(
            (band(F(-1, 4)),), (band(F(1, 8)),), (-1, 1), (-1, 1),
            (band(F(-1, 8)), band(F(1, 8))),
            (band(F(-1, 16)), band(F(1, 16))),
            (F(-1), F(1)), (F(-1), F(1)), 3, backend,
        )
        input_band = band(F(-1, 4))
        d1, d2 = I(F(-1, 64), F(1, 64)), I(F(-1, 128), F(1, 128))
        twice = lambda q: I(2*q.lower, 2*q.upper)
        result = propagate_rational_static_observations(
            input_band, d1, d2, architecture, twice, identity, identity,
        )
        allowed = {(r.stage1_symbol, r.stage2_symbol, r.backend_centered_code)
                   for r in result.outcomes}
        for x in (input_band.lower, F(-1, 4), input_band.upper):
            for choices in product((0, 1), repeat=7):
                t1 = (architecture.stage1_thresholds[0].lower,
                      architecture.stage1_thresholds[0].upper)[choices[0]]
                first = int(x >= t1)
                dac1 = architecture.stage1_dac_levels[first]
                w1 = x-(dac1.lower, dac1.upper)[choices[1]]+(d1.lower, d1.upper)[choices[2]]
                t2 = (architecture.stage2_thresholds[0].lower,
                      architecture.stage2_thresholds[0].upper)[choices[3]]
                second = int(w1 >= t2)
                dac2 = architecture.stage2_dac_levels[second]
                output = 2*w1-(dac2.lower, dac2.upper)[choices[4]]+(d2.lower, d2.upper)[choices[5]]
                raw = sum(output >= (t.lower, t.upper)[choices[6]] for t in backend)
                self.assertIn(((-1, 1)[first], (-1, 1)[second], raw-4), allowed)

    def test_nondyadic_cdac_dither_and_uniform_sar_use_exact_arithmetic(self):
        epsilon = F(1, 10**80)
        architecture = StaticCandidateArchitecture(
            (), (), (0,), (0,), (F(1, 10),), (F(1, 5),),
            (F(-1), F(1)), (F(-1, 10), F(9, 10)), 3,
        )
        # x-1/10+1/30-1/5+1/7 is exactly the first SAR threshold.
        threshold = F(1, 40)
        x = threshold+F(1, 10)-F(1, 30)+F(1, 5)-F(1, 7)
        for offset, expected in ((-epsilon, -4), (F(0), -3), (epsilon, -3)):
            result = propagate_rational_static_observations(
                point(x+offset), point(F(1, 30)), point(F(1, 7)), architecture,
                identity, identity, identity,
            )
            self.assertEqual(result.outcomes[0].backend_centered_code, expected)

    def test_rejects_float_inputs_architecture_and_callback_endpoints(self):
        architecture = geometry()
        changes = (
            {"stage1_thresholds": (I(0.125, 0.125),)},
            {"stage2_dac_levels": (0.0, 0.0)},
            {"backend_range": (-1.0, 1.0)},
            {"backend_thresholds": tuple(I(float(F(-1)+F(k, 128)),
                                             float(F(-1)+F(k, 128))) for k in range(1, 256))},
        )
        for change in changes:
            with self.assertRaises(TypeError):
                propagate_rational_static_observations(
                    point(0), point(0), point(0), replace(architecture, **change),
                    identity, identity, identity,
                )
        with self.assertRaises(TypeError):
            propagate_rational_static_observations(
                I(0.0, 0.0), point(0), point(0), architecture, identity, identity, identity,
            )
        with self.assertRaises(TypeError):
            propagate_rational_static_observations(
                point(0), point(0), point(0), architecture,
                lambda q: I(float(q.lower), float(q.upper)), identity, identity,
            )

    def test_package_exact_normalization_union_and_domain_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            package = audit_scan_package(generate_fixture(Path(directory)))
            selected = ("synthetic_case_a", "synthetic_case_b")
            exact = package.rational_path_envelope("stage1_main", selected)
            query = point(F(3, 100))
            result = exact(query)
            expected = [package.envelopes[(case, "stage1_main")].voltage_bounds(
                query.lower/2, query.upper/2) for case in selected]
            self.assertEqual(result, I(2*min(e[0] for e in expected),
                                       2*max(e[1] for e in expected)))
            self.assertIsInstance(result.lower, F)
            with self.assertRaises(TypeError):
                exact(I(0.03, 0.03))
            with self.assertRaises(ValueError):
                exact(point(F(101, 100)))
            package.report["package_checks_passed"] = False
            with self.assertRaises(ValueError):
                package.rational_path_envelope("stage1_main", selected)

    def test_exact_two_observations_connect_to_online_integer_states(self):
        architecture = StaticCandidateArchitecture(
            (), (), (0,), (0,), (F(0),), (F(0),),
            (F(-1), F(1)), (F(-1), F(1)), 8,
        )
        epsilon = F(1, 10**80)
        config = _config()
        initial = FixedTwoStageAdaptiveState(
            FixedGatedLmsState.unity(config.stage1_lms),
            FixedGatedLmsState.unity(config.stage2_lms),
        )
        frames = (StaticAnalogFrame(I(-epsilon, epsilon), point(0), point(0), -1, 1),
                  StaticAnalogFrame(point(F(1, 128)), point(0), point(0), 1, -1))
        result = propagate_rational_static_fixed_online_codes(
            frames, architecture, identity, identity, identity,
            FixedStateBox.from_state(initial), config,
        )
        self.assertEqual([len(e.outcomes) for e in result.observation_envelopes], [2, 1])
        for first_backend in (-1, 0):
            state = initial
            for index, sample in enumerate((
                DigitalCalibrationSample(0, 0, first_backend, -1, 1),
                DigitalCalibrationSample(0, 0, 1, 1, -1),
            )):
                actual = correct_and_update_fixed(sample, state, config)
                state = actual.state
                code = min(max(round_fraction(actual.calibration.unclipped_output_scaled,
                                               8, "nearest_even"), 0), 4095)
                self.assertLessEqual(result.code_bounds.lower_codes[index], code)
                self.assertLessEqual(code, result.code_bounds.upper_codes[index])
            for bank, bounds in ((state.stage1, result.code_bounds.final_state_box.stage1_accumulators),
                                 (state.stage2, result.code_bounds.final_state_box.stage2_accumulators)):
                for actual, bound in zip(bank.accumulator_codes, bounds):
                    self.assertLessEqual(bound.lower, actual)
                    self.assertLessEqual(actual, bound.upper)

    def test_exact_chain_propagates_domain_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            package = audit_scan_package(generate_fixture(Path(directory)))
            function = package.rational_path_envelope("stage1_main", ("synthetic_case_a",))
            with self.assertRaisesRegex(ValueError, "outside the measured"):
                propagate_rational_static_observations(
                    point(F(2)), point(0), point(0), geometry(), function, identity, identity,
                )
