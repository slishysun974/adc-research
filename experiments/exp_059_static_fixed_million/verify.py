"""Independent rational readouts/commits and original-core probe replay."""
import argparse
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path

import numpy as np

from adc_research.theory.static_fixed_contract import readout, nearest_even, commit, pwl
from adc_research.platform.pipeline import process
from adc_research.evaluation.observations import digital_sample
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.fixed_four_lane_window import _bank, FourLaneConversion
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState
from dataclasses import replace
from experiments.exp_058_static_fixed_preflight.run import config
from experiments.exp_057_static_two_stage_million.common import setup, truth, input_tags, corrected_arrays, write

ROOT=Path(__file__).resolve().parents[2]


def verify(folder):
    p=json.loads((folder/'source_protocol.json').read_text(encoding='utf-8-sig'))
    pipeline,_=setup(p);cfg,steps=config(p)
    samples=readouts=windows=q22banks=baseline_values=0;float_error=0
    edge_words=round_controls=0
    if (folder/'pwl_edges.bin').exists():
        for width,raw,*other in np.fromfile(folder/'pwl_edges.bin',dtype='<f8').reshape(-1,7):
            k=tuple(F.from_float(v) for v in other[:4])
            assert float(pwl(F.from_float(raw),int(width),k,True))==other[4]
            edge_words+=1
        for numerator,denominator,actual in np.fromfile(folder/'round_edges.bin',dtype='<i8').reshape(-1,3):
            assert nearest_even(F(int(numerator),int(denominator)))==actual
            round_controls+=1
    for case in p['cases']:
        for method in p['methods']:
            for seed in p['seeds']:
                stem=f"{case['name']}_{method['name']}_{seed}"
                path=folder/(stem+'.json')
                if not path.exists():continue
                meta=json.loads(path.read_text(encoding='utf-8-sig'))
                baseline_values+=meta['BaselineStatesChecked']
                n=method['selected']
                rows=np.fromfile(folder/(stem+'_probes.bin'),dtype='<f8').reshape(-1,97+33*n)
                states=[np.memmap(folder/(stem+'_'+layer+'.bin'),dtype='<f8',mode='r',shape=(meta['Windows']+1,8)) for layer in ('q3','export','q22')]
                for row in rows:
                    w=int(row[0]);before=row[1:33].reshape(4,8)
                    obs=row[33:33+33*n].reshape(n,33)
                    sums=row[33+33*n:65+33*n].reshape(4,8)
                    after=row[65+33*n:].reshape(4,8)
                    assert all(np.array_equal(before[m+1],states[m][w]) and np.array_equal(after[m+1],states[m][w+1]) for m in range(3))
                    computed=np.zeros((4,8))
                    original_rows=[];original_values=[[],[]]
                    ks=[tuple(F.from_float(v) for v in before[m]) if m<2 else
                        tuple(F(min(2047,max(0,nearest_even(F.from_float(v)*1024))),1024) for v in before[m]) for m in range(4)]
                    for offset,sample in enumerate(obs):
                        x,d1,d2=sample[:3];q1,q2,rv1,rv2,_,be=sample[3:9]
                        expected_x,tags=input_tags(seed,120*w+offset)
                        assert x==expected_x and tags==(int(d1),int(d2))
                        plant=process(x,pipeline,sample_index=120*w+offset,dither_symbols=tags,nonidealities=truth(case))
                        digital=digital_sample(plant)
                        assert (digital.stage1_symbol,digital.stage2_symbol,digital.backend_centered_code)==(q1,q2,be)
                        assert max(abs(rv1-plant.stage1.residue),abs(rv2-plant.stage2.residue))<1e-12
                        values=sample[9:].reshape(4,6)
                        for m in range(4):
                            expected=readout(int(q1),int(q2),F(int(be)),int(d1),int(d2),ks[m],data_q3=m>0)
                            arr=np.array(list(map(float,(expected.output,expected.y1,expected.y2,expected.raw1))))
                            err=float(np.max(np.abs(arr-values[m,:4])))
                            if m>0:assert err==0,(stem,w,m,arr,values[m,:4])
                            else:float_error=max(float_error,err)
                            gm=sum(int(g)<<j for j,g in enumerate(sum(expected.gates,())))
                            bm=sum(int(b)<<j for j,b in enumerate(sum(expected.support,())))
                            assert (gm,bm)==tuple(values[m,4:].astype(int))
                            for bank,y in enumerate((expected.y1,expected.y2)):
                                for j,g in enumerate(expected.gates[bank]):
                                    if g:computed[m,4*bank+j]+=float((64*d1 if bank==0 else 16*d2)*y)
                            readouts+=1
                        # Independent production fixed readout with exported old state.
                        cascade=replace(cfg.cascade,
                            stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=tuple(int(v*1024) for v in ks[3][:4])),
                            stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=tuple(int(v*1024) for v in ks[3][4:])))
                        original=correct_two_stage_fixed_observed(digital,cascade)
                        assert original.unclipped_output_scaled==8*values[3,0]
                        assert original.stage1_raw_scaled==8*values[3,3]
                        original_rows.append(FourLaneConversion(120*w+offset,offset%4,digital))
                        for bank in range(2):
                            original_values[bank].append((int((512*d1 if bank==0 else 128*d2)),int(8*values[3,bank+1])))
                        samples+=1
                    assert np.max(np.abs(computed[0]-sums[0]))<1e-7
                    assert np.array_equal(computed[1:],sums[1:])
                    for m in (0,1,2):
                        mu=np.array([float(v) for v in steps])
                        expect=before[m]-mu*method['multiplier']*sums[m]
                        assert np.max(np.abs(expect-after[m]))<1e-10
                    acc=tuple(int(v*(1<<22)) for v in before[3])
                    requests,expected=commit(acc,tuple(F.from_float(v) for v in sums[3]),method['multiplier'],steps)
                    assert expected==tuple(int(v*(1<<22)) for v in after[3])
                    assert tuple(b-a for a,b in zip(acc,expected))==requests
                    for bank,bcfg in enumerate((cfg.stage1_lms,cfg.stage2_lms)):
                        bs=FixedGatedLmsState(acc[bank*4:bank*4+4],(0,)*4,(0,)*4,(0,)*4,120*w)
                        original_update=_bank(bs,bcfg,original_rows,original_values[bank],(True,)*n,method['multiplier'])
                        assert original_update.requested_deltas==requests[bank*4:bank*4+4]
                        assert original_update.state.accumulator_codes==expected[bank*4:bank*4+4]
                    windows+=1;q22banks+=2
                assert meta['PhysicalOverloads']==0 and not any(meta['CoefficientClips']) and not any(meta['OutputClips'])
                print('verified',stem,len(rows),'windows',flush=True)
    hashes=json.loads((folder/'source_hashes.json').read_text(encoding='utf-8-sig'))
    assert all(sha256(Path(h['Path']).read_bytes()).hexdigest().upper()==h['Hash'] for h in hashes)
    assert float_error<1e-10
    result={'passed':True,'platform_samples':samples,'digital_readouts':readouts,'window_layer_commits':windows*4,
            'q22_bank_commits':q22banks,'maximum_float_readout_difference':float_error,
            'fixed_readouts_and_q22_commits_exact':True,'source_hashes_unchanged':True,
            'native_q3_endpoint_words':edge_words,'native_round_controls':round_controls,
            'full_new_path_transition_replay':False,'baseline_values_checked_by_native':baseline_values,
            'original_fixed_bank_commit_replayed':True,'bank_helper_sample_count_uses_selected_rows':True}
    write(folder/'verification.json',result);print(json.dumps(result),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path)
    verify(parser.parse_args().folder.resolve())
