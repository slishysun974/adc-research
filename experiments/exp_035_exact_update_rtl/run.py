"""Synthesize the exact specialization with the unchanged EXP-034 flow."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys

from experiments.exp_034_generic_synthesis import run as synthesis

ROOT = synthesis.ROOT
SOURCES = synthesis.SOURCES[:-1] + (
    "rtl/gu_baseline/fixed_gated_lms_exact_candidate_a.sv",
    "rtl/gu_baseline/two_stage_adaptive_exact_candidate_a.sv",
    "experiments/exp_035_exact_update_rtl/cost_top.sv",
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--baseline", type=Path, default=Path("artifacts/runs/EXP_034/generic_staged_v1/summary.json"))
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    output.relative_to(ROOT / "artifacts/runs/EXP_035")
    output.mkdir(parents=True, exist_ok=True)
    baseline_path = (ROOT / args.baseline).resolve()
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    hashes = {s: hashlib.sha256((ROOT / s).read_bytes()).hexdigest() for s in SOURCES}
    # Five unmodified baseline RTL sources must match the reviewed comparison.
    for source in synthesis.SOURCES[:-1]:
        if hashes[source] != baseline["source_sha256"][source]:
            raise ValueError(f"Baseline RTL changed: {source}")
    env = os.environ.copy()
    tool_dir = ROOT / "artifacts/tooling/yowasp"
    env["PYTHONPATH"] = str(tool_dir)
    env["YOWASP_CACHE_DIR"] = str(ROOT / "artifacts/tooling/yowasp_cache")
    synthesis._run_yosys(["-V"], env, output / "tool_version.txt")
    version = (output / "tool_version.txt").read_text(encoding="utf-8").strip()
    dependencies = {d.metadata["Name"]: d.version for d in importlib.metadata.distributions(path=[str(tool_dir)])}
    if (version != baseline["tool_version"] or baseline["mapping_schedule"] != "staged"
            or baseline["synthesis_flags"] != synthesis.FLAGS
            or dependencies != baseline["local_tool_packages"]):
        raise ValueError("Comparison tool version or mapping flow differs")
    # Reuse the exact mapping implementation; substitutions are local to this
    # process. The historical sources and EXP-034 entry point stay untouched.
    synthesis.SOURCES = SOURCES
    result = synthesis.synthesize("online", output / "online", env, "staged")
    old = baseline["tops"]["online"]
    for key in ("input_bits", "output_bits", "sequential_bits", "observable_outputs"):
        if result[key] != old[key]:
            raise ValueError(f"Comparison boundary differs: {key}")
    comparison = {
        "baseline_summary": synthesis._relative(baseline_path),
        "baseline_summary_sha256": hashlib.sha256(baseline_path.read_bytes()).hexdigest(),
        "baseline_sources_unchanged": True,
        "baseline_total_generic_cells": old["total_generic_cells"],
        "exact_total_generic_cells": result["total_generic_cells"],
        "generic_cell_reduction_percent": 100*(1-result["total_generic_cells"]/old["total_generic_cells"]),
        "baseline_path_cells": old["longest_combinational_topological_path_cells"],
        "exact_path_cells": result["longest_combinational_topological_path_cells"],
        "scope": "same-flow generic structure; no technology area/timing/power claim",
    }
    summary = {
        "scope": "candidate_a_exact_update_generic_synthesis_v1",
        "tool_version": version, "python_version": sys.version,
        "local_tool_packages": dependencies,
        "synthesis_flags": synthesis.FLAGS, "mapping_schedule": "staged",
        "technology_library": None, "clock_constraint": None, "throughput_constraint": None,
        "source_sha256": hashes, "tops": {"online": result}, "comparison": comparison,
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(comparison, indent=2), flush=True)


if __name__ == "__main__":
    main()
