"""Check saved functional, routed timing, constraint and source evidence."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def reject_simulation_diagnostics(data: str, source: Path) -> None:
    # A PASS marker can coexist with XSim scheduling or SDF warnings. Such a
    # run is diagnostic evidence, not a successful timing replay.
    failure = re.search(r"fatal:|timing violation|warning:|error:|\$setuphold|\$recrem", data, re.I)
    assert failure is None, f"simulation diagnostic in {source}: {failure.group(0) if failure else ''}"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("implementation", type=Path)
    parser.add_argument("--rtl-run", required=True, type=Path)
    parser.add_argument("--sdf-tag", default="routed")
    args = parser.parse_args()
    impl, rtl = args.implementation.resolve(), args.rtl_run.resolve()
    im, rm = (json.loads(read(p / "manifest.json")) for p in (impl, rtl))
    latency = im["contract"].get("latency_cycles", im["contract"]["compute_cycles"])
    assert latency == rm["contract"].get("latency_cycles", rm["contract"]["compute_cycles"])
    assert im["vectors_sha256"] == rm["vectors_sha256"]
    assert hashlib.sha256((impl / "online.txt").read_bytes()).hexdigest() == im["vectors_sha256"]
    names = ("fixed_pwl_candidate_a.sv", "two_stage_fixed_candidate_a.sv",
        "fixed_gated_lms_exact_candidate_a.sv", "two_stage_multicycle_candidate_a.sv",
        "two_stage_adaptive_exact_candidate_a.sv", "tb_multicycle.sv")
    reused = {}
    for name in names:
        ih = hashlib.sha256((impl / "sources" / name).read_bytes()).hexdigest()
        rh = hashlib.sha256((rtl / "sources" / name).read_bytes()).hexdigest()
        assert ih == rh, name
        reused[name] = ih
    for rel, expected in im["source_sha256"].items():
        # Normalize manifests created on either Windows or Linux.
        name = rel.replace("\\", "/").split("/")[-1]
        assert hashlib.sha256((impl / "sources" / name).read_bytes()).hexdigest() == expected
    markers = {
        rtl / "logs/multicycle.log": f"MULTICYCLE_PASS vectors=8263 replay=128 reset_phases={latency} cycles={latency}",
        rtl / "logs/original_online.log": "8263 sequential oracle vectors passed",
        rtl / "logs/exact_arithmetic.log": "173872 deltas, 869360 saturation probes, 173872 disabled probes passed",
        impl / f"logs/{args.sdf_tag}_simulate.log": f"MULTICYCLE_COST_PASS vectors=8263 replay=128 reset_phases={latency-1}",
    }
    for path, marker in markers.items():
        data = read(path)
        assert marker in data, str(path)
        reject_simulation_diagnostics(data, path)
    for stage in ("compile", "elaborate"):
        path = impl / f"logs/{args.sdf_tag}_{stage}.log"
        data = read(path)
        reject_simulation_diagnostics(data, path)
        if stage == "elaborate":
            assert re.search(r'SDF backannotation was successful[^\n]*routed\.sdf', data), str(path)
    assert "multicycle mismatch pass=0 row=0" in read(rtl / "logs/negative.log")
    assert "cost mismatch pass=0 row=0" in read(impl / f"logs/{args.sdf_tag}_negative.log")
    assert "MULTICYCLE_COST_PASS" not in read(impl / f"logs/{args.sdf_tag}_negative.log")
    timing = json.loads(read(impl / "timing_result.json"))
    assert timing["wns_ns"] >= 0 and timing["whs_ns"] >= 0
    assert timing["period_ns"] == 10 and timing["compute_cycles"] == 16
    assert timing.get("latency_cycles", timing["compute_cycles"]) == latency
    assert timing["initiation_interval_cycles"] == latency+1
    constraints = dict(re.findall(r"checking (\w+) \((\d+)\)", read(impl / "reports/check_timing.rpt")))
    assert len(constraints) == 12 and all(int(v) == 0 for v in constraints.values())
    assert "# of nets with routing errors.......... :           0" in read(impl / "reports/route_status.rpt")
    assert "Violations found: 0" in read(impl / "reports/methodology.rpt")
    assert "MULTICYCLE_ROUTED_TIMING_PASS" in read(impl / "logs/vivado.log")
    summary = {
        "timing": timing, "constraint_checks": constraints,
        "rtl_reference_run": str(rtl), "same_rtl_sha256": reused,
        "rtl_full_state_vectors": 8263, "rtl_reset_replay": 128,
        "rtl_abort_phases": latency, "sdf_output_vectors": 8263,
        "sdf_reset_replay": 128, "sdf_abort_phases": latency-1, "sdf_tag": args.sdf_tag,
        "negative_controls_rejected": True,
        "route_and_methodology_pass": True,
        "boundary": "Zynq xc7z020, assumed IO contract; no board pin contract or Artix-7 signoff",
    }
    (impl / "validation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
