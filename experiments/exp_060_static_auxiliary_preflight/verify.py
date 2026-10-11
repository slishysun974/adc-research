"""Independent full replay: native scalar plant, exact math and digital contract.

No platform/calibration implementation imports. No source modification or
training rerun. Exact-vs-double boundary differences are retained separately.
"""

import argparse
from fractions import Fraction as F
import gzip
from hashlib import sha256
import json
import math
from pathlib import Path
import traceback

from adc_research.theory.static_auxiliary_mismatch import (
    CubicTransfer, convert, flash, rear_reconstruction_error, linear_branch_difference,
)
from adc_research.theory.static_fixed_contract import readout, export, commit, nearest_even, pwl

ROOT = Path(__file__).resolve().parents[2]


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def rows(path):
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            yield json.loads(line)


def native(x, d1, d2, case):
    thresholds = [(-7 + 2 * j) / 8 for j in range(8)]
    q1 = sum(x >= t for t in thresholds) - 4
    z1 = 4 * (x - q1 / 4 + d1 / 32)
    a1, b1 = case["stage1"]
    aa, ba = case["auxiliary"]
    a2, b2 = case["stage2"]
    m, a = a1 * z1 + b1 * z1**3, aa * z1 + ba * z1**3
    q2 = sum(a >= t for t in thresholds) - 4
    z2 = 4 * (m - q2 / 4 + d2 / 32)
    r2 = a2 * z2 + b2 * z2**3
    return [q1, q2, math.floor((r2 + 1) * 128) - 128], [z1, m, a, z2, r2]


def transfer(values):
    return CubicTransfer(*(F(str(v)) for v in values))


def exact(x, d1, d2, case):
    return convert(x, d1, d2, transfer(case["stage1"]),
                   transfer(case["auxiliary"]), transfer(case["stage2"]))


def check_record(row, case, tol, disagreements):
    d1, d2 = row["d"]
    word, voltage = native(row["x"], d1, d2, case)
    assert word == row["word"], (row["case"], row["x"], "native word")
    assert max(abs(a - b) for a, b in zip(voltage, row["v"], strict=True)) <= tol
    x = F(row["x_rational"]) if "x_rational" in row else F.from_float(row["x"])
    trace = exact(x, d1, d2, case)
    exact_word = [trace.q1, trace.q2, trace.backend]
    if word != exact_word:
        margins = [min(abs(x - F(2 * j - 7, 8)) for j in range(8)),
                   min(abs(trace.auxiliary1 - F(2 * j - 7, 8)) for j in range(8)),
                   min((128 * (trace.main2 + 1)) % 1, 1 - (128 * (trace.main2 + 1)) % 1) / 128]
        changed = [i for i, (a, b) in enumerate(zip(word, exact_word, strict=True)) if a != b]
        assert all(float(margins[i]) <= tol for i in changed), ("unprotected exact mismatch", row)
        disagreements.append({"case": row["case"], "x": str(x), "d": [d1, d2],
                              "native": word, "exact": exact_word, "margin": [str(m) for m in margins]})
    assert -1 <= voltage[1] < 1 and -1 <= voltage[4] < 1
    return trace


def fields(value):
    return [int(8 * value.raw1), int(8 * value.y1), int(8 * value.y2), int(8 * value.output)]


def verify_grid(out, p, cases, disagreements):
    unit = (F(1),) * 8
    grid = {}
    moments = {}
    totals = 0
    for row in rows(out / "grid.jsonl.gz"):
        case = cases[row["case"]]
        trace = check_record(row, case, p["acceptance"]["voltage_tolerance"], disagreements)
        q1, q2, c3 = row["word"]
        d1, d2 = row["d"]
        value = readout(q1, q2, F(c3), d1, d2, unit, data_q3=True)
        assert fields(value) == row["unit"]
        grid[(row["case"], row["i"], d1, d2)] = row
        # Identity on the exact physical trace for continuous/unit/SAR modes.
        for backend in (128 * trace.main2, F(trace.backend)):
            corrected = pwl(backend, 32, unit[4:], False)
            raw1, delta2 = rear_reconstruction_error(trace, d2, corrected)
            assert raw1 == 512 * trace.main1 + delta2
        if case["stage1"][1] == case["stage2"][1] == 0:
            k = (1 / F(str(case["stage1"][0])),) * 4 + (1 / F(str(case["stage2"][0])),) * 4
            khat = tuple(F(nearest_even(1024 * v), 1024) for v in k)
            assert fields(readout(q1, q2, F(c3), d1, d2, khat, data_q3=True)) == row["inverse_export"]
            entry = moments.setdefault(row["case"], {mode: [F(0)] * 8 for mode in ("continuous_inverse", "sar_inverse", "sar_export_q3")})
            for mode, backend, coeffs, q3 in (("continuous_inverse", 128 * trace.main2, k, False),
                                              ("sar_inverse", F(trace.backend), k, False),
                                              ("sar_export_q3", F(trace.backend), khat, True)):
                value = readout(trace.q1, trace.q2, backend, d1, d2, coeffs, data_q3=q3)
                for bank, (d, y) in enumerate(((64 * d1, value.y1), (16 * d2, value.y2))):
                    for j, gate in enumerate(value.gates[bank]):
                        entry[mode][4 * bank + j] += d * y * gate
            if row["case"].startswith("ideal"):
                v = readout(trace.q1, trace.q2, F(trace.backend), d1, d2, unit, data_q3=True)
                target = (2048 * (F(row["x_rational"]) + 1)).__floor__()
                assert v.output == target
        totals += 1
    for name, entry in moments.items():
        assert entry["continuous_inverse"] == [0] * 8, (name, "balanced continuous")
        if name.startswith("ideal"):
            assert entry["sar_inverse"] == entry["sar_export_q3"] == [0] * 8
    pairs = []
    for case in p["cases"]:
        if case["name"] == case["paired_reference"]:
            continue
        stats = {"case": case["name"], "q2_changes": 0, "unit_output_changes": 0,
                 "unit_rear_gate_changes": [0] * 4, "unit_front_gate_changes": [0] * 4,
                 "max_unit_output_difference_codes": 0.0, "native_ideal_boundary_output_differences": []}
        for i in range(p["grid"]["points"]):
            for d1, d2 in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
                right = grid[(case["name"], i, d1, d2)]
                left = grid[(case["paired_reference"], i, d1, d2)]
                stats["q2_changes"] += int(left["word"][1] != right["word"][1])
                values = [readout(*r["word"][:2], F(r["word"][2]), d1, d2, unit, data_q3=True) for r in (left, right)]
                diff = values[1].output - values[0].output
                stats["unit_output_changes"] += int(diff != 0)
                stats["max_unit_output_difference_codes"] = max(stats["max_unit_output_difference_codes"], float(abs(diff)))
                for bank, key in enumerate(("unit_front_gate_changes", "unit_rear_gate_changes")):
                    for j in range(4):
                        stats[key][j] += int(values[0].gates[bank][j] != values[1].gates[bank][j])
                if case["stage1"][1] == case["stage2"][1] == 0:
                    # Equation 9.1 uses the same exact main transfer and tags.
                    lt = exact(F(left["x_rational"]), d1, d2, cases[case["paired_reference"]])
                    rt = exact(F(right["x_rational"]), d1, d2, case)
                    a2 = F(str(case["stage2"][0]))
                    k = F(nearest_even(1024 / a2), 1024)
                    ep = (F(lt.backend) - 128 * lt.main2, F(rt.backend) - 128 * rt.main2)
                    eta = tuple(pwl(F(t.backend), 32, (k,) * 4, True) - k * t.backend for t in (lt, rt))
                    raw = tuple(128 * t.q2 + pwl(F(t.backend), 32, (k,) * 4, True) - 16 * d2 for t in (lt, rt))
                    assert raw[1] - raw[0] == linear_branch_difference(rt.q2 - lt.q2, k, a2, ep[1] - ep[0], eta[1] - eta[0])
                if case["name"].startswith("ideal") and diff:
                    target = 2048 * (F(right["x_rational"]) + 1)
                    margin = min(target % 1, 1 - target % 1) / 2048
                    assert float(margin) <= p["acceptance"]["exact_float_boundary_margin"]
                    stats["native_ideal_boundary_output_differences"].append({"i": i, "d": [d1, d2], "difference": str(diff)})
        pairs.append(stats)
    return {"records": totals, "paired_fixed_unit": pairs,
            "balanced_correlations_per_sample": {name: {mode: [float(v / (4 * p["grid"]["points"])) for v in values]
             for mode, values in entry.items()} for name, entry in moments.items()}}


def verify_boundaries(out, p, cases, disagreements):
    counts = {"input": 0, "node": 0, "history": 0}
    for row in rows(out / "boundaries.jsonl.gz"):
        case = cases[row["case"]]
        counts[row["kind"]] += 1
        if row["kind"] != "node":
            check_record(row, case, p["acceptance"]["voltage_tolerance"], disagreements)
            if "unit" in row:
                assert fields(readout(*row["word"][:2], F(row["word"][2]), *row["d"], (F(1),) * 8, data_q3=True)) == row["unit"]
        else:
            z = F(row["z_rational"])
            zz = float(z)
            a1, b1 = case["stage1"]
            aa, ba = case["auxiliary"]
            a2, b2 = case["stage2"]
            m, a = a1 * zz + b1 * zz**3, aa * zz + ba * zz**3
            q = sum(a >= (2 * j - 7) / 8 for j in range(8)) - 4
            z2 = 4 * (m - q / 4 + row["d2"] / 32)
            r2 = a2 * z2 + b2 * z2**3
            assert row["q2"] == q and row["c3"] == math.floor((r2 + 1) * 128) - 128
            assert max(abs(a - b) for a, b in zip(row["v"], (m, a, z2, r2), strict=True)) <= p["acceptance"]["voltage_tolerance"]
            qa = flash(transfer(case["auxiliary"])(z))
            if qa != q:
                margin = abs(transfer(case["auxiliary"])(z) - F(row["threshold"]))
                assert float(margin) <= p["acceptance"]["exact_float_boundary_margin"]
                disagreements.append({"kind": "node", "case": row["case"], "z": str(z),
                                      "native_q2": q, "exact_q2": qa, "margin": str(margin)})
    return counts


def verify_short(out, p, cases, disagreements):
    steps = tuple(F(n, p["steps"][bank + "_denominator"]) for bank in ("stage1", "stage2") for n in p["steps"]["numerators"])
    previous, final = {}, {}
    support = {}
    shared_source = {}
    windows = conversions = observations = 0
    for row in rows(out / "short.jsonl.gz"):
        key = (row["case"], row["seed"], row["method"])
        assert row["before"] == previous.get(key, [1 << 22] * 8)
        codes = export(tuple(row["before"]))
        assert list(codes) == row["coefficients"][0] + row["coefficients"][1]
        coeffs = tuple(F(c, 1024) for c in codes)
        products, counts = [F(0)] * 8, [0] * 8
        entry = support.setdefault(key, {"gate": [0] * 8, "basis": [0] * 8, "both": [0] * 8})
        for j, value in enumerate(row["values"]):
            value["case"] = row["case"]
            check_record(value, cases[row["case"]], p["acceptance"]["voltage_tolerance"], disagreements)
            index = row["window"] * 120 + j
            sourcekey = (row["seed"], index)
            source = (value["x"], value["d"])
            if sourcekey in shared_source:
                assert shared_source[sourcekey] == source
            else:
                shared_source[sourcekey] = source
            q1, q2, c3 = value["word"]
            d1, d2 = value["d"]
            score = readout(q1, q2, F(c3), d1, d2, coeffs, data_q3=True)
            assert fields(score) == [row["raw1_scaled"][j], row["y1_scaled"][j], row["y2_scaled"][j], row["output_scaled"][j]]
            assert 0 <= score.output <= 4095
            selected = row["method"] == "full120" or j in p["short"]["selected_positions_point"]
            if selected:
                for bank, (d, y) in enumerate(((64 * d1, score.y1), (16 * d2, score.y2))):
                    for slope in range(4):
                        b = 4 * bank + slope
                        gate, basis = score.gates[bank][slope], score.support[bank][slope]
                        counts[b] += int(gate)
                        products[b] += d * y * gate
                        entry["gate"][b] += int(gate)
                        entry["basis"][b] += int(basis)
                        entry["both"][b] += int(gate and basis)
                observations += 1
            conversions += 1
        assert counts == row["gate_counts"][0] + row["gate_counts"][1]
        assert [64 * v for v in products] == row["products_scaled"][0] + row["products_scaled"][1]
        requests, after = commit(tuple(row["before"]), tuple(products), 30 if row["method"] == "point30" else 1, steps)
        assert list(requests) == row["requests"][0] + row["requests"][1]
        assert list(after) == row["after"]
        assert tuple(a - b for a, b in zip(after, row["before"], strict=True)) == requests
        previous[key] = list(after)
        final[key] = {"case": key[0], "seed": key[1], "method": key[2], "accumulators": list(after),
                      "coefficient_codes": list(export(after)), "support": entry}
        windows += 1
    assert len(previous) == len(p["cases"]) * len(p["short"]["seeds"]) * len(p["short"]["methods"])
    return {"paths": len(previous), "windows": windows, "conversions": conversions,
            "observations_per_bank": observations, "bank_commits": 2 * windows,
            "shared_physical_input_tag_samples": len(shared_source), "final": list(final.values())}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not args.run_id.replace("_", "").replace("-", "").isalnum():
        raise ValueError("run-id must be simple")
    out = ROOT / "artifacts/runs/EXP_060" / args.run_id
    if (out / "validation.json").exists() or (out / "verification_failure.json").exists():
        raise ValueError("preserve existing verification; do not overwrite")
    try:
        p = json.loads((out / "protocol.json").read_text(encoding="utf-8"))
        for path, expected in json.loads((out / "source_hashes.json").read_text(encoding="utf-8")).items():
            assert sha256((ROOT / path).read_bytes()).hexdigest() == expected, path
        cases = {c["name"]: c for c in p["cases"]}
        disagreements = []
        grid = verify_grid(out, p, cases, disagreements)
        print("grid replay complete", grid["records"], flush=True)
        boundaries = verify_boundaries(out, p, cases, disagreements)
        print("boundary replay complete", boundaries, flush=True)
        short = verify_short(out, p, cases, disagreements)
        write(out / "validation.json", {"status": "pass", "grid": grid, "boundaries": boundaries,
            "short": short, "exact_float_boundary_disagreements": disagreements,
            "native_original_mismatches": 0, "readout_commit_mismatches": 0,
            "physical_overloads": 0, "output_clips": 0, "coefficient_saturations": 0})
        print("PASS", short["paths"], short["conversions"], "exact/double boundary differences", len(disagreements), flush=True)
    except Exception:
        write(out / "verification_failure.json", {"traceback": traceback.format_exc()})
        raise


if __name__ == "__main__":
    main()
