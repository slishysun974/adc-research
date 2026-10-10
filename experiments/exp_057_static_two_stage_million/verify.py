"""Independent original-platform and original-LMS replay of retained probes."""

import argparse
from dataclasses import replace
import json
from pathlib import Path

import numpy as np

from adc_research.calibration.gated_lms import GatedLmsState,update_block_mean
from adc_research.calibration.gated_lms import adaptive_lower_thresholds
from adc_research.calibration.pwl import PwlConfig,correct
from adc_research.calibration.adaptive_two_stage import TwoStageAdaptiveState,observe
from adc_research.evaluation.observations import digital_sample
from adc_research.platform.pipeline import process
from adc_research.platform.backend_sar import convert
from experiments.exp_057_static_two_stage_million.common import setup,truth,input_tags,write


def verify(folder):
    protocol=json.loads((folder/"protocol.json").read_text(encoding="utf-8-sig"))
    pipeline,cfg=setup(protocol)
    max_voltage=max_coefficient=max_products=0.0
    checked_samples=checked_windows=0
    for case in protocol["cases"]:
        nonideal=truth(case)
        grid_path=folder/f"{case['name']}_grid.bin"
        if grid_path.exists():
            rows=np.fromfile(grid_path,dtype="<f8").reshape(-1,9)
            for row in rows:
                x,d1,d2,*raw=row
                original=process(x,pipeline,dither_symbols=(int(d1),int(d2)),nonidealities=nonideal)
                assert (original.stage1.quantizer.symbol,original.stage2.quantizer.symbol,original.backend.centered_code)==(raw[0],raw[1],raw[5])
                max_voltage=max(max_voltage,abs(raw[2]-original.stage1.residue),abs(raw[3]-original.stage2.residue))
        for method in protocol["methods"]:
            for seed in protocol["seeds"]:
                stem=f"{case['name']}_{method['name']}_{seed}"
                metadata_path=folder/(stem+".json")
                if not metadata_path.exists():continue
                meta=json.loads(metadata_path.read_text(encoding="utf-8-sig"))
                n=method["selected"]
                probe=np.fromfile(folder/(stem+"_probes.bin"),dtype="<f8").reshape(-1,49+9*n)
                states=[np.memmap(folder/(stem+suffix),dtype="<f8",mode="r",shape=(meta["Windows"]+1,8))
                        for suffix in ("_continuous.bin","_sar8.bin")]
                for row in probe:
                    w=int(row[0]);before=row[1:17].reshape(2,8)
                    samples=row[17:17+9*n].reshape(n,9)
                    native_products=row[17+9*n:33+9*n].reshape(2,8)
                    after=row[33+9*n:49+9*n].reshape(2,8)
                    observations=[[],[]]
                    for offset,sample in enumerate(samples):
                        x,d1,d2,*raw=sample
                        expect_x,expect_tags=input_tags(seed,120*w+offset)
                        assert x==expect_x and (int(d1),int(d2))==expect_tags
                        result=process(x,pipeline,dither_symbols=expect_tags,nonidealities=nonideal)
                        digital=digital_sample(result)
                        assert (digital.stage1_symbol,digital.stage2_symbol,digital.backend_centered_code)==(raw[0],raw[1],raw[5])
                        max_voltage=max(max_voltage,abs(raw[2]-result.stage1.residue),abs(raw[3]-result.stage2.residue))
                        state=TwoStageAdaptiveState(GatedLmsState(tuple(before[1,:4]),(0,)*4),
                            GatedLmsState(tuple(before[1,4:]),(0,)*4))
                        quant=observe(digital,state,cfg)
                        observations[1].append(((64*d1,quant.stage1_local_learning_output),
                                                (16*d2,quant.stage2_local_learning_output)))
                        # Continuous backend is explicitly an offline primitive
                        # control; do not put fractional codes in DigitalSample.
                        p2=correct(128*result.stage2.residue,PwlConfig(32,tuple(before[0,4:]))).corrected_code
                        raw1=128*digital.stage2_symbol+p2-16*d2
                        p1=correct(raw1,PwlConfig(128,tuple(before[0,:4]))).corrected_code
                        observations[0].append(((64*d1,p1-64*d1),(16*d2,p2-16*d2)))
                        checked_samples+=1
                    for mode in (0,1):
                        assert np.array_equal(before[mode],states[mode][w])
                        assert np.array_equal(after[mode],states[mode][w+1])
                        for bank,base in enumerate((cfg.stage1_lms,cfg.stage2_lms)):
                            state=GatedLmsState(tuple(before[mode,bank*4:bank*4+4]),(0,)*4)
                            adapted=replace(base,step_sizes=tuple(mu*method["multiplier"]*n for mu in base.step_sizes))
                            update=update_block_mean(state,observations=[obs[bank] for obs in observations[mode]],config=adapted)
                            err=np.max(np.abs(np.array(update.state.coefficients)-after[mode,bank*4:bank*4+4]))
                            max_coefficient=max(max_coefficient,float(err))
                            original_sums=np.array(update.mean_gated_products)*n
                            max_products=max(max_products,float(np.max(np.abs(original_sums-native_products[mode,bank*4:bank*4+4]))))
                        checked_windows+=1
                print(f"original-core verified {stem}, probes={len(probe)}",flush=True)
    edge_path=folder/"pwl_edges.bin"
    edge_count=0
    if edge_path.exists():
        for width,raw,k1,k2,k3,k4,value in np.fromfile(edge_path,dtype="<f8").reshape(-1,7):
            assert abs(correct(raw,PwlConfig(width,(k1,k2,k3,k4))).corrected_code-value)<=1e-12
            edge_count+=1
    gate_count=sar_count=0
    if (folder/"gate_edges.bin").exists():
        for width,k1,k2,k3,k4,j,local,mask in np.fromfile(folder/"gate_edges.bin",dtype="<f8").reshape(-1,8):
            thresholds=adaptive_lower_thresholds((k1,k2,k3,k4),width)
            assert bool(mask)==(int(j)==0 or abs(local)>=thresholds[int(j)])
            gate_count+=1
    if (folder/"sar_edges.bin").exists():
        for voltage,code,low,high in np.fromfile(folder/"sar_edges.bin",dtype="<f8").reshape(-1,4):
            got=convert(voltage,pipeline.backend)
            assert got.centered_code==code and got.overload_low==bool(low) and got.overload_high==bool(high)
            sar_count+=1
    assert max_voltage<=protocol["verification"]["native_voltage_tolerance"]
    assert max_coefficient<=protocol["verification"]["native_original_coefficient_tolerance"]
    result={"passed":True,"original_platform_samples":checked_samples,"original_lms_window_bank_pairs":checked_windows*2,
            "maximum_analog_voltage_difference":max_voltage,"maximum_coefficient_difference":max_coefficient,
            "maximum_unscaled_product_sum_difference":max_products,"pwl_endpoint_and_boundary_probes":edge_count,
            "lower_gate_equality_probes":gate_count,"sar_endpoint_and_boundary_probes":sar_count,
            "full_record_all_transition_replay":False,"probe_schedule_predeclared":True}
    write(folder/"verification.json",result)
    print(json.dumps(result),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("folder",type=Path)
    verify(p.parse_args().folder.resolve())
