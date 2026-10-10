"""Record completed Icarus RTL/netlist checks without changing synthesis data.

Success logs must have the expected Python record counts. An explicit option
records an incomplete online gate attempt without claiming it passed.
The compiler version comes from the generated VVP files. No WSL is invoked.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from .run import ROOT, _relative


def record(output: Path, online_gate_rows: int = 128,
           online_gate_directory: Path | None = None,
           allow_incomplete_online_gate: bool = False,
           online_gate_reset_rows: int = 128) -> dict:
    output = output.resolve()
    _relative(output)
    summary_path = output / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    for source, expected in summary["source_sha256"].items():
        if hashlib.sha256((ROOT / source).read_bytes()).hexdigest() != expected:
            raise ValueError(f"Candidate source changed since synthesis: {source}")
    results = {}
    if not 1 <= online_gate_rows <= 8263 or not 1 <= online_gate_reset_rows <= 8263:
        raise ValueError("Online gate window must be between 1 and 8263 rows")
    for name, online in (("frozen", 0), ("online", 1)):
        phases = {}
        for phase, compiled in (("rtl", "rtl_tb.vvp"), ("gate", "gates_tb.vvp")):
            expected_count = (8391 if phase == "rtl" else online_gate_rows+online_gate_reset_rows) if online else 18432
            directory = online_gate_directory if online and phase == "gate" and online_gate_directory else output/name
            _relative(directory)
            log_path = directory / f"{phase}_simulation.log"
            text = log_path.read_text(encoding="utf-8")
            pattern = rf"gu_cost_top online={online} (\d+) Python code records passed"
            matches = re.findall(pattern, text)
            passed = matches == [str(expected_count)] and "FATAL" not in text
            exit_status_path = directory/"gate_exit_status.txt"
            if phase == "gate" and exit_status_path.exists():
                if passed and exit_status_path.read_text().strip() != "0":
                    raise ValueError("Gate simulation reported a nonzero exit status")
            incomplete = (allow_incomplete_online_gate and online and phase == "gate"
                          and not matches and "FATAL" not in text)
            if not passed and not incomplete:
                raise ValueError(f"Missing or unexpected success result: {log_path}")
            with (directory / compiled).open(encoding="utf-8") as stream:
                header = "".join(stream.readline() for _ in range(40))
            version = re.search(r':ivl_version "([^"]+)";', header)
            if not version:
                raise ValueError("Icarus compiler version not present in VVP header")
            limit_match = re.search(r'\.param/l "FIRST_PASS_LIMIT"[^\n]*C4<([01]+)>', header)
            compiled_limit = int(limit_match.group(1), 2) if limit_match else 1000000
            required_limit = online_gate_rows if online and phase == "gate" else 1000000
            if compiled_limit != required_limit:
                raise ValueError(f"Unexpected compiled record limit: {compiled}")
            reset_match = re.search(r'\.param/l "RESET_PASS_LIMIT"[^\n]*C4<([01]+)>', header)
            reset_limit = int(reset_match.group(1), 2) if reset_match else 128
            required_reset = online_gate_reset_rows if online and phase == "gate" else 128
            if reset_limit != required_reset:
                raise ValueError(f"Unexpected compiled reset record limit: {compiled}")
            first_rows = (8263 if phase == "rtl" else online_gate_rows) if online else 18432
            reset_rows = required_reset if online else 0
            phases[phase] = {"passed": passed, "checked_records": expected_count if passed else None,
                             "outcome": "passed" if passed else "incomplete_without_success_marker",
                             "requested_records": expected_count,
                             "icarus_version": version.group(1),
                             "compiled_first_pass_limit": compiled_limit,
                             "first_pass_rows": first_rows if passed else None,
                             "reset_prefix_replay_rows": reset_rows if passed else None,
                             "compiled_reset_pass_limit": reset_limit,
                             "idle_clocks_checked": expected_count if online and passed else (None if online else 0),
                             "log": _relative(log_path),
                             "log_sha256": hashlib.sha256(log_path.read_bytes()).hexdigest(),
                             "compiled_vvp_sha256": hashlib.sha256((directory/compiled).read_bytes()).hexdigest(),
                             "gate_verilog_sha256": hashlib.sha256((directory/"gates.v").read_bytes()).hexdigest() if phase == "gate" else None}
        source_vectors = ROOT / summary["tops"][name]["native_replay"]["source_vectors"]
        vector_digest = hashlib.sha256(source_vectors.read_bytes()).hexdigest()
        if vector_digest != summary["tops"][name]["native_replay"]["source_vector_sha256"]:
            raise ValueError("Reviewed Python vectors changed since native replay")
        result = {"scope": "finite_icarus_zero_delay_code_checks_not_formal_or_timing_proof",
                  "phases": phases, "reference_rows": 8263 if online else 18432,
                  "online_gate_first_pass_limit": online_gate_rows if online else None,
                  "final_invalid_word_checks_per_phase": 2,
                  "source_vector_sha256": vector_digest,
                  "original_gate_verilog_sha256": hashlib.sha256((output/name/"gates.v").read_bytes()).hexdigest(),
                  "current_reproducible_testbench_sha256": hashlib.sha256((ROOT/"experiments/exp_034_generic_synthesis/tb_cost_tops.sv").read_bytes()).hexdigest()}
        if online_gate_directory and online:
            export_summary = online_gate_directory/"export_summary.json"
            if export_summary.exists():
                exported = json.loads(export_summary.read_text(encoding="utf-8"))
                original_digest = hashlib.sha256((output/name/"gates.json").read_bytes()).hexdigest()
                if exported["source_json_sha256"] != original_digest:
                    raise ValueError("Scalar export was not made from the reviewed gate graph")
                if exported["verilog_sha256"] != phases["gate"]["gate_verilog_sha256"]:
                    raise ValueError("Scalar export changed after serialization")
                if exported["cells_by_type"] != summary["tops"][name]["cell_counts"]:
                    raise ValueError("Scalar serialization did not preserve the reviewed cells")
                result["scalar_export"] = exported
        results[name] = result
    # Write summaries only after every required result has been validated.
    for name, result in results.items():
        summary["tops"][name]["icarus_validation"] = result
        summary["tops"][name]["post_synthesis_simulation"] = (
            "native_and_icarus_zero_delay_code_checks_passed" if result["phases"]["gate"]["passed"]
            else "native_replay_and_icarus_rtl_passed_icarus_gate_incomplete")
        (output/name/"summary.json").write_text(json.dumps(summary["tops"][name], indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (output/"icarus_validation.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--online-gate-rows", type=int, default=128)
    parser.add_argument("--online-gate-directory", type=Path)
    parser.add_argument("--online-gate-reset-rows", type=int, default=128)
    parser.add_argument("--allow-incomplete-online-gate", action="store_true")
    args = parser.parse_args()
    directory = ROOT/args.online_gate_directory if args.online_gate_directory else None
    print(json.dumps(record(ROOT / args.output, args.online_gate_rows, directory,
                            args.allow_incomplete_online_gate, args.online_gate_reset_rows), indent=2))
