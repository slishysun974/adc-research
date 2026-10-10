"""Read-only EXP-039/040 excitation and constrained propagation audit."""

from __future__ import annotations

import argparse
from collections import Counter
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.window_mean_map import MeanGeometry, analyze_window_mean, exact_matrix_rank
from adc_research.theory.window_excitation import (
    chronological_product, empirical_total_variation, exact_nullspace, gram_lower_bound,
    infinity_norm, product_magnitude_bounds, readout_gram, restricted_transition,
)
from experiments.exp_032_online_lms_rtl.generate_vectors import _config


ROOT = Path(__file__).resolve().parents[2]
SUPPORTS = {"all8": tuple(range(8)), "low4": (0, 1, 4, 5), "possible5": (0, 1, 2, 4, 5)}
BLOCK_SIZE = 8  # Declared consecutive blocks; never cross the training/sine boundary.


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def plain(value):
    if isinstance(value, F):
        return str(value)
    if isinstance(value, dict):
        return {k: plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(x) for x in value]
    return value


def write(path, value):
    path.write_text(json.dumps(plain(value), ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def average_matrices(matrices):
    return tuple(tuple(sum((m[i][j] for m in matrices), F(0))/len(matrices)
                       for j in range(8)) for i in range(8))


def summarize_directions(grams, jacobians):
    gram = average_matrices(grams)
    stacked = tuple(row for j in jacobians for row in j)
    inactive = [i for i in range(8) if all(all(x == 0 for x in j[i]) for j in jacobians)]
    return {"readout_gram": gram, "readout_rank": exact_matrix_rank(gram),
            "readout_nullspace": exact_nullspace(gram),
            "stacked_update_rank": exact_matrix_rank(stacked),
            "stacked_update_nullspace": exact_nullspace(stacked),
            "always_inactive_update_rows": inactive,
            "inactive_rows_with_readout_energy": [i for i in inactive if gram[i][i] > 0]}


def unit_reference_mean(samples):
    """Independent integer evaluation of the continuous unit-slope PWL.

    At unit slopes P(r)=r on its declared domain, so no multiplier,
    quantized state, or analog record is needed for this reference.
    """
    sums = [0]*8
    for sample in samples:
        d2, d1 = 16*sample.stage2_dither_symbol, 64*sample.stage1_dither_symbol
        raw2 = sample.backend_centered_code
        y2 = raw2-d2
        raw1 = 128*sample.stage2_symbol+y2
        if not -128 <= raw2 < 128 or not -512 <= raw1 < 512:
            raise ValueError("unit-reference digital PWL domain violation")
        y1 = raw1-d1
        for i in range(4):
            sums[i] += d2*y2*int(i == 0 or abs(y2) >= 32*i)
            sums[4+i] += d1*y1*int(i == 0 or abs(y1) >= 128*i)
    return tuple(F(x, len(samples)) for x in sums)


def run(source39, source40, output):
    output.mkdir(parents=True, exist_ok=False)
    originals = {}

    def checked_read(path, expected=None):
        data = path.read_bytes()
        value = hashlib.sha256(data).hexdigest()
        if expected is not None and value != expected:
            raise ValueError(f"source digest mismatch: {path}")
        originals[path] = value
        return json.loads(data)

    summary39 = checked_read(source39/"summary.json")
    summary40 = checked_read(source40/"summary.json")
    assert digest(source39/"summary.json") == summary40["source_summary_sha256"]
    for summary in (summary39, summary40):
        for name, expected in summary["source_sha256"].items():
            if digest(ROOT/name) != expected:
                raise ValueError(f"source code digest mismatch: {name}")
            originals[ROOT/name] = expected
    config = _config()
    steps = tuple(120*x for x in (*config.stage2_lms.step_sizes, *config.stage1_lms.step_sizes))
    cases, records_by_case, means_by_case = [], {}, {}
    for case39, case40 in zip(summary39["cases"], summary40["cases"], strict=True):
        assert case39["name"] == case40["name"]
        name = case39["name"]
        record_path = source39/name/"analog_digital_records.jsonl"
        assert digest(record_path) == case39["physical"]["raw_record_sha256"]
        originals[record_path] = digest(record_path)
        # Only the decoded sample fields enter this research calculation.
        samples = [Sample(**json.loads(line)["sample"]) for line in record_path.read_text().splitlines()]
        records_by_case[name] = samples
        method = next(x for x in case39["methods"] if x["method"] == "all_products")
        trajectory = checked_read(source39/name/"all_products.json", method["artifact_sha256"])["trajectory"]
        audits = checked_read(source40/(name+".json"), case40["output_sha256"])["windows"]
        grams, jacobians, windows, references = [], [], [], []
        for item, audit in zip(trajectory, audits, strict=True):
            old = item["coefficients_before"]
            slopes = tuple(F(x, 1024) for x in (*old["stage2"], *old["stage1"]))
            observations = samples[item["start"]:item["end"]+1]
            mean = analyze_window_mean(observations, slopes)
            j = tuple(tuple(F(x) for x in row) for row in audit["analytic_fixed_mask_jacobian"])
            assert j == mean.fixed_mask_jacobian and mean.open_cell_regular == audit["open_cell_regular"]
            gram = readout_gram(mean)
            grams.append(gram)
            jacobians.append(j)
            references.append(unit_reference_mean(observations))
            if item["window"] == 0:
                assert references[-1] == analyze_window_mean(observations, (F(1),)*8).mean_products
            inactive = [i for i, row in enumerate(j) if all(x == 0 for x in row)]
            restrictions = {label: restricted_transition(j, steps, support)
                            for label, support in SUPPORTS.items()}
            windows.append({"window": item["window"], "phase": item["phase"],
                "open_cell_regular": mean.open_cell_regular,
                "readout_rank": exact_matrix_rank(gram), "update_rank": exact_matrix_rank(j),
                "inactive_update_rows": inactive,
                "inactive_rows_with_readout_energy": [i for i in inactive if gram[i][i] > 0],
                "restrictions": {label: {"invariant": r.invariant, "local_norm": r.norm_bound}
                                 for label, r in restrictions.items()}})
        means_by_case[name] = references
        blocks = []
        for start in range(0, len(windows), BLOCK_SIZE):
            end = start+BLOCK_SIZE
            assert len(windows[start:end]) == BLOCK_SIZE
            assert len({w["phase"] for w in windows[start:end]}) == 1
            pooled = average_matrices(grams[start:end])
            diagnostic = {}
            for label, support in SUPPORTS.items():
                rs = [restricted_transition(j, steps, support) for j in jacobians[start:end]]
                closed = all(r.invariant for r in rs)
                principal_gram = tuple(tuple(pooled[i][j] for j in support) for i in support)
                product = chronological_product([r.transition for r in rs]) if closed else None
                norm = infinity_norm(product) if product is not None else None
                diagnostic[label] = {"invariant": closed,
                    "finite_block_gram_lower_bound": gram_lower_bound(principal_gram),
                    "product": product, "product_norm": norm,
                    "linearized_product_strictly_contracts": closed and norm < 1,
                    "all_open_cells_regular": all(w["open_cell_regular"] for w in windows[start:end])}
            blocks.append({"start_window": start, "end_window": end-1, "phase": windows[start]["phase"],
                           "supports": diagnostic})
        phases = {}
        for phase in ("training", "online_sine"):
            ids = [i for i, w in enumerate(windows) if w["phase"] == phase]
            phases[phase] = summarize_directions([grams[i] for i in ids], [jacobians[i] for i in ids])
        target = output/(name+".json")
        write(target, {"windows": windows, "blocks": blocks, "phase_directions": phases})
        compact = {"name": name, "windows": len(windows),
            "readout_rank_counts": dict(Counter(w["readout_rank"] for w in windows)),
            "update_rank_counts": dict(Counter(w["update_rank"] for w in windows)),
            "phase_directions": {phase: {k: v for k, v in data.items() if k != "readout_gram"}
                                 for phase, data in phases.items()},
            "supports": {label: {
                "invariant_windows": sum(w["restrictions"][label]["invariant"] for w in windows),
                "positive_gram_blocks": sum(b["supports"][label]["finite_block_gram_lower_bound"] > 0 for b in blocks),
                "strict_product_blocks": sum(b["supports"][label]["linearized_product_strictly_contracts"] for b in blocks),
                "regular_strict_product_blocks": sum(b["supports"][label]["linearized_product_strictly_contracts"]
                    and b["supports"][label]["all_open_cells_regular"] for b in blocks),
                "product_norm_range": [min(values), max(values)] if (values := [
                    b["supports"][label]["product_norm"] for b in blocks if b["supports"][label]["invariant"]]) else None
            } for label in SUPPORTS}, "output_sha256": digest(target)}
        cases.append(compact)
        print(json.dumps({"case": name, "readout_ranks": compact["readout_rank_counts"],
                          "update_ranks": compact["update_rank_counts"]}), flush=True)
    pairs = []
    bounds = product_magnitude_bounds((F(1),)*8, MeanGeometry())
    for excitation in ("iid", "periodic255"):
        for history in ("two_phase", "direct_hold"):
            left_name, right_name = excitation+"_reset", excitation+"_"+history
            left, right = records_by_case[left_name], records_by_case[right_name]
            assert len(left) == len(right)
            assert all((a.stage1_symbol, a.stage1_dither_symbol, a.stage2_dither_symbol) ==
                       (b.stage1_symbol, b.stage1_dither_symbol, b.stage2_dither_symbol)
                       for a, b in zip(left, right))
            changes = []
            for i in range(len(left)//120):
                a, b = left[120*i:120*(i+1)], right[120*i:120*(i+1)]
                tv = empirical_total_variation(a, b)
                disagreement = sum(x != y for x, y in zip(a, b))
                assert tv <= F(disagreement, 120)
                difference = tuple(abs(x-y) for x, y in zip(means_by_case[left_name][i], means_by_case[right_name][i]))
                limit = tuple(2*x*tv for x in bounds)
                assert all(x <= y for x, y in zip(difference, limit))
                changes.append({"window": i, "phase": "training" if i < 128 else "online_sine",
                                "paired_digital_disagreements": disagreement, "empirical_tv": tv,
                                "common_unit_reference_mean_difference": difference, "tv_mean_change_bound": limit})
            target = output/(left_name+"_vs_"+right_name+".json")
            write(target, {"left": left_name, "right": right_name, "windows": changes})
            pairs.append({"left": left_name, "right": right_name,
                "disagreements": sum(x["paired_digital_disagreements"] for x in changes),
                "changed_mean_windows": sum(any(x["common_unit_reference_mean_difference"]) for x in changes),
                "tv_range": [min(x["empirical_tv"] for x in changes), max(x["empirical_tv"] for x in changes)],
                "coordinate_bounds_checked": len(changes)*8,
                "all_coordinate_bounds_passed": True, "output_sha256": digest(target)})
    for path, original in originals.items():
        assert digest(path) == original, path
    sources = ("src/adc_research/theory/window_excitation.py", "experiments/exp_041_excitation_stability/run.py",
               "tests/test_window_excitation.py")
    write(output/"summary.json", {"scope": "finite-record readout excitation, constrained analytic products, common-reference law changes",
        "cadence_used": False, "online_algorithm_changed": False, "new_training_samples": 0,
        "physical_guarantee": False, "global_convergence_established": False,
        "uniform_persistent_excitation_established": False, "source_package_unchanged": True,
        "state_order": "stage2[0..3],stage1[0..3]", "supports": SUPPORTS, "block_windows": BLOCK_SIZE,
        "step_per_window": steps, "source39_summary_sha256": digest(source39/"summary.json"),
        "source40_summary_sha256": digest(source40/"summary.json"),
        "source_sha256": {name: digest(ROOT/name) for name in sources}, "cases": cases, "history_pairs": pairs})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source39", type=Path)
    parser.add_argument("source40", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    paths = [(ROOT/p).resolve() for p in (args.source39, args.source40, args.output)]
    for path, allowed in zip(paths, ("EXP_039", "EXP_040", "EXP_041")):
        path.relative_to(ROOT/"artifacts"/"runs"/allowed)
    run(*paths)
