"""Independent original-platform and rational digital probe replay."""
import argparse
from dataclasses import replace
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import traceback

import numpy as np

from adc_research.theory.static_fixed_contract import readout, export, commit
from adc_research.evaluation.observations import digital_sample
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.fixed_four_lane_window import _bank, FourLaneConversion
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState
from experiments.exp_060_static_auxiliary_preflight.run import plant, fixed_setup, voltage_fields, check_physical
from experiments.exp_057_static_two_stage_million.common import input_tags, write

ROOT=Path(__file__).resolve().parents[2]


def sources(folder):
    frozen=json.loads((folder/'source_hashes.json').read_text(encoding='utf-8-sig'))
    assert all(sha256(Path(h['Path']).read_bytes()).hexdigest().upper()==h['Hash'] for h in frozen)


def verify(folder):
    p=json.loads((folder/'protocol.json').read_text(encoding='utf-8-sig'))
    src=json.loads((folder/'source_protocol.json').read_text(encoding='utf-8-sig'))
    aux=json.loads((folder/'auxiliary_protocol.json').read_text(encoding='utf-8-sig'))
    pipeline,cfg=fixed_setup(src)
    steps=cfg.stage1_lms.step_sizes+cfg.stage2_lms.step_sizes
    samples=windows=paths=0;maximum_voltage_error=0
    for case in aux['cases']:
        for method in src['methods']:
            for seed in p['seeds']:
                stem=f"{case['name']}_{method['name']}_{seed}"
                if not (folder/(stem+'.json')).exists():continue
                meta=json.loads((folder/(stem+'.json')).read_text(encoding='utf-8-sig'))
                n=meta['Selected'];states=np.memmap(folder/(stem+'_q22.bin'),dtype='<f8',mode='r',shape=(meta['Windows']+1,8))
                rows=np.fromfile(folder/(stem+'_probes.bin'),dtype='<f8').reshape(-1,25+17*n)
                assert len(rows)==meta['ProbeWindows']
                gates=np.zeros(8,dtype=np.int64);basis=gates.copy();both=gates.copy()
                for row in rows:
                    w=int(row[0]);before=row[1:9];obs=row[9:9+17*n].reshape(n,17)
                    sums=row[9+17*n:17+17*n];after=row[17+17*n:]
                    assert np.array_equal(before,states[w]) and np.array_equal(after,states[w+1])
                    acc=tuple(int(v*(1<<22)) for v in before);k=tuple(F(v,1024) for v in export(acc))
                    cascade=replace(cfg.cascade,
                        stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=tuple(int(v*1024) for v in k[:4])),
                        stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=tuple(int(v*1024) for v in k[4:])))
                    computed=np.zeros(8);original_rows=[];original_values=[[],[]]
                    for j,sample in enumerate(obs):
                        x,d1,d2=sample[:3];q1,q2,z1,m,a,z2,r2,be=sample[3:11];values=sample[11:15]
                        expected_x,tags=input_tags(seed,120*w+j)
                        assert expected_x==x and tags==(int(d1),int(d2))
                        physical=plant(x,int(d1),int(d2),case,pipeline,120*w+j);check_physical(physical)
                        digital=digital_sample(physical.pipeline)
                        assert (digital.stage1_symbol,digital.stage2_symbol,digital.backend_centered_code)==(q1,q2,be)
                        error=max(abs(v-u) for v,u in zip(voltage_fields(physical),(z1,m,a,z2,r2),strict=True))
                        maximum_voltage_error=max(maximum_voltage_error,error);assert error<2e-12
                        expected=readout(int(q1),int(q2),F(int(be)),int(d1),int(d2),k,data_q3=True)
                        assert list(map(float,(expected.output,expected.y1,expected.y2,expected.raw1)))==values.tolist()
                        gm=sum(int(v)<<j for j,v in enumerate(sum(expected.gates,())))
                        bm=sum(int(v)<<j for j,v in enumerate(sum(expected.support,())))
                        assert (gm,bm)==tuple(sample[15:].astype(int))
                        for bank,y in enumerate((expected.y1,expected.y2)):
                            for h,g in enumerate(expected.gates[bank]):
                                idx=4*bank+h;b=expected.support[bank][h]
                                computed[idx]+=float((64*d1 if bank==0 else 16*d2)*y*g)
                                gates[idx]+=g;basis[idx]+=b;both[idx]+=g and b
                        core=correct_two_stage_fixed_observed(digital,cascade)
                        assert (core.unclipped_output_scaled,core.stage1_raw_scaled)==(8*values[0],8*values[3])
                        original_rows.append(FourLaneConversion(120*w+j,j%4,digital))
                        for bank in range(2):original_values[bank].append((int(512*d1 if bank==0 else 128*d2),int(8*values[bank+1])))
                        samples+=1
                    assert np.array_equal(computed,sums)
                    requests,expected=commit(acc,tuple(F(int(v)) for v in sums),method['multiplier'],steps)
                    assert expected==tuple(int(v*(1<<22)) for v in after)
                    for bank,bcfg in enumerate((cfg.stage1_lms,cfg.stage2_lms)):
                        bs=FixedGatedLmsState(acc[4*bank:4*bank+4],(0,)*4,(0,)*4,(0,)*4,120*w)
                        core=_bank(bs,bcfg,original_rows,original_values[bank],(True,)*n,method['multiplier'])
                        assert core.requested_deltas==requests[4*bank:4*bank+4]
                        assert core.state.accumulator_codes==expected[4*bank:4*bank+4]
                    windows+=1
                if len(rows)==meta['Windows']:
                    assert all(np.array_equal(v,meta[key]) for v,key in ((gates,'Gates'),(basis,'Basis'),(both,'Both')))
                assert meta['CoefficientClips']==meta['OutputClips']==0
                paths+=1;print('verified',stem,len(rows),'windows',flush=True)
    expected_paths=16 if not (folder/'ideal_match_point30_202610612.json').exists() else 80
    assert paths==expected_paths
    sources(folder)
    result={'passed':True,'paths':paths,'platform_samples':samples,'rational_readouts':samples,'window_commits':windows,
        'q22_bank_commits':2*windows,'maximum_voltage_error':maximum_voltage_error,
        'fixed_readout_and_update_exact':True,'original_fixed_bank_commit_replayed':True,
        'source_hashes_unchanged':True,'all_transitions_replayed':paths==16,
        'full_long_record_transition_replay':False}
    write(folder/'verification.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);folder=parser.parse_args().folder.resolve()
    try:verify(folder)
    except Exception:
        write(folder/'verification_failure.json',{'traceback':traceback.format_exc()});raise
