"""Check exact scan-to-observation-to-Q22-code bounds on synthetic data."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

import yaml

from adc_research.calibration.fixed_adaptive_two_stage import (
    FixedTwoStageAdaptiveState, correct_and_update_fixed,
)
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState
from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.evaluation.fixed_online_state_bounds import FixedStateBox
from adc_research.evaluation.physical_scan_package import PATHS, audit_scan_package
from adc_research.evaluation.static_online_reachability import (
    StaticAnalogFrame, propagate_rational_static_fixed_online_codes,
)
from adc_research.platform.amplifier import StaticCubicTruthConfig, amplify_static_cubic_truth
from adc_research.platform.backend_sar import convert as convert_sar
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stage import StaticStageNonidealities, process as process_stage
from adc_research.theory.rational_static_reachability import propagate_rational_static_observations
from adc_research.theory.static_observation_reachability import (
    ClosedInterval as I, StaticCandidateArchitecture, propagate_static_observations,
)
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_036_physical_scan_intake.generate_fixture import generate_fixture, transfer

ROOT = Path(__file__).resolve().parents[2]
ARCHITECTURE = ROOT / "configs/architectures/gu_behavioral_v1.yaml"
SAMPLE_COUNT = 128


def point(value):
    return I(F(value), F(value))


def geometry():
    # BaseLoader preserves source decimal strings, before any float parsing.
    document = yaml.load(ARCHITECTURE.read_text(), Loader=yaml.BaseLoader)
    front = document["front_stage_template"]
    thresholds = tuple(point(F(x)) for x in front["thresholds"])
    levels = tuple(F(x) for x in front["dac_levels"])
    nominal = tuple(F(x) for x in document["normalized_domain"]["input_range"])
    symbols = tuple(int(x) for x in front["output_symbols"])
    return StaticCandidateArchitecture(
        thresholds, thresholds, symbols, symbols, levels, levels,
        nominal, nominal, int(document["backend"]["bits"]),
    )


def exact_observation(frame, architecture, case):
    # Independent point reference: actual analytic voltages and explicit
    # comparator threshold counts, never grid envelope values or floor bins.
    scale = F(1, 2)
    x = frame.input_voltage.lower
    first = sum(x >= t.lower for t in architecture.stage1_thresholds)
    w1 = x-architecture.stage1_dac_levels[first].lower+frame.stage1_dither_preamp.lower
    main1 = transfer(case, "stage1_main", w1*scale)/scale
    aux1 = transfer(case, "stage1_auxiliary", w1*scale)/scale
    second = sum(aux1 >= t.lower for t in architecture.stage2_thresholds)
    w2 = main1-architecture.stage2_dac_levels[second].lower+frame.stage2_dither_preamp.lower
    main2 = transfer(case, "stage2_main", w2*scale)/scale
    count = 1 << architecture.backend_bits
    low, high = architecture.backend_range
    raw = sum(main2 >= low+(high-low)*F(k, count) for k in range(1, count))
    return DigitalCalibrationSample(
        architecture.stage1_symbols[first], architecture.stage2_symbols[second],
        raw-count//2, frame.stage1_dither_symbol, frame.stage2_dither_symbol,
    )


def platform_observation(frame, platform, case, index):
    gain = 4.0 if case == 0 else 3.8
    offset = 0.0 if case == 0 else 0.01
    main_truth = StaticCubicTruthConfig(1.0, 0.1/gain**3)
    aux_truth = StaticCubicTruthConfig(1.0, 0.05/gain**3)
    nonideal = StaticStageNonidealities(actual_interstage_gain=gain, cubic_truth=main_truth)
    x = float(frame.input_voltage.lower)
    first = process_stage(x, x, frame.stage1_dither_symbol, platform.stage1,
                          nonidealities=nonideal)
    main1 = first.residue+offset
    aux1 = amplify_static_cubic_truth(first.residue_preamp, nominal_gain=4.0,
        actual_gain=gain, truth=aux_truth).output_value+offset
    second = process_stage(main1, aux1, frame.stage2_dither_symbol, platform.stage2,
                           nonidealities=nonideal)
    backend = convert_sar(second.residue+offset, platform.backend, sample_index=index)
    return DigitalCalibrationSample(
        first.quantizer.symbol, second.quantizer.symbol, backend.centered_code,
        frame.stage1_dither_symbol, frame.stage2_dither_symbol,
    )


def check_boundaries():
    epsilon = F(1, 10**80)
    architecture = StaticCandidateArchitecture(
        (point(F(1, 8)),), (point(F(1, 8)),), (-1, 1), (-1, 1),
        (F(0), F(0)), (F(0), F(0)), (F(-1), F(1)), (F(-1), F(1)), 8,
    )
    identity = lambda q: q
    count = 0
    for boundary in range(257):
        threshold = F(-1)+F(boundary, 128)
        for offset in (-epsilon, F(0), epsilon):
            x = threshold+offset
            result = propagate_rational_static_observations(
                point(x), point(0), point(0), architecture, identity, identity, identity,
            )
            raw = sum(x >= F(-1)+F(k, 128) for k in range(1, 256))
            symbol = -1 if x < F(1, 8) else 1
            assert len(result.outcomes) == 1
            assert asdict(result.outcomes[0]) == {
                "stage1_symbol": symbol, "stage2_symbol": symbol,
                "backend_centered_code": raw-128,
            }
            count += 1
    x = F(1, 8)-epsilon
    exact = propagate_rational_static_observations(
        point(x), point(0), point(0), architecture, identity, identity, identity,
    )
    rounded_geometry = StaticCandidateArchitecture(
        (I(0.125, 0.125),), (I(0.125, 0.125),), (-1, 1), (-1, 1),
        (0.0, 0.0), (0.0, 0.0), (-1.0, 1.0), (-1.0, 1.0), 8,
    )
    rounded = propagate_static_observations(
        I(float(x), float(x)), I(0.0, 0.0), I(0.0, 0.0), rounded_geometry,
        identity, identity, identity,
    )
    return {"exact_point_records_checked": count, "epsilon": str(epsilon),
            "example_input": str(x), "example_rounded_input": float(x),
            "example_exact_outcome": asdict(exact.outcomes[0]),
            "example_after_rounding_input": asdict(rounded.outcomes[0]),
            "scope": "representation-loss example, not physical error rate"}


def run(output):
    manifest = generate_fixture(output / "synthetic")
    package = audit_scan_package(manifest)
    assert package.report["package_checks_passed"]
    source_directory = manifest.parent
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
              for p in source_directory.iterdir() if p.is_file()}
    assert package.report["volts_per_normalized_unit"] == "1/2"
    architecture = geometry()
    selected = ("synthetic_case_a", "synthetic_case_b")
    envelopes = tuple(package.rational_path_envelope(path, selected) for path in PATHS)
    config = _config()
    initial = FixedTwoStageAdaptiveState(
        FixedGatedLmsState.unity(config.stage1_lms), FixedGatedLmsState.unity(config.stage2_lms),
    )
    frames = []
    for index in range(SAMPLE_COUNT):
        x = -F(3, 25)+F(6, 25)*(F(index)+F(37, 100))/SAMPLE_COUNT
        d1, d2 = (1 if index % 2 else -1), (1 if index % 3 else -1)
        frames.append(StaticAnalogFrame(point(x), point(F(d1, 32)), point(F(d2, 32)), d1, d2))
    box = FixedStateBox.from_state(initial)
    states = [initial, initial]
    platform = build_gu_static_hypothesis_a(yaml.safe_load(ARCHITECTURE.read_text()))
    records, lows, highs, observation_counts = [], [], [], []
    for index, frame in enumerate(frames):
        result = propagate_rational_static_fixed_online_codes(
            (frame,), architecture, *envelopes, box, config,
        )
        allowed = result.observation_envelopes[0].outcomes
        allowed_triples = {(o.stage1_symbol, o.stage2_symbol, o.backend_centered_code) for o in allowed}
        observation_counts.append(len(allowed))
        box = result.code_bounds.final_state_box
        low, high = result.code_bounds.lower_codes[0], result.code_bounds.upper_codes[0]
        lows.append(low)
        highs.append(high)
        for case in range(2):
            sample = exact_observation(frame, architecture, case)
            assert sample == platform_observation(frame, platform, case, index)
            assert (sample.stage1_symbol, sample.stage2_symbol,
                    sample.backend_centered_code) in allowed_triples
            actual = correct_and_update_fixed(sample, states[case], config)
            states[case] = actual.state
            code = min(max(round_fraction(actual.calibration.unclipped_output_scaled,
                                           8, "nearest_even"), 0), 4095)
            assert low <= code <= high
            for bank, bounds in ((actual.state.stage1, box.stage1_accumulators),
                                 (actual.state.stage2, box.stage2_accumulators)):
                assert all(b.lower <= a <= b.upper for a, b in zip(bank.accumulator_codes, bounds))
            records.append({"conversion": index, "synthetic_case": case,
                            "input_normalized": str(frame.input_voltage.lower),
                            "observation": asdict(sample), "actual_code": code,
                            "code_interval": [low, high],
                            "actual_stage1_accumulators": list(actual.state.stage1.accumulator_codes),
                            "actual_stage2_accumulators": list(actual.state.stage2.accumulator_codes),
                            "state_box": asdict(box)})
    # Check the public whole-record composition against per-step replay.
    complete = propagate_rational_static_fixed_online_codes(
        frames, architecture, *envelopes, FixedStateBox.from_state(initial), config,
    )
    assert complete.code_bounds.lower_codes == tuple(lows)
    assert complete.code_bounds.upper_codes == tuple(highs)
    assert complete.code_bounds.final_state_box == box
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
             for p in source_directory.iterdir() if p.is_file()}
    assert before == after
    (output / "records.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
    widths = [high-low for low, high in zip(lows, highs)]
    sources = (
        "src/adc_research/theory/rational_static_reachability.py",
        "src/adc_research/theory/static_observation_reachability.py",
        "src/adc_research/theory/lipschitz_grid_envelope.py",
        "src/adc_research/evaluation/physical_scan_package.py",
        "src/adc_research/evaluation/static_online_reachability.py",
        "src/adc_research/evaluation/fixed_online_state_bounds.py",
        "src/adc_research/calibration/fixed_pwl.py",
        "src/adc_research/calibration/fixed_point.py",
        "src/adc_research/calibration/fixed_gated_lms.py",
        "src/adc_research/calibration/fixed_adaptive_two_stage.py",
        "experiments/exp_032_online_lms_rtl/generate_vectors.py",
        "experiments/exp_036_physical_scan_intake/generate_fixture.py",
        "experiments/exp_037_rational_static_online/run.py",
        "tests/test_rational_static_reachability.py",
        "src/adc_research/platform/presets.py",
        "src/adc_research/platform/stage.py",
        "src/adc_research/platform/amplifier.py",
        "src/adc_research/platform/backend_sar.py",
        "configs/architectures/gu_behavioral_v1.yaml",
    )
    summary = {
        "scope": "synthetic_static_scan_to_q22_online_code_bounds",
        "source_kind": "synthetic", "physical_guarantee": False,
        "spectrum_numerically_certified": False,
        "arithmetic_scope": "exact rational source voltages through static decisions; integer Q22 states and codes",
        "frames": SAMPLE_COUNT, "synthetic_condition_trajectories": 2,
        "exact_and_platform_observations_checked": len(records),
        "online_codes_and_eight_states_checked_each_conversion": len(records),
        "code_interval_width_minimum": min(widths), "code_interval_width_maximum": max(widths),
        "observation_count_minimum": min(observation_counts), "observation_count_maximum": max(observation_counts),
        "final_state_box": asdict(box), "whole_record_matches_step_replay": True,
        "source_package_unchanged": before == after,
        "package_checks_passed": package.report["package_checks_passed"],
        "manifest_sha256": package.report["manifest_sha256"],
        "records_sha256": hashlib.sha256((output / "records.json").read_bytes()).hexdigest(),
        "boundary_checks": check_boundaries(),
        "source_sha256": {s: hashlib.sha256((ROOT / s).read_bytes()).hexdigest() for s in sources},
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    output.relative_to(ROOT / "artifacts/runs/EXP_037")
    output.mkdir(parents=True, exist_ok=True)
    print(json.dumps(run(output), indent=2))


if __name__ == "__main__":
    main()
