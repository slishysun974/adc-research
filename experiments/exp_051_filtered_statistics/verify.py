"""Independent scalar PWL, gate, filter and coefficient replay."""

import argparse
from fractions import Fraction as F
import json
from pathlib import Path

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from experiments.exp_049_normal_start_closed_loop.run import ROOT,digest,write,score
from experiments.exp_049_normal_start_closed_loop.verify_and_propagate import scalar,nearest


def run(directory):
    summary = json.loads((directory/"summary.json").read_text())
    assert digest(directory/"protocol.json") == summary["protocol_sha256"]
    for path,expected in summary["source_evidence_sha256"].items():
        assert digest(Path(path)) == expected,path
    counts = {"windows":0,"scalar_conversions":0,"state_coordinates":0,
              "filter_state_checks":0,"front_delta_identities":0,"online_codes":0}
    outcome_paths = []
    for case in summary["cases"]:
        path = directory/case["name"]/"analog_digital_records.jsonl"
        assert digest(path) == case["record_sha256"]
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        samples,targets = tuple(Sample(**r["sample"]) for r in rows),tuple(r["ideal_code_offline_only"] for r in rows)
        assert len(samples) == 19200
        for compact in case["methods"]:
            method = compact["method"]
            path = directory/case["name"]/(method+".json")
            assert digest(path) == compact["artifact_sha256"]
            outcome_paths.append(path)
            detail = json.loads(path.read_text())
            previous = None
            filters = [[0]*4 for _ in range(2)]
            shadows = [[F(0)]*4 for _ in range(3)]
            online = []
            for window in detail["windows"]:
                start = 120*window["window"]
                before,after = window["coefficients_before"],window["coefficients_after"]
                if previous is None:
                    assert before["stage1_q22"] == before["stage2_q22"] == [1 << 22]*4
                else:
                    assert previous == before
                previous = after
                for bank in ("stage1","stage2"):
                    assert before[bank] == [nearest(x,4096) for x in before[bank+"_q22"]]
                products = [[0]*4 for _ in range(2)]
                target_sums,error_sums = [0]*4,[0]*4
                actual_codes = []
                for offset,sample in enumerate(samples[start:start+120]):
                    final,y1,y2,_ = scalar(sample,before)
                    actual_codes.append(final)
                    counts["scalar_conversions"] += 1
                    if offset >= 4:
                        continue
                    for b,(y,d,width,bank) in enumerate(((y1,512*sample.stage1_dither_symbol,1024,"stage1"),
                                                       (y2,128*sample.stage2_dither_symbol,256,"stage2"))):
                        for i in range(4):
                            if i == 0 or abs(y) >= nearest(width*sum(before[bank][:i]),1024):
                                products[b][i] += d*y
                                if b == 0:
                                    target = 8*targets[start+offset]-16384-4096*sample.stage1_symbol
                                    target_sums[i] += d*target
                                    error_sums[i] += d*(y-target)
                for b,bank in enumerate(("stage1","stage2")):
                    assert products[b] == window[bank+"_products"]
                    for i,norm in enumerate((1,3,6,12)):
                        denominator = 4000 if b == 0 else 250
                        old_h = filters[b][i]
                        if method == "ema_quarter":
                            h = nearest(3*old_h+4*products[b][i],4)
                            filters[b][i] = h
                            assert h == window["filters_after"][b][i]
                            assert abs(h) <= (71270400 if b == 0 else 4454400)
                            counts["filter_state_checks"] += 1
                            delta = nearest(-norm*30*h,denominator*4)
                        else:
                            h = 4*products[b][i]
                            delta = nearest(-norm*30*products[b][i],denominator*(4 if method == "quarter_step" else 1))
                        assert delta == window["requested_deltas"][b][i]
                        assert after[bank+"_q22"][i] == min(max(before[bank+"_q22"][i]+delta,0),2047 << 12)
                        actual = after[bank+"_q22"][i]-before[bank+"_q22"][i]
                        assert actual == window["applied_deltas"][b][i]
                        counts["state_coordinates"] += 1
                        if b != 0:
                            continue
                        evidence = window["front_attribution"][i]
                        assert evidence["target_product_sum"] == target_sums[i]
                        assert evidence["error_product_sum"] == error_sums[i]
                        if method == "ema_quarter":
                            shadows[0][i] = 3*shadows[0][i]/4+target_sums[i]
                            shadows[1][i] = 3*shadows[1][i]/4+error_sums[i]
                            shadows[2][i] = 3*shadows[2][i]/4+F(h)-F(3*old_h+4*products[b][i],4)
                        else:
                            shadows[0][i],shadows[1][i],shadows[2][i] = F(4*target_sums[i]),F(4*error_sums[i]),F(0)
                        assert sum((s[i] for s in shadows),F(0)) == h
                        factor = F(-norm*30,4000*4*(4 if method == "quarter_step" else 1))
                        for part,key in enumerate(("target_delta_q22","error_delta_q22","filter_rounding_delta_q22")):
                            assert F(evidence[key]) == factor*shadows[part][i]
                        assert sum((F(evidence[k]) for k in ("target_delta_q22","error_delta_q22","filter_rounding_delta_q22",
                            "request_rounding_delta_q22","clipping_delta_q22")),F(0)) == actual
                        counts["front_delta_identities"] += 1
                assert F(window["integer_error_stats"]["mse_codes_squared"]) == F(sum((a-b)**2 for a,b in zip(actual_codes,targets[start:start+120])),120)
                if start >= 15360:
                    online.extend(actual_codes)
                    counts["online_codes"] += 120
                counts["windows"] += 1
            assert online == detail["online_sine_codes"]
            assert score(online,targets[15360:],case["tone_bin"]) == compact["online_sine"]
        print(f"Verified {case['name']}",flush=True)
    write(directory/"verification.json",{"counts":counts,"independent_scalar_filter_replay_passed":True,
        "summary_sha256":digest(directory/"summary.json"),"protocol_sha256":summary["protocol_sha256"],
        "source_sha256":{str(Path(__file__)):digest(Path(__file__)),
            str(ROOT/"experiments/exp_049_normal_start_closed_loop/verify_and_propagate.py"):digest(ROOT/"experiments/exp_049_normal_start_closed_loop/verify_and_propagate.py")},
        "outcome_sha256":{str(p):digest(p) for p in outcome_paths}})
    print(json.dumps(counts),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    run(parser.parse_args().directory.resolve())
