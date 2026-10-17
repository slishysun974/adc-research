"""Independent Fraction lookup readouts and all-window request/score checks."""
import argparse
from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
import sys
import traceback
import numpy as np

ROOT = Path('D:/ADC')
sys.path[:0] = [str(ROOT),str(ROOT/'src')]
from experiments.exp_073_bank_feedback_intervention.analyze_fixed_learning_alignment import (
    BASE, OLD, CAP, BASIS, HISTORY, SEEDS, W, B, N, ZS, INDEPENDENT_LIMITS,
    source, load, write, digest, guard, ExactProjector, Budget, pack,
)
from adc_research.theory.static_fixed_contract import readout
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.calibration.fixed_four_lane_window import _bank, FourLaneConversion
from adc_research.calibration.fixed_gated_lms import FixedGatedLmsState
from experiments.exp_060_static_auxiliary_preflight.run import fixed_setup


def scalar(raw,k,width):
    m = abs(int(raw));j = min(m//(8*width),3)
    z = round(F(8*width*sum(map(int,k[:j])),1024))+round(F((m-j*8*width)*int(k[j]),1024))
    return z if raw>=0 else -z


def dot(a,b):
    # Python bigint multiplication/reduction, distinct from main safe int64.
    return int((np.asarray(a,dtype=object)*np.asarray(b,dtype=object)).sum())


def check(out):
    assert not (out/'independent_check.json').exists(), 'Refuse overwrite'
    assert digest(Path(__file__)) == digest(out/'frozen_checker.py')
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    rows = load(out/'results.json')['rows']
    old = {(r['seed'],r['rate'],r['initialization']):r for r in load(BASIS/'results.json')['rows']}
    bud = Budget(INDEPENDENT_LIMITS);p = ExactProjector();done = 0;probes = []
    t2 = F(sum(t*t for t in p.ti),len(p.ti)*p.D*p.D)
    _,cfg = fixed_setup(load(OLD/'source_protocol.json'))
    try:
        for seed in SEEDS:
            bud.charge('source_tuple_values',N*4);words = np.array(source(seed),dtype=np.int64)
            q1,q2,sar,bits = (words[:,:,j] for j in range(4))
            d,d2 = 2*(bits&1)-1,2*((bits>>1)&1)-1
            for rate,den in [('base',1),('quarter',4)]:
                stem = f'{seed}_{rate}'
                for idx,init in ((0,'actual'),(2,'prefix')):
                    name = f'{stem}_{init}'
                    bud.charge('initial_Q22_values',8)
                    a0 = np.array(np.memmap(BASE/f'{stem}_q22.bin',dtype='<i4',mode='r',shape=(W+1,4,8))[0,idx],dtype=np.int64)
                    k0 = np.array([round(F(int(z),4096)) for z in a0],dtype=np.int64)
                    bud.charge('old24_values',W*24);mom = np.fromfile(HISTORY/f'{name}_front_moments.bin',dtype='<i8').reshape(W,24)
                    # Rear Fraction lookup has at most256 attained backend codes.
                    vals = np.unique(sar);bud.charge('rear_Fraction_PWL_lookup',len(vals))
                    rt = {int(v):scalar(8*int(v),k0[4:],32) for v in vals}
                    rear = np.array([rt[int(v)] for v in sar.ravel()],dtype=np.int64).reshape(W,120)
                    raw = 1024*q2+rear-128*d2
                    assert raw.min()>=-4096 and raw.max()<4096
                    phi = np.stack([np.sign(raw)*np.minimum(np.maximum(abs(raw)-1024*j,0),1024) for j in range(2)],axis=2)
                    bud.charge('held_output_values',N)
                    held = np.array(np.memmap(BASE/f'{stem}_outputs.bin',dtype='<i2',mode='r',shape=(W,4,120))[:,idx+1],dtype=np.int64)
                    pm = old[seed,rate,init]['position_moments'];h = [[F(z) for z in a] for a in pm['Gram_H']]
                    means = [F(int(mom[:,10+j].sum()),W) for j in range(2)]
                    for row in [r for r in rows if (r['seed'],r['rate'],r['initialization'])==(seed,rate,init)]:
                        k = np.array(row['codes'],dtype=np.int64);key = f"{name}_{row['reference']}"
                        assert row['initial_codes']==k0.tolist() and row['diagnostic_Q22']==(4096*k).tolist()
                        if row['reference']=='mean':assert k[:2].tolist()==[round(z) for z in means]
                        else:
                            cap = next(r for r in load(CAP/'results.json')['rows'] if (r['seed'],r['rate'],r['initialization'])==(seed,rate,init))
                            assert k[:2].tolist()==cap['capacity']['legal_low_Q10_witness']
                        assert np.array_equal(k[2:],k0[2:])
                        vals = np.unique(raw);bud.charge('front_Fraction_PWL_lookup',len(vals))
                        tab = {int(v):scalar(int(v),k[:4],128) for v in vals}
                        y = np.array([tab[int(v)] for v in raw.ravel()],dtype=np.int64).reshape(W,120)-512*d
                        oq = 16384+4096*q1+y
                        # Independent integerize exact Q3, including signed ties.
                        quotient = oq//8;rem = oq-8*quotient
                        output = quotient+((rem>4)|((rem==4)&(quotient%2!=0)))
                        bud.charge('saved_output_values',N)
                        saved = np.fromfile(out/f'{key}_outputs.bin',dtype='<i2').reshape(W,120)
                        assert np.array_equal(saved,output)
                        threshold = np.array([sum(map(int,k[:j])) for j in range(4)])
                        bud.charge('gate_tests',N*4);g = np.stack([abs(y)>=t for t in threshold],axis=2)
                        bud.charge('gate_product_word_components',N*4)
                        c = d[:,:,None]*y[:,:,None]*g
                        fs,ss = c.sum(axis=1),c[:,:4].sum(axis=1)
                        rq = []
                        for sums,base in ((ss,F(-96,25*den)),(fs,F(-16,125*den))):
                            bud.charge('request_Fraction_roundings',W*4)
                            rq.append(np.array([[round(base*m*int(v)) for m,v in zip((1,3,6,12),a)] for a in sums],dtype=np.int64))
                        data = np.column_stack((fs,ss,g.sum(axis=1),g[:,:4].sum(axis=1),*rq))
                        bud.charge('saved_moment_values',W*24)
                        assert np.array_equal(data,np.fromfile(out/f'{key}_moments.bin',dtype='<i8').reshape(W,24))
                        # Continuous output using all4 independent basis terms.
                        bud.charge('continuous_basis_components',N*4)
                        allphi = [np.sign(raw)*np.minimum(np.maximum(abs(raw)-1024*j,0),1024) for j in range(4)]
                        ynum = ZS*(2048+512*q1-64*d)+sum(int(k[j])*allphi[j] for j in range(4))
                        for z,scale,metric in ((output,1,'integer_loss'),(ynum,ZS,'continuous_loss')):
                            bud.charge('exact_loss_word_inputs',N);bud.charge('exact_dot_word_products',N)
                            ph = z.reshape(-1,len(p.ti)).astype(object).sum(axis=0)
                            bud.charge('target_scalar_products',len(ph))
                            td = sum(int(a)*int(b) for a,b in zip(ph,p.ti))
                            loss = F(dot(z,z),N*scale*scale)-F(2*td,N*scale*p.D)+t2
                            assert loss==F(row['total'][metric]['exact'])
                        # Independent gradient identity from the already-checked
                        # held-integer family, retaining its rounding residual.
                        residual = ynum-ZS*held-sum(int(k[j]-k0[j])*phi[:,:,j] for j in range(2))
                        gradient = []
                        for j in range(2):
                            bud.charge('exact_dot_word_products',N)
                            grad = F(pm['gradient_at_mean_position'][j]['exact'])
                            grad += 2*sum(h[j][i]*F(F(int(k[i]))-means[i],1024) for i in range(2))
                            grad += F(2*dot(phi[:,:,j],residual),N*8*ZS)
                            assert grad==F(row['total']['gradient'][j]['exact'])
                            gradient.append(grad)
                        localnum = ynum-ZS*(2048+512*q1)
                        bud.charge('gate_tests',N*4)
                        cg = np.stack([abs(localnum)>=1024*t for t in threshold],axis=2)
                        bud.charge('gate_product_word_components',N*4)
                        cp = d[:,:,None]*localnum[:,:,None]*cg
                        assert np.count_nonzero(g!=cg)==row['gate_Q3_vs_continuous_differences']
                        for method,arr,ca,rr in [('full',fs,cp.sum(axis=1),rq[1]),
                                                ('selected',ss,cp[:,:4].sum(axis=1),rq[0])]:
                            base = F(-16,125*den) if method=='full' else F(-96,25*den)
                            for label,sums,scale in [('Q3',arr,1),('continuous_front',ca,1024)]:
                                step = [base*m*F(sum(map(int,sums[:,j])),W*scale*(1<<22)) for j,m in enumerate((1,3))]
                                actual = row['total']['directions'][method+'_'+label]
                                assert list(map(str,step))==actual['mean_step_low2']
                                derivative = sum(gradient[j]*step[j] for j in range(2))
                                curve = sum(step[i]*h[i][j]*step[j] for i in range(2) for j in range(2))
                                assert derivative==F(actual['derivative']['exact'])
                                assert derivative+curve==F(actual['mean_step_continuous_loss_change']['exact'])
                            step = [F(sum(map(int,rr[:,j])),W*(1<<22)) for j in range(2)]
                            actual = row['total']['directions'][method+'_rounded_Q22']
                            assert list(map(str,step))==actual['mean_step_low2']
                            assert sum(gradient[j]*step[j] for j in range(2))==F(actual['derivative']['exact'])
                        cc = replace(cfg.cascade,stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=tuple(map(int,k[:4]))),
                                     stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=tuple(map(int,k[4:]))))
                        local = []
                        for w in (0,1024,2047):
                            conversions = []
                            for s in range(120):
                                sample = DigitalCalibrationSample(int(q1[w,s]),int(q2[w,s]),int(sar[w,s]),int(d[w,s]),int(d2[w,s]))
                                conversions.append(FourLaneConversion(120*(128*256+w)+s,s%4,sample))
                                if s in (0,1,2,3,59,119):
                                    bud.charge('formal_readouts',1)
                                    formal = correct_two_stage_fixed_observed(sample,cc)
                                    assert formal.stage1_raw_scaled==int(raw[w,s])
                                    assert formal.unclipped_output_scaled==int(oq[w,s])
                            after = np.clip(k[:4]*4096+rq[0][w],0,2047*4096)
                            ka = np.array([round(F(int(z),4096)) for z in after],dtype=np.int64)
                            bank = FixedGatedLmsState(tuple(map(int,k[:4]*4096)),(0,)*4,(0,)*4,(0,)*4,120*(128*256+w))
                            bud.charge('formal_front_bank_probes',1)
                            update = _bank(bank,replace(cfg.stage1_lms,step_sizes=tuple(mu/den for mu in cfg.stage1_lms.step_sizes)),
                                           conversions,[(512*int(d[w,s]),int(y[w,s])) for s in range(120)],tuple(s<4 for s in range(120)),30)
                            assert update.requested_deltas==tuple(map(int,rq[0][w]))
                            assert update.state.accumulator_codes==tuple(map(int,after))
                            bud.charge('Fraction_after_step_PWL',120)
                            ya = np.array([round(F(16384+4096*int(q1[w,s])+scalar(int(raw[w,s]),ka,128)-512*int(d[w,s]),8)) for s in range(120)])
                            bud.charge('local_step_integer_score_inputs',120);bud.charge('local_step_target_products',120)
                            change = F(sum(int(ya[s]-output[w,s])*int(ya[s]+output[w,s]) for s in range(120)),120)
                            change -= F(2*sum(int(ya[s]-output[w,s])*int(p.ti[(w*120+s)%len(p.ti)]) for s in range(120)),120*p.D)
                            local.append({'window':w,'requested_Q22':rq[0][w].tolist(),'exported_after':ka.tolist(),
                                          'export_changed':bool(np.any(ka!=k[:4])),'integer_loss_change':pack(change)})
                        probes.append({'case':key,'local_steps':local})
                        done += 1;print(key,'independent full readout/requests/loss/gradient and3 local steps exact',flush=True)
        assert done==40
        guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'));guard(load(out/'new_moment_hashes.json'))
        write(out/'local_step_controls.json',{'passed':True,'rows':probes})
        write(out/'independent_check.json',{'passed':True,'positions':done,'all_saved_integer_readouts_and_window_requests_exact':True,
                                           'all_losses_and_true_continuous_gradients_exact':True,'formal_probes':bud.used['formal_readouts'],
                                           'formal_bank_probes':bud.used['formal_front_bank_probes'],'source_execution_output_hashes_preserved':True})
    finally:
        write(out/'accounting_independent.json',{'limits':INDEPENDENT_LIMITS,'used':bud.used,
                'all_limits_met':all(bud.used[k]<=INDEPENDENT_LIMITS[k] for k in INDEPENDENT_LIMITS),'completed':done==40})


if __name__=='__main__':
    ap = argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a = ap.parse_args()
    try:check(a.out)
    except Exception:
        write(a.out/'independent_failure.json',{'traceback':traceback.format_exc()})
        raise
