"""Read-only additional gate/support and same-state branch analysis."""

from fractions import Fraction as F
import gzip
from hashlib import sha256
import json
from pathlib import Path

from adc_research.theory.static_auxiliary_mismatch import CubicTransfer, convert
from adc_research.theory.static_fixed_contract import readout, nearest_even

ROOT = Path(__file__).resolve().parents[2]


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not args.run_id.replace("_", "").replace("-", "").isalnum():
        raise ValueError("run-id must be simple")
    out = ROOT / "artifacts/runs/EXP_060" / args.run_id
    if (out / "analysis.json").exists():
        raise ValueError("preserve existing analysis")
    paths = [Path(__file__), ROOT / "src/adc_research/theory/static_auxiliary_mismatch.py",
             ROOT / "src/adc_research/theory/static_fixed_contract.py", out / "grid.jsonl.gz", out / "validation.json"]
    write(out / "analysis_source_hashes.json", {str(p.relative_to(ROOT)).replace("\\", "/"): sha256(p.read_bytes()).hexdigest() for p in paths})
    p = json.loads((out / "protocol.json").read_text(encoding="utf-8"))
    data = {}
    with gzip.open(out / "grid.jsonl.gz", "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            data[(row["case"], row["i"], *row["d"])] = row
    groups, pairs = [], []
    for case in p["cases"]:
        linear = case["stage1"][1] == case["stage2"][1] == 0
        modes = ["unit"] + (["sar_exact_inverse", "sar_export_q3"] if linear else [])
        for mode in modes:
            k = ((F(1),) * 8 if mode == "unit" else
                 (1 / F(str(case["stage1"][0])),) * 4 + (1 / F(str(case["stage2"][0])),) * 4)
            if mode == "sar_export_q3":
                k = tuple(F(nearest_even(1024 * c), 1024) for c in k)
            stats = {"case": case["name"], "mode": mode, "gate": [0] * 8,
                     "basis": [0] * 8, "both": [0] * 8, "max_pre_dither_cdac_residual": 0.0}
            pair = {"case": case["name"], "mode": mode, "output_changes": 0,
                    "max_output_difference_codes": 0.0, "max_integer_output_difference_codes": 0}
            for i in range(p["grid"]["points"]):
                for d1, d2 in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
                    row = data[(case["name"], i, d1, d2)]
                    if mode == "sar_exact_inverse":
                        make = lambda v: CubicTransfer(*(F(str(c)) for c in v))
                        t = convert(F(row["x_rational"]), d1, d2, make(case["stage1"]), make(case["auxiliary"]), make(case["stage2"]))
                        word = (t.q1, t.q2, t.backend)
                    else:
                        word = row["word"]
                    v = readout(*word[:2], F(word[2]), d1, d2, k, data_q3=mode != "sar_exact_inverse")
                    for bank in range(2):
                        for j in range(4):
                            b = 4 * bank + j
                            stats["gate"][b] += int(v.gates[bank][j])
                            stats["basis"][b] += int(v.support[bank][j])
                            stats["both"][b] += int(v.gates[bank][j] and v.support[bank][j])
                    stats["max_pre_dither_cdac_residual"] = max(stats["max_pre_dither_cdac_residual"], abs(row["v"][1] - row["word"][1] / 4))
                    if case["name"] != case["paired_reference"]:
                        other = data[(case["paired_reference"], i, d1, d2)]
                        if mode == "sar_exact_inverse":
                            refcase = next(c for c in p["cases"] if c["name"] == case["paired_reference"])
                            ot = convert(F(other["x_rational"]), d1, d2, make(refcase["stage1"]), make(refcase["auxiliary"]), make(refcase["stage2"]))
                            oword = (ot.q1, ot.q2, ot.backend)
                        else:
                            oword = other["word"]
                        ov = readout(*oword[:2], F(oword[2]), d1, d2, k, data_q3=mode != "sar_exact_inverse")
                        diff = v.output - ov.output
                        pair["output_changes"] += int(diff != 0)
                        pair["max_output_difference_codes"] = max(pair["max_output_difference_codes"], float(abs(diff)))
                        pair["max_integer_output_difference_codes"] = max(pair["max_integer_output_difference_codes"], abs(nearest_even(v.output) - nearest_even(ov.output)))
            groups.append(stats)
            if case["name"] != case["paired_reference"]:
                pairs.append(pair)
    validation = json.loads((out / "validation.json").read_text(encoding="utf-8"))
    final = {(r["case"], r["seed"], r["method"]): r for r in validation["short"]["final"]}
    short_pairs = []
    for case in p["cases"]:
        if case["name"] == case["paired_reference"]:
            continue
        for seed in p["short"]["seeds"]:
            for method in p["short"]["methods"]:
                a, b = final[(case["name"], seed, method)], final[(case["paired_reference"], seed, method)]
                short_pairs.append({"case": case["name"], "seed": seed, "method": method,
                    "export_differences": [u - v for u, v in zip(a["coefficient_codes"], b["coefficient_codes"], strict=True)],
                    "q22_differences": [u - v for u, v in zip(a["accumulators"], b["accumulators"], strict=True)]})
    write(out / "analysis.json", {"groups": groups, "pairs": pairs, "short_pairs": short_pairs,
        "scope": "Fixed grid and16-window descriptive controls only. No oracle learning, convergence, causal full-state or chip claim. Supplemental analysis after predeclared gates passed."})
    print("analysis complete", len(groups), "fixed states;", len(short_pairs), "short pairs")


if __name__ == "__main__":
    main()
