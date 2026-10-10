"""Generate an explicitly synthetic three-path, two-condition scan package.

Exact cubic voltages and their analytic slope bound exercise data intake.
They do not stand in for Cadence waveforms or measured chip characteristics.
"""
from __future__ import annotations

import csv
from fractions import Fraction
import hashlib
import json
from pathlib import Path

from adc_research.evaluation.physical_scan_package import COLUMNS, PATHS


def transfer(case_index: int, path: str, x: Fraction) -> Fraction:
    gain = Fraction(4) if case_index == 0 else Fraction(19, 5)
    cubic = Fraction(1, 5) if path == "stage1_auxiliary" else Fraction(2, 5)
    offset = Fraction(0) if case_index == 0 else Fraction(1, 200)
    return gain*x + cubic*x**3 + offset


def generate_fixture(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    conditions = []
    for index, case_id in enumerate(("synthetic_case_a", "synthetic_case_b")):
        conditions.append({
            "id": case_id, "process": "synthetic parameter set; no process model",
            "supply": "synthetic; no supply model", "temperature": "synthetic; no thermal model",
            "channel": str(index), "trim": "none", "noise": "none; bounded export error only",
            "history": "static memoryless synthetic function", "decision_time": "static evaluation",
            "paths": {path: {
                "input_node": "synthetic amplifier input", "output_node": f"synthetic {path} output",
                "slope_bound": "5", "slope_provenance": "analytic",
                "slope_domain": ["-501/1000", "501/1000"],
                "required_domain": ["-1/2", "1/2"],
            } for path in PATHS},
        })
    for split in ("fit", "holdout"):
        with (directory / f"{split}.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(COLUMNS)
            for index, case in enumerate(conditions):
                for path in PATHS:
                    for k in range(21 if split == "fit" else 20):
                        x = -Fraction(1, 2) + Fraction(k, 20)
                        if split == "holdout":
                            x += Fraction(1, 40)
                        input_error = Fraction(1, 100000)
                        actual_input = x + (input_error if k % 2 else -input_error)
                        value = transfer(index, path, actual_input)
                        output_error = Fraction(1, 10000)
                        writer.writerow((f"{split}:{index}:{path}:{k}", case["id"], path,
                                         str(x), str(input_error), str(value-output_error),
                                         str(value+output_error)))
    evidence = (
        "SYNTHETIC ONLY. No Cadence or chip data.\n"
        "g(x)=a*x+b*x^3+c, with a in {4,19/5}, b in {1/5,2/5},\n"
        "c in {0,1/200}; |x|<=501/1000. |g'(x)|<=4+(6/5)*(501/1000)^2<5.\n"
        "Each exported input has radius 1/100000 V; output interval radius is\n"
        "1/10000 V about the exact synthetic output at the actual input.\n"
        "All rows are exact rational numbers. fit and holdout use separate\n"
        "input locations, fixed before envelope construction. No random noise.\n"
    )
    (directory / "evidence.txt").write_text(evidence, encoding="utf-8")
    def descriptor(name):
        return {"file": name, "sha256": hashlib.sha256((directory/name).read_bytes()).hexdigest()}
    manifest = {
        "schema_version": 1, "source": {"kind": "synthetic", "description": "EXP-036 exact cubic scan fixture"},
        "units": {"input": "V", "output": "V", "definition": "differential", "volts_per_normalized_unit": "1/2"},
        "model": "static_memoryless", "error_semantics": "all_allowed_outputs",
        "fit": descriptor("fit.csv"), "holdout": descriptor("holdout.csv"),
        "evidence": descriptor("evidence.txt"),
        "evidence_description": "Exact synthetic formula and analytic slope/error premises; not physical evidence",
        "conditions": conditions,
    }
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest_path
