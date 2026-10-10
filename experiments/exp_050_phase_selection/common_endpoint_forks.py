"""Post-primary offline intervention: distinguish training and sine effects.

All three four-point schedules start the sine at the fixed-phase training
endpoint on the same record. Schedules keep their declared phase state.
This control does not change the prespecified normal-start screening result.
"""

import argparse
from dataclasses import replace
import json
from pathlib import Path

from adc_research.calibration.fixed_four_lane_window import (
    FourLaneConversion, FixedFourLaneWindowConfig, correct_fixed_four_lane_window,
)
from adc_research.calibration.window_phase_selection import WindowPhaseSchedule
from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from experiments.exp_032_online_lms_rtl.generate_vectors import _config
from experiments.exp_039_four_lane_dynamic_loop.run import code,coefficients
from experiments.exp_049_normal_start_closed_loop.run import ROOT,digest,write,score
from experiments.exp_049_normal_start_closed_loop.verify_and_propagate import make_state,scalar,nearest


def run(directory):
    summary = json.loads((directory/"summary.json").read_text())
    counts = {"windows":0,"scalar_conversions":0,"state_coordinates":0}
    cases = []
    cfg = _config()
    for case in summary["cases"]:
        path = directory/case["name"]/"analog_digital_records.jsonl"
        assert digest(path) == case["record_sha256"]
        rows = [json.loads(line) for line in path.read_text().splitlines()][15360:]
        samples,targets = tuple(Sample(**r["sample"]) for r in rows),tuple(r["ideal_code_offline_only"] for r in rows)
        fixed = next(m for m in case["methods"] if m["method"] == "fixed")
        common = make_state(fixed["training_endpoint"],cfg)
        common = replace(common,stage1=replace(common.stage1,sample_count=15360),
                         stage2=replace(common.stage2,sample_count=15360))
        methods = []
        for method in ("fixed","rotate","xorshift32"):
            original_path = directory/case["name"]/(method+".json")
            expected = next(m for m in case["methods"] if m["method"] == method)["artifact_sha256"]
            assert digest(original_path) == expected
            detail = json.loads(original_path.read_text())
            schedule = WindowPhaseSchedule(method,detail["windows"][128]["selection_state_before"])
            state = common
            codes,windows = [],[]
            for start in range(0,3840,120):
                before = state
                batch = samples[start:start+120]
                before_codes = coefficients(before,cfg)
                result = correct_fixed_four_lane_window(tuple(FourLaneConversion(15360+start+i,i % 4,s)
                    for i,s in enumerate(batch)),state,FixedFourLaneWindowConfig(cfg,selection="point_products",point_phase=schedule.phase))
                state = result.state
                outputs = [code(c) for c in result.calibrations]
                reference = [scalar(s,before_codes) for s in batch]
                assert outputs == [r[0] for r in reference]
                for b,(bank,update) in enumerate((("stage1",result.stage1_update),("stage2",result.stage2_update))):
                    for i,norm in enumerate((1,3,6,12)):
                        width = 1024 if b == 0 else 256
                        threshold = nearest(width*sum(before_codes[bank][:i]),1024)
                        product = 0
                        for offset,(sample,ref) in enumerate(zip(batch,reference,strict=True)):
                            if offset//4 != schedule.phase:
                                continue
                            y = ref[1] if b == 0 else ref[2]
                            if i == 0 or abs(y) >= threshold:
                                d = (512*sample.stage1_dither_symbol) if b == 0 else (128*sample.stage2_dither_symbol)
                                product += d*y
                        delta = nearest(-norm*30*product,4000 if b == 0 else 250)
                        assert update.requested_deltas[i] == delta
                        after = before_codes[bank+"_q22"][i]+delta
                        assert getattr(state,bank).accumulator_codes[i] == min(max(after,0),2047 << 12)
                        counts["state_coordinates"] += 1
                codes.extend(outputs)
                windows.append({"sine_window":start//120,"phase":schedule.phase,
                    "coefficients_before":before_codes,"coefficients_after":coefficients(state,cfg)})
                schedule = schedule.advance()
                counts["windows"] += 1
                counts["scalar_conversions"] += 120
            metrics = score(codes,targets,case["tone_bin"])
            if method == "fixed":
                assert codes == detail["online_sine_codes"]
                assert metrics == fixed["online_sine"]
            methods.append({"method":method,"online_sine":metrics,"codes":codes,"windows":windows,
                "paired_gain_vs_fixed_db":metrics["sndr_db"]-fixed["online_sine"]["sndr_db"]})
        cases.append({"name":case["name"],"trial":case["trial"],"methods":methods})
    comparisons = []
    for method in ("rotate","xorshift32"):
        gains = [next(m for m in c["methods"] if m["method"] == method)["paired_gain_vs_fixed_db"] for c in cases]
        comparisons.append({"method":method,"mean_gain_db":sum(gains)/len(gains),
            "positive_cells":sum(g > 0 for g in gains),"minimum_gain_db":min(gains),"maximum_gain_db":max(gains)})
    write(directory/"common_endpoint_forks.json",{"post_primary_diagnostic":True,
        "common_state_contract":"fixed-phase training endpoint for all three selectors; no oracle coefficients; schedule state retained",
        "prespecified_normal_start_screen_unchanged":True,"counts":counts,"cases":cases,
        "comparisons":comparisons,"summary_sha256":digest(directory/"summary.json"),
        "source_sha256":{str(Path(__file__)):digest(Path(__file__))}})
    print(json.dumps({"counts":counts,"comparisons":comparisons}),flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    run(parser.parse_args().directory.resolve())
