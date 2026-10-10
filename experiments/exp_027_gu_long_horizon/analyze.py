"""Print paired finite-window metrics from an EXP-027 summary."""

from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path)
    args = parser.parse_args()
    data = json.loads(args.summary.read_text(encoding="utf-8"))
    if data["experiment_id"] != "EXP_027" or not data["protocol_passed"]:
        raise ValueError("expected a passed EXP-027 summary")
    print("case seed | validation start→end [late min,max] | random start→end | "
          "SNDR start→end | largest coefficient drift | fourth-slice gates")
    for case_name, case in data["cases"].items():
        start_random = []
        end_random = []
        start_sndr = []
        end_sndr = []
        for row in case["runs"]:
            points = row["trajectory"]
            first, last = points[0], points[-1]
            late = [point["validation"]["mae_codes"] for point in points
                    if point["training_samples"] >= 327680]
            drift = max(
                abs(end - initial)
                for stage in ("stage1", "stage2")
                for initial, end in zip(first[f"{stage}_coefficients"],
                                        last[f"{stage}_coefficients"], strict=True)
            )
            fourth = (last["stage1_gate_counts"][3], last["stage2_gate_counts"][3])
            random_pair = (first["heldout_random"]["mae_codes"],
                           last["heldout_random"]["mae_codes"])
            sndr_pair = (first["heldout_tone"]["spectrum"]["sndr_db"],
                         last["heldout_tone"]["spectrum"]["sndr_db"])
            start_random.append(random_pair[0])
            end_random.append(random_pair[1])
            start_sndr.append(sndr_pair[0])
            end_sndr.append(sndr_pair[1])
            print(
                f"{case_name} {row['training_seed']} | "
                f"{first['validation']['mae_codes']:.4f}→"
                f"{last['validation']['mae_codes']:.4f} "
                f"[{min(late):.4f},{max(late):.4f}] | "
                f"{random_pair[0]:.4f}→{random_pair[1]:.4f} | "
                f"{sndr_pair[0]:.3f}→{sndr_pair[1]:.3f} | "
                f"{drift:.6f} | {fourth}"
            )
        print(
            f"{case_name} mean: random {statistics.fmean(start_random):.4f}→"
            f"{statistics.fmean(end_random):.4f}, "
            f"SNDR {statistics.fmean(start_sndr):.3f}→"
            f"{statistics.fmean(end_sndr):.3f}; "
            f"end ranges random [{min(end_random):.4f},{max(end_random):.4f}], "
            f"SNDR [{min(end_sndr):.3f},{max(end_sndr):.3f}]"
        )
        for index, count in enumerate(data["checkpoints"]):
            maes = [row["trajectory"][index]["validation"]["mae_codes"]
                    for row in case["runs"]]
            print(f"  checkpoint {count}: validation mean {statistics.fmean(maes):.4f}, "
                  f"range [{min(maes):.4f},{max(maes):.4f}]")
            if count in data["spectral_checkpoints"]:
                random_maes = [row["trajectory"][index]["heldout_random"]["mae_codes"]
                               for row in case["runs"]]
                sndrs = [row["trajectory"][index]["heldout_tone"]["spectrum"]["sndr_db"]
                         for row in case["runs"]]
                print(f"    heldout random mean {statistics.fmean(random_maes):.4f}; "
                      f"SNDR mean {statistics.fmean(sndrs):.3f}")


if __name__ == "__main__":
    main()
