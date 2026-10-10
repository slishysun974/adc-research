"""Record only successful, hash-aligned EXP-035 RTL and gate checks."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from .run import ROOT


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(path: Path, pattern: str) -> list[str]:
    matches = re.findall(pattern, path.read_text(encoding="utf-8"))
    if not matches:
        raise ValueError(f"Missing successful result: {path}")
    return matches


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    output.relative_to(ROOT / "artifacts/runs/EXP_035")
    summary_path = output / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    for source, digest in summary["source_sha256"].items():
        if sha(ROOT / source) != digest:
            raise ValueError(f"Source changed since synthesis: {source}")
    vectors = ROOT / "artifacts/runs/EXP_032/candidate_a_q22/vectors.txt"
    rows = len(vectors.read_text(encoding="ascii").splitlines())
    if rows != 8263:
        raise ValueError("Reviewed continuous vector count changed")
    logs = [output / "rtl" / name for name in ("arithmetic.log", "online.log", "cost.log")]
    require(logs[0], r"exact arithmetic: 173872 deltas, 869360 saturation probes, 173872 disabled probes passed")
    require(logs[1], r"two_stage_adaptive_exact_candidate_a 8263 sequential oracle vectors passed")
    require(logs[2], r"gu_cost_top online=1 8391 Python code records passed")
    gate_dir = output / "scalar/full_online"
    if (gate_dir / "gate_exit_status.txt").read_text().strip() != "0":
        raise ValueError("HDL netlist simulation did not complete successfully")
    gate_log = gate_dir / "gate_simulation.log"
    require(gate_log, r"gu_cost_top online=1 8391 Python code records passed")
    require(gate_log, r"progress online=1 pass=1 records=128 ")
    export = json.loads((gate_dir / "export_summary.json").read_text())
    if (export["source_json_sha256"] != sha(output / "online/gates.json")
            or export["verilog_sha256"] != sha(gate_dir / "gates.v")
            or export["total_cells"] != 21121 or export["state_bits"] != 184):
        raise ValueError("HDL netlist graph differs from synthesized graph")
    native = summary["tops"]["online"]["native_replay"]
    if (not native["passed"] or not native["corrupt_expected_code_rejected"]
            or native["source_vector_sha256"] != sha(vectors)
            or native["gate_netlist_sha256"] != export["source_json_sha256"]):
        raise ValueError("Native replay evidence differs")
    sources = [
        "experiments/exp_035_exact_update_rtl/run.py",
        "experiments/exp_035_exact_update_rtl/tb_exact_arithmetic.sv",
        "experiments/exp_035_exact_update_rtl/tb_exact_online.sv",
        "experiments/exp_035_exact_update_rtl/simulate.sh",
        "experiments/exp_035_exact_update_rtl/simulate_netlist.sh",
        "experiments/exp_035_exact_update_rtl/record_validation.py",
        "experiments/exp_034_generic_synthesis/run.py",
        "experiments/exp_034_generic_synthesis/tb_cost_tops.sv",
        "experiments/exp_034_generic_synthesis/export_scalar.py",
        "artifacts/tooling/yowasp/yowasp_yosys/share/simcells.v",
    ]
    result = {
        "scope": "candidate_a_exact_update_finite_RTL_and_HDL_gate_validation",
        "rtl_delta_cases": 173872, "rtl_enabled_saturation_probes": 869360,
        "rtl_disabled_probes": 173872,
        "rtl_full_state_records": 8263, "rtl_full_state_idle_clocks": 8263,
        "rtl_cost_records": 8391, "rtl_cost_idle_clocks": 8391,
        "hdl_gate_continuous_records": 8263, "hdl_gate_reset_records": 128,
        "hdl_gate_idle_clocks": 8391,
        "native_corrupt_expected_code_rejected": True,
        "vector_sha256": sha(vectors),
        "validation_source_sha256": {s: sha(ROOT / s) for s in sources},
        "evidence_sha256": {p.relative_to(ROOT).as_posix(): sha(p)
            for p in [*logs, gate_log, gate_dir / "gate_exit_status.txt",
                      gate_dir / "export_summary.json", gate_dir / "gates.v"]},
        "formal_netlist_equivalence": "not_performed",
        "physical_validation": "not_performed",
    }
    (output / "validation.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    summary["validation"] = result
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
