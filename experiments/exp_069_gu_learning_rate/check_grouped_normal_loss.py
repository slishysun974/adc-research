"""D-129 frozen whole-group read-only attribution and condition audit.

Keeps previous protocols/sources intact. Reuses one declared mean-export
reference, expands selected groups, and summarizes seen switch/dynamic data.
"""
import argparse
from fractions import Fraction as F
import json
from pathlib import Path
import shutil
import traceback

import numpy as np

from adc_research.theory.grouped_output_moments import nested_moments, subset_loss_shift
from adc_research.theory.static_fixed_contract import export, nearest_even, readout
from experiments.exp_062_same_input_background.verify import pwl_scaled, round_ratio
from .check_normal_loss_limits import ROOT, OLD, NEW, N, NW, load, write, digest, relative, verify_hashes, output_only

PREVIOUS = ROOT/'artifacts/research/normal_loss_limits_20261012_v1'
SWITCH = ROOT/'artifacts/runs/EXP_070/tracking_v1'
DYNAMIC = ROOT/'artifacts/runs/EXP_068/background_v1'
GROUPS = {'startup':(0,8,16),'tail':(128,184,248)}
M = 9*9*256*4


def prepare(folder):
    folder.mkdir(parents=True,exist_ok=False)
    write(folder/'protocol.json', {
        'version':'D129-grouped-normal-loss-v1','date':'2026-10-12',
        'authority':'User continues D-129 tasks1/2/3; current STATUS execution gate',
        'cases':['ideal','both_linear','both_smooth'],'seeds':list(range(202610621,202610626)),
        'rates':['quarter','half','base','double'],'methods':['point30','full120'],
        'static_paths':120,'groups':GROUPS,'group_blocks':8,
        'sample_subset':'First block of EACH prespecified group, exactly the previous diagnostic subset. Keep all other seven blocks; no score-selected groups.',
        'full_intervals':'Old startup[0,24) and tail[128,256); old complete scores remain authoritative. Whole-group raw analysis is startup24 and tail24 selected blocks, not all128 tail blocks.',
        'reference':'Previous frozen mean_export state for each path/interval; no new fitting. Same words,actual old window state,front-only/rear-only/joint replacement,Q3/integer arithmetic.',
        'target':'Same exact binary64 ideal real level2048*(1+stored tone); final output integer. No online target use.',
        'partition':'Current five-field word O; finer analytical partition(O,30720-code block). Block partition is not claimed as additional online information.',
        'static_actual_readouts':120*48*N,'static_counterfactual_readouts':120*48*N*3,
        'unit_readouts':15*48*N,'static_source_words':15*48*N,
        'window_start_states':120*48*256,'selected_slots_per_stage':60*48*256*(4+120),
        'scalar_actual_and_counterfactual_readouts':120*48*3*4,
        'scalar_continuous_reference_readouts':120*48*3,
        'exact_moment_controls':'First/middle/last code of every expanded block; nested/subset identities use same full probe set and its first block per group.',
        'conditions':'Compare every actual Q3 gate count to original metadata. Count selected Q3 gate equalities, continuous exported-coefficient gate equalities and front segment equalities, and actual-to-fixed-rear segment changes. No fitted Jacobian or claimed uniform contraction.',
        'reuse_metadata':{'switch_paths':120,'dynamic_paths':60,'startup':[0,24],'tail':[64,128],'group_first_blocks':[0,8,16,64,88,120]},
        'metadata_score_blocks':120*152+180*88,
        'predictions':['All actual/unit readouts match stored codes and all gate counts match original metadata',
            'First-block minus whole-selected-group loss equals composition plus conditional loss change, including full support missing from subset',
            'Output variance/covariance splits into within-block and between-block parts with correct word/block weights',
            'Original subset joint/reference metrics reproduce previous result',
            'Strict gate/segment protection may fail; such failures do not prove actual instability'],
        'precision':'Float64 descriptive moments/tolerances1e-8; independent rational readout and exact finite controls at declared probes. No new information-bound/global optimization claim.',
        'stop':'Fixed groups,reference,all paths. Preserve failure; no extension or score-driven repair.',
        'new_adc_conversions':0,'new_learning_observations':0,'new_online_outputs':0,'new_fft':0,
        'limits':'Seen mechanism data. Static whole-group word effects are not future feedback interventions; switch/dynamic metadata is not new readout validation or causal attribution.'})
    manifest = load(PREVIOUS/'original_data_hashes.json')
    for stem in [f'{c}_{s}' for c in ('ideal','both_linear','both_smooth') for s in range(202610621,202610626)]:
        manifest[relative(OLD/(stem+'.json'))] = load(OLD/'delivery_hashes.json')[stem+'.json']
    for source in (SWITCH,DYNAMIC):
        expected = load(source/'delivery_hashes.json')
        for name in ('analysis.json','protocol.json','delivery_validation.json'):
            manifest[relative(source/name)] = expected[name]
    for name in ('results.json','protocol.json','delivery_validation.json'):
        path = PREVIOUS/name
        manifest[relative(path)] = load(PREVIOUS/'delivery_hashes.json')[name]
    write(folder/'original_data_hashes.json',manifest)
    sources = ['experiments/exp_069_gu_learning_rate/check_grouped_normal_loss.py',
        'experiments/exp_069_gu_learning_rate/check_normal_loss_limits.py',
        'experiments/exp_062_same_input_background/verify.py',
        'src/adc_research/theory/static_fixed_contract.py',
        'src/adc_research/theory/grouped_output_moments.py','tests/test_grouped_output_moments.py']
    write(folder/'execution_hashes.json',{n:digest(ROOT/n) for n in sources})
    for name in ('docs/STATUS.md','docs/DECISIONS.md','docs/theory/README.md',
        'docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md',
        'docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md',
        'docs/theory/WINDOW_MEAN_AND_GATE_MARGIN_CONDITIONS_V1.md',
        'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md',
        'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
        'docs/reports/GU_ALGORITHM_EVALUATION_V1.md','docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md'):
        dest = folder/'documents_before'/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,dest)
    verify_hashes(manifest)
    print('Frozen:120 static paths,48 complete blocks each,one old reference;120 switch+60 dynamic metadata paths',flush=True)


def continuous_pwl_num(raw, codes, width):
    # Input raw is an integer numerator in a stated common input scale.
    mag = np.abs(raw);sign = np.sign(raw)
    return sign*sum(np.minimum(np.maximum(mag-j*width,0),width)*codes[:,j,None]
                    for j in range(4))


def readout_details(words,acc):
    q1,q2,be,bits = (words[:,:,i].astype(np.int64) for i in range(4))
    d1,d2 = 2*(bits&1)-1,2*((bits>>1)&1)-1
    k = round_ratio(acc,4096)
    p2 = pwl_scaled(8*be,k[:,4:],32)
    raw = 1024*q2+p2-128*d2
    y2 = p2-128*d2
    y1 = pwl_scaled(raw,k[:,:4],128)-512*d1
    cum1 = np.column_stack((np.zeros(len(k),dtype=np.int64),np.cumsum(k[:,:3],axis=1)))
    cum2 = np.column_stack((np.zeros(len(k),dtype=np.int64),np.cumsum(k[:,4:7],axis=1)))
    th1,th2 = cum1,round_ratio(256*cum2,1024)
    g1,g2 = np.abs(y1[:,:,None]) >= th1[:,None,:],np.abs(y2[:,:,None]) >= th2[:,None,:]
    p2n = continuous_pwl_num(8*be,k[:,4:],256)
    rawn = (1024*q2-128*d2)*1024+p2n
    y2n = p2n-128*d2*1024
    y1n = continuous_pwl_num(rawn,k[:,:4],1024*1024)-512*d1*1024**2
    return {'gates':np.concatenate((g1,g2),axis=2),
        'q3_equalities':np.concatenate((np.abs(y1[:,:,None]) == th1[:,None,1:],np.abs(y2[:,:,None]) == th2[:,None,1:]),axis=2),
        'continuous_equalities':np.concatenate((np.abs(y1n[:,:,None]) == cum1[:,None,1:]*1024**2,
                                                 np.abs(y2n[:,:,None]) == cum2[:,None,1:]*256),axis=2),
        'continuous_front_segment_equalities':np.any(np.abs(rawn[:,:,None]) == np.array([1,2,3])[None,None,:]*1024**2,axis=2),
        'q3_front_segment_equalities':np.any(np.abs(raw[:,:,None]) == np.array([1,2,3])[None,None,:]*1024,axis=2),
        'segment':np.minimum(np.abs(raw)//1024,3), 'raw':raw,'raw_num':rawn,'y1_num':y1n,'y2_num':y2n}


def statistics(keys,t,y):
    return np.array([np.bincount(keys,weights=v,minlength=M) for v in
                     (None,y,y*y,t,t*t,t*y,(y-t)**2)])


def projected(s):
    n,sy,sy2,st,st2,syt,loss = s
    mask = n > 0;n=n[mask]
    vy = float(np.sum(sy2[mask]-sy[mask]**2/n))
    vt = float(np.sum(st2[mask]-st[mask]**2/n))
    cov = float(np.sum(syt[mask]-sy[mask]*st[mask]/n))
    mean_error = float(np.sum((sy[mask]-st[mask])**2/n))
    count = float(np.sum(n))
    mse = float(np.sum(loss))
    assert abs(mse-(vt+vy-2*cov+mean_error)) < 1e-7*max(1,mse)
    return {'output_variance_sum':vy,'target_variance_sum':vt,'covariance_sum':cov,
            'conditional_mean_error_sum':mean_error,'count':count,'loss_sum':mse}


def audit_scalar(words,acc,grids,target,details):
    probes=[]
    for pos in (0,N//2,N-1):
        w,j = divmod(pos,120);q1,q2,be,bits=map(int,words[w,j])
        d1,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
        row=[]
        for bank,values in zip(acc,grids,strict=True):
            ks=tuple(F(a,1024) for a in export(tuple(map(int,bank[w]))))
            y=nearest_even(readout(q1,q2,F(be),d1,d2,ks,data_q3=True).output)
            assert y == int(values.ravel()[pos]);row.append(y)
        ks=tuple(F(a,1024) for a in export(tuple(map(int,acc[0][w]))))
        continuous=readout(q1,q2,F(be),d1,d2,ks,data_q3=False)
        assert continuous.raw1 == F(int(details['raw_num'][w,j]),8*1024)
        assert continuous.y1 == F(int(details['y1_num'][w,j]),8*1024**2)
        assert continuous.y2 == F(int(details['y2_num'][w,j]),8*1024)
        eq = tuple(abs(y)==t for y,ts in zip((continuous.y1,continuous.y2),continuous.thresholds,strict=True) for t in ts[1:])
        assert eq == tuple(bool(a) for a in details['continuous_equalities'][w,j])
        probes.append((pos,F(float(target[pos])),row[0]))
    return probes


def minimal_controls():
    words=np.zeros((1,120,4),dtype=np.int8);words[:,:,2]=16
    for coeff in ((1024,)*8,(768,1024,1024,1024,1536,1024,1024,1024)):
        acc=np.array([coeff],dtype=np.int64)*4096
        details=readout_details(words,acc)
        ks=tuple(F(k,1024) for k in coeff)
        exact=readout(0,0,F(16),-1,-1,ks,data_q3=False)
        assert exact.raw1 == F(int(details['raw_num'][0,0]),8*1024)
        assert exact.y1 == F(int(details['y1_num'][0,0]),8*1024**2)
    return 2


def metadata_analysis():
    rows=[]
    for label,source,tail,fields in (('static',NEW,128,('case','seed','method','rate')),
        ('switch',SWITCH,64,('case','seed','method','rate','variant')),
        ('dynamic',DYNAMIC,64,('case','seed','method','history'))):
        paths=load(source/'analysis.json')['paths']
        assert len(paths) == (120 if label != 'dynamic' else 60)
        for path in paths:
            for interval,(start,stop) in {'startup':(0,24),'tail':(tail,2*tail)}.items():
                scores=path['block_scores']; values=np.array([s['mse_codes_squared'] for s in scores[start:stop]])
                grouped=values.reshape(-1,8)
                full=float(np.mean(values));first=float(np.mean(grouped[:,0]));rest=float(np.mean(grouped[:,1:]))
                assert abs(full-(first+7*rest)/8)<1e-8
                chosen=(0,1,2) if interval=='startup' else (0,(len(grouped)-1)//2,len(grouped)-1)
                selected=grouped[list(chosen)]
                rows.append({'source':label,**{k:path[k] for k in fields},'interval':interval,
                    'full_mse':full,'all_groups_first_block_mse':first,'all_groups_other_seven_mse':rest,
                    'offset_mse':list(map(float,np.mean(grouped,axis=0))),
                    'selected_first_mse':float(selected[:,0].mean()),
                    'selected_whole_mse':float(selected.mean()),
                    'selected_group_indices':list(chosen),'all_group_means':list(map(float,grouped.mean(axis=1)))})
    return rows


def analyze(folder):
    p=load(folder/'protocol.json');assert not (folder/'results.json').exists()
    verify_hashes(load(folder/'execution_hashes.json'));verify_hashes(load(folder/'original_data_hashes.json'))
    controls=minimal_controls()
    previous=load(PREVIOUS/'results.json')
    prev={(r['case'],r['seed'],r['rate'],r['method'],r['interval']):r for r in previous['paths']}
    score_rows=metadata_analysis()
    score_index={(r['case'],r['seed'],r['rate'],r['method'],r['interval']):r for r in score_rows if r['source']=='static'}
    target=2048*(1+np.fromfile(OLD/'tone.bin',dtype='<f8'))
    rows=[];actual_count=counter_count=unit_count=scalar_count=continuous_count=0
    largest_error=0.0;gate_block_checks=0;exact_moment_checks=0
    for case in p['cases']:
        for seed in p['seeds']:
            stem=f'{case}_{seed}';meta=load(NEW/(stem+'.json'));ometa=load(OLD/(stem+'.json'))
            words=np.memmap(OLD/(stem+'_words.bin'),dtype='i1',mode='r',shape=(NW,120,4))
            original=np.memmap(OLD/(stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(NW,120,3))
            new=np.memmap(NEW/(stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(NW,120,6))
            # Source blocks/units are shared across all8 digital paths.
            inputs={}
            for interval,starts in GROUPS.items():
                for start in starts:
                    for b in range(start,start+8):
                        w=np.array(words[b*256:(b+1)*256]);u=output_only(w,np.full((256,8),1 << 22,dtype=np.int64))
                        assert np.array_equal(u,original[b*256:(b+1)*256,:,0]);unit_count+=N
                        q1,q2,be,bits=(w[:,:,i].ravel().astype(np.int64) for i in range(4))
                        keys=(((q1+4)*9+(q2+4))*256+(be+128))*4+bits
                        inputs[b]=(w,u,keys,target-u.ravel())
            for rate in p['rates']:
                for method in p['methods']:
                    name=rate+'_'+method;mi=p['methods'].index(method)
                    new_index=meta['Paths'].index(name) if rate != 'base' else mi
                    source_state=OLD/(stem+'_'+method+'_q22.bin') if rate=='base' else NEW/(stem+'_'+name+'_q22.bin')
                    states=np.memmap(source_state,dtype='<f8' if rate=='base' else '<i4',mode='r',shape=(NW+1,8))
                    selected=4 if method=='point30' else 120
                    for interval,starts in GROUPS.items():
                        prior=prev[case,seed,rate,method,interval]
                        ref=np.array(prior['references']['mean_export']['state_q22'],dtype=np.int64)
                        total=np.zeros((7,M));sub=np.zeros((7,M));within_v=within_c=0.0
                        blocks=[];losses_sum=np.zeros(4);displacement=cross=interaction=0.0
                        counts={'q3_gate_equalities':np.zeros(6,dtype=np.int64),
                            'continuous_gate_equalities':np.zeros(6,dtype=np.int64),
                            'q3_front_segment_equalities':0,'continuous_front_segment_equalities':0,
                            'fixed_rear_segment_changes_all_slots':0,'selected_slots':0}
                        probe_o=[];probe_b=[];probe_t=[];probe_y=[];probe_selected=[]
                        for group_start in starts:
                            for b in range(group_start,group_start+8):
                                w,u,keys,t=inputs[b]
                                a=np.asarray(states[b*256:(b+1)*256],dtype=np.int64) if rate != 'base' else np.rint(states[b*256:(b+1)*256]*(1 << 22)).astype(np.int64)
                                aa=(a,np.column_stack((np.broadcast_to(ref[:4],(256,4)),a[:,4:])),
                                    np.column_stack((a[:,:4],np.broadcast_to(ref[4:],(256,4)))),np.broadcast_to(ref,(256,8)))
                                grids=[output_only(w,bank) for bank in aa]
                                saved=original[b*256:(b+1)*256,:,mi+1] if rate=='base' else new[b*256:(b+1)*256,:,new_index]
                                assert np.array_equal(grids[0],saved)
                                actual_count+=N;counter_count+=3*N
                                y=grids[0].ravel();dy=y-u.ravel()
                                s=statistics(keys,t,dy);total+=s
                                if b==group_start:sub+=s
                                part=projected(s);within_v+=part['output_variance_sum'];within_c+=part['covariance_sum']
                                errors=[z.ravel()-target for z in grids]
                                losses=np.array([np.mean(e*e) for e in errors],dtype=float);losses_sum+=losses
                                x,z,c=grids[1]-grids[0],grids[2]-grids[0],grids[3]-grids[1]-grids[2]+grids[0]
                                ie=float(np.mean(2*x*z+2*errors[0].reshape(256,120)*c+2*x*c+2*z*c+c*c))
                                assert abs(losses[3]-losses[1]-losses[2]+losses[0]-ie)<1e-8
                                d=grids[0]-grids[3];pw=float(np.mean(d*d));cr=float(2*np.mean(errors[3].reshape(256,120)*d))
                                assert abs(losses[0]-losses[3]-pw-cr)<1e-8
                                displacement+=pw;cross+=cr;interaction+=ie
                                details=readout_details(w,a)
                                used=details['gates'][:,:selected].sum(axis=(0,1))
                                all_counts=details['gates'].sum(axis=(0,1))
                                old_block=(ometa if rate=='base' else meta)['Blocks'][b]
                                assert np.array_equal(used,old_block['Selected'][new_index]['Gates'])
                                assert np.array_equal(all_counts,old_block['All'][new_index]['Gates'])
                                gate_block_checks+=1
                                counts['q3_gate_equalities']+=details['q3_equalities'][:,:selected].sum(axis=(0,1))
                                counts['continuous_gate_equalities']+=details['continuous_equalities'][:,:selected].sum(axis=(0,1))
                                for field in ('q3_front_segment_equalities','continuous_front_segment_equalities'):
                                    counts[field]+=int(np.count_nonzero(details[field][:,:selected]))
                                rear_ref_k=round_ratio(ref[4:],4096)
                                q2,be,bits=(w[:,:,i].astype(np.int64) for i in (1,2,3))
                                ref_raw=1024*q2+pwl_scaled(8*be,np.broadcast_to(rear_ref_k,(256,4)),32)-128*(2*((bits>>1)&1)-1)
                                counts['fixed_rear_segment_changes_all_slots']+=int(np.count_nonzero(details['segment'] != np.minimum(np.abs(ref_raw)//1024,3)))
                                counts['selected_slots']+=256*selected
                                probes=audit_scalar(w,aa,grids,target,details)
                                scalar_count+=12;continuous_count+=3
                                for pos,tval,yval in probes:
                                    if b==group_start:probe_selected.append(len(probe_y))
                                    probe_o.append(int(keys[pos]));probe_b.append(b);probe_t.append(tval);probe_y.append(yval)
                                blocks.append({'block':b,'losses':list(map(float,losses)),'loss_interaction':ie})
                        coarse=projected(total);count=coarse['count'];mask=total[0]>0
                        lf=np.zeros(M);lf[mask]=total[6,mask]/total[0,mask]
                        ns=float(sub[0].sum());composition=float(np.sum((sub[0]/ns-total[0]/count)*lf))
                        change=float(np.sum(sub[6]/ns-sub[0]/ns*lf))
                        full_mse=coarse['loss_sum']/count;sample_mse=float(sub[6].sum()/ns)
                        assert abs(sample_mse-full_mse-composition-change)<1e-8
                        expected=score_index[case,seed,rate,method,interval]
                        error=max(abs(full_mse-expected['selected_whole_mse']),abs(sample_mse-prior['conditional_current_word']['actual_mse']))
                        largest_error=max(largest_error,error);assert error<1e-8
                        subset_ref=float(np.mean([r['losses'][3] for r in blocks if r['block'] in starts]))
                        assert abs(subset_ref-prior['references']['mean_export']['losses_00_10_01_11'][3])<1e-8
                        nested_moments(probe_o,probe_b,probe_t,probe_y)
                        subset_loss_shift(probe_o,probe_t,probe_y,probe_selected);exact_moment_checks+=2
                        summary={'output_variance':coarse['output_variance_sum']/count,
                            'within_block_output_variance':within_v/count,
                            'between_block_output_variance':(coarse['output_variance_sum']-within_v)/count,
                            'target_output_covariance':coarse['covariance_sum']/count,
                            'within_block_covariance':within_c/count,
                            'between_block_covariance':(coarse['covariance_sum']-within_c)/count,
                            'target_variance':coarse['target_variance_sum']/count,
                            'conditional_mean_error_square':coarse['conditional_mean_error_sum']/count,
                            'selected_group_mse':full_mse,'subset_mse':sample_mse,
                            'subset_composition':composition,'subset_conditional_change':change,
                            'full_mass_missing_in_subset':float(total[0,(total[0]>0)&(sub[0]==0)].sum()/count),
                            'selected_minus_full_interval':full_mse-expected['full_mse']}
                        assert summary['between_block_output_variance'] >= -1e-8
                        counts={k:list(map(int,v)) if isinstance(v,np.ndarray) else int(v) for k,v in counts.items()}
                        rows.append({'case':case,'seed':seed,'rate':rate,'method':method,'interval':interval,
                            'moments':summary,'reference':{'state_q22':list(map(int,ref)),
                                'losses_00_10_01_11':list(map(float,losses_sum/24)),
                                'displacement_power':displacement/24,'reference_error_cross':cross/24,'loss_interaction':interaction/24},
                            'conditions':counts,'blocks':blocks})
            print('checked whole groups',stem,'all8 paths',flush=True)
    assert actual_count==p['static_actual_readouts'] and counter_count==p['static_counterfactual_readouts']
    assert unit_count==p['unit_readouts'] and scalar_count==p['scalar_actual_and_counterfactual_readouts']
    assert continuous_count==p['scalar_continuous_reference_readouts']
    verify_hashes(load(folder/'original_data_hashes.json'));verify_hashes(load(folder/'execution_hashes.json'))
    result={'paths':rows,'metadata_paths':score_rows,'validation':{
        'actual_readouts':actual_count,'counterfactual_readouts':counter_count,'unit_readouts':unit_count,
        'rational_integer_readouts':scalar_count,'rational_continuous_readouts':continuous_count,
        'exact_partition_controls':exact_moment_checks,'minimal_continuous_controls':controls,
        'gate_metadata_blocks':gate_block_checks,'metadata_score_blocks':p['metadata_score_blocks'],
        'max_saved_score_difference':largest_error,'original_files_unchanged':len(load(folder/'original_data_hashes.json')),
        'execution_files_unchanged':6,'new_adc_conversions':0,'new_learning_observations':0,'new_online_outputs':0,'new_fft':0}}
    write(folder/'results.json',result);print(json.dumps(result['validation']),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);parser.add_argument('--prepare',action='store_true')
    args=parser.parse_args()
    try:
        if args.prepare:prepare(args.folder)
        else:analyze(args.folder)
    except Exception:
        if args.folder.exists():(args.folder/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
