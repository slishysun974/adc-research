"""Fixed-record sampling, dither groups and state-history covariance audit.

Minimal Q3 reconstruction only: no gates, products, requests or training.
Compact per-window moments are saved to permit subsequent read-only reuse.
"""
import argparse
from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
import shutil
import traceback
import numpy as np
from experiments.exp_074_learning_signal_gate_intervention.analyze_response import (
    ROOT, OLD, CHANNEL, PHASE, SEEDS, N, W, DOCS, source, load, write,
    digest, guard, round_ratio, pwl_scaled, isum, mulsum, pack,
    fixed_setup, readout, export, correct_two_stage_fixed_observed,
    DigitalCalibrationSample,
)
from experiments.exp_074_learning_signal_gate_intervention.run import BASE, NEW

PRIOR=ROOT/'artifacts/research/first_moment_audit_20261013_v1'
CD=115200
MD=8*CD
COLS=['deltaK1','delta_corr_num','label_mean_num','between_group_num','within_group_num',
      'full_d_sum','selected_d_sum','selected_dy_Q3_sum','full_dy_Q3_sum',
      'full_v_Q3_sum','selected_v_Q3_sum','baseline_K1','treated_K1']


def product_partition(k,x,groups):
    size=len(k);mean_product=F(isum(k)*isum(x),MD*size*size)
    total=F(mulsum(k,x),MD*size)
    gp=sum(F(isum(k[ii])*isum(x[ii]),MD*len(ii)**2) for ii in groups)/len(groups)
    return {'total':pack(total),'mean_product':pack(mean_product),
            'between_group_covariance':pack(gp-mean_product),
            'within_group_covariance':pack(total-gp),
            'covariance':pack(total-mean_product)}


def controls():
    # Exact Gaussian roots for N=12, sine bin3, three-slot windows.
    roots=[(F(1),F(0)),(F(0),F(1)),(F(-1),F(0)),(F(0),F(-1))]
    full=[roots[n%4] for n in range(12)];sel=[full[3*w] for w in range(4)]
    avg=lambda z:sum(z)/len(z)
    for v in (full,sel):
        assert avg([z[0] for z in v])==avg([z[1] for z in v])==0
        assert avg([z[0]**2 for z in v])==avg([z[1]**2 for z in v])==F(1,2)
    # Alias: N=8, window2, bin4; selected even slots have value1.
    assert avg([F((-1)**n) for n in range(8)])==0
    assert avg([F((-1)**(2*w)) for w in range(4)])==1
    # Weight on first window breaks the unweighted cancellation.
    assert sel[0][0]/4==F(1,4)
    assert sum(z[0] for z in full[:3])/12==0
    assert sum(z[1] for z in full[:3])/12==F(1,12)
    # Both label means zero can still have nonzero selection correction.
    d=np.array([[1,-1,1,-1]],dtype=np.int64)
    v=np.array([[1,1,3,1]],dtype=np.int64)
    assert int(d.sum())==int(d[:,:2].sum())==0
    assert int((d*v).sum())-2*int((d[:,:2]*v[:,:2]).sum())==2
    # Direct dither subtraction is a constant in d*y and cancels.
    assert np.array_equal((d*(v-512*d)).sum(axis=1)-2*(d[:,:2]*(v[:,:2]-512*d[:,:2])).sum(axis=1),
                          (d*v).sum(axis=1)-2*(d[:,:2]*v[:,:2]).sum(axis=1))
    k=np.array([1,-1,1,-1],dtype=np.int64);x=np.array([1,-1,-1,1],dtype=np.int64)
    pp=product_partition(k,x,[np.arange(2),np.arange(2,4)])
    assert F(pp['total']['exact'])==sum(F(pp[n]['exact']) for n in ['mean_product','between_group_covariance','within_group_covariance'])
    kk=np.array([1,-1],dtype=np.int64);xx=kk.copy()
    assert isum(kk)*isum(xx)==0 and mulsum(kk,xx)==2
    assert 30720==120*256 and 2048==8*256 and 127%256 and 254%256
    return {'passed':True,'controls':['Gaussian-root input mean/power','alias bin',
        'weighted harmonic','balanced labels with nonzero correction','direct copy cancellation',
        'group covariance partition','zero mean product with nonzero covariance','original frequency congruences']}


def prepare(out):
    assert not out.exists(),'Refuse overwrite'
    assert load(PRIOR/'verification.json')['passed']
    out.mkdir(parents=True)
    files=dict(load(PRIOR/'source_hashes.json'))
    for p in [PRIOR/'results.json',PRIOR/'verification.json',PRIOR/'protocol.json']:
        files[str(p)]=digest(p)
    guard(files);write(out/'source_hashes.json',files)
    sources=list((ROOT/'src/adc_research').rglob('*.py'))+list((ROOT/'experiments').rglob('*.py'))
    write(out/'execution_hashes.json',{str(p):digest(p) for p in sources})
    shutil.copyfile(Path(__file__),out/'frozen_analysis.py')
    write(out/'controls.json',controls())
    write(out/'protocol.json',{
        'version':'EXP074-sampling-history-v1','date':'2026-10-13',
        'authority':'D136..139 and user continue; current STATUS next sampling/history question',
        'scope':'Original40 gate pairs/320 blocks, all5 seeds, rates1/1/4, two starts, two learner sources,128..136. No new policy or source.',
        'alternatives':['Mean state times mean correlation gap suffices, versus within/between time or repeated-input-phase covariances being essential.',
                       'The nominal input selection changes sine mean/power, versus its low harmonics cancelling while signed/state-weighted correlation still differs.',
                       'Marginal label imbalance or explicit64*d subtraction alone accounts for the gap, versus phase-group/within-group associations remaining.'],
        'derivation':'Finite Fourier selection mask N=120*256, prefix4; frequency127 and254 are not multiples256. Weighted harmonics retain the window-state transform. Existing finite covariance identities split128*E[k*(cP-cS)] by8 time blocks and256 repeated nominal input phases. Direct64*d subtraction cancels; label mean plus between4-slot group and within-group covariance closes the current gap.',
        'predictions':['All old40/320 sampling corrections reproduce as exact fractions; all new covariance and label/group terms close.',
                       'Direct digital dither copy cancels in every window; balanced labels need not eliminate signed readout correlation.',
                       'Source-table first/second nominal moments agree with analytic mask cancellation within the original certified table error, without FFT.',
                       'All baseline normal outputs reproduce; minimal/shadow y values agree with rational/formal probes; no state updates.'],
        'budget':{'normal_minimal_Q3_readouts':9830400,'held_minimal_Q3_readouts':4915200,
                  'PWL_evaluations_each_stage':14745600,'normal_integer_code_replays':9830400,
                  'per_window_moment_pairs':81920,'4slot_phase_groups':2457600,
                  'rational_and_formal_readouts_each':1080,'independent_Fraction_group_checks':120,
                  'source_table_values':30720,'integer_output_values_loaded':14745600,'Q22_values_loaded':1639200,
                  'compact_window_moment_bytes':8519680,'new_learning_gates_requests_commits_paths_source_fft_holdout':0},
        'compact_columns':COLS,'compact_format':'40 files, each2048x13 little-endian int64; correlation components denominator115200 code, weight gap denominator1024; source controls and fingerprints included.',
        'limits':'Finite partitions are descriptive, not event causal shares, iid distributions, policy comparisons or target information. The mask relation is for nominal input harmonics, not general dither/PWL/history data. Existing NG38/39/43 target conditions remain.',
        'stopping':'Original scope and upper budgets only; stop/archive source, domain, arithmetic or probe mismatch; no source/profile/horizon/learning adjustment.'})
    for name in DOCS+['docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md',
                      'docs/theory/DITHER_INFORMATION_AND_STOCHASTIC_UPDATE_AUDIT_V1.md']:
        p=out/'documents_before'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
    print('Frozen all40/320 sampling-history audit and compact moments',flush=True)


def minimal(words,front,rear):
    kf,kr=round_ratio(front,4096),round_ratio(rear,4096)
    q2=words[:,:,1].astype(np.int64);sar=words[:,:,2].astype(np.int64);bits=words[:,:,3].astype(np.int64)
    d1=2*(bits&1)-1;d2=2*((bits>>1)&1)-1
    raw=1024*q2+pwl_scaled(8*sar,kr,32)-128*d2
    y=pwl_scaled(raw,kf,128)-512*d1
    return y,raw


def source_moments():
    tone=np.fromfile(OLD/'tone.bin',dtype='<f8');rr=[float(v).as_integer_ratio() for v in tone]
    den=max(b for _,b in rr);xx=[a*(den//b) for a,b in rr]
    nu=F(load(PHASE)['tone_grid_error_upper']);amp=F(41,50)
    result={}
    for name,idx in [('full',range(N)),('selected',[i for i in range(N) if i%120<4])]:
        size=len(idx);mean=F(sum(xx[i] for i in idx),den*size)
        power=F(sum(xx[i]**2 for i in idx),den**2*size)
        assert abs(mean)<=nu and abs(power-amp**2/2)<=2*amp*nu+nu**2
        result[name]={'count':size,'mean':pack(mean),'power':pack(power),
                      'nominal_exact_mean':'0','nominal_exact_power':str(amp**2/2)}
    return result


def group_terms(d,v):
    dg=d.reshape(-1,30,4);vg=v.reshape(-1,30,4)
    ds=dg.sum(axis=2);vs=vg.sum(axis=2);hs=(dg*vg).sum(axis=2)
    dp=ds.sum(axis=1);vp=vs.sum(axis=1);dv=(ds*vs).sum(axis=1)
    label=dp*vp-900*ds[:,0]*vs[:,0]
    between=30*dv-dp*vp
    within=30*(4*hs.sum(axis=1)-dv-120*hs[:,0]+30*ds[:,0]*vs[:,0])
    delta=120*(hs.sum(axis=1)-30*hs[:,0])
    assert np.array_equal(delta,label+between+within)
    return delta,(label,between,within),dp,ds[:,0],vp,vs[:,0]


def probe(words,front,rear,yn,yl,rrheld,aa,expected):
    _,cfg=fixed_setup(load(OLD/'source_protocol.json'));count=group_checks=0
    for w in (0,1024,2047):
        for rr,y,normal in [(rear[w],yn,True)]+([] if aa else [(rrheld[w],yl,False)]):
            codes=export(tuple(map(int,np.concatenate((front[w],rr)))))
            cc=replace(cfg.cascade,stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=codes[:4]),
                       stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=codes[4:]))
            for j in (0,1,2,3,59,119):
                q1,q2,sar,bits=map(int,words[w,j]);d1=2*(bits&1)-1;d2=2*((bits>>1)&1)-1
                rd=readout(q1,q2,F(sar),d1,d2,tuple(F(k,1024) for k in codes),data_q3=True)
                formal=correct_two_stage_fixed_observed(DigitalCalibrationSample(q1,q2,sar,d1,d2),cc)
                assert formal.unclipped_output_scaled==8*rd.output
                assert int(8*rd.y1)==int(y[w,j])
                if normal:assert round(rd.output)==int(expected[w,j])
                count+=1
        dd=[F(2*(int(words[w,j,3])&1)-1) for j in range(120)]
        vv=[F(int(yl[w,j]),8)+64*dd[j] for j in range(120)]
        avg=lambda v:sum(v)/len(v)
        md=avg(dd);mv=avg(vv);ds=avg(dd[:4]);vs=avg(vv[:4])
        groupd=[avg(dd[4*p:4*p+4]) for p in range(30)]
        groupv=[avg(vv[4*p:4*p+4]) for p in range(30)]
        gh=[avg([dd[4*p+j]*vv[4*p+j] for j in range(4)]) for p in range(30)]
        items=[md*mv-ds*vs,avg([a*b for a,b in zip(groupd,groupv)])-md*mv,
               avg([gh[p]-groupd[p]*groupv[p] for p in range(30)])-(gh[0]-ds*vs)]
        gd,ct,*_=group_terms(np.array(dd,dtype=np.int64).reshape(1,120),np.array([int(z*8) for z in vv],dtype=np.int64).reshape(1,120))
        assert items==[F(int(z[0]),CD) for z in ct]
        group_checks+=1
    return count,group_checks


def analyze(out):
    assert not (out/'results.json').exists(),'Refuse complete overwrite'
    assert digest(Path(__file__))==digest(out/'frozen_analysis.py')
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'));controls()
    write(out/'source_moments.json',source_moments())
    prior={(r['seed'],r['rate'],r['initialization'],r['context']):r for r in load(PRIOR/'results.json')['rows']}
    rows=[];sc=gc=0
    for seed in SEEDS:
        words=source(seed);d=2*(words[:,:,3].astype(np.int64)&1)-1
        for rate in ('base','quarter'):
            stem=f'{seed}_{rate}'
            a=np.fromfile(BASE/f'{stem}_q22.bin',dtype='<i4').reshape(W+1,4,8).astype(np.int64)
            b=np.fromfile(NEW/f'{stem}_q22.bin',dtype='<i4').reshape(W+1,4,8).astype(np.int64)
            fs=np.fromfile(CHANNEL/f'{stem}_front_q22.bin',dtype='<i4').reshape(W+1,4,4).astype(np.int64)
            fy=np.fromfile(CHANNEL/f'{stem}_outputs.bin',dtype='<i2').reshape(W,4,120)
            by=np.fromfile(NEW/f'{stem}_bridge_outputs.bin',dtype='<i2').reshape(W,2,120)
            for h,init in ((0,'actual'),(2,'prefix')):
                for aa,ctx in ((1,'gate_signal_moving'),(0,'gate_signal_held')):
                    if aa:bst,tst,yr=fs[:,h],a[:,h,:4],fy[:,h]
                    else:bst,tst,yr=b[:,h,:4],fs[:,h+1],by[:,h//2]
                    rear=a[:-1,h,4:];held=np.broadcast_to(a[0,h,4:],(W,4))
                    yn,_=minimal(words,bst[:-1],rear)
                    q3=16384+4096*words[:,:,0].astype(np.int64)+yn
                    assert np.all((q3>=0)&(q3<=4095*8)) and np.array_equal(round_ratio(q3,8),yr)
                    yl=yn if aa else minimal(words,bst[:-1],held)[0]
                    kb=round_ratio(bst[:-1],4096);kt=round_ratio(tst[:-1],4096);k=kt[:,0]-kb[:,0]
                    v=yl+512*d
                    x,parts,dp,ds,vp,vs=group_terms(d,v)
                    cp=(d*yl).sum(axis=1);cs=(d[:,:4]*yl[:,:4]).sum(axis=1)
                    assert np.array_equal(x,120*(cp-30*cs))
                    old=prior[seed,rate,init,ctx]
                    def one(sl,previous):
                        kk,xx=k[sl],x[sl];size=len(kk)
                        ids=np.arange(size)
                        groups=[z for z in np.array_split(ids,8)] if size==W else [ids]
                        partition=product_partition(kk,xx,groups)
                        assert F(partition['total']['exact'])==F(previous['terms']['sampling_correction']['exact'])
                        comps=[F(mulsum(kk,z[sl]),MD*size) for z in parts]
                        assert sum(comps)==F(partition['total']['exact'])
                        return {'time_partition':partition,'label_group_terms':[pack(z) for z in comps],
                                'selected_balanced_windows':int(np.count_nonzero(ds[sl]==0)),
                                'both_balanced_nonzero_gap_windows':int(np.count_nonzero((ds[sl]==0)&(dp[sl]==0)&(xx!=0))),
                                'nonzero_correlation_gap_windows':int(np.count_nonzero(xx)),
                                'mean_deltaK1':pack(F(isum(kk),1024*size)),
                                'mean_correlation_gap':pack(F(isum(xx),CD*size))}
                    row={'seed':seed,'rate':rate,'initialization':init,'context':ctx,'moments':one(slice(None),old['moments']),'blocks':[]}
                    phases=[np.arange(r,W,256) for r in range(256)]
                    row['nominal_input_phase_partition']=product_partition(k,x,phases)
                    assert F(row['nominal_input_phase_partition']['total']['exact'])==F(row['moments']['time_partition']['total']['exact'])
                    for bb in range(8):
                        sl=slice(bb*256,(bb+1)*256)
                        row['blocks'].append({'block':128+bb,'moments':one(sl,old['blocks'][bb]['moments'])})
                    assert sum(F(z['moments']['time_partition']['total']['exact']) for z in row['blocks'])/8==F(row['moments']['time_partition']['total']['exact'])
                    c,z=probe(words,bst[:-1],rear,yn,yl,held,aa,yr);sc+=c;gc+=z
                    record=np.column_stack((k,x,*parts,dp,ds,cs,cp,vp,vs,kb[:,0],kt[:,0]))
                    assert record.shape==(W,len(COLS))
                    record.astype('<i8').tofile(out/f'{stem}_{init}_{aa}_window_moments.bin')
                    rows.append(row)
                    p=row['moments']['time_partition'];print(seed,rate,init,aa,'sampling',p['total']['value'],
                        'mean',p['mean_product']['value'],'cov',p['covariance']['value'],flush=True)
    assert len(rows)==40 and sc==1080 and gc==120
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    write(out/'results.json',{'completed':True,'rows':rows})
    write(out/'verification.json',{'passed':True,'pairs':40,'blocks':320,'all_old_sampling_and_new_covariance_group_splits_exact':True,
        'direct_dither_subtraction_cancels_every_window':True,'rational_and_formal_readouts_each':sc,
        'independent_Fraction_group_checks':gc,'source_files_preserved':len(load(out/'source_hashes.json')),
        'python_sources_preserved':len(load(out/'execution_hashes.json')),
        'compact_window_moment_bytes':sum(p.stat().st_size for p in out.glob('*_window_moments.bin')),
        'new_learning_gates_requests_commits_paths_source_fft_holdout':0})
    print('All sampling-history partitions, source moments and probes passed',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','analyze']);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    try:(prepare if args.mode=='prepare' else analyze)(args.out)
    except Exception:
        if args.out.exists():(args.out/f'{args.mode}_failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
