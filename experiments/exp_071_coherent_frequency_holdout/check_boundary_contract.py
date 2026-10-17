"""Frozen saved-data range audit; no analog generation or new learning."""
import argparse
import ast
from dataclasses import replace
from fractions import Fraction as F
import json
from pathlib import Path
import platform
import shutil
import traceback

import numpy as np

from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.theory.static_fixed_contract import (
    readout, export, nearest_even, saturated_integer, output_range_bound,
)
from experiments.exp_060_static_auxiliary_preflight.run import fixed_setup
from experiments.exp_062_same_input_background.verify import digital, pwl_scaled, round_ratio, tags
from experiments.exp_069_gu_learning_rate.check_normal_loss_limits import (
    ROOT, load, write, digest, relative, verify_hashes,
)

CONTRACT = Path(__file__).with_name('boundary_contract_v2.json')
BACKUP = ROOT/'artifacts/research/output_range_contract_20261012_v1'


def raw_q3(words, acc):
    """Exact Q3 level before final saturation/rounding, using saved words."""
    q1,q2,be,bits=(words[:,:,i].astype(np.int64) for i in range(4))
    k=round_ratio(acc,4096)
    p2=pwl_scaled(8*be,k[:,4:],32)
    r1=1024*q2+p2-128*(2*((bits>>1)&1)-1)
    y1=pwl_scaled(r1,k[:,:4],128)-512*(2*(bits&1)-1)
    return 16384+4096*q1+y1,r1


def audit(folder):
    folder.mkdir(parents=True,exist_ok=False)
    c=load(CONTRACT);old=ROOT/c['previous_development'];p=load(old/'protocol.json')
    shutil.copyfile(CONTRACT,folder/'boundary_contract_v2.json')
    original=load(old/'delivery_hashes.json')
    used={relative(old/name):value for name,value in original.items()}
    used[relative(old/'delivery_hashes.json')]=digest(old/'delivery_hashes.json')
    verify_hashes(used)
    for name in ('design_hashes.json','input_hashes.json'):
        verify_hashes(load(old/name))
    assert not load(old/'verification.json')['passed']
    assert not load(old/'verification.json')['confirmation_opened']
    previous_execution=load(old/'execution_hashes.json')
    module='src/adc_research/theory/static_fixed_contract.py'
    before=BACKUP/'before'/module
    assert digest(before)==previous_execution[module]
    old_ast=ast.parse(before.read_text(encoding='utf-8'))
    new_ast=ast.parse((ROOT/module).read_text(encoding='utf-8'))
    assert len(new_ast.body)>=len(old_ast.body)
    assert all(ast.dump(a)==ast.dump(b) for a,b in zip(old_ast.body,new_ast.body))
    verify_hashes({k:v for k,v in previous_execution.items() if k!=module})
    executable={n:digest(ROOT/n) for n in previous_execution}
    for f in (Path(__file__),CONTRACT,ROOT/'tests/test_static_fixed_contract.py'):
        executable[relative(f)]=digest(f)
    write(folder/'execution_hashes.json',executable);write(folder/'used_data_hashes.json',used)
    write(folder/'environment.json',{'python':platform.python_version(),'numpy':np.__version__,'platform':platform.platform()})
    shutil.copyfile(Path(__file__),folder/'check_boundary_contract_frozen.py')
    shutil.copyfile(ROOT/module,folder/'static_fixed_contract_frozen.py')
    _,cfg=fixed_setup(load(old/'architecture_protocol.json'))
    counts={'source_records_read':0,'integer_readouts':0,'q3_range_readouts':0,
            'online_codes_replayed':0,'unit_codes_replayed':0,'endpoint_codes_replayed':0,
            'bank_pair_transitions_replayed':0,'learning_observations_per_stage_replayed':0,
            'rational_probes':0,'formal_probes':0}
    paths=[];probes=[];boundaries=[]

    def probe(w,a,level):
        q1,q2,be,bits=map(int,w);d1=2*(bits&1)-1;d2=2*((bits>>1)&1)-1
        ks=export(tuple(map(int,a)))
        rd=readout(q1,q2,F(be),d1,d2,tuple(F(k,1024) for k in ks),data_q3=True)
        cascade=replace(cfg.cascade,stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=ks[:4]),
                        stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=ks[4:]))
        core=correct_two_stage_fixed_observed(DigitalCalibrationSample(q1,q2,be,d1,d2),cascade)
        assert 8*rd.output==int(level)==core.unclipped_output_scaled
        assert saturated_integer(rd.output)==nearest_even(F(core.output_scaled,8))
        assert core.saturated_low==(int(level)<0) and core.saturated_high==(int(level)>32760)
        probes.append({'word':list(map(int,w)),'q22':list(map(int,a)), 'raw_q3':int(level),
                       'raw_integer':nearest_even(rd.output),'saturated_integer':saturated_integer(rd.output),
                       'low':core.saturated_low,'high':core.saturated_high})
        counts['rational_probes']+=1;counts['formal_probes']+=1

    for source_name in ('dev_509','dev_1009','old127_control','ideal509'):
        words=np.fromfile(old/(source_name+'_words.bin'),dtype='i1').reshape(-1,4)
        counts['source_records_read']+=len(words)
        d1,d2=tags(p['preflight_seed'],np.arange(len(words)))
        assert np.array_equal(words[:,3],(d1>0)+2*(d2>0))
        if source_name!='ideal509':
            assert np.all(np.abs(words[:,0])<=3) and np.all(np.abs(words[:,1])<=2)
            assert np.all((words[:,2]>=-79)&(words[:,2]<=78))
            tone=np.fromfile(old/(source_name+'_tone.bin'),dtype='<f8')
            assert len(tone)==30720 and np.max(np.abs(tone))<=0.82
        # Unit and every saved online path, including the serialized pieces.
        outputs=sorted(old.glob(source_name+'_*_outputs.bin'))
        for output_file in outputs:
            stem=output_file.name.removesuffix('_outputs.bin')
            state_file=old/(stem+'_q22.bin')
            if state_file.exists():
                states=np.fromfile(state_file,dtype='<i4').reshape(-1,8).astype(np.int64)
                recorded=np.fromfile(output_file,dtype='<i2').reshape(-1,120)
                assert len(states)==len(recorded)+1
                start=1920 if stem.endswith('_restart_second') else 0
                w=words[start:start+recorded.size].reshape(-1,120,4);a=states[:-1]
                yy,g,_,products=digital(w,a)
                rate=next(r for r in p['rate_scales'] if '_'+r['name']+'_' in stem)
                method=next(m for m in p['methods'] if '_'+m['name'] in stem)
                selected=method['selected'];s=products[:,:selected].sum(axis=1)
                delta=round_ratio(s*np.array([-2,-6,-12,-24,-32,-96,-192,-384])*method['multiplier']*rate['numerator'],125*rate['denominator'])
                assert np.all((a+delta>=0)&(a+delta<=2047*4096))
                assert np.array_equal(a+delta,states[1:])
                recorded_counters=load(old/(stem+'_counters.json'))
                for i,row in enumerate(recorded_counters):
                    actual={'gates':g[i,:selected].sum(axis=0),'correlations':s[i],
                            'zero_request':(delta[i]==0).astype(int),
                            'nonzero_sum_zero':((delta[i]==0)&(s[i]!=0)).astype(int),
                            'hidden_changed':(a[i]!=states[i+1]).astype(int),
                            'export_changed':(round_ratio(a[i],4096)!=round_ratio(states[i+1],4096)).astype(int)}
                    for key,value in actual.items():assert np.array_equal(row[key],value),(stem,i,key)
                counts['online_codes_replayed']+=recorded.size
                counts['bank_pair_transitions_replayed']+=len(recorded)
                counts['learning_observations_per_stage_replayed']+=len(recorded)*selected
            else:
                assert stem==source_name+'_unit'
                recorded=np.fromfile(output_file,dtype='<i2').reshape(1,-1)
                w=words[None,:,:];a=np.full((1,8),1<<22,dtype=np.int64)
                yy=digital(w,a)[0];counts['unit_codes_replayed']+=recorded.size
            assert np.array_equal(yy,recorded)
            levels,raw1=raw_q3(w,a)
            assert np.all((levels>=0)&(levels<=32760)),stem
            assert np.array_equal(round_ratio(levels,8),recorded)
            if source_name!='ideal509' and not state_file.exists():
                assert np.all((recorded>=97)&(recorded<=3999))
            tube=[]
            if source_name!='ideal509':
                for acc in a:
                    k=export(tuple(map(int,acc)))
                    tube.append(output_range_bound(3,2,79,max(k[:4]),max(k[4:])).no_saturation)
            counts['integer_readouts']+=recorded.size;counts['q3_range_readouts']+=recorded.size
            # Serialized pieces already match the complete path byte-for-byte;
            # do not spend the frozen scalar cap probing those duplicates.
            if '_restart_' not in stem:
                for j in (0,recorded.size//2,recorded.size-1):
                    probe(w.reshape(-1,4)[j],a[j//120] if state_file.exists() else a[0],levels.ravel()[j])
            paths.append({'path':stem,'codes':recorded.size,'raw_q3_min':int(levels.min()),
                          'raw_q3_max':int(levels.max()),'raw1_q3_min':int(raw1.min()),'raw1_q3_max':int(raw1.max()),
                          'output_clips':0,'preinteger_saturations':0,
                          'sufficient_bound_states':sum(tube),'bound_states_checked':len(tube)})
        print('working saved-data range passed',source_name,flush=True)

    for model in ('both_smooth','ideal'):
        stem=model+'_endpoint'
        words=np.fromfile(old/(stem+'_words.bin'),dtype='i1').reshape(-1,4)
        a=np.full((1,8),1<<22,dtype=np.int64)
        yy=digital(words[None,:,:],a)[0].ravel();levels,_=raw_q3(words[None,:,:],a)
        levels=levels.ravel();flags=(levels<0)|(levels>32760)
        saturated=round_ratio(np.clip(levels,0,32760),8)
        bad=np.flatnonzero(yy!=saturated)
        assert np.array_equal(yy,np.fromfile(old/(stem+'_outputs.bin'),dtype='<i2'))
        assert np.array_equal(saturated,np.fromfile(old/(stem+'_saturated_outputs.bin'),dtype='<i2'))
        previous=load(old/(stem+'_boundary.json'))
        assert bad.tolist()==previous['indices'] and yy[bad].tolist()==previous['raw_codes']
        boundaries.append({'model':model,'records':len(words),'q3_saturations':int(flags.sum()),
                           'rounded_code_clips':len(bad),'raw_min':int(yy.min()),'raw_max':int(yy.max()),
                           'indices':bad.tolist(),'raw_codes':yy[bad].tolist()})
        selected=sorted(set(bad.tolist()+[0,1,len(words)-2,len(words)-1]))
        for j in selected:probe(words[j],a[0],levels[j])
        np.column_stack((levels,yy,saturated,flags)).astype('<i4').tofile(folder/(stem+'_raw_q3_integer_saturated_flag.bin'))
        counts['source_records_read']+=len(words);counts['endpoint_codes_replayed']+=len(words)
        counts['integer_readouts']+=len(words);counts['q3_range_readouts']+=len(words)
    b=c['frozen_audit_budget']
    write(folder/'actual_counts.json',counts)
    write(folder/'paths.json',paths);write(folder/'boundaries.json',boundaries);write(folder/'probes.json',probes)
    for actual,expected in (('source_records_read','saved_source_word_records'),('integer_readouts','new_offline_integer_readouts'),
                           ('q3_range_readouts','new_offline_q3_range_readouts'),('online_codes_replayed','saved_online_codes_replayed'),
                           ('unit_codes_replayed','saved_unit_codes_replayed'),('endpoint_codes_replayed','saved_endpoint_codes_replayed'),
                           ('bank_pair_transitions_replayed','saved_bank_pair_transitions_replayed'),
                           ('learning_observations_per_stage_replayed','saved_learning_observations_per_stage_replayed_not_new')):
        assert counts[actual]==b[expected],(actual,counts[actual],b[expected])
    assert counts['rational_probes']<=b['rational_and_formal_probe_cap_each']
    verify_hashes(used);verify_hashes(executable)
    result={'passed':True,'boundary_preflight_accepted':True,'original_zero_clipping_gate_passed':False,
            'counts':counts,'source_module_original_definitions_AST_identical':True,
            'used_files':len(used),'execution_files':len(executable),
            'working_output_clips':0,'working_preinteger_saturations':0,'coefficient_saturations':0,
            'implementation_mismatches':0,'confirmation_opened':False,'future_reservation_opened':False,
            'new_source_conversions':0,'new_online_codes':0,'new_learning_observations':0,'fft':0,'performance_scores':0,
            'long_ready':False,'reason':'Range-contract audit accepted; final long executable/source/storage freeze and final-implementation development controls remain required.'}
    write(folder/'verification.json',result)
    write(folder/'delivery_hashes.json',{f.name:digest(f) for f in folder.iterdir() if f.is_file() and f.name!='delivery_hashes.json'})
    print(json.dumps(result),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);args=parser.parse_args()
    try:audit(args.folder.resolve())
    except Exception:
        if args.folder.exists():(args.folder/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
