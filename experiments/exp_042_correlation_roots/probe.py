"""Inspect stage-2 roots before constructing full-chain root candidates."""

from collections import Counter
from fractions import Fraction as F
import json
from pathlib import Path

from adc_research.theory.gated_correlation_roots import WeightedStageRow, scan_two_slope_roots, stage_basis


if __name__ == "__main__":
    source = Path("artifacts/runs/EXP_039/window_v1")
    summary = json.loads((source/"summary.json").read_text())
    for case in summary["cases"]:
        rows = [json.loads(line)["sample"] for line in (source/case["name"]/"analog_digital_records.jsonl").read_text().splitlines()[:11520]]
        counts = Counter((r["backend_centered_code"], 16*r["stage2_dither_symbol"]) for r in rows)
        stage = tuple(WeightedStageRow(F(raw), F(dither), count) for (raw, dither), count in sorted(counts.items()))
        scan = scan_two_slope_roots(stage, 32)
        print(case["name"],scan.status,'cells',len(scan.cells),'roots',[(tuple(float(k) for k in r.coefficients),r.at_gate_boundary) for r in scan.roots],flush=True)
        for root in scan.roots:
            def raw1(row):
                corrected = sum((k*b for k,b in zip(root.coefficients,stage_basis(row["backend_centered_code"],32))),F(0))
                return 128*row["stage2_symbol"]+corrected-16*row["stage2_dither_symbol"]
            counts1=Counter((raw1(r),64*r["stage1_dither_symbol"]) for r in rows)
            stage1=tuple(WeightedStageRow(F(raw),F(dither),count) for (raw,dither),count in sorted(counts1.items()))
            one=scan_two_slope_roots(stage1,128)
            print('  stage1',one.status,'cells',len(one.cells),'roots',[(tuple(float(k) for k in r.coefficients),r.at_gate_boundary) for r in one.roots],flush=True)
