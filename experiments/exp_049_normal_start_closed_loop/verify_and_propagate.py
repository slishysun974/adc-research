"""Independent scalar replay and offline sine-state intervention audit."""

import argparse
from dataclasses import replace
from fractions import Fraction as F
import json
from pathlib import Path

from adc_research.calibration.fixed_point import round_fraction
from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_033_fixed_online_box.run import _initial
from experiments.exp_049_normal_start_closed_loop.run import ROOT, digest, write, frozen_codes, score


def nearest(numerator, denominator):
    # Independent signed integer nearest-even, without production arithmetic.
    sign = -1 if numerator < 0 else 1
    q,r = divmod(abs(numerator),denominator)
    return sign*(q+int(2*r > denominator or (2*r == denominator and q % 2)))


def pwl(raw, width, slopes):
    if not -4*width <= raw < 4*width:
        raise ValueError("independent scalar correction domain")
    index = min(abs(raw)//width,3)
    local = abs(raw)-index*width
    return (-1 if raw < 0 else 1)*(nearest(local*slopes[index],1024)+nearest(width*sum(slopes[:index]),1024))


def scalar(sample, before):
    y2 = pwl(8*sample.backend_centered_code,256,before["stage2"])-128*sample.stage2_dither_symbol
    raw1 = 1024*sample.stage2_symbol+y2
    y1 = pwl(raw1,1024,before["stage1"])-512*sample.stage1_dither_symbol
    final = min(max(nearest(16384+4096*sample.stage1_symbol+y1,8),0),4095)
    return final,y1,y2,raw1


def make_state(endpoint,cfg):
    initial = _initial(cfg)
    return replace(initial,stage1=replace(initial.stage1,accumulator_codes=tuple(endpoint["stage1_q22"])),
                   stage2=replace(initial.stage2,accumulator_codes=tuple(endpoint["stage2_q22"])))


def run(directory, source):
    summary = json.loads((directory/"summary.json").read_text())
    protocol = json.loads((directory/"protocol.json").read_text())
    assert digest(directory/"protocol.json") == summary["protocol_sha256"]
    for path,expected in {**summary["source_sha256"],**summary["source_evidence_sha256"]}.items():
        assert digest(Path(path)) == expected,path
    cfg = _config()
    interventions,counts = [], {"windows":0,"scalar_conversions":0,"state_coordinates":0,"front_product_identities":0}
    for case in summary["cases"]:
        record_path = (source/case["name"] if case["section"] == "prior" else directory/case["name"])/"analog_digital_records.jsonl"
        if case["section"] == "holdout":
            assert digest(record_path) == case["record_sha256"]
        rows = tuple(json.loads(line) for line in record_path.read_text().splitlines())
        samples = tuple(Sample(**r["sample"]) for r in rows)
        targets = tuple(r["ideal_code_offline_only"] for r in rows)
        training = protocol["training_samples"]
        tone = 67 if case["section"] == "prior" else next(i["tone_bin"] for i in protocol["inputs"] if f"__{i['name']}__" in case["name"])
        for compact in case["methods"]:
            method = compact["method"]
            detail_path = directory/case["name"]/(method+".json")
            detail = json.loads(detail_path.read_text())
            endpoint = make_state(compact["training_endpoint"],cfg)
            trained_codes = frozen_codes(samples[training:],endpoint,cfg)
            variants = {"trained_both":list(trained_codes),"current_front":[],"current_backend":[],"current_both":[]}
            previous = None
            for window in detail["windows"]:
                start = 120*window["window"]
                before,after = window["coefficients_before"],window["coefficients_after"]
                if previous is None:
                    assert before["stage1_q22"] == before["stage2_q22"] == [1 << 22]*4
                else:
                    assert before == previous
                previous = after
                counts["windows"] += 1
                for bank in ("stage1","stage2"):
                    assert before[bank] == [nearest(a,4096) for a in before[bank+"_q22"]]
                reconstructed = []
                product_sums = [[0]*4 for _ in range(2)]
                signal = [0]*4
                error = [0]*4
                for offset,sample in enumerate(samples[start:start+120]):
                    final,y1,y2,raw1 = scalar(sample,before)
                    reconstructed.append(final)
                    counts["scalar_conversions"] += 1
                    take = method == "all_products" or offset < 4
                    if take:
                        for b,(local,d,width,slopes) in enumerate(((y1,512*sample.stage1_dither_symbol,1024,before["stage1"]),
                            (y2,128*sample.stage2_dither_symbol,256,before["stage2"]))):
                            for i in range(4):
                                gate = i == 0 or abs(local) >= nearest(width*sum(slopes[:i]),1024)
                                if gate:
                                    product_sums[b][i] += d*local
                                    if b == 0:
                                        target = 8*targets[start+offset]-16384-4096*sample.stage1_symbol
                                        signal[i] += d*target
                                        error[i] += d*(local-target)
                multiplier = 1 if method == "all_products" else 30
                for b,bank in enumerate(("stage1","stage2")):
                    denom = 4000 if b == 0 else 250
                    for i,norm in enumerate((1,3,6,12)):
                        delta = nearest(-norm*multiplier*product_sums[b][i],denom)
                        actual = after[bank+"_q22"][i]-before[bank+"_q22"][i]
                        maximum = 2047 << 12
                        assert after[bank+"_q22"][i] == min(max(before[bank+"_q22"][i]+delta,0),maximum)
                        counts["state_coordinates"] += 1
                        if b == 0:
                            gate = window["front_attribution"][i]
                            assert product_sums[b][i] == gate["learning_product_sum"]
                            assert signal[i] == gate["target_product_sum"]
                            assert error[i] == gate["error_product_sum"]
                            assert sum((F(gate[k]) for k in ("target_delta_q22","error_delta_q22",
                                "rounding_delta_q22","clipping_delta_q22")),F(0)) == actual
                            counts["front_product_identities"] += 1
                cf = window["same_window_counterfactual"]
                assert cf["sse_change_backend_first"]+cf["sse_change_front_second"] == cf["sse_change_all"]
                if start >= training:
                    test_start = start-training
                    assert reconstructed == detail["online_sine_codes"][test_start:test_start+120]
                    current = make_state(before,cfg)
                    batch = samples[start:start+120]
                    front = replace(endpoint,stage1=current.stage1)
                    back = replace(endpoint,stage2=current.stage2)
                    variants["current_front"].extend(frozen_codes(batch,front,cfg))
                    variants["current_backend"].extend(frozen_codes(batch,back,cfg))
                    variants["current_both"].extend(reconstructed)
            scores = {name:score(codes,targets[training:],tone) for name,codes in variants.items()}
            sse = {name:sum((a-b)**2 for a,b in zip(codes,targets[training:],strict=True)) for name,codes in variants.items()}
            base = sse["trained_both"]
            effects = {"front_only_sse":sse["current_front"]-base,"backend_only_sse":sse["current_backend"]-base,
                "interaction_sse":sse["current_both"]-sse["current_front"]-sse["current_backend"]+base,
                "total_sse":sse["current_both"]-base}
            assert effects["front_only_sse"]+effects["backend_only_sse"]+effects["interaction_sse"] == effects["total_sse"]
            interventions.append({"case":case["name"],"section":case["section"],"method":method,
                "scores":scores,"exact_sse_effects":effects,
                "changed_codes_vs_frozen":{name:sum(a != b for a,b in zip(codes,trained_codes)) for name,codes in variants.items()}})
            assert scores["current_both"] == compact["online_sine"]
            assert scores["trained_both"] == compact["frozen_checkpoint_sine"]["128"]
    output = {"counts":counts,"independent_scalar_replay_passed":True,"interventions":interventions,
        "summary_sha256":digest(directory/"summary.json"),"protocol_sha256":summary["protocol_sha256"],
        "source_sha256":{str(Path(__file__)):digest(Path(__file__))},
        "detail_sha256":{str(p):digest(p) for p in sorted(directory.glob("*/*products.json"))},
        "scope":"frozen trained/current bank interventions on identical sine observations; interaction retained; no feedback submission"}
    write(directory/"verification_and_propagation.json",output)
    print(json.dumps(counts),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    parser.add_argument("source",type=Path)
    args = parser.parse_args()
    run(args.directory.resolve(),args.source.resolve())
