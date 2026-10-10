"""Exercise scan intake and its three-path connection on synthetic data only."""
from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil

import yaml

from adc_research.calibration.gu_baseline import build_gu_two_stage_baseline
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.calibration.two_stage import correct_two_stage_observed
from adc_research.evaluation.full_chain_code_envelope import bound_static_gu_codes
from adc_research.evaluation.physical_scan_package import audit_scan_package
from adc_research.platform.amplifier import StaticCubicTruthConfig, amplify_static_cubic_truth
from adc_research.platform.backend_sar import convert as convert_sar
from adc_research.platform.presets import build_gu_static_hypothesis_a
from adc_research.platform.stage import StaticStageNonidealities, process as process_stage
from adc_research.theory.static_observation_reachability import (
    ClosedInterval, StaticCandidateArchitecture, propagate_static_observations,
)

from .generate_fixture import generate_fixture

ROOT = Path(__file__).resolve().parents[2]


def check_static_connection(package) -> dict:
    architecture = yaml.safe_load((ROOT / "configs/architectures/gu_behavioral_v1.yaml").read_text())
    assert Fraction(str(architecture["normalized_domain"]["differential_volts_per_normalized_unit"])) == Fraction(1, 2)
    assert package.report["volts_per_normalized_unit"] == "1/2"
    front = architecture["front_stage_template"]
    thresholds = tuple(ClosedInterval(x, x) for x in front["thresholds"])
    geometry = StaticCandidateArchitecture(thresholds, thresholds,
        tuple(front["output_symbols"]), tuple(front["output_symbols"]),
        tuple(front["dac_levels"]), tuple(front["dac_levels"]),
        (-1.0, 1.0), (-1.0, 1.0), 8)
    platform = build_gu_static_hypothesis_a(architecture)
    calibration = build_gu_two_stage_baseline(platform, architecture["pwl_implications"])
    selected = ("synthetic_case_a", "synthetic_case_b")
    envelope_functions = [package.path_envelope(path, selected) for path in
                          ("stage1_main", "stage1_auxiliary", "stage2_main")]
    records, widths = [], []
    for k in range(128):
        x = -0.12 + 0.24*(k+0.37)/128
        observations = propagate_static_observations(ClosedInterval(x, x),
            ClosedInterval(0.0, 0.0), ClosedInterval(0.0, 0.0), geometry, *envelope_functions)
        code_range = bound_static_gu_codes(observations, calibration,
            stage1_dither_symbol=None, stage2_dither_symbol=None)
        allowed = {(r.stage1_symbol, r.stage2_symbol, r.backend_centered_code)
                   for r in observations.outcomes}
        # Independent sample-wise stage/SAR primitives use known synthetic
        # parameters. No scan-derived sensitivity or fitted curve enters them.
        for case_index in range(2):
            gain = 4.0 if case_index == 0 else 3.8
            offset = 0.0 if case_index == 0 else 0.01
            main_truth = StaticCubicTruthConfig(1.0, 0.1/gain**3)
            aux_truth = StaticCubicTruthConfig(1.0, 0.05/gain**3)
            nonidealities = StaticStageNonidealities(actual_interstage_gain=gain, cubic_truth=main_truth)
            first = process_stage(x, x, None, platform.stage1, nonidealities=nonidealities)
            main1 = first.residue + offset
            auxiliary = amplify_static_cubic_truth(first.residue_preamp,
                nominal_gain=4.0, actual_gain=gain, truth=aux_truth).output_value + offset
            second = process_stage(main1, auxiliary, None, platform.stage2, nonidealities=nonidealities)
            backend = convert_sar(second.residue+offset, platform.backend, sample_index=k)
            actual = (first.quantizer.symbol, second.quantizer.symbol, backend.centered_code)
            if actual not in allowed:
                raise AssertionError((k, case_index, "digital observation not covered", actual))
            sample = DigitalCalibrationSample(*actual, None, None)
            corrected = correct_two_stage_observed(sample, calibration)
            code = min(max(round(corrected.unclipped_output_code), 0), 4095)
            if not code_range.lower_output_code <= code <= code_range.upper_output_code:
                raise AssertionError((k, case_index, "final code not covered", code))
            records.append({"input": x, "synthetic_case": case_index, "actual_code": code,
                            "code_interval": [code_range.lower_output_code, code_range.upper_output_code]})
        widths.append(code_range.upper_output_code-code_range.lower_output_code)
    return {"scope": "synthetic_static_three_path_connection; frozen unity coefficients; no dither",
            "platform_records_checked": len(records), "all_observations_and_codes_covered": True,
            "code_interval_width_minimum": min(widths), "code_interval_width_maximum": max(widths),
            "records": records, "physical_guarantee": False,
            "numerical_scope": "exact transfer envelope only; existing float chain is not certified"}


def negative_case(base: Path, target: Path, mode: str) -> dict:
    shutil.copytree(base, target, dirs_exist_ok=True)
    manifest_path = target / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    path = target / "holdout.csv"
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        fields, rows = reader.fieldnames, list(reader)
    if mode == "contradiction":
        rows[0].update(output_lower="10", output_upper="11")
    else:
        original = audit_scan_package(manifest_path)
        low, high = original.envelopes[("synthetic_case_a", "stage1_main")].voltage_bounds(
            -Fraction(19, 40)-Fraction(1, 100000), -Fraction(19, 40)+Fraction(1, 100000))
        rows[0].update(output_lower=str((low+high)/2), output_upper=str(high+Fraction(1, 100)))
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    manifest["holdout"]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, indent=2))
    report = audit_scan_package(manifest_path).report
    assert not report["package_checks_passed"]
    assert report["groups"][0]["holdout_counts"][mode] == 1
    (target / "audit.json").write_text(json.dumps(report, indent=2))
    return {"injected_case": mode, "package_checks_passed": False,
            "holdout_counts": report["groups"][0]["holdout_counts"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    output.relative_to(ROOT / "artifacts/runs/EXP_036")
    manifest_path = generate_fixture(output / "synthetic")
    package = audit_scan_package(manifest_path)
    assert package.report["package_checks_passed"]
    (output / "intake_audit.json").write_text(json.dumps(package.report, indent=2), encoding="utf-8")
    connection = check_static_connection(package)
    (output / "static_connection.json").write_text(json.dumps(connection, indent=2))
    negatives = [negative_case(manifest_path.parent, output / mode, mode)
                 for mode in ("contradiction", "inconclusive")]
    source_paths = (
        "src/adc_research/evaluation/physical_scan_package.py",
        "src/adc_research/theory/lipschitz_grid_envelope.py",
        "src/adc_research/theory/static_observation_reachability.py",
        "src/adc_research/evaluation/full_chain_code_envelope.py",
        "experiments/exp_036_physical_scan_intake/generate_fixture.py",
        "experiments/exp_036_physical_scan_intake/run.py",
        "configs/architectures/gu_behavioral_v1.yaml",
    )
    summary = {
        "scope": "synthetic_validation_of_static_scan_intake",
        "source_kind": "synthetic", "fit_records": 126, "holdout_records": 120,
        "condition_count": 2, "path_count": 3,
        "package_checks_passed": True, "physical_guarantee": False,
        "static_platform_records_checked": connection["platform_records_checked"],
        "static_code_width_range": [connection["code_interval_width_minimum"], connection["code_interval_width_maximum"]],
        "negative_checks": negatives,
        "source_sha256": {s: hashlib.sha256((ROOT / s).read_bytes()).hexdigest() for s in source_paths},
        "manifest_sha256": package.report["manifest_sha256"],
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
