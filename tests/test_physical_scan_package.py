"""Evidence intake must distinguish coverage, contradiction and uncertainty."""
from __future__ import annotations

import csv
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from adc_research.evaluation.physical_scan_package import (
    PATHS, RationalScanEnvelope, ScanPackageError, audit_scan_package,
)
from adc_research.theory.lipschitz_grid_envelope import LipschitzGridEnvelope
from adc_research.theory.static_observation_reachability import ClosedInterval
from experiments.exp_036_physical_scan_intake.generate_fixture import generate_fixture, transfer


class PhysicalScanPackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.manifest_path = generate_fixture(self.directory)
        self.manifest = json.loads(self.manifest_path.read_text())

    def save(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")

    def edit_csv(self, split, edit):
        path = self.directory / f"{split}.csv"
        with path.open(newline="") as stream:
            reader = csv.DictReader(stream)
            columns, rows = reader.fieldnames, list(reader)
        edit(rows)
        with path.open("w", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)
        self.manifest[split]["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.save()

    def test_complete_independent_holdout_is_covered_but_not_physical_evidence(self):
        package = audit_scan_package(self.manifest_path)
        self.assertTrue(package.report["package_checks_passed"])
        self.assertFalse(package.report["physical_guarantee"])
        self.assertEqual(len(package.envelopes), 6)
        self.assertEqual(sum(g["holdout_counts"]["covered"] for g in package.report["groups"]), 120)
        for index, case in enumerate(("synthetic_case_a", "synthetic_case_b")):
            for path in PATHS:
                exact = package.envelopes[(case, path)]
                for k in range(100):
                    x = -Fraction(1, 2) + Fraction(k, 100)
                    low, high = exact.voltage_bounds(x, x)
                    self.assertLessEqual(low, transfer(index, path, x))
                    self.assertLessEqual(transfer(index, path, x), high)

    def test_hash_units_conditions_and_slope_provenance_are_required(self):
        edits = [
            lambda d: d["fit"].update(sha256="0"*64),
            lambda d: d["units"].update(input="mV"),
            lambda d: d["conditions"][0].pop("decision_time"),
            lambda d: d["conditions"][0]["paths"]["stage1_main"].update(slope_provenance="grid_fitted"),
            lambda d: d["conditions"][0]["paths"]["stage1_main"].update(slope_bound=5.0),
            lambda d: d.update(error_semantics="three_sigma"),
            lambda d: d.update(model="one_pole_memory"),
        ]
        pristine = json.dumps(self.manifest)
        for edit in edits:
            with self.subTest(edit=edit):
                self.manifest = json.loads(pristine)
                edit(self.manifest)
                self.save()
                with self.assertRaises(ScanPackageError):
                    audit_scan_package(self.manifest_path)

    def test_holdout_outside_domain_and_reuse_of_fit_location_fail(self):
        self.edit_csv("holdout", lambda rows: rows[0].update(input_voltage="1/2"))
        with self.assertRaisesRegex(ScanPackageError, "reuses a fit input"):
            audit_scan_package(self.manifest_path)
        self.edit_csv("holdout", lambda rows: rows[0].update(input_voltage="3/5"))
        with self.assertRaisesRegex(ScanPackageError, "outside declared slope domain"):
            audit_scan_package(self.manifest_path)

    def test_partial_overlap_does_not_pass_or_assert_a_contradiction(self):
        package = audit_scan_package(self.manifest_path)
        low, high = package.envelopes[("synthetic_case_a", "stage1_main")].voltage_bounds(
            -Fraction(19, 40)-Fraction(1, 100000), -Fraction(19, 40)+Fraction(1, 100000))
        self.edit_csv("holdout", lambda rows: rows[0].update(
            output_lower=str((low+high)/2), output_upper=str(high+Fraction(1, 100))))
        package = audit_scan_package(self.manifest_path)
        counts = package.report["groups"][0]["holdout_counts"]
        self.assertEqual(counts["inconclusive"], 1)
        self.assertEqual(counts["contradiction"], 0)
        self.assertFalse(package.report["package_checks_passed"])
        with self.assertRaisesRegex(ScanPackageError, "unresolved holdout"):
            package.path_envelope("stage1_main", ("synthetic_case_a",))

    def test_disjoint_holdout_error_interval_is_a_contradiction(self):
        self.edit_csv("holdout", lambda rows: rows[0].update(output_lower="10", output_upper="11"))
        package = audit_scan_package(self.manifest_path)
        self.assertEqual(package.report["groups"][0]["holdout_counts"]["contradiction"], 1)
        self.assertFalse(package.report["package_checks_passed"])

    def test_repeated_nominal_input_cannot_hide_history_dependence(self):
        def edit(rows):
            changed = dict(rows[0], record_id="changed-history", output_lower="10", output_upper="11")
            rows.append(changed)
        self.edit_csv("fit", edit)
        with self.assertRaisesRegex(ScanPackageError, "contradicts static/error premises"):
            audit_scan_package(self.manifest_path)

    def test_distinct_conditions_are_unioned_not_intersected(self):
        package = audit_scan_package(self.manifest_path)
        combined = package.path_envelope("stage1_main", ("synthetic_case_a", "synthetic_case_b"))
        query = ClosedInterval(-0.2, -0.1)
        bounds = combined(query)
        for case in ("synthetic_case_a", "synthetic_case_b"):
            individual = package.envelopes[(case, "stage1_main")](query)
            self.assertLessEqual(bounds.lower, individual.lower)
            self.assertGreaterEqual(bounds.upper, individual.upper)
        with self.assertRaises(ScanPackageError):
            package.path_envelope("stage1_main", ("unknown",))

    def test_input_error_transports_grid_intervals_by_exact_slope_bound(self):
        package = audit_scan_package(self.manifest_path)
        core = package.envelopes[("synthetic_case_a", "stage1_main")].envelope
        x = core.grid_inputs[0]
        measured = transfer(0, "stage1_main", x-Fraction(1, 100000))
        # The original measured band need not enclose g(nominal x). Its
        # transport by L*input_error must do so, with no decimal rounding.
        self.assertEqual(core.measured_outputs[0].lower, measured-Fraction(1, 10000)-Fraction(5, 100000))
        self.assertLessEqual(core.measured_outputs[0].lower, transfer(0, "stage1_main", x))
        self.assertGreaterEqual(core.measured_outputs[0].upper, transfer(0, "stage1_main", x))

    def test_nonbinary_decimal_bound_rounds_outward_only_at_adapter(self):
        exact_value = Fraction(1, 10)
        core = LipschitzGridEnvelope((Fraction(0), Fraction(1)),
            (ClosedInterval(exact_value, exact_value),)*2, Fraction(0))
        exact = RationalScanEnvelope(core, Fraction(1))
        self.assertEqual(exact.voltage_bounds(Fraction(1, 3), Fraction(1, 3)), (exact_value, exact_value))
        outward = exact(ClosedInterval(0.3, 0.3))
        self.assertLessEqual(Fraction.from_float(outward.lower), exact_value)
        self.assertGreaterEqual(Fraction.from_float(outward.upper), exact_value)
        self.assertLess(outward.lower, outward.upper)

    def test_declaring_cadence_cannot_automatically_certify_physical_premises(self):
        self.manifest["source"]["kind"] = "cadence"
        self.save()
        package = audit_scan_package(self.manifest_path)
        self.assertTrue(package.report["package_checks_passed"])
        self.assertFalse(package.report["physical_guarantee"])

    def test_rational_bounds_keep_error_bands_smaller_than_float_resolution(self):
        center, radius = Fraction(1, 10), Fraction(1, 10**25)
        core = LipschitzGridEnvelope((Fraction(0), Fraction(1)),
            (ClosedInterval(center-radius, center+radius),)*2, Fraction(0))
        exact = RationalScanEnvelope(core, Fraction(1))
        low, high = exact.voltage_bounds(Fraction(1, 3), Fraction(2, 3))
        self.assertEqual(high-low, 2*radius)
        self.assertLess(low, center)
        self.assertGreater(high, center)

    def test_missing_path_and_insufficient_requested_domain_fail(self):
        self.edit_csv("holdout", lambda rows: rows.__setitem__(slice(None),
            [r for r in rows if not (r["condition_id"] == "synthetic_case_b" and r["path"] == "stage2_main")]))
        with self.assertRaisesRegex(ScanPackageError, "missing fit/holdout"):
            audit_scan_package(self.manifest_path)
        self.manifest_path = generate_fixture(self.directory)
        self.manifest = json.loads(self.manifest_path.read_text())
        self.manifest["conditions"][0]["paths"]["stage2_main"]["required_domain"] = ["-3/5", "3/5"]
        self.save()
        with self.assertRaisesRegex(ScanPackageError, "does not cover required domain"):
            audit_scan_package(self.manifest_path)


if __name__ == "__main__":
    unittest.main()
