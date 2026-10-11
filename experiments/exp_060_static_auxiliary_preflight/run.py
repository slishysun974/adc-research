"""Run the frozen original-platform/static auxiliary preflight."""

import argparse
from dataclasses import replace
from fractions import Fraction as F
import gzip
from hashlib import sha256
import json
from pathlib import Path
import platform
import sys
import traceback

from adc_research.calibration.fixed_adaptive_two_stage import (
    FixedTwoStageAdaptiveConfig, FixedTwoStageAdaptiveState,
)
from adc_research.calibration.fixed_four_lane_window import (
    FixedFourLaneWindowConfig, FourLaneConversion, correct_fixed_four_lane_window,
)
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsConfig, FixedGatedLmsState
from adc_research.calibration.fixed_pwl import (
    FixedPwlArithmetic, quantize_two_stage_config, correct_two_stage_fixed_observed,
)
from adc_research.evaluation.observations import digital_sample
from adc_research.platform.amplifier import StaticCubicTruthConfig, amplify_static_cubic_truth
from adc_research.platform.backend_sar import convert as sar
from adc_research.platform.dual_path_settling import DualPathSettlingState
from adc_research.platform.stage import process as stage
from adc_research.platform.two_phase_dual_path import (
    TwoPhasePath, TwoPhaseDualPathConfig, process,
)
from experiments.exp_057_static_two_stage_million.common import setup, truth, input_tags

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = Path(__file__).with_name("protocol.json")


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def emit(handle, row):
    handle.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")


def hashes():
    paths = []
    for directory in ("src/adc_research", "rtl", "experiments/exp_057_static_two_stage_million",
                      "experiments/exp_058_static_fixed_preflight", "experiments/exp_059_static_fixed_million",
                      "experiments/exp_060_static_auxiliary_preflight"):
        paths.extend(p for p in (ROOT / directory).rglob("*")
                     if p.is_file() and "__pycache__" not in p.parts)
    paths.extend((ROOT / "configs/architectures/gu_behavioral_v1.yaml",
                  ROOT / "tests/test_static_auxiliary_mismatch.py"))
    return {str(p.relative_to(ROOT)).replace("\\", "/"): sha256(p.read_bytes()).hexdigest()
            for p in sorted(paths)}


def plant(x, d1, d2, case, pipeline, index=0, prior=None):
    zero = TwoPhasePath(0.0, 0.0)
    phases = TwoPhaseDualPathConfig(zero, zero, zero,
        auxiliary_truth=StaticCubicTruthConfig(*case["auxiliary"]))
    return process(x, pipeline, phases, prior or DualPathSettlingState(),
                   sample_index=index, dither_symbols=(d1, d2), nonidealities=truth(case))


def voltage_fields(result):
    p = result.pipeline
    return [p.stage1.residue_preamp * 4, p.stage1.residue,
            result.auxiliary_output, p.stage2.residue_preamp * 4, p.stage2.residue]


def word_fields(sample):
    return [sample.stage1_symbol, sample.stage2_symbol, sample.backend_centered_code]


def score_fields(sample, cascade):
    result = correct_two_stage_fixed_observed(sample, cascade)
    return [result.stage1_raw_scaled,
            result.stage1_pwl.corrected_code_scaled - result.stage1_dither_scaled,
            result.stage2_pwl.corrected_code_scaled - result.stage2_dither_scaled,
            result.unclipped_output_scaled]


def fixed_setup(source):
    pipeline, floating = setup(source)
    cascade = quantize_two_stage_config(floating.cascade, FixedPwlArithmetic())
    steps1 = tuple(F(n, source["steps"]["stage1_denominator"]) for n in source["steps"]["numerators"])
    steps2 = tuple(F(n, source["steps"]["stage2_denominator"]) for n in source["steps"]["numerators"])
    cfg = FixedTwoStageAdaptiveConfig(cascade,
        FixedGatedLmsConfig(1024, steps1), FixedGatedLmsConfig(256, steps2))
    return pipeline, cfg


def inverse_config(cfg, case):
    codes = tuple(round(1024 / case[bank][0]) for bank in ("stage1", "stage2"))
    return replace(cfg.cascade,
        stage1_pwl=replace(cfg.cascade.stage1_pwl, coefficient_codes=(codes[0],) * 4),
        stage2_pwl=replace(cfg.cascade.stage2_pwl, coefficient_codes=(codes[1],) * 4))


def check_physical(result):
    p = result.pipeline
    flags = [p.stage1.main_input_overload_low, p.stage1.main_input_overload_high,
             p.stage1.overload_low, p.stage1.overload_high,
             p.stage2.main_input_overload_low, p.stage2.main_input_overload_high,
             p.stage2.overload_low, p.stage2.overload_high,
             p.backend.overload_low, p.backend.overload_high]
    if any(flags):
        raise ValueError("physical overload in preflight")


def grid(out, protocol, pipeline, cfg):
    count = 0
    with gzip.open(out / "grid.jsonl.gz", "wt", encoding="utf-8") as handle:
        for case in protocol["cases"]:
            n = protocol["grid"]["points"]
            for i in range(n):
                x = F(-41, 50) + F(2 * i + 1, 2 * n) * F(41, 25)
                for d1, d2 in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
                    result = plant(float(x), d1, d2, case, pipeline, i * 4)
                    check_physical(result)
                    sample = digital_sample(result.pipeline)
                    row = {"case": case["name"], "i": i, "x_rational": str(x),
                           "x": float(x), "d": [d1, d2], "v": voltage_fields(result),
                           "word": word_fields(sample), "unit": score_fields(sample, cfg.cascade)}
                    if case["stage1"][1] == case["stage2"][1] == 0:
                        row["inverse_export"] = score_fields(sample, inverse_config(cfg, case))
                    emit(handle, row)
                    count += 1
    return count


def boundary(out, protocol, pipeline, cfg):
    count = nodes = histories = 0
    with gzip.open(out / "boundaries.jsonl.gz", "wt", encoding="utf-8") as handle:
        for case in protocol["cases"]:
            for j in range(8):
                t = F(2 * j - 7, 8)
                for offset in (-F(1, 2**40), F(0), F(1, 2**40)):
                    x = t + offset
                    for d1, d2 in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
                        result = plant(float(x), d1, d2, case, pipeline)
                        check_physical(result)
                        sample = digital_sample(result.pipeline)
                        emit(handle, {"kind": "input", "case": case["name"], "x_rational": str(x),
                             "x": float(x), "d": [d1, d2], "v": voltage_fields(result),
                             "word": word_fields(sample), "unit": score_fields(sample, cfg.cascade)})
                        count += 1
                aa, ba = map(lambda x: F(str(x)), case["auxiliary"])
                if not aa + ba >= abs(t):
                    continue
                if ba == 0:
                    probes = (t / aa - F(1, 2**40), t / aa, t / aa + F(1, 2**40))
                else:
                    low, high = F(-1), F(1)
                    for _ in range(80):
                        mid = (low + high) / 2
                        if aa * mid + ba * mid**3 < t:
                            low = mid
                        else:
                            high = mid
                    probes = (low - F(1, 2**32), high + F(1, 2**32))
                for z in probes:
                    m = amplify_static_cubic_truth(float(z / 4), nominal_gain=4,
                        truth=StaticCubicTruthConfig(*case["stage1"])).output_value
                    a = amplify_static_cubic_truth(float(z / 4), nominal_gain=4,
                        truth=StaticCubicTruthConfig(*case["auxiliary"])).output_value
                    for d2 in (-1, 1):
                        second = stage(m, a, d2, pipeline.stage2, nonidealities=truth(case).stage2)
                        backend = sar(second.residue, pipeline.backend)
                        if second.overload_low or second.overload_high or backend.overload_low or backend.overload_high:
                            raise ValueError("standalone second-stage node overload")
                        emit(handle, {"kind": "node", "case": case["name"], "z_rational": str(z),
                            "threshold": str(t), "d2": d2, "v": [m, a, 4 * second.residue_preamp, second.residue],
                            "q2": second.quantizer.symbol, "c3": backend.centered_code})
                        nodes += 1
            for x, d1, d2 in ((0.0, -1, -1), (1 / 2048, 1, 1), (-.3, 1, -1), (.3, -1, 1)):
                base = plant(x, d1, d2, case, pipeline)
                for prior in (DualPathSettlingState(), DualPathSettlingState(.5, -.5, .25),
                              DualPathSettlingState(-.75, .75, -.25)):
                    result = plant(x, d1, d2, case, pipeline, prior=prior)
                    assert voltage_fields(result) == voltage_fields(base)
                    assert result.pipeline.backend.centered_code == base.pipeline.backend.centered_code
                    emit(handle, {"kind": "history", "case": case["name"], "x": x,
                         "d": [d1, d2], "prior": prior.as_tuple(), "v": voltage_fields(result),
                         "word": word_fields(digital_sample(result.pipeline))})
                    histories += 1
    return {"input": count, "node": nodes, "zero_history": histories}


def short(out, protocol, pipeline, cfg):
    paths = windows = conversions = observations = 0
    with gzip.open(out / "short.jsonl.gz", "wt", encoding="utf-8") as handle:
        for case in protocol["cases"]:
            for seed in protocol["short"]["seeds"]:
                for method in protocol["short"]["methods"]:
                    wcfg = FixedFourLaneWindowConfig(cfg, selection="point_products" if method == "point30" else "all_products")
                    state = FixedTwoStageAdaptiveState(FixedGatedLmsState.unity(cfg.stage1_lms),
                                                       FixedGatedLmsState.unity(cfg.stage2_lms))
                    for w in range(protocol["short"]["windows"]):
                        values, rows = [], []
                        before = list(state.stage1.accumulator_codes + state.stage2.accumulator_codes)
                        for j in range(120):
                            index = w * 120 + j
                            x, (d1, d2) = input_tags(seed, index)
                            result = plant(x, d1, d2, case, pipeline, index)
                            check_physical(result)
                            sample = digital_sample(result.pipeline)
                            rows.append(FourLaneConversion(index, index % 4, sample))
                            values.append({"x": x, "d": [d1, d2], "v": voltage_fields(result), "word": word_fields(sample)})
                        result = correct_fixed_four_lane_window(rows, state, wcfg)
                        if any(c.saturated_low or c.saturated_high for c in result.calibrations):
                            raise ValueError("digital clipping in short path")
                        updates = (result.stage1_update, result.stage2_update)
                        if any(u.requested_deltas != u.applied_deltas for u in updates):
                            raise ValueError("coefficient saturation in short path")
                        emit(handle, {"case": case["name"], "seed": seed, "method": method, "window": w,
                             "before": before, "after": list(result.state.stage1.accumulator_codes + result.state.stage2.accumulator_codes),
                             "coefficients": [list(u.coefficient_codes_before) for u in updates],
                             "products_scaled": [list(u.selected_product_sums) for u in updates],
                             "gate_counts": [list(u.selected_gate_counts) for u in updates],
                             "requests": [list(u.requested_deltas) for u in updates],
                             "output_scaled": [c.unclipped_output_scaled for c in result.calibrations],
                             "raw1_scaled": [c.stage1_raw_scaled for c in result.calibrations],
                             "y1_scaled": result.stage1_learning_outputs_scaled,
                             "y2_scaled": result.stage2_learning_outputs_scaled, "values": values})
                        state = result.state
                        windows += 1
                        conversions += 120
                        observations += 4 if method == "point30" else 120
                    paths += 1
    return {"paths": paths, "windows": windows, "physical_conversions": conversions,
            "observations_per_bank": observations, "bank_commits": 2 * windows}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    if not args.run_id.replace("_", "").replace("-", "").isalnum():
        raise ValueError("run-id must be a simple directory name")
    out = ROOT / "artifacts/runs/EXP_060" / args.run_id
    out.mkdir(parents=True, exist_ok=False)
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    source = json.loads((ROOT / protocol["source_protocol"]).read_text(encoding="utf-8"))
    write(out / "protocol.json", protocol)
    write(out / "source_protocol.json", source)
    frozen = hashes()
    write(out / "source_hashes.json", frozen)
    write(out / "environment.json", {"python": sys.version, "executable": sys.executable, "platform": platform.platform()})
    try:
        pipeline, cfg = fixed_setup(source)
        counts = {"grid": grid(out, protocol, pipeline, cfg)}
        print("grid complete", counts["grid"], flush=True)
        counts["boundary"] = boundary(out, protocol, pipeline, cfg)
        print("boundary complete", counts["boundary"], flush=True)
        counts["short"] = short(out, protocol, pipeline, cfg)
        assert hashes() == frozen
        write(out / "run_summary.json", {"status": "complete", "counts": counts, "source_hashes_unchanged": True})
        print(json.dumps(counts), flush=True)
    except Exception:
        write(out / "run_failure.json", {"traceback": traceback.format_exc()})
        raise


if __name__ == "__main__":
    main()
