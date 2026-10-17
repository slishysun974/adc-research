"""Two low-coordinate statistics at the already-read forty positions.

Analytic fixed-mask matrices, not numerical Jacobians of the Q3 learner.
Independent grouped Fraction contractions use the same digital source only.
"""
import argparse
from collections import Counter
from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
import shutil
import sys
import traceback
import numpy as np

ROOT=Path('D:/ADC');sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from experiments.exp_073_bank_feedback_intervention.analyze_front_history import (
    BASE,OLD,SEEDS,W,source,load,write,digest,guard,round_ratio,pwl_scaled,
)
from experiments.exp_073_bank_feedback_intervention.analyze_front_fixed_sampling import Budget
from adc_research.theory.static_fixed_contract import readout
from adc_research.theory.window_mean_map import exact_matrix_rank
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.observation import DigitalCalibrationSample
from experiments.exp_060_static_auxiliary_preflight.run import fixed_setup

ALIGN=ROOT/'artifacts/research/front_fixed_alignment_20261014_v2'
BASIS=ROOT/'artifacts/research/front_block_migration_20261014_v1'
N=W*120;B=256
LIMITS={'source_tuple_values':5*N*4,'initial_Q22_values':20*8,
        'basis_values':20*N*2,'old40_moment_values':40*W*24,
        'rear_Q3_PWL':20*N,'front_Q3_PWL':40*N,'continuous_front_PWL':40*N,
        'second_gate_tests':40*N*2,'instrument_basis_word_products':40*N*6,
        'readout_correlation_word_products':40*(N*4+W*4),
        'gate_margin_word_inputs':40*N,'new_window_moment_bytes':40*W*12*8}
CHECK_LIMITS={'source_tuple_values':5*N*4,'rear_Fraction_PWL':20*256,
              'grouped_word_inputs':20*N,'grouped_gate_basis_cells':40*16384,
              'old_window_moment_values':40*W*12,
              'new_requests_learning_output_scores_fft':0}


def scalar(raw,k,width):
    a=abs(int(raw));j=min(a//(8*width),3)
    z=round(F(8*width*sum(map(int,k[:j])),1024))+round(F((a-j*8*width)*int(k[j]),1024))
    return z if raw>=0 else -z


def matrix(sums,n):
    # dither TAG, basis is Q3. Multiplying by actual64 does not change rank.
    a=[[F(int(sums[i*2+j]),8*n) for j in range(2)] for i in range(2)]
    det=a[0][0]*a[1][1]-a[0][1]*a[1][0]
    rank=2 if det else 1 if any(z for r in a for z in r) else 0
    assert rank==exact_matrix_rank(a)
    return {'A':[[str(z) for z in r] for r in a],'determinant':str(det),'rank':rank}


def controls():
    _,cfg=fixed_setup(load(OLD/'source_protocol.json'));used=0
    def evaluate(r,k):
        nonlocal used
        q2=0 if r==64 else 1;sar=r-128*q2+16
        coefficients=tuple(F(int(z),1024) for z in k)
        rd=readout(0,q2,F(sar),1,1,coefficients,data_q3=True)
        cc=replace(cfg.cascade,stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=tuple(k[:4])),
                   stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=tuple(k[4:])))
        formal=correct_two_stage_fixed_observed(DigitalCalibrationSample(0,q2,sar,1,1),cc)
        assert formal.stage1_raw_scaled==8*r and formal.unclipped_output_scaled==8*rd.output
        used+=1;return rd
    one=[1024]*8;other=one.copy();other[:2]=[1040,928]
    original=[evaluate(r,one) for r in (64,160)]
    shifted=[evaluate(r,other) for r in (64,160)]
    assert [z.y1 for z in original]==[0,96] and [z.y1 for z in shifted]==[1,95]
    assert all(not z.gates[0][1] for z in original+shifted)
    assert sum(z.y1 for z in original)==sum(z.y1 for z in shifted)==96
    assert [round(z.output) for z in shifted]==[round(z.output)+d for z,d in zip(original,[1,-1])]
    a=[[F(96),F(16)],[F(0),F(0)]];h=[[F(10240),F(2048)],[F(2048),F(512)]]
    assert exact_matrix_rank(a)==1 and h[0][0]*h[1][1]-h[0][1]**2>0
    v=[F(1),F(-6)]
    assert all(sum(a[i][j]*v[j] for j in range(2))==0 for i in range(2))
    assert sum(v[i]*h[i][j]*v[j] for i in range(2) for j in range(2))==4096
    # Both parameters distinguishable, while a legal algebraic target can
    # yield an uphill Gu direction. No physical source/target claim here.
    full=[evaluate(r,one) for r in (64,200)]
    a2=[[F(96),F(36)],[F(64),F(36)]]
    assert exact_matrix_rank(a2)==2 and a2[0][0]*a2[1][1]-a2[0][1]*a2[1][0]==1152
    g=[F(-64),F(-72)];step=[F(-68),F(-204)]
    assert sum(g[j]*step[j] for j in range(2))>0
    # At a continuous gate equality a fixed-mask matrix is not a derivative.
    tied=[]
    for dz in (-2,-1,0,1,2):
        k=one.copy();k[1]+=dz;tied.append(evaluate(192,k))
    assert [z.gates[0][1] for z in tied]==[False,True,True,True,True]
    assert tied[1].y1==tied[2].y1==tied[3].y1==128
    assert F(128)-F(1,16)<128<F(128)+F(1,16)
    assert used==11
    return {'passed':True,'Fraction_and_formal_readouts_each':used,
            'rank1_A':[['96','16'],['0','0']],'rank1_kernel':['1','-6'],
            'rank1_output_power':'4096','rank2_A':[['96','36'],['64','36']],
            'rank2_determinant':'1152','Q10_rank1_distinct_equal_statistics':True,
            'gate_equality_and_Q3_plateau_checked':True,
            'physical_source_or_counterexample':False,'new_algorithm':False}


def freeze(out):
    assert not out.exists(),'Refuse overwrite';out.mkdir(parents=True)
    files=dict(load(ALIGN/'source_hashes.json'));files.update(load(ALIGN/'new_moment_hashes.json'))
    for f in ['results.json','verification.json','independent_check.json','delivery_verification.json']:
        files[str(ALIGN/f)]=digest(ALIGN/f)
    guard(files);write(out/'source_hashes.json',files)
    paths=list((ROOT/'src/adc_research').rglob('*.py'))+list((ROOT/'experiments').rglob('*.py'))
    write(out/'execution_hashes.json',{str(p):digest(p) for p in paths})
    shutil.copyfile(Path(__file__),out/'frozen_analysis.py')
    write(out/'protocol.json',{
        'date':'2026-10-14','authority':'User resumes/continues approved D140 mainline; same40 positions already consumed.',
        'question':'Are the two low-coordinate statistics locally unable to distinguish output changes, or do identifiable parameters still have learning/output direction mismatch?',
        'scope':'Exactly previous40 prescribed fixed positions,20 original records, all8 blocks. No new position, coefficient optimizer, readout scores, requests or policy.',
        'missing':'Saved learning products and gate counts lack E_Q[d*G_i*psi_j]; they cannot determine the low2 matrix rank. Reconstruct ONLY digital raw/front masks to contract this missing matrix; old losses/gradients are reused, not recomputed.',
        'matrix':'A_ij=E_Q[d1_tag*G_i*psi_j], psi in code units, two low FRONT coordinates; full120 and selected4, actual Q3 masks and own continuous-front masks separately. First gate always open. Q3-mask A is frozen-mask continuous-output sensitivity ONLY, never the actual Q3 mean derivative.',
        'conditions':'Rear fixed Q3, raw and psi do not depend on front coefficients. Continuous G2 at |y*|>=128*k1. If all its margins are positive, sufficient infinity-radius rho=min_n(| |y*|-128*k1 |/(|psi1|+|psi2|+128)), further capped by legal low2 coefficient margins. Equality gives no open-cell certificate. Full-rank A rules out a low2 fixed-mask kernel but does not equate C with output gradient or certify integer/long-term identification.',
        'predictions':['All old low2 bases and same-position Q3 products/gate counts match previous matrices.',
            'Rank-deficient A with positive definite old output H gives a local missing output direction only where the declared fixed-mask condition holds.',
            'Full-rank A removes simple local low2-rank-loss explanation; retain target/weighting and gate/quantization/history possibilities.',
            'Certificate radius smaller than aQ10 step does not prove grid neighbors cross gates; it only fails to protect them.'],
        'controls':'11 Fraction/formal digital readouts: two legal rank1 coefficient pairs with equal nonzero Q3 statistics and different integers, full-rank direction mismatch algebraic target, continuous gate equality and Q3 adjacent-grid plateau. Not new physical source or general information bound.',
        'limits':LIMITS,'independent_limits':CHECK_LIMITS,
        'budget':'Charge BEFORE operations; one shared rear per20 cases, front masks per40, saved12-column window matrix; exact2x2 contractions and rank, no repeated MSE/FFT. Independent grouped digital-word counts and scalar Fraction bases/readouts, no shared vector contraction.',
        'stop':'All40 matrices/8 blocks or reject source/domain/moment/control/budget mismatch. Stop at rank/conditions judgement, retain small margins, no root solution, long-axis, extra position, learner, FFT, future6007/8009 or algorithm.'})
    write(out/'controls.json',controls())


def analyze(out):
    assert not (out/'results.json').exists()
    assert digest(Path(__file__))==digest(out/'frozen_analysis.py')
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    assert load(out/'controls.json')['passed']
    rows=load(ALIGN/'results.json')['rows'];bud=Budget(LIMITS);results=[]
    try:
        for seed in SEEDS:
            bud.charge('source_tuple_values',N*4);words=np.array(source(seed),dtype=np.int64)
            q2,sar,bits=(words[:,:,j] for j in (1,2,3));d,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
            for rate in ('base','quarter'):
                for idx,init in ((0,'actual'),(2,'prefix')):
                    name=f'{seed}_{rate}_{init}'
                    bud.charge('initial_Q22_values',8)
                    a0=np.array(np.memmap(BASE/f'{seed}_{rate}_q22.bin',dtype='<i4',mode='r',shape=(W+1,4,8))[0,idx],dtype=np.int64)
                    k0=round_ratio(a0,4096)
                    bud.charge('rear_Q3_PWL',N)
                    raw=1024*q2+pwl_scaled(8*sar,np.broadcast_to(k0[4:],(W,4)),32)-128*d2
                    phi=np.stack([np.sign(raw)*np.minimum(np.maximum(abs(raw)-1024*j,0),1024) for j in range(2)],axis=2)
                    bud.charge('basis_values',N*2)
                    assert np.array_equal(phi,np.fromfile(BASIS/f'{name}_basis.bin',dtype='<i2').reshape(W,120,2))
                    for prior in [r for r in rows if (r['seed'],r['rate'],r['initialization'])==(seed,rate,init)]:
                        tag=prior['reference'];key=name+'_'+tag;k=np.array(prior['codes'],dtype=np.int64)
                        bud.charge('front_Q3_PWL',N);y=pwl_scaled(raw,np.broadcast_to(k[:4],(W,4)),128)-512*d
                        bud.charge('continuous_front_PWL',N)
                        mag=abs(raw);seg=np.minimum(mag//1024,3);cum=np.concatenate(([0],np.cumsum(k[:3])))
                        yc=np.sign(raw)*(1024*cum[seg]+(mag-1024*seg)*k[seg])-512*1024*d
                        bud.charge('second_gate_tests',N*2);gq=abs(y)>=k[0];gc=abs(yc)>=1024*k[0]
                        bud.charge('readout_correlation_word_products',N*2)
                        xq=d*y;xc=d*yc
                        bud.charge('old40_moment_values',W*24)
                        old=np.fromfile(ALIGN/f'{key}_moments.bin',dtype='<i8').reshape(W,24)
                        bud.charge('readout_correlation_word_products',N+W*4)
                        assert np.array_equal(xq.sum(axis=1),old[:,0]) and np.array_equal((xq*gq).sum(axis=1),old[:,1])
                        assert np.array_equal(xq[:,:4].sum(axis=1),old[:,4]) and np.array_equal((xq[:,:4]*gq[:,:4]).sum(axis=1),old[:,5])
                        assert np.array_equal(gq.sum(axis=1),old[:,9]) and np.array_equal(gq[:,:4].sum(axis=1),old[:,13])
                        bud.charge('instrument_basis_word_products',N*6)
                        z=d[:,:,None]*phi
                        pieces=[z,z*gq[:,:,None],z*gc[:,:,None]]
                        wm=np.column_stack([a.sum(axis=1) for a in pieces]+[a[:,:4].sum(axis=1) for a in pieces])
                        bud.charge('new_window_moment_bytes',wm.nbytes);wm.astype('<i8').tofile(out/f'{key}_statistics.bin')
                        bud.charge('gate_margin_word_inputs',N)
                        gap=abs(abs(yc)-1024*k[0]);bound=(abs(phi).sum(axis=2)+1024)*1024
                        legal=min(int(k[0]),int(k[1]),2047-int(k[0]),2047-int(k[1]))
                        def describe(sl):
                            m=wm[sl];v=m.sum(axis=0)
                            matrices={}
                            for method,offset,nn in [('full',0,len(m)*120),('selected',6,len(m)*4)]:
                                for mask,c in [('Q3_mask',2),('continuous_mask',4)]:
                                    ids=[offset,offset+1,offset+c,offset+c+1]
                                    matrices[method+'_'+mask]=matrix(v[ids],nn)
                            radii={}
                            for method,ss in [('full',slice(None)),('selected',slice(0,4))]:
                                pairs=set(zip(map(int,gap[sl,ss].ravel()),map(int,bound[sl,ss].ravel())))
                                rho=min([F(a,b) for a,b in pairs]+[F(legal,1024)])
                                ties=int(np.count_nonzero(gap[sl,ss]==0))
                                radii[method]={'rho_sufficient':str(rho),'open_continuous_cell_certified':rho>0,
                                               'continuous_gate_equalities':ties,'rho_larger_than_Q10_step':rho>F(1,1024)}
                            return {'matrices':matrices,'cell':radii}
                        total=describe(slice(None));blocks=[{'block':128+b,**describe(slice(b*B,(b+1)*B))} for b in range(8)]
                        for key2,mat in total['matrices'].items():
                            for i in range(2):
                                for j in range(2):assert F(mat['A'][i][j])==sum(F(b['matrices'][key2]['A'][i][j]) for b in blocks)/8
                        bud.charge('readout_correlation_word_products',N)
                        results.append({'seed':seed,'rate':rate,'initialization':init,'reference':tag,'codes':k.tolist(),
                                        'total':total,'blocks':blocks,'continuous_correlation_sum_scaled1024_full':xc.sum(axis=1).tolist(),
                                        'continuous_second_correlation_sum_scaled1024_full':(xc*gc).sum(axis=1).tolist()})
                        print(key,{key2:a['rank'] for key2,a in total['matrices'].items()},total['cell'],flush=True)
        assert len(results)==40
        write(out/'results.json',{'completed':True,'rows':results})
        write(out/'new_moment_hashes.json',{str(p):digest(p) for p in out.glob('*.bin')})
        guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
        write(out/'verification.json',{'passed':True,'positions':40,'whole_matrices':160,'block_matrices':1280,
                                        'all_old_source_moments_and_block_sums_exact':True,'new_loss_scores_source_requests_learning_paths_fft_holdout':0})
    finally:write(out/'accounting_main.json',{'limits':LIMITS,'used':bud.used,'all_limits_met':all(bud.used[k]<=LIMITS[k] for k in LIMITS),'completed':len(results)==40})


def verify(out):
    assert not (out/'independent_check.json').exists()
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'));guard(load(out/'new_moment_hashes.json'))
    prior=load(ALIGN/'results.json')['rows'];rows=load(out/'results.json')['rows'];bud=Budget(CHECK_LIMITS);done=0
    try:
        for seed in SEEDS:
            bud.charge('source_tuple_values',N*4);words=np.array(source(seed),dtype=np.int64)
            for rate in ('base','quarter'):
                for init in ('actual','prefix'):
                    pp=[r for r in prior if (r['seed'],r['rate'],r['initialization'])==(seed,rate,init)]
                    k0=pp[0]['initial_codes'];backend=sorted(set(map(int,words[:,:,2].ravel())))
                    bud.charge('rear_Fraction_PWL',len(backend));rt={b:scalar(8*b,k0[4:],32) for b in backend}
                    counts={};bud.charge('grouped_word_inputs',N)
                    # Each cell keeps integer weights separately for all8 blocks
                    # and selected4. No vector mask/basis sum is reused.
                    for w in range(W):
                        b=w//B
                        for slot in range(120):
                            _,q2,sar,bits=map(int,words[w,slot]);d=2*(bits&1)-1;d2=2*((bits>>1)&1)-1
                            raw=1024*q2+rt[sar]-128*d2;key=(raw,d)
                            if key not in counts:counts[key]=[0]*16
                            counts[key][b]+=1
                            if slot<4:counts[key][8+b]+=1
                    for rr in [r for r in rows if (r['seed'],r['rate'],r['initialization'])==(seed,rate,init)]:
                        k=rr['codes'];name=f"{seed}_{rate}_{init}_{rr['reference']}"
                        bud.charge('old_window_moment_values',W*12)
                        saved=np.fromfile(out/f'{name}_statistics.bin',dtype='<i8').reshape(W,12)
                        sums=[[0]*12 for _ in range(8)];rhos=[{'full':F(min(k[0],k[1],2047-k[0],2047-k[1]),1024),'selected':F(min(k[0],k[1],2047-k[0],2047-k[1]),1024)} for _ in range(8)]
                        ties=[{'full':0,'selected':0} for _ in range(8)]
                        bud.charge('grouped_gate_basis_cells',len(counts))
                        for (raw,d),nn in counts.items():
                            sg=1 if raw>=0 else -1;mag=abs(raw)
                            phi=[sg*min(max(mag-1024*j,0),1024) for j in range(4)]
                            y=scalar(raw,k[:4],128)-512*d
                            yc=sum(F(k[j]*phi[j],1024) for j in range(4))-512*d
                            gq=abs(y)>=k[0];gc=abs(yc)>=k[0]
                            v=[d*phi[0],d*phi[1],d*gq*phi[0],d*gq*phi[1],d*gc*phi[0],d*gc*phi[1]]
                            rho=abs(abs(yc)-k[0])/(abs(phi[0])+abs(phi[1])+1024)
                            for b in range(8):
                                for method,offset,count in [('full',0,nn[b]),('selected',6,nn[8+b])]:
                                    if count:
                                        for j in range(6):sums[b][offset+j]+=count*v[j]
                                        rhos[b][method]=min(rhos[b][method],rho)
                                        if abs(yc)==k[0]:ties[b][method]+=count
                        for b in range(8):
                            assert sums[b]==saved[b*B:(b+1)*B].sum(axis=0).tolist()
                            for method in ('full','selected'):
                                old=rr['blocks'][b]['cell'][method]
                                assert str(rhos[b][method])==old['rho_sufficient'] and ties[b][method]==old['continuous_gate_equalities']
                            for key2,mat in rr['blocks'][b]['matrices'].items():
                                assert exact_matrix_rank([[F(z) for z in line] for line in mat['A']])==mat['rank']
                        for method in ('full','selected'):
                            assert str(min(rhos[b][method] for b in range(8)))==rr['total']['cell'][method]['rho_sufficient']
                            assert sum(ties[b][method] for b in range(8))==rr['total']['cell'][method]['continuous_gate_equalities']
                        done+=1;print(name,'all grouped Fraction block matrices and gate radii exact',flush=True)
        assert done==40
        guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'));guard(load(out/'new_moment_hashes.json'))
        write(out/'independent_check.json',{'passed':True,'positions':40,'grouped_blocks':320,'all_rank_and_gate_radius_results_exact':True})
    finally:write(out/'accounting_independent.json',{'limits':CHECK_LIMITS,'used':bud.used,'all_limits_met':all(bud.used[k]<=CHECK_LIMITS[k] for k in CHECK_LIMITS),'completed':done==40})


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['freeze','analyze','verify']);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    try:{'freeze':freeze,'analyze':analyze,'verify':verify}[a.mode](a.out)
    except Exception:
        if a.out.exists():write(a.out/(a.mode+'_failure.json'),{'traceback':traceback.format_exc()})
        raise
