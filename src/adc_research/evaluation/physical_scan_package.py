"""Offline static-scan intake, with exact rational envelope arithmetic.

File provenance is recorded, not authenticated. A successful package check
cannot establish physical slope/measurement bounds or dynamic applicability.
The online calibration receives none of these analog or provenance fields.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from fractions import Fraction
import csv
import hashlib
import json
from math import isfinite, nextafter, inf
from pathlib import Path
from typing import Any, Mapping

from adc_research.theory.lipschitz_grid_envelope import LipschitzGridEnvelope
from adc_research.theory.static_observation_reachability import ClosedInterval

PATHS = ("stage1_main", "stage1_auxiliary", "stage2_main")
COLUMNS = ("record_id", "condition_id", "path", "input_voltage",
           "input_error", "output_lower", "output_upper")


class ScanPackageError(ValueError):
    """Declared scan evidence is incomplete or internally inconsistent."""


def _object(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ScanPackageError(f"{label} must be an object")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScanPackageError(f"{label} must be a nonempty string")
    return value


def _number(value: Any, label: str) -> Fraction:
    # Decimal strings retain the exact values in the export. A JSON float
    # would already have rounded away the source value before this parser.
    value = _text(value, label)
    try:
        result = Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise ScanPackageError(f"{label} must be a finite decimal or rational string") from error
    try:
        finite = isfinite(result)
    except OverflowError as error:
        raise ScanPackageError(f"{label} is outside supported finite voltage range") from error
    if not finite:
        raise ScanPackageError(f"{label} must be finite")
    return result


def _interval(values: Any, label: str) -> tuple[Fraction, Fraction]:
    if not isinstance(values, list) or len(values) != 2:
        raise ScanPackageError(f"{label} must contain two endpoint strings")
    lower, upper = (_number(v, label) for v in values)
    if lower > upper:
        raise ScanPackageError(f"{label} endpoints are reversed")
    return lower, upper


def _verified_file(directory: Path, item: Any, label: str) -> tuple[Path, dict]:
    item = _object(item, label)
    relative = _text(item.get("file"), f"{label}.file")
    path = (directory / relative).resolve()
    try:
        path.relative_to(directory)
    except ValueError as error:
        raise ScanPackageError(f"{label} escapes the package directory") from error
    if not path.is_file():
        raise ScanPackageError(f"{label} file is missing: {relative}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != item.get("sha256"):
        raise ScanPackageError(f"{label} SHA-256 mismatch: {relative}")
    return path, {"file": relative, "sha256": digest}


def _directed_float(value: Fraction, upward: bool) -> float:
    try:
        result = float(value)
    except OverflowError as error:
        raise ScanPackageError("envelope endpoint exceeds finite float range") from error
    if not isfinite(result):
        raise ScanPackageError("envelope endpoint cannot be represented by a finite float")
    exact_float = Fraction.from_float(result)
    if (upward and exact_float < value) or (not upward and exact_float > value):
        result = nextafter(result, inf if upward else -inf)
    if not isfinite(result):
        raise ScanPackageError("outward envelope endpoint exceeds finite float range")
    return result


@dataclass(frozen=True)
class RationalScanEnvelope:
    """Exact instance of the existing cone construction for parsed fractions."""
    envelope: LipschitzGridEnvelope
    volts_per_normalized_unit: Fraction

    def voltage_bounds(self, lower: Fraction, upper: Fraction) -> tuple[Fraction, Fraction]:
        if not isinstance(lower, Fraction) or not isinstance(upper, Fraction):
            raise TypeError("exact queries require Fraction endpoints")
        result = self.envelope(ClosedInterval(lower, upper))
        if not isinstance(result.lower, Fraction) or not isinstance(result.upper, Fraction):
            raise ScanPackageError("envelope computation left the exact rational arithmetic path")
        return result.lower, result.upper

    def __call__(self, query: ClosedInterval) -> ClosedInterval:
        """Adapter only: enclose exact bounds for the supplied binary endpoints.

        Upstream float arithmetic and downstream quantizers/FFT are not
        certified by this adapter. The scale is shared by all three paths.
        """
        def rational(value):
            return value if isinstance(value, Fraction) else Fraction(value)
        scale = self.volts_per_normalized_unit
        low, high = self.voltage_bounds(rational(query.lower)*scale,
                                       rational(query.upper)*scale)
        return ClosedInterval(_directed_float(low/scale, False),
                              _directed_float(high/scale, True))

    def rational_normalized_bounds(self, query: ClosedInterval) -> ClosedInterval:
        """Preserve exact source numbers throughout normalized voltage queries."""
        if not isinstance(query, ClosedInterval) or not all(
            isinstance(endpoint, Fraction) for endpoint in (query.lower, query.upper)
        ):
            raise TypeError("exact normalized queries require Fraction endpoints")
        scale = self.volts_per_normalized_unit
        low, high = self.voltage_bounds(query.lower*scale, query.upper*scale)
        return ClosedInterval(low/scale, high/scale)


@dataclass(frozen=True)
class ScanRow:
    record_id: str
    condition_id: str
    path: str
    input_voltage: Fraction
    input_error: Fraction
    output_lower: Fraction
    output_upper: Fraction


@dataclass(frozen=True)
class AuditedScanPackage:
    envelopes: Mapping[tuple[str, str], RationalScanEnvelope]
    report: dict[str, Any]

    def _selected_envelopes(self, path: str, condition_ids: tuple[str, ...]):
        if not self.report["package_checks_passed"]:
            raise ScanPackageError("unresolved holdout coverage prevents using this package")
        if path not in PATHS or not condition_ids or len(set(condition_ids)) != len(condition_ids):
            raise ScanPackageError("select a known path and distinct nonempty condition IDs")
        try:
            return tuple(self.envelopes[(condition, path)] for condition in condition_ids)
        except KeyError as error:
            raise ScanPackageError("selected condition is not in the package") from error

    def path_envelope(self, path: str, condition_ids: tuple[str, ...]):
        """Union selected conditions with outward float output endpoints."""
        selected = self._selected_envelopes(path, condition_ids)

        def combined(query: ClosedInterval) -> ClosedInterval:
            bounds = [envelope(query) for envelope in selected]
            return ClosedInterval(min(b.lower for b in bounds), max(b.upper for b in bounds))
        return combined

    def rational_path_envelope(self, path: str, condition_ids: tuple[str, ...]):
        """Union selected conditions while keeping every voltage a Fraction.

        Each selected condition must cover the full query. Package checks
        remain conditional evidence checks, never physical authentication.
        """
        selected = self._selected_envelopes(path, condition_ids)

        def combined(query: ClosedInterval) -> ClosedInterval:
            bounds = [envelope.rational_normalized_bounds(query) for envelope in selected]
            return ClosedInterval(min(b.lower for b in bounds), max(b.upper for b in bounds))
        return combined


def _read_rows(path: Path, condition_ids: set[str]) -> list[ScanRow]:
    rows = []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames != list(COLUMNS):
            raise ScanPackageError(f"CSV columns must be exactly {COLUMNS}: {path.name}")
        for raw in reader:
            if None in raw or any(v is None for v in raw.values()):
                raise ScanPackageError("CSV row has missing or extra fields")
            record = _text(raw["record_id"], "record_id")
            condition = _text(raw["condition_id"], "condition_id")
            path_name = raw["path"]
            if condition not in condition_ids or path_name not in PATHS:
                raise ScanPackageError(f"unknown condition/path in record {record}")
            x, error, lower, upper = (_number(raw[key], key) for key in COLUMNS[3:])
            if error < 0 or lower > upper:
                raise ScanPackageError(f"invalid error/output interval in record {record}")
            rows.append(ScanRow(record, condition, path_name, x, error, lower, upper))
    if not rows:
        raise ScanPackageError(f"empty CSV: {path.name}")
    return rows


def audit_scan_package(manifest_path: Path | str) -> AuditedScanPackage:
    """Check package consistency and independent finite holdout coverage.

    Mathematical results remain conditional on *supplied* all-domain slope,
    input/output error bounds and a static transfer for each declared case.
    """
    manifest_path = Path(manifest_path).resolve()
    directory = manifest_path.parent
    with manifest_path.open(encoding="utf-8-sig") as stream:
        document = _object(json.load(stream), "manifest")
    if type(document.get("schema_version")) is not int or document["schema_version"] != 1:
        raise ScanPackageError("unsupported scan schema_version")
    source = _object(document.get("source"), "source")
    if source.get("kind") not in ("synthetic", "cadence", "measurement"):
        raise ScanPackageError("source.kind must declare synthetic, cadence or measurement")
    source_description = _text(source.get("description"), "source.description")
    units = _object(document.get("units"), "units")
    if units.get("input") != "V" or units.get("output") != "V" or units.get("definition") != "differential":
        raise ScanPackageError("this schema requires explicit differential input/output volts")
    scale = _number(units.get("volts_per_normalized_unit"), "volts_per_normalized_unit")
    if scale <= 0:
        raise ScanPackageError("normalization scale must be positive")
    if document.get("model") != "static_memoryless":
        raise ScanPackageError("dynamic/time-state scans require a different model")
    if document.get("error_semantics") != "all_allowed_outputs":
        raise ScanPackageError("point intervals must claim all_allowed_outputs, not a confidence band")
    evidence_path, evidence_digest = _verified_file(directory, document.get("evidence"), "evidence")
    evidence_description = _text(document.get("evidence_description"), "evidence_description")
    fit_path, fit_digest = _verified_file(directory, document.get("fit"), "fit")
    holdout_path, holdout_digest = _verified_file(directory, document.get("holdout"), "holdout")
    if fit_path == holdout_path or fit_digest["sha256"] == holdout_digest["sha256"]:
        raise ScanPackageError("fit and holdout must be distinct data files")
    if evidence_path in (fit_path, holdout_path):
        raise ScanPackageError("slope/error evidence must be separate from scan rows")
    declarations = document.get("conditions")
    if not isinstance(declarations, list) or not declarations:
        raise ScanPackageError("conditions must be a nonempty list")
    cases = {}
    for declaration in declarations:
        case = _object(declaration, "condition")
        case_id = _text(case.get("id"), "condition.id")
        if case_id in cases:
            raise ScanPackageError("duplicate condition ID")
        for key in ("process", "supply", "temperature", "channel", "trim", "noise", "history", "decision_time"):
            _text(case.get(key), f"condition.{key}")
        paths = _object(case.get("paths"), "condition.paths")
        if set(paths) != set(PATHS):
            raise ScanPackageError("each condition must declare all three physical paths")
        cases[case_id] = case
    fit_rows = _read_rows(fit_path, set(cases))
    holdout_rows = _read_rows(holdout_path, set(cases))
    ids = [r.record_id for r in [*fit_rows, *holdout_rows]]
    if len(ids) != len(set(ids)):
        raise ScanPackageError("record IDs must be unique across fit and holdout")
    envelopes, results = {}, []
    for case_id, case in cases.items():
        for path in PATHS:
            key = (case_id, path)
            spec = _object(case["paths"][path], "path specification")
            slope = _number(spec.get("slope_bound"), "slope_bound")
            if slope < 0:
                raise ScanPackageError("slope_bound must be nonnegative")
            if spec.get("slope_provenance") not in ("assumed", "analytic", "circuit_analysis", "specification"):
                raise ScanPackageError("slope provenance must be explicit; a grid fit is not a bound")
            _text(spec.get("input_node"), "input_node")
            _text(spec.get("output_node"), "output_node")
            slope_domain = _interval(spec.get("slope_domain"), "slope_domain")
            requested_domain = _interval(spec.get("required_domain"), "required_domain")
            group = [r for r in fit_rows if (r.condition_id, r.path) == key]
            held = [r for r in holdout_rows if (r.condition_id, r.path) == key]
            if not group or not held:
                raise ScanPackageError(f"missing fit/holdout rows for {key}")
            if any(r.input_voltage-r.input_error < slope_domain[0] or
                   r.input_voltage+r.input_error > slope_domain[1] for r in [*group, *held]):
                raise ScanPackageError(f"input uncertainty outside declared slope domain: {key}")
            # If the actual excitation is x +/- e, transport its covered
            # output interval to nominal x by L*e before applying grid cones.
            grid = {}
            for row in group:
                low = row.output_lower-slope*row.input_error
                high = row.output_upper+slope*row.input_error
                if row.input_voltage in grid:
                    prior_low, prior_high = grid[row.input_voltage]
                    low, high = max(low, prior_low), min(high, prior_high)
                    if low > high:
                        raise ScanPackageError(f"repeated nominal input contradicts static/error premises: {key}")
                grid[row.input_voltage] = low, high
            xs = tuple(sorted(grid))
            if len(xs) < 2:
                raise ScanPackageError(f"at least two distinct fit inputs required: {key}")
            if requested_domain[0] < xs[0] or requested_domain[1] > xs[-1]:
                raise ScanPackageError(f"fit grid does not cover required domain: {key}")
            try:
                core = LipschitzGridEnvelope(xs, tuple(ClosedInterval(*grid[x]) for x in xs), slope)
            except ValueError as error:
                raise ScanPackageError(f"grid contradicts supplied slope: {key}") from error
            exact = RationalScanEnvelope(core, scale)
            envelopes[key] = exact
            counts = {"covered": 0, "inconclusive": 0, "contradiction": 0}
            records = []
            for row in held:
                if row.input_voltage in grid:
                    raise ScanPackageError(f"holdout reuses a fit input: {row.record_id}")
                try:
                    low, high = exact.voltage_bounds(row.input_voltage-row.input_error,
                                                    row.input_voltage+row.input_error)
                except ValueError as error:
                    raise ScanPackageError(f"holdout query outside fit domain: {row.record_id}") from error
                if row.output_upper < low or row.output_lower > high:
                    status = "contradiction"
                elif low <= row.output_lower and row.output_upper <= high:
                    status = "covered"
                else:
                    status = "inconclusive"
                counts[status] += 1
                records.append({"record_id": row.record_id, "status": status,
                                "predicted_voltage_interval": [str(low), str(high)],
                                "observed_voltage_interval": [str(row.output_lower), str(row.output_upper)]})
            results.append({"condition_id": case_id, "path": path,
                            "slope_bound": str(slope), "slope_provenance": spec["slope_provenance"],
                            "fit_records": len(group), "distinct_grid_inputs": len(xs),
                            "fit_domain": [str(xs[0]), str(xs[-1])],
                            "required_domain": [str(v) for v in requested_domain],
                            "holdout_counts": counts, "holdout_records": records})
    passed = all(r["holdout_counts"]["inconclusive"] == 0 and
                 r["holdout_counts"]["contradiction"] == 0 for r in results)
    report = {
        "scope": "static_scan_consistency_and_finite_holdout_audit",
        "schema_version": 1, "source_kind": source["kind"], "source_description": source_description,
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "files": {"fit": fit_digest, "holdout": holdout_digest, "evidence": evidence_digest},
        "evidence_description": evidence_description,
        "arithmetic": "exact rational from source strings; float adapter rounds endpoints outward",
        "volts_per_normalized_unit": str(scale),
        "conditions": [dict(case) for case in cases.values()], "groups": results,
        "package_checks_passed": passed, "physical_guarantee": False,
        "evidence_status": "source claims recorded; physical premises require independent review",
        "remaining_premises": ["all-domain slope and input/output error coverage",
                               "static memoryless applicability for every declared case",
                               "coverage of unlisted PVT/history/noise conditions is not claimed",
                               "upstream/downstream interval arithmetic and FFT are not certified"],
    }
    return AuditedScanPackage(envelopes, report)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        report = audit_scan_package(args.manifest).report
    except (ScanPackageError, OSError, json.JSONDecodeError) as error:
        report = {"package_checks_passed": False, "physical_guarantee": False,
                  "error": str(error)}
    serialized = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        # Keep all source package files read-only, including malformed ones
        # whose descriptors could not be retained in a successful report.
        if args.output.resolve().is_relative_to(args.manifest.resolve().parent):
            print("Audit output must be outside the source package directory; no file was written")
            raise SystemExit(1)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized)
    raise SystemExit(0 if report["package_checks_passed"] else 1)


if __name__ == "__main__":
    main()
