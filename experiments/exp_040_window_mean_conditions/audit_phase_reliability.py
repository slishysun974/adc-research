"""Exact finite-phase reliability, separate from mean/unrounded convergence."""

from __future__ import annotations

import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

from experiments.exp_040_window_mean_conditions.run import ROOT, write


def audit(output):
    summary_file = output/"summary.json"
    before = summary_file.read_bytes()
    summary = json.loads(before)
    comparisons = [0]*8
    phase_missed = [0]*8
    request_zero = [0]*8
    first_example = None
    for case in summary["cases"]:
        path = output/(case["name"]+".json")
        assert hashlib.sha256(path.read_bytes()).hexdigest() == case["output_sha256"]
        windows = json.loads(path.read_text())["windows"]
        for window in windows:
            means = tuple(F(x) for x in window["integer_reference_mean"])
            phases = tuple(tuple(F(x) for x in phase) for phase in window["point_phase_means_integer_reference"])
            for i, mean in enumerate(means):
                if mean == 0:
                    continue  # no nonzero reference direction to preserve
                variance = sum(((phase[i]-mean)**2 for phase in phases), F(0))/30
                probability = F(sum(phase[i]*mean <= 0 for phase in phases), 30)
                bound = variance/(variance+mean**2)
                assert probability <= bound
                comparisons[i] += 1
                phase_missed[i] += int(phases[0][i]*mean <= 0)
                if window["full_requested_q22_deltas"][i] != 0:
                    request_zero[i] += int(window["all_phase_requested_q22_deltas"][0][i] == 0)
                if case["name"] == "periodic255_direct_hold" and window["window"] == 0 and i == 2:
                    active_phases = [r for r, phase in enumerate(phases) if phase[i] != 0]
                    first_example = {
                        "case": case["name"], "coordinate": "stage2 coefficient 3",
                        "active_phases": active_phases, "full_correlation_mean": mean,
                        "phase_correlation_variance": variance,
                        "nonpositive_relative_direction_probability": probability,
                        "one_sided_second_moment_bound": bound,
                        "full_requested_q22_delta": window["full_requested_q22_deltas"][i],
                        "all_phase_requested_q22_deltas": [phase[i] for phase in window["all_phase_requested_q22_deltas"]],
                        "uniform_phase_mean_request_q22": sum((F(phase[i]) for phase in window["all_phase_requested_q22_deltas"]), F(0))/30,
                    }
    assert first_example is not None
    assert first_example["active_phases"] == [17, 26]
    assert first_example["nonpositive_relative_direction_probability"] == F(14, 15)
    # The two active phase products differ (-256 and -264), so the moment
    # bound is slightly above the exact missing probability, not equal to it.
    assert first_example["one_sided_second_moment_bound"] == F(11833, 12678)
    assert summary_file.read_bytes() == before
    result = {"scope": "conditional uniform phase, fixed integer-observation window; not a chip probability or loss direction",
        "input_summary_sha256": hashlib.sha256(before).hexdigest(),
        "source_file": "experiments/exp_040_window_mean_conditions/audit_phase_reliability.py",
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "nonzero_mean_window_coordinate_checks": comparisons,
        "phase0_nonpositive_relative_correlation_windows": phase_missed,
        "phase0_zero_request_when_full_nonzero_windows": request_zero,
        "rare_gate_example": first_example}
    write(output/"phase_reliability.json", result)
    print(json.dumps({"checks": comparisons, "phase0_stalls": request_zero,
                      "rare_gate_example": {k: str(v) for k, v in first_example.items() if k != "all_phase_requested_q22_deltas"}}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = (ROOT/args.output).resolve()
    output.relative_to(ROOT/"artifacts/runs/EXP_040")
    audit(output)
