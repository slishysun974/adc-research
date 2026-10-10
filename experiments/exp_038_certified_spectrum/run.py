"""Certified spectra for synthetic Q22 digital and exact static-scan records."""

from __future__ import annotations

import argparse
from dataclasses import asdict
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

from adc_research.calibration.fixed_adaptive_two_stage import correct_and_update_fixed
from adc_research.calibration.fixed_point import round_fraction
from adc_research.evaluation.fixed_online_state_bounds import FixedStateBox, bound_fixed_online_codes
from adc_research.evaluation.physical_scan_package import PATHS, audit_scan_package
from adc_research.evaluation.static_online_reachability import (
    StaticAnalogFrame, propagate_rational_static_fixed_online_codes,
)
from adc_research.metrics.spectral import analyze_coherent_tone
from adc_research.theory.certified_spectral_bounds import (
    ExtendedInterval, bound_certified_coherent_tone, certified_phase,
)
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _endpoint_record, _initial, _observations
from experiments.exp_036_physical_scan_intake.generate_fixture import generate_fixture
from experiments.exp_037_rational_static_online.run import (
    ARCHITECTURE, exact_observation, geometry, platform_observation, point,
)
from adc_research.platform.presets import build_gu_static_hypothesis_a
import yaml


ROOT = Path(__file__).resolve().parents[2]
BITS = 72
SCAN_COUNT = 128
SCAN_TONE = 7


def _json(value):
    if isinstance(value, F):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(v) for v in value]
    return value


def _write(path, document):
    path.write_text(json.dumps(_json(document), indent=2, ensure_ascii=False,
                              allow_nan=False), encoding="utf-8")


def _decimal_endpoint(value, *, lower, digits=6):
    if isinstance(value, str):
        return value
    scale = 10**digits
    integer = (value.numerator*scale)//value.denominator if lower else -(
        (-value.numerator*scale)//value.denominator)
    sign = "-" if integer < 0 else ""
    integer = abs(integer)
    return f"{sign}{integer//scale}.{integer%scale:0{digits}d}"


def _display(interval):
    # These decimal strings are also rounded outward, never nearest floats.
    return {"lower": _decimal_endpoint(interval.lower, lower=True),
            "upper": _decimal_endpoint(interval.upper, lower=False)}


def _included(outer: ExtendedInterval, inner: ExtendedInterval):
    def leq(a, b):
        if a == "-inf" or b == "+inf":
            return True
        if a == "+inf" or b == "-inf":
            return a == b
        return a <= b
    return leq(outer.lower, inner.lower) and leq(inner.upper, outer.upper)


def _spectral_check(name, lower, upper, endpoint_codes, tone, output):
    certificate = bound_certified_coherent_tone(lower, upper, fundamental_bin=tone, bits=BITS)
    assert certificate.fundamental_guaranteed_nonzero
    _write(output / f"{name}_certificate.json", asdict(certificate))
    endpoint_certificates = []
    # A point certificate verifies exact ratio containment; NumPy gives an
    # independent approximate scoring comparison with no certification claim.
    approximate_scores = []
    for codes in endpoint_codes:
        exact = bound_certified_coherent_tone(codes, codes, fundamental_bin=tone, bits=BITS)
        assert _included(certificate.sndr_power_ratio, exact.sndr_power_ratio)
        assert _included(certificate.sfdr_power_ratio, exact.sfdr_power_ratio)
        endpoint_certificates.append({
            "sndr_power_ratio": asdict(exact.sndr_power_ratio),
            "sfdr_power_ratio": asdict(exact.sfdr_power_ratio),
            "sndr_db": asdict(exact.sndr_db), "sfdr_dbc": asdict(exact.sfdr_dbc),
        })
        score = analyze_coherent_tone(codes, sample_rate_hz=len(codes),
                                     fundamental_bin=tone, harmonic_orders=()).metrics
        approximate_scores.append({"sndr_db": score.sndr_db, "sfdr_dbc": score.sfdr_dbc,
                                   "sndr_difference_from_certificate_midpoint_db":
                                   score.sndr_db-float((exact.sndr_db.lower+exact.sndr_db.upper)/2),
                                   "sfdr_difference_from_certificate_midpoint_db":
                                   score.sfdr_dbc-float((exact.sfdr_dbc.lower+exact.sfdr_dbc.upper)/2)})
        for interval, value in ((exact.sndr_db, score.sndr_db), (exact.sfdr_dbc, score.sfdr_dbc)):
            # NumPy SNDR subtracts fundamental from total power. Cancellation
            # can place that approximate score outside the tight point
            # certificate; this tolerance is only a parity check, not a bound.
            assert float(interval.lower)-1e-8 <= value <= float(interval.upper)+1e-8
    _write(output / f"{name}_endpoints.json", endpoint_certificates)
    widths = [high-low for low, high in zip(lower, upper)]
    return {
        "sample_count": len(lower), "fundamental_bin": tone,
        "code_interval_width": {"minimum": min(widths), "maximum": max(widths)},
        "fundamental_guaranteed_nonzero": certificate.fundamental_guaranteed_nonzero,
        "certified_sndr_db_outward_decimal": _display(certificate.sndr_db),
        "certified_sfdr_dbc_outward_decimal": _display(certificate.sfdr_dbc),
        "endpoint_approximate_scores": approximate_scores,
        "approximate_parity_tolerance_db": "1/100000000 (consistency only)",
        "endpoint_exact_ratio_certificates_contained": len(endpoint_codes),
        "certificate_sha256": hashlib.sha256((output/f"{name}_certificate.json").read_bytes()).hexdigest(),
    }


def _digital(output):
    config = _config()
    initial = _initial(config)
    observations = tuple(_observations())
    bounds = bound_fixed_online_codes(observations, FixedStateBox.from_state(initial), config)
    endpoints = tuple(_endpoint_record(observations, initial, config, choice)[0] for choice in (0, 1))
    _write(output / "digital_records.json", {
        "source_kind": "synthetic", "source": "EXP-033 unchanged digital-observation construction",
        "observation_sets": [[asdict(s) for s in group] for group in observations],
        "lower_codes": bounds.lower_codes, "upper_codes": bounds.upper_codes,
        "endpoint_codes": endpoints,
        "source_numeric_note": "historical floating sine constructs integer observations; certificate begins at saved integer records",
    })
    return _spectral_check("digital", bounds.lower_codes, bounds.upper_codes, endpoints, 19, output)


def _scan(output):
    manifest = generate_fixture(output / "synthetic")
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in manifest.parent.iterdir() if p.is_file()}
    package = audit_scan_package(manifest)
    assert package.report["package_checks_passed"]
    architecture, config = geometry(), _config()
    initial = _initial(config)
    envelopes = tuple(package.rational_path_envelope(path, ("synthetic_case_a", "synthetic_case_b"))
                      for path in PATHS)
    frames = []
    # The applied waveform is a rationally quantized coherent sine, not an
    # unbounded conversion of a floating sine to an exact-looking Fraction.
    for index in range(SCAN_COUNT):
        _, sine = certified_phase(SCAN_TONE*index, SCAN_COUNT, bits=BITS)
        rounding_interval = sine.scale(F(3, 25)*10**12)
        low, high = round(rounding_interval.lower), round(rounding_interval.upper)
        assert low == high, "sine input rounding was unresolved"
        x = F(low, 10**12)
        d1, d2 = (1 if index % 2 else -1), (1 if index % 3 else -1)
        frames.append(StaticAnalogFrame(point(x), point(F(d1, 32)), point(F(d2, 32)), d1, d2))
    propagation = propagate_rational_static_fixed_online_codes(
        frames, architecture, *envelopes, FixedStateBox.from_state(initial), config,
    )
    states = [initial, initial]
    endpoint_codes = [[], []]
    rows = []
    platform = build_gu_static_hypothesis_a(yaml.safe_load(ARCHITECTURE.read_text()))
    for index, frame in enumerate(frames):
        allowed = {(o.stage1_symbol, o.stage2_symbol, o.backend_centered_code)
                   for o in propagation.observation_envelopes[index].outcomes}
        low, high = propagation.code_bounds.lower_codes[index], propagation.code_bounds.upper_codes[index]
        observations = []
        for case in range(2):
            sample = exact_observation(frame, architecture, case)
            assert sample == platform_observation(frame, platform, case, index)
            assert (sample.stage1_symbol, sample.stage2_symbol, sample.backend_centered_code) in allowed
            result = correct_and_update_fixed(sample, states[case], config)
            states[case] = result.state
            code = min(max(round_fraction(result.calibration.unclipped_output_scaled,
                                           8, "nearest_even"), 0), 4095)
            assert low <= code <= high
            endpoint_codes[case].append(code)
            observations.append(asdict(sample))
        rows.append({"conversion": index, "input_normalized": frame.input_voltage.lower,
                     "code_interval": [low, high], "observations": observations,
                     "endpoint_codes": [codes[-1] for codes in endpoint_codes]})
    final_box = propagation.code_bounds.final_state_box
    for state in states:
        for bank, intervals in ((state.stage1, final_box.stage1_accumulators),
                                (state.stage2, final_box.stage2_accumulators)):
            assert all(b.lower <= a <= b.upper for a, b in zip(bank.accumulator_codes, intervals))
    after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in manifest.parent.iterdir() if p.is_file()}
    assert before == after
    _write(output / "scan_records.json", {
        "source_kind": "synthetic", "input_rule": "round_even(10^12*(3/25)*sin(2*pi*7*n/128))/10^12",
        "input_quantization_error_at_most": "1/2000000000000 normalized unit",
        "rows": rows, "source_package_unchanged": True,
        "final_state_box": asdict(propagation.code_bounds.final_state_box),
        "endpoint_final_states": [asdict(state) for state in states],
    })
    result = _spectral_check("scan", propagation.code_bounds.lower_codes,
                             propagation.code_bounds.upper_codes, endpoint_codes, SCAN_TONE, output)
    result.update({"source_package_unchanged": True, "package_checks_passed": True,
                   "analytic_and_platform_observations_checked": 2*SCAN_COUNT,
                   "endpoint_final_eight_state_boxes_checked": 2,
                   "manifest_sha256": package.report["manifest_sha256"],
                   "condition_combination": "per-path union, cross-path and cross-conversion correlation relaxed"})
    return result


def run(output):
    digital = _digital(output)
    scan = _scan(output)
    sources = (
        "src/adc_research/theory/certified_spectral_bounds.py",
        "src/adc_research/theory/rational_static_reachability.py",
        "src/adc_research/theory/static_observation_reachability.py",
        "src/adc_research/theory/lipschitz_grid_envelope.py",
        "src/adc_research/evaluation/physical_scan_package.py",
        "src/adc_research/evaluation/static_online_reachability.py",
        "src/adc_research/evaluation/fixed_online_state_bounds.py",
        "src/adc_research/calibration/fixed_point.py",
        "src/adc_research/calibration/fixed_pwl.py",
        "src/adc_research/calibration/fixed_gated_lms.py",
        "src/adc_research/calibration/fixed_adaptive_two_stage.py",
        "experiments/exp_032_online_lms_rtl/generate_vectors.py",
        "experiments/exp_033_fixed_online_box/run.py",
        "experiments/exp_036_physical_scan_intake/generate_fixture.py",
        "experiments/exp_037_rational_static_online/run.py",
        "experiments/exp_038_certified_spectrum/run.py",
        "configs/architectures/gu_behavioral_v1.yaml",
        "tests/test_certified_spectral_bounds.py",
        "src/adc_research/platform/presets.py",
        "src/adc_research/platform/stage.py",
        "src/adc_research/platform/amplifier.py",
        "src/adc_research/platform/backend_sar.py",
        "src/adc_research/metrics/spectral.py",
    )
    summary = {
        "scope": "conditional_rational_numerical_certificate_for_synthetic_final_code_envelopes",
        "source_kind": "synthetic", "physical_guarantee": False,
        "spectrum_numerically_enclosed": True, "all_input_formal_verification": False,
        "precision_bits": BITS, "window": "rectangular", "dc": "excluded",
        "nyquist_power_weight": 1, "other_positive_bin_power_weight": 2,
        "sample_rate_interpretation": "normalized uniform candidate conversions, not chip measurement or four-lane output",
        "display_note": "six-place decimal interval endpoints are also rounded outward",
        "digital": digital, "scan": scan,
        "source_sha256": {s: hashlib.sha256((ROOT/s).read_bytes()).hexdigest() for s in sources},
        "record_sha256": {s: hashlib.sha256((output/s).read_bytes()).hexdigest()
                          for s in ("digital_records.json", "scan_records.json")},
    }
    _write(output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = (ROOT/args.output).resolve()
    output.relative_to(ROOT/"artifacts/runs/EXP_038")
    output.mkdir(parents=True, exist_ok=True)
    print(json.dumps(run(output), indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
