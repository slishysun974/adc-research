"""Independent phase-control and scalar Gu replay of all declared paths."""

import argparse
from fractions import Fraction as F
import json
from pathlib import Path

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from experiments.exp_049_normal_start_closed_loop.run import ROOT,digest,write,score
from experiments.exp_049_normal_start_closed_loop.verify_and_propagate import scalar,nearest


def bitwise_prng(value):
    # Reference bit-vector transforms, independent of masked integer shifts.
    bits = [(value >> i) & 1 for i in range(32)]
    bits = [b ^ (bits[i-13] if i >= 13 else 0) for i,b in enumerate(bits)]
    bits = [b ^ (bits[i+17] if i+17 < 32 else 0) for i,b in enumerate(bits)]
    bits = [b ^ (bits[i-5] if i >= 5 else 0) for i,b in enumerate(bits)]
    return sum(b << i for i,b in enumerate(bits))


def run(directory):
    summary = json.loads((directory/"summary.json").read_text())
    protocol = json.loads((directory/"protocol.json").read_text())
    assert digest(directory/"protocol.json") == summary["protocol_sha256"]
    for path,expected in summary["source_evidence_sha256"].items():
        assert digest(Path(path)) == expected,path
    counts = {"windows":0,"scalar_conversions":0,"state_coordinates":0,
              "front_product_identities":0,"phase_state_checks":0,"online_codes":0}
    outcome_paths = []
    for case in summary["cases"]:
        record = directory/case["name"]/"analog_digital_records.jsonl"
        assert digest(record) == case["record_sha256"]
        rows = [json.loads(line) for line in record.read_text().splitlines()]
        samples = tuple(Sample(**r["sample"]) for r in rows)
        targets = tuple(r["ideal_code_offline_only"] for r in rows)
        assert len(samples) == protocol["training_samples"]+protocol["sine_samples"]
        assert sum(r["physical_overload"] for r in rows) == case["physical_overloads"]
        for compact in case["methods"]:
            method = compact["method"]
            path = directory/case["name"]/(method+".json")
            assert digest(path) == compact["artifact_sha256"]
            outcome_paths.append(path)
            detail = json.loads(path.read_text())
            previous,control = None,case["phase_seed"] if method == "xorshift32" else 0
            online = []
            for window in detail["windows"]:
                start = 120*window["window"]
                before,after = window["coefficients_before"],window["coefficients_after"]
                expected_phase = control % 30
                assert window["phase"] == expected_phase
                if method != "all_reference":
                    assert window["selection_state_before"] == control
                    assert window["selected_conversion_ids"] == [start+4*expected_phase+i for i in range(4)]
                    counts["phase_state_checks"] += 1
                else:
                    assert window["selected_conversion_ids"] == list(range(start,start+120))
                if previous is None:
                    assert before["stage1_q22"] == before["stage2_q22"] == [1 << 22]*4
                else:
                    assert previous == before
                previous = after
                for bank in ("stage1","stage2"):
                    assert before[bank] == [nearest(x,4096) for x in before[bank+"_q22"]]
                products = [[0]*4 for _ in range(2)]
                targets_sums,errors_sums,zero_counts = [0]*4,[0]*4,[0]*4
                actual_codes = []
                for offset,sample in enumerate(samples[start:start+120]):
                    final,y1,y2,raw1 = scalar(sample,before)
                    actual_codes.append(final)
                    counts["scalar_conversions"] += 1
                    take = method == "all_reference" or offset//4 == expected_phase
                    if not take:
                        continue
                    for b,(y,d,width,slopes) in enumerate(((y1,512*sample.stage1_dither_symbol,1024,before["stage1"]),
                        (y2,128*sample.stage2_dither_symbol,256,before["stage2"]))):
                        for i in range(4):
                            if i == 0 or abs(y) >= nearest(width*sum(slopes[:i]),1024):
                                products[b][i] += d*y
                                if b == 0:
                                    target = 8*targets[start+offset]-16384-4096*sample.stage1_symbol
                                    targets_sums[i] += d*target
                                    errors_sums[i] += d*(y-target)
                                    zero_counts[i] += abs(raw1) <= i*1024
                multiplier = 1 if method == "all_reference" else 30
                for b,bank in enumerate(("stage1","stage2")):
                    assert products[b] == window[bank+"_products"]
                    denominator = 4000 if b == 0 else 250
                    for i,normal in enumerate((1,3,6,12)):
                        delta = nearest(-normal*multiplier*products[b][i],denominator)
                        assert delta == window[bank+"_requested_deltas"][i]
                        assert after[bank+"_q22"][i] == min(max(before[bank+"_q22"][i]+delta,0),2047 << 12)
                        counts["state_coordinates"] += 1
                        if b == 0:
                            evidence = window["front_attribution"][i]
                            assert evidence["target_product_sum"] == targets_sums[i]
                            assert evidence["error_product_sum"] == errors_sums[i]
                            assert evidence["zero_basis_selected_count"] == zero_counts[i]
                            assert sum((F(evidence[k]) for k in ("target_delta_q22","error_delta_q22",
                                "rounding_delta_q22","clipping_delta_q22")),F(0)) == after[bank+"_q22"][i]-before[bank+"_q22"][i]
                            counts["front_product_identities"] += 1
                if start >= protocol["training_samples"]:
                    online.extend(actual_codes)
                    counts["online_codes"] += len(actual_codes)
                if method == "rotate":
                    control = (control+1) % 30
                elif method == "xorshift32":
                    control = bitwise_prng(control)
                counts["windows"] += 1
            assert online == detail["online_sine_codes"]
            assert score(online,targets[protocol["training_samples"]:],case["tone_bin"]) == compact["online_sine"]
        print(f"Verified {case['name']}",flush=True)
    result = {"counts":counts,"independent_bit_vector_and_scalar_replay_passed":True,
        "summary_sha256":digest(directory/"summary.json"),"protocol_sha256":summary["protocol_sha256"],
        "source_sha256":{str(Path(__file__)):digest(Path(__file__)),
            str(ROOT/"experiments/exp_049_normal_start_closed_loop/verify_and_propagate.py"):digest(ROOT/"experiments/exp_049_normal_start_closed_loop/verify_and_propagate.py")},
        "outcome_sha256":{str(p):digest(p) for p in outcome_paths}}
    write(directory/"verification.json",result)
    print(json.dumps(counts),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    run(parser.parse_args().directory.resolve())
