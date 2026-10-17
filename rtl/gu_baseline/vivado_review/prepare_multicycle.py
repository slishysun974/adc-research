"""Freeze the multicycle candidate and reuse the published digital vectors."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--part", default="xc7a100tcsg324-1")
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    (out / "sources").mkdir()
    (out / "logs").mkdir()
    paths = [ROOT / "rtl/gu_baseline" / n for n in (
        "fixed_pwl_candidate_a.sv", "two_stage_fixed_candidate_a.sv",
        "fixed_gated_lms_exact_candidate_a.sv", "two_stage_multicycle_candidate_a.sv",
        "two_stage_adaptive_exact_candidate_a.sv", "fixed_gated_lms_candidate_a.sv",
        "gated_product_candidate_a.sv")]
    paths += [HERE / n for n in ("multicycle_cost_top.sv", "tb_multicycle.sv",
        "build_multicycle.tcl", "multicycle.xdc", "prepare_multicycle.py", "simulate_multicycle.sh",
        "tb_multicycle_cost.sv", "simulate_routed.sh", "validate_multicycle.py")]
    paths += [ROOT / "experiments/exp_035_exact_update_rtl" / n for n in (
        "tb_exact_arithmetic.sv", "tb_exact_online.sv")]
    for p in paths:
        shutil.copyfile(p, out / "sources" / p.name)
    archive = ROOT / "docs/reports/circuit_review_2026-10-11/ADC_Circuit_Review_Package.zip"
    with ZipFile(archive) as z:
        data = z.read("hardware/vectors/online.txt")
    (out / "online.txt").write_bytes(data)
    negative = data.decode("ascii").splitlines()
    fields = negative[0].split()
    fields[6] = str(int(fields[6]) ^ 1)
    negative[0] = " ".join(fields)
    (out / "negative.txt").write_text("\n".join(negative) + "\n", encoding="ascii")
    manifest = {
        "source_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        "vectors_sha256": hashlib.sha256(data).hexdigest(),
        "vector_source": "published ZIP hardware/vectors/online.txt; no new model or training",
        "vectors": len(data.splitlines()),
        "contract": {"compute_cycles": 16, "latency_cycles": 39, "initiation_interval_cycles": 40,
            "update_division": "8 parallel restoring /125, 21 bits; exact original biased numerator and low 14 quotient bits",
            "maximum_dsp_blocks": 0,
            "flatten_hierarchy": "full",
            "period_ns": 10, "part": args.part,
            "commit": "both banks simultaneously, outputs computed with old state",
            "reset": "synchronous high, aborts transaction and resets both banks; ready rises one edge after release",
            "invalid": "done pulse, valid_out=0, code/gates/learning=0, banks held"},
        "validation_budget": "one full 8263-row replay plus 128 reset replay per simulator/configuration; 39 RTL and 38 SDF abort phases; original exact arithmetic and original online regression; corrupted-row negative control; one routed implementation (new attempt in a new directory if repair is needed)",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"run": str(out), "vectors": manifest["vectors"]}))


if __name__ == "__main__":
    main()
