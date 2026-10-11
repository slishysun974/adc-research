"""Freeze and execute independent exact preflight, without long training."""

import argparse
from dataclasses import replace
from fractions import Fraction as F
from hashlib import sha256
import json
from math import nextafter, inf
from pathlib import Path
import traceback

from adc_research.calibration.fixed_adaptive_two_stage import FixedTwoStageAdaptiveConfig, FixedTwoStageAdaptiveState
from adc_research.calibration.fixed_four_lane_window import FixedFourLaneWindowConfig, FourLaneConversion, correct_fixed_four_lane_window
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsConfig, FixedGatedLmsState, exported_coefficient_codes, adaptive_lower_thresholds_scaled, update_fixed
from adc_research.calibration.fixed_pwl import FixedPwlArithmetic, FixedPwlConfig, quantize_two_stage_config, correct_fixed, correct_two_stage_fixed_observed
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.evaluation.observations import digital_sample
from adc_research.platform.pipeline import process
from adc_research.platform.backend_sar import convert
from adc_research.theory.static_fixed_contract import nearest_even, export, pwl, readout, commit, local_error_bounds, gate_error_bounds, protected
from experiments.exp_057_static_two_stage_million.common import setup, truth, input_tags

ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = Path(__file__).with_name("protocol.json")


def write(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def rational_plant(x, d1, d2, a1, a2):
    # Offline analytic model, independently implemented from platform.
    def flash(v):
        return sum(v >= F(2 * j - 7, 8) for j in range(8)) - 4
    q1 = flash(x)
    v1 = 4 * a1 * (x - F(q1, 4) + F(d1, 32))
    q2 = flash(v1)
    v2 = 4 * a2 * (v1 - F(q2, 4) + F(d2, 32))
    backend = (128 * (v2 + 1)).__floor__() - 128
    assert -1 <= v2 < 1
    return q1, q2, backend, v1, v2


def config(source):
    _, floating = setup(source)
    cascade = quantize_two_stage_config(floating.cascade, FixedPwlArithmetic())
    steps = tuple(F(n, source["steps"]["stage1_denominator"]) for n in source["steps"]["numerators"]) + tuple(F(n, source["steps"]["stage2_denominator"]) for n in source["steps"]["numerators"])
    cfg = FixedTwoStageAdaptiveConfig(cascade,
        FixedGatedLmsConfig(1024, steps[:4]), FixedGatedLmsConfig(256, steps[4:]))
    return cfg, steps


def static_grid(source, cfg, protocol):
    grid = protocol["fixed_state_grid"]
    n = grid["points"]
    rows = []
    bound_checks = protected_checks = gate_changes = 0
    max_errors = [F(0), F(0)]
    for case in source["cases"]:
        if case["name"] not in grid["cases"]:
            continue
        a1, a2 = F(str(case["stage1"][0])), F(str(case["stage2"][0]))
        k = (1 / a1,) * 4 + (1 / a2,) * 4
        codes = tuple(nearest_even(1024 * value) for value in k)
        khat = tuple(F(c, 1024) for c in codes)
        frozen = replace(cfg.cascade,
                         stage1_pwl=replace(cfg.cascade.stage1_pwl, coefficient_codes=codes[:4]),
                         stage2_pwl=replace(cfg.cascade.stage2_pwl, coefficient_codes=codes[4:]))
        counts = {level: {"gate": [[0]*4 for _ in range(2)], "basis": [[0]*4 for _ in range(2)], "both": [[0]*4 for _ in range(2)], "max_local": [F(0), F(0)]}
                  for level in grid["levels"]}
        for i in range(n):
            x = F(-41, 50) + F(2*i+1, 2*n) * F(41, 25)
            for d1, d2 in ((-1,-1), (-1,1), (1,-1), (1,1)):
                q1, q2, backend, _, _ = rational_plant(x, d1, d2, a1, a2)
                values = (readout(q1,q2,F(backend),d1,d2,k,data_q3=False),
                          readout(q1,q2,F(backend),d1,d2,k,data_q3=True),
                          readout(q1,q2,F(backend),d1,d2,khat,data_q3=True))
                actual = correct_two_stage_fixed_observed(DigitalCalibrationSample(q1,q2,backend,d1,d2), frozen)
                final = values[2]
                assert actual.stage1_raw_scaled == 8 * final.raw1
                assert actual.stage1_pwl.corrected_code_scaled - 512*d1 == 8*final.y1
                assert actual.stage2_pwl.corrected_code_scaled - 128*d2 == 8*final.y2
                assert actual.unclipped_output_scaled == 8*final.output
                assert not actual.saturated_low and not actual.saturated_high
                for level, value in zip(grid["levels"], values, strict=True):
                    c = counts[level]
                    for bank, y in enumerate((value.y1,value.y2)):
                        c["max_local"][bank] = max(c["max_local"][bank],abs(y))
                        for j in range(4):
                            g, b = value.gates[bank][j], value.support[bank][j]
                            c["gate"][bank][j] += int(g)
                            c["basis"][bank][j] += int(b)
                            c["both"][bank][j] += int(g and b)
                base = values[0]
                bounds = local_error_bounds(base.raw1,F(backend),max(k[:4]))
                threshold_bounds = gate_error_bounds()
                for bank, (y, yh) in enumerate(zip((base.y1,base.y2),(final.y1,final.y2),strict=True)):
                    error = abs(yh-y)
                    assert error <= bounds[bank]
                    max_errors[bank] = max(max_errors[bank],error)
                    bound_checks += 1
                    for j in range(1,4):
                        margin = abs(y)-base.thresholds[bank][j]
                        assert abs(final.thresholds[bank][j]-base.thresholds[bank][j]) <= threshold_bounds[bank][j]
                        if protected(margin,bounds[bank],threshold_bounds[bank][j]):
                            assert base.gates[bank][j] == final.gates[bank][j]
                            protected_checks += 1
                        gate_changes += int(base.gates[bank][j] != final.gates[bank][j])
        for level,c in counts.items():
            if a1<1:
                assert c["gate"][0][2] == 0
            if a2<1:
                assert c["gate"][1][2] == 0
            assert c["basis"][0][3] == c["basis"][1][3] == 0
            rows.append({"case":case["name"],"level":level,"observations":n*4,
                         **{key:value for key,value in c.items() if key!="max_local"},
                         "max_local":list(map(float,c["max_local"]))})
        print("fixed-state grid checked",case["name"],flush=True)
    return {"rows":rows,"local_bounds_checked":bound_checks,"protected_gates_checked":protected_checks,
            "gate_changes_exact_to_q1_10_q3":gate_changes,"max_local_errors":list(map(float,max_errors)),
            "original_integer_readouts_checked":len(grid["cases"])*n*4,
            "mathematical_rational_backend_control":True,"new_training":False}


def edges(source, cfg):
    pipeline, _ = setup(source)
    counts = {"q3_pwl_words":0,"gate_neighbors":0,"export_neighbors":0,
              "request_saturation_probes":0,"flash_float_probes":0,
              "rational_flash_probes":0,"sar_float_probes":0,"float_rational_floor_disagreements":0}
    for width in (32,128):
        bankcfg = cfg.stage2_lms if width==32 else cfg.stage1_lms
        for codes in ((1024,)*4,(1025,1043,1067,1101),(0,2047,1024,1)):
            k = tuple(F(c,1024) for c in codes)
            pcfg = FixedPwlConfig(8*width,codes,tuple(map(float,k)),FixedPwlArithmetic(),(False,)*4)
            for raw in range(-32*width,32*width):
                expected = pwl(F(raw,8),width,k,True)
                assert correct_fixed(raw,pcfg).corrected_code_scaled == 8*expected
                counts["q3_pwl_words"] += 1
            thresholds = adaptive_lower_thresholds_scaled(codes,bankcfg)
            state = FixedGatedLmsState(tuple(c*4096 for c in codes),(0,)*4,(0,)*4,(0,)*4)
            for j,t in enumerate(thresholds):
                for sign in (-1,1):
                    for delta in (-1,0,1):
                        y = sign*(t+delta)
                        result = update_fixed(state,dither_code_scaled=128,corrected_output_scaled=y,config=bankcfg)
                        assert result.gate_mask[j] == (j==0 or abs(y)>=t)
                        counts["gate_neighbors"] += 1
    for c in (0,1,1023,1024,1025,2046):
        for delta in (-1,0,1):
            a = c*4096+2048+delta
            state = FixedGatedLmsState((a,)*4,(0,)*4,(0,)*4,(0,)*4)
            assert exported_coefficient_codes(state,cfg.stage1_lms) == export((a,)*4)
            counts["export_neighbors"] += 1
    for a in (0,1,1<<22,2047*4096-1,2047*4096):
        for product in (-3,-1,1,3):
            step = F(1,1<<23)
            tied = replace(cfg.stage2_lms,step_sizes=(step,)*4)
            state = FixedGatedLmsState((a,)*4,(0,)*4,(0,)*4,(0,)*4)
            result = update_fixed(state,dither_code_scaled=8,corrected_output_scaled=8*product,config=tied)
            expected = nearest_even(-step*product*(1<<22))
            assert result.requested_accumulator_deltas[0] == expected
            assert result.accumulator_codes_after[0] == min(2047*4096,max(0,a+expected))
            counts["request_saturation_probes"] += 1
    # Every float probe follows the original bias-addition operation order.
    for m in range(257):
        center = -1+m/128
        for v in (nextafter(center,-inf),center,nextafter(center,inf)):
            got = convert(v,pipeline.backend)
            original = min(127,max(-128,int((F.from_float((v+1)*128)).__floor__())-128))
            exact = min(127,max(-128,(128*(F.from_float(v)+1)).__floor__()-128))
            assert got.centered_code == original
            counts["float_rational_floor_disagreements"] += int(original!=exact)
            counts["sar_float_probes"] += 1
    for case in source["cases"]:
        nonideal = truth(case)
        for t in pipeline.stage1.quantizer.thresholds:
            for x in (nextafter(t,-inf),t,nextafter(t,inf)):
                for d1,d2 in ((-1,-1),(-1,1),(1,-1),(1,1)):
                    result = process(x,pipeline,dither_symbols=(d1,d2),nonidealities=nonideal)
                    q1 = sum(x >= threshold for threshold in pipeline.stage1.quantizer.thresholds)-4
                    assert result.stage1.quantizer.symbol == q1
                    counts["flash_float_probes"] += 1
    # Exact unity counterexample across the entire negative endpoint bin.
    witnesses = []
    for t in (F(2*j-7,8) for j in range(8)):
        for dx in (-F(1,1<<40),F(0),F(1,1<<40)):
            for d1,d2 in ((-1,-1),(-1,1),(1,-1),(1,1)):
                q1,q2,be,v1,v2 = rational_plant(t+dx,d1,d2,F(1),F(1))
                r = readout(q1,q2,F(be),d1,d2,(F(1),)*8,data_q3=False)
                assert r.y1 == (2048*(t+dx-F(q1,4))).__floor__()
                assert r.y2 == (512*(v1-F(q2,4))).__floor__()
                counts["rational_flash_probes"] += 1
    for x in (F(1,8),F(1,8)+F(1,4096),F(1,8)+F(1,2048)):
        q1,q2,be,v1,v2 = rational_plant(x,-1,-1,F(1),F(1))
        r = readout(q1,q2,F(be),-1,-1,(F(1),)*8,data_q3=False)
        witnesses.append({"x":str(x),"q1":q1,"q2":q2,"backend":be,"y1":str(r.y1),"y2":str(r.y2),"third_gates":[r.gates[0][2],r.gates[1][2]],"third_basis":[r.support[0][2],r.support[1][2]]})
    assert witnesses[0]["third_gates"][0] and witnesses[1]["third_gates"][0]
    assert not witnesses[2]["third_gates"][0]
    # Deliberate source state near a second-gate boundary: export to unity
    # opens the gate although the raw has no second basis support.
    source=(F(4097,4096),)*8
    before=readout(0,0,F(16),1,-1,source,data_q3=False)
    after=readout(0,0,F(16),1,-1,(F(1),)*8,data_q3=True)
    e=local_error_bounds(before.raw1,F(16),source[0])
    t=gate_error_bounds()
    margin=abs(before.y2)-before.thresholds[1][1]
    assert not before.gates[1][1] and after.gates[1][1]
    assert not protected(margin,e[1],t[1][1])
    return {**counts,"unity_witnesses":witnesses,
            "unprotected_gate_change":{"digital_word":[0,0,16,1,-1],"source_slope":str(source[0]),
                "rear_second_margin":str(margin),"before_gate":False,"after_gate":True,
                "rear_second_basis_nonzero":after.support[1][1],"protected":False}}


def short_paths(source,cfg,steps,protocol,folder):
    pipeline,_ = setup(source)
    rows = []
    total = commits = 0
    maxwidth = 0
    for case in source["cases"]:
        for seed in source["seeds"]:
            for method in protocol["short_paths"]["methods"]:
                windowcfg = FixedFourLaneWindowConfig(cfg,selection="point_products" if method=="point30" else "all_products")
                state = FixedTwoStageAdaptiveState(FixedGatedLmsState.unity(cfg.stage1_lms),FixedGatedLmsState.unity(cfg.stage2_lms))
                acc = (1<<22,)*8
                gates = [[0]*4 for _ in range(2)]
                bases = [[0]*4 for _ in range(2)]
                both = [[0]*4 for _ in range(2)]
                states = [list(acc)]
                trace = []
                selected_count = 0
                for w in range(protocol["short_paths"]["windows"]):
                    observations=[]
                    for offset in range(120):
                        index=120*w+offset
                        x,tags=input_tags(seed,index)
                        raw=process(x,pipeline,sample_index=index,dither_symbols=tags,nonidealities=truth(case))
                        assert all(s.correctable and not s.main_input_overload_low and not s.main_input_overload_high
                                   for s in (raw.stage1,raw.stage2))
                        assert not raw.backend.overload_low and not raw.backend.overload_high
                        observations.append(FourLaneConversion(index,index%4,digital_sample(raw)))
                    result=correct_fixed_four_lane_window(observations,state,windowcfg)
                    k=tuple(F(c,1024) for c in export(acc))
                    products=[F(0)]*8
                    windowgates=[0]*8
                    for offset,row in enumerate(observations):
                        ob=row.sample
                        value=readout(ob.stage1_symbol,ob.stage2_symbol,F(ob.backend_centered_code),ob.stage1_dither_symbol,ob.stage2_dither_symbol,k,data_q3=True)
                        actual=result.calibrations[offset]
                        assert actual.unclipped_output_scaled==8*value.output
                        assert result.stage1_learning_outputs_scaled[offset]==8*value.y1
                        assert result.stage2_learning_outputs_scaled[offset]==8*value.y2
                        assert not actual.saturated_low and not actual.saturated_high
                        maxwidth=max(maxwidth,actual.maximum_signed_data_bits_required)
                        # Output integerization occurs AFTER gate/product formation.
                        final=nearest_even(min(F(4095),max(F(0),value.output)))
                        assert 0<=final<=4095
                        if method=="full120" or offset<4:
                            selected_count+=1
                            for bank,(y,d) in enumerate(((value.y1,64*ob.stage1_dither_symbol),(value.y2,16*ob.stage2_dither_symbol))):
                                for j in range(4):
                                    g,b=value.gates[bank][j],value.support[bank][j]
                                    gates[bank][j]+=int(g);bases[bank][j]+=int(b);both[bank][j]+=int(g and b)
                                    windowgates[bank*4+j]+=int(g)
                                    if g:products[bank*4+j]+=d*y
                        total+=1
                    requests,after=commit(acc,tuple(products),30 if method=="point30" else 1,steps)
                    for bank,update in enumerate((result.stage1_update,result.stage2_update)):
                        assert update.requested_deltas==requests[bank*4:bank*4+4]
                        assert update.selected_product_sums==tuple(64*p for p in products[bank*4:bank*4+4])
                        assert update.selected_gate_counts==tuple(windowgates[bank*4:bank*4+4])
                        assert update.state.accumulator_codes==after[bank*4:bank*4+4]
                        assert update.requested_deltas==update.applied_deltas
                        commits+=1
                    trace.append({"window":w,"before":list(acc),"product_sums_q6":[int(64*p) for p in products],"requests":list(requests),"after":list(after)})
                    acc=after;state=result.state;states.append(list(acc))
                rows.append({"case":case["name"],"seed":seed,"method":method,"scored_conversions":120*protocol["short_paths"]["windows"],"learning_observations_per_bank":selected_count,"gates":gates,"basis":bases,"both":both,"states_q22":states,"commits":trace})
        print("short paths checked",case["name"],flush=True)
    write(folder/"short_paths.json",rows)
    return {"paths":len(rows),"original_platform_conversions":total,"bank_commits_checked":commits,
            "maximum_signed_data_bits_required":maxwidth,"overloads":0,"output_clips":0,"coefficient_saturations":0,
            "per_path_scored_conversions":120*protocol["short_paths"]["windows"],"million_training":False}


def main(folder):
    folder.mkdir(parents=True,exist_ok=False)
    protocol=json.loads(PROTOCOL.read_text(encoding="utf-8"))
    source_path=ROOT/protocol["source_protocol"]
    source=json.loads(source_path.read_text(encoding="utf-8"))
    write(folder/"protocol.json",protocol)
    write(folder/"source_protocol.json",source)
    files=sorted(set(ROOT.glob("src/**/*.py"))|set(Path(__file__).parent.glob("*.py"))|{PROTOCOL,source_path,ROOT/"configs/architectures/gu_behavioral_v1.yaml"})
    hashes={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in files}
    write(folder/"source_hashes.json",hashes)
    try:
        cfg,steps=config(source)
        result={"edges":edges(source,cfg)}
        write(folder/"edges.json",result["edges"])
        print("edge controls checked",flush=True)
        result["grid"]=static_grid(source,cfg,protocol)
        write(folder/"grid.json",result["grid"])
        result["short"]=short_paths(source,cfg,steps,protocol,folder)
        assert all(sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in hashes.items())
        result.update(passed=True,source_hashes_unchanged=True,source_files=len(hashes),chip_certified=False)
        write(folder/"summary.json",result)
        print(json.dumps({"passed":True,"short":result["short"],"sources":len(hashes)}),flush=True)
    except Exception:
        write(folder/"failure.json",{"passed":False,"traceback":traceback.format_exc()})
        raise


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("folder",type=Path)
    main(parser.parse_args().folder.resolve())
