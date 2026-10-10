"""Synthesize the existing candidate with a reproducible generic gate boundary.

No technology library, delay model, four-way extractor, or physical throughput
is supplied. Cell counts and topological depth are structural diagnostics.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[2]
SOURCES = (
    "rtl/gu_baseline/gated_product_candidate_a.sv",
    "rtl/gu_baseline/fixed_pwl_candidate_a.sv",
    "rtl/gu_baseline/two_stage_fixed_candidate_a.sv",
    "rtl/gu_baseline/fixed_gated_lms_candidate_a.sv",
    "rtl/gu_baseline/two_stage_adaptive_candidate_a.sv",
    "experiments/exp_034_generic_synthesis/cost_tops.sv",
)
TOPS = {"frozen": "gu_frozen_cost_top", "online": "gu_online_cost_top"}
FLAGS = "-flatten -noabc -noalumacc"


def _run_yosys(arguments: list[str], env: dict[str, str], output: Path) -> None:
    command = [sys.executable, "-c",
               "import sys; from yowasp_yosys import run_yosys; "
               "raise SystemExit(run_yosys(sys.argv[1:]))", *arguments]
    with output.open("w", encoding="utf-8") as stream:
        subprocess.run(command, cwd=ROOT, env=env, stdout=stream,
                       stderr=subprocess.STDOUT, check=True)


def _relative(path: Path) -> str:
    resolved = path.resolve()
    # Restrict all synthesis outputs to this research workspace.
    relative = resolved.relative_to(ROOT)
    if any(c.isspace() for c in relative.as_posix()) or '"' in relative.as_posix():
        raise ValueError("Yosys output paths must not contain whitespace or quotes")
    return relative.as_posix()


def synthesize(name: str, output: Path, env: dict[str, str], mapping: str) -> dict:
    top = TOPS[name]
    output.mkdir(parents=True, exist_ok=True)
    destination = _relative(output)
    commands = [
        "read_verilog -sv " + " ".join(SOURCES),
        # The end label is exclusive: stop at 'fine' after coarse synthesis.
        f"synth -top {top} {FLAGS} -run begin:fine",
        "delete t:$scopeinfo",  # Source-scope metadata, not hardware.
        "check -assert",
        f"tee -o {destination}/coarse_stat.json stat -json -width",
        f"write_json {destination}/coarse.json",
    ]
    if mapping == "staged":
        # Fold constants before expanding the next level of divider/add logic.
        # This is a mapping schedule, not an arithmetic or RTL modification.
        commands += ["opt -fast -full", "memory_map", "opt -full"]
        for _ in range(12):
            commands += ["techmap -max_iter 1", "opt -fast"]
        commands += ["techmap -assert", "opt -fast"]
    else:
        commands += [f"synth -top {top} {FLAGS} -run fine:check"]
    commands += [
        "check -assert",
        f"tee -o {destination}/gate_stat.json stat -json",
        f"write_json {destination}/gates.json",
        f"write_verilog -noattr {destination}/gates.v",
        "ltp -noff",
        "",
    ]
    script = "\n".join(commands)
    script_path = output / "synth.ys"
    script_path.write_text(script, encoding="utf-8")
    start = time.monotonic()
    _run_yosys(["-Q", "-T", "-s", _relative(script_path)], env,
               output / "synthesis.log")
    elapsed = time.monotonic() - start
    gates = json.loads((output / "gates.json").read_text(encoding="utf-8"))
    module = gates["modules"][top]
    counts = Counter(cell["type"] for cell in module["cells"].values())
    unsupported = [kind for kind in counts if not kind.startswith("$_")]
    if unsupported:
        raise RuntimeError(f"Unmapped cells remain: {unsupported}")
    latch_cells = sum(count for kind, count in counts.items() if "LATCH" in kind)
    if latch_cells:
        raise RuntimeError(f"Unexpected latch cells: {latch_cells}")
    sequential = sum(count for kind, count in counts.items() if "DFF" in kind)
    if sequential != (184 if name == "online" else 0):
        raise RuntimeError(f"Unexpected retained state-bit count: {sequential}")
    log = (output / "synthesis.log").read_text(encoding="utf-8")
    depths = re.findall(r"longest topological path.*?length[= :]+(\d+)",
                        log, flags=re.IGNORECASE)
    result = {
        "top": top,
        "mapping_schedule": mapping,
        "observable_outputs": {"valid_out": 1, "final_code": 12},
        "coefficient_boundary": ("eight external unsigned Q1.10 inputs; storage excluded"
                                 if name == "frozen" else "eight internal Q22 accumulators"),
        "input_bits": sum(len(p["bits"]) for p in module["ports"].values()
                          if p["direction"] == "input"),
        "output_bits": sum(len(p["bits"]) for p in module["ports"].values()
                           if p["direction"] == "output"),
        "total_generic_cells": sum(counts.values()),
        "sequential_bits": sequential,
        "combinational_cells": sum(counts.values()) - sequential,
        "cell_counts": dict(sorted(counts.items())),
        "longest_combinational_topological_path_cells": int(depths[-1]) if depths else None,
        "coarse_statistics": json.loads((output / "coarse_stat.json").read_text(encoding="utf-8")),
        "gate_statistics": json.loads((output / "gate_stat.json").read_text(encoding="utf-8")),
        "synthesis_seconds_host_only": elapsed,
        "structural_check_passed": True,
        "post_synthesis_simulation": "not_run_by_this_command",
        "artifacts": destination,
    }
    (output / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--top", choices=[*TOPS, "all"], default="all")
    parser.add_argument("--mapping", choices=("staged", "direct"), default="staged")
    parser.add_argument("--tool-dir", type=Path, default=ROOT / "artifacts/tooling/yowasp")
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    _relative(output)
    output.mkdir(parents=True, exist_ok=True)
    tool_dir = args.tool_dir.resolve()
    env = os.environ.copy()
    env["PYTHONPATH"] = str(tool_dir)
    env["YOWASP_CACHE_DIR"] = str(ROOT / "artifacts/tooling/yowasp_cache")
    _run_yosys(["-V"], env, output / "tool_version.txt")
    version = (output / "tool_version.txt").read_text(encoding="utf-8").strip()
    dependencies = {}
    for dist in importlib.metadata.distributions(path=[str(tool_dir)]):
        dependencies[dist.metadata["Name"]] = dist.version
    metadata = {
        "scope": "candidate_a_code_only_generic_synthesis_v1",
        "tool_version": version,
        "python_version": sys.version,
        "local_tool_packages": dict(sorted(dependencies.items())),
        "synthesis_flags": FLAGS,
        "mapping_schedule": args.mapping,
        "technology_library": None,
        "clock_constraint": None,
        "throughput_constraint": None,
        "source_sha256": {s: hashlib.sha256((ROOT / s).read_bytes()).hexdigest()
                          for s in SOURCES},
        "tops": {},
    }
    for name in TOPS if args.top == "all" else (args.top,):
        print(f"Synthesizing {TOPS[name]}...", flush=True)
        result = synthesize(name, output / name, env, args.mapping)
        metadata["tops"][name] = result
        print(json.dumps({k: result[k] for k in (
            "top", "total_generic_cells", "sequential_bits",
            "longest_combinational_topological_path_cells")}), flush=True)
    (output / "summary.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
