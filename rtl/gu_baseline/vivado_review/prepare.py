"""Freeze an independent, portable Vivado review workspace around existing RTL."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
RTL = (
    "rtl/gu_baseline/gated_product_candidate_a.sv",
    "rtl/gu_baseline/fixed_pwl_candidate_a.sv",
    "rtl/gu_baseline/two_stage_fixed_candidate_a.sv",
    "rtl/gu_baseline/fixed_gated_lms_candidate_a.sv",
    "rtl/gu_baseline/fixed_gated_lms_exact_candidate_a.sv",
    "rtl/gu_baseline/two_stage_adaptive_exact_candidate_a.sv",
    "experiments/exp_035_exact_update_rtl/cost_top.sv",
    "experiments/exp_035_exact_update_rtl/tb_exact_arithmetic.sv",
    "experiments/exp_035_exact_update_rtl/tb_exact_online.sv",
)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    if (output / "manifest.json").exists():
        raise SystemExit("Refusing to overwrite a frozen review run; choose a new directory")
    for sub in ("sources", "vectors", "reports", "netlists", "checkpoints", "schematics", "logs", "sim"):
        (output / sub).mkdir(parents=True, exist_ok=True)
    sources = {}
    for rel in RTL:
        source = ROOT / rel
        target = output / "sources" / source.name
        shutil.copyfile(source, target)
        sources[rel] = hashlib.sha256(source.read_bytes()).hexdigest()
    for name in ("tb_review_cost.sv", "tb_review_bank.sv", "build.tcl", "export_schematics.tcl", "review_protocol.json", "validate.py"):
        shutil.copyfile(HERE / name, output / ("sources" if name.endswith(".sv") else "") / name)
        sources[str((HERE / name).relative_to(ROOT)).replace("\\", "/")] = hashlib.sha256((HERE / name).read_bytes()).hexdigest()
    sys.path.insert(0, str(ROOT / "src"))
    sys.path.insert(0, str(ROOT))
    from experiments.exp_032_online_lms_rtl.generate_vectors import generate
    summary = generate(output / "vectors" / "online.txt")
    if summary["total_vectors"] != 8263:
        raise ValueError("Unexpected reviewed vector count")
    lines = (output / "vectors" / "online.txt").read_text(encoding="ascii").splitlines()
    corrupted = list(lines)
    fields = corrupted[0].split()
    fields[6] = str(int(fields[6]) ^ 1)
    corrupted[0] = " ".join(fields)
    (output / "vectors" / "negative.txt").write_text("\n".join(corrupted) + "\n", encoding="ascii")
    manifest = {
        "protocol": json.loads((HERE / "review_protocol.json").read_text()),
        "repository": str(ROOT),
        "run_directory": str(output),
        "source_sha256": sources,
        "vectors_sha256": hashlib.sha256((output / "vectors" / "online.txt").read_bytes()).hexdigest(),
        "vector_summary": summary,
        "provenance": "new regeneration using the unchanged EXP-032 generator; not recovered historical data",
        "negative_control": "first expected final code bit flipped; must fail",
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"directory": str(output), "vectors": summary["total_vectors"], "invalid": summary["counts"]["invalid"]}))

if __name__ == "__main__":
    main()
