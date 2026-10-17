"""Read-only fixed-state forcing and own-state response of front-only Gu.

No learner is propagated. Frozen requests are current-word references only.
All twenty existing cases and all eight blocks are preserved.
"""
import argparse
from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
import shutil
import traceback
import numpy as np

from experiments.exp_073_bank_feedback_intervention.run import (
    ROOT, OLD, BASE, PHASE, SEEDS, W, source, load, write, digest, guard,
    round_ratio, pwl_scaled, fixed_setup, readout, export, nearest_even,
    correct_two_stage_fixed_observed, DigitalCalibrationSample,
)
from experiments.exp_074_learning_signal_gate_intervention.analyze_response import Projector
from experiments.exp_074_learning_signal_gate_intervention.analyze_gates import pack

NEW = ROOT/'artifacts/runs/EXP_073/bank_feedback_v1'
PRIOR = ROOT/'artifacts/research/anchor_sampling_20261013_v1'
SCALE = W*(1 << 25)
TAGS = ['mean_frozen_drive', 'centered_frozen_drive', 'own_state_response', 'export_rounding', 'current_readout_rounding']
COLS = ['actual_request1', 'actual_request2', 'frozen_request1', 'frozen_request2',
        'actual_second_gate_count', 'frozen_second_gate_count', 'actual_dy1_Q3', 'frozen_dy1_Q3',
        'actual_gated_dy2_Q3', 'frozen_gated_dy2_Q3', 'K1', 'K2',
        'mean1_numW', 'mean2_numW', 'centered1_numW', 'centered2_numW',
        'response1_numW', 'response2_numW', 'export1_numW', 'export2_numW',
        'signal_first_second_corr', 'gate_after_signal_second_corr',
        'signal_after_gate_second_corr', 'gate_first_second_corr']
DOCS = ['docs/STATUS.md', 'docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md',
        'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md', 'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
        'docs/theory/README.md', 'docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md',
        'docs/reports/GU_ALGORITHM_EVALUATION_V1.md', 'docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
        'docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md',
        'docs/reports/experiments/EXP_073_BANK_FEEDBACK_INTERVENTION_V1.md',
        'experiments/exp_073_bank_feedback_intervention/README.md']


def isum(a):
    a=np.asarray(a,dtype=np.int64).ravel();total=0
    for i in range(0,len(a),16384):total+=int(a[i:i+16384].astype(object).sum())
    return total


def mulsum(a,b):
    a=np.asarray(a,dtype=np.int64).ravel();b=np.asarray(b,dtype=np.int64).ravel()
    assert a.shape==b.shape;total=0
    for i in range(0,len(a),16384):
        total+=int((a[i:i+16384].astype(object)*b[i:i+16384].astype(object)).sum())
    return total


class ExactProjector(Projector):
    """Same target relations; only products/reductions use bounded bigint chunks."""
    def phase_sum(self,u):
        z=np.asarray(u,dtype=np.int64).reshape(-1,len(self.ti))
        assert int(np.max(np.abs(z),initial=0))*len(z)<1<<63
        return z.sum(axis=0,dtype=np.int64)

    def score(self,num,y,scale=1):
        num=np.asarray(num,dtype=np.int64);y=np.asarray(y,dtype=np.int64);size=num.size
        phase=self.phase_sum(num)
        target=sum(int(z)*t for z,t in zip(phase,self.ti))
        power=F(mulsum(num,num),size*scale*scale)
        cross=F(2*mulsum(num,y),size*scale)-F(2*target,size*scale*self.D)
        net=power+cross;rad=2*self.rad*F(isum(np.abs(num)),size*scale)
        interval=[net-rad,net+rad]
        return {'power':pack(power),'error_cross':pack(cross),'net':pack(net),
                'target_interval':[str(v) for v in interval],
                'sign_certified':interval[0]>0 or interval[1]<0,'count':size,'normalization_count':size,
                'error_projection_over_power':float(cross/(2*power)) if power else None}

    def projected(self,u,y,scale=1):
        r=self.score(u,y,scale);phase=self.phase_sum(u)
        v=F(sum(int(z)*t for z,t in zip(phase,self.xi)),u.size*scale*self.XD)
        c=F(sum(int(z)*t for z,t in zip(phase,self.ci)),u.size*scale*self.XD)
        ma=F(isum(np.abs(u)),u.size*scale)
        noise=self.eta+self.nu*(1+self.rho)+self.center_round/2048
        rad=4096*(self.rho*abs(c)+self.rho**2*abs(v)/2+noise*ma)
        center=F(r['net']['exact']);box=[F(z) for z in r['target_interval']]
        new=[center-rad,center+rad];both=[max(box[0],new[0]),min(box[1],new[1])]
        assert both[0]<=both[1]
        r.update({'sine_tone_projection':pack(v),'cosine_tone_projection':pack(c),
                  'shared_phase_radius':pack(rad),'shared_phase_interval':[str(z) for z in new],
                  'intersection_interval':[str(z) for z in both],
                  'intersection_sign_certified':both[0]>0 or both[1]<0})
        return r


def prefix(v):
    return np.vstack((np.zeros((1, v.shape[1]), dtype=np.int64), np.cumsum(v, axis=0, dtype=np.int64)))


def controls():
    # Finite-record centered forcing closes at the chosen endpoint by definition.
    u0 = np.array([[1, -2], [3, 0], [-1, 2], [1, 0]], dtype=np.int64)
    ua = u0+np.array([[0, 0], [-1, 1], [2, -1], [-1, 0]], dtype=np.int64)
    n = len(ua);v = np.arange(n+1)[:, None]
    mean = v*u0.sum(axis=0);centered = n*prefix(u0)-mean;response = n*prefix(ua-u0)
    assert np.array_equal(mean+centered+response, n*prefix(ua))
    assert not centered[-1].any() and not response[0].any()
    # A large forcing/response cancellation is possible without small forcing.
    assert F(3)**2+F(-2)**2+2*F(3)*F(-2) == 1
    # Loss direction requires the baseline error cross, not just power.
    assert F(1)**2+2*F(0)*F(1) == 1
    assert F(1)**2+2*F(-2)*F(1) == -3
    # Nearest-even export gap differs from an accumulator gap.
    a0, a1 = 4095, 4097
    assert round(F(a1,4096))-round(F(a0,4096)) == 0
    assert F(a1-a0,4096) == F(1,2048)
    # Both signal/gate orders and their interaction.
    y0,y1,g0,g1=F(1),F(2),0,1
    assert (y1-y0)*g0+y1*(g1-g0)==(y1-y0)*g1+y0*(g1-g0)==2
    # Reduced odd denominator25 gives sharp12/25 single-rounding error.
    assert abs(round(F(12,25))-F(12,25))==F(12,25)
    big=np.array([1<<40,-(1<<40),3],dtype=np.int64)
    assert mulsum(big,big)==2*(1<<80)+9 and isum(big)==3
    return {'passed':True,'exact_controls':9,'new_physical_source':False}


def prepare(out):
    assert not out.exists(), 'Refuse overwrite'
    assert load(NEW/'verification.json')['passed'] and load(PRIOR/'delivery_verification.json')['passed']
    # Existing moments concern gate-policy differences; they lack these frozen
    # first/second selected products. No repeat of their actual readout audit.
    out.mkdir(parents=True)
    files={}
    paths=[OLD/'tone.bin',OLD/'source_protocol.json',PHASE,NEW/'protocol.json',NEW/'results.json',NEW/'verification.json',
           PRIOR/'protocol.json',PRIOR/'verification.json',PRIOR/'new_moment_hashes.json']
    previous=load(PRIOR/'source_hashes.json')
    for seed in SEEDS:
        p=OLD/f'both_smooth_{seed}_words.bin';assert digest(p)==previous[str(p)];paths.append(p)
        for rate in ('base','quarter'):
            stem=f'{seed}_{rate}'
            paths += [NEW/f'{stem}_q22.bin',NEW/f'{stem}_outputs.bin',NEW/f'{stem}_requests.bin',
                      BASE/f'{stem}_q22.bin',BASE/f'{stem}_outputs.bin']
    for p in paths:files[str(p)]=digest(p)
    guard(files)
    write(out/'source_hashes.json',files)
    sources=list((ROOT/'src/adc_research').rglob('*.py'))+list((ROOT/'experiments').rglob('*.py'))
    write(out/'execution_hashes.json',{str(p):digest(p) for p in sources})
    shutil.copyfile(Path(__file__),out/'frozen_analysis.py')
    write(out/'controls.json',controls())
    write(out/'protocol.json',{
        'version':'EXP073-front-fixed-forcing-own-response-v2','date':'2026-10-13',
        'authority':'D136..139 and user continue; STATUS front autonomous learning gap',
        'scope':'Original5 seeds, rates1/1/4, actual/prefix,20 front-only versus both-held cases,128..136,40960 windows/160 blocks.',
        'reference':'Common legal initial front/rear Q22 before evaluation. Frozen front request is computed on same current words at that state; rear stays fixed in original front-only path. No target chooses reference or endpoint.',
        'missing_quantity':'Prior NG44/45 matrices have sampling gaps for different gate-policy pairs; they do not provide this front-only path frozen selected first2 products and its second gate. Compute only these missing/current Q3 and selected quantities.',
        'derivation':'Accumulator displacement equals w*mean(frozen requests) plus prefix-centered frozen requests plus prefix(actual-frozen response). Finite mean uses complete saved record, not online or population expectation. Q1.10 export residual and current Q3/integer gap complete exact five-component output. Full Gram cross and held-error projections reproduce actual integer loss.',
        'alternatives':['A fixed-state mean drive alone explains harmful output change, versus centered forcing and own response needing to be retained.',
                        'Large four-word fluctuations map directly to output loss, versus own-state response cancelling them and changing their target projection.',
                        'Hidden-state displacement alone equals output change, versus exported and current-readout remainders needing separate treatment.'],
        'orders':['mean, centered, response, export, readout','centered, mean, response, export, readout'],
        'predictions':['Actual low requests, states and both output sequences reproduce; frozen first window requests equal actual.',
                       'All finite cumulative components sum to every saved Q22 state, both request/product orders and bounds close.',
                       'All5 output components sum to saved integer gap, full Gram/projections and160 block sums reproduce original20 front losses.',
                       'No ranking or sign is preassumed for mean, centered, response or their interactions; retain all zeros, opposite signs and uncertified target ranges.'],
        'budget':{'source_unique_word_tuples':1228800,'active_Q22_values':327840,'initial_BASE_Q22_values':160,
                  'actual_front_request_values':163840,'saved_integer_outputs_loaded':9830400,
                  'front_Q3_PWL':9830400,'rear_Q3_PWL':4915200,'selected_second_gate_comparisons':327680,
                  'low_request_vectors_actual_and_frozen':81920,'rational_and_formal_readouts_each':720,
                  'independent_Fraction_low_request_vectors':120,'new_window_matrix_bytes':7864320,
                  'reference_score_code_inputs_total_and_blocks':88473600,
                  'off_diagonal_Gram_word_products_total_and_blocks':98304000,
                  'new_learning_submissions_paths_analog_source_fft_holdout':0},
        'matrix_columns':COLS,'matrix_format':'20 files2048x24 little-endian int64. History numerator denominatorW=2048 Q22; component output denominator2^36 code.',
        'stopping':'Fixed20/160 and136 endpoint only; reject source/domain/arithmetic/probe inconsistency and preserve failures. No additional horizon, rate, seed, model, policy, fitting or tuning.',
        'limits':'Deterministic record-conditioned components and references, not independent causal policies, stationary/iid noise or unique percentages. Reference components may not form legal coefficients. Target cross is offline with existing NG39/43 conditions.'})
    write(out/'numeric_repair.json',{'prior':'artifacts/research/front_forcing_response_20261013_v1',
        'reason':'Inherited int64 product guard rejects exact output numerators before first score. No published result or new learner.',
        'change':'Local scalar Python bigint sums and products in chunks16384; original target/phase enclosure formulas unchanged.',
        'unchanged':'All20 cases, sources, histories, reference, denominator2^36, decomposition, endpoint, readout/probe budgets and target.',
        'failed_attempt_accounting':{'front_Q3_PWL':491520,'rear_Q3_PWL':245760,
          'active_Q22_values':16392,'initial_BASE_Q22_values':8,'request_values':8192,'saved_integer_outputs':491520,
          'completed_reference_scores':0,'new_learning_submissions_paths_source_fft_holdout':0}})
    for name in DOCS:
        p=out/'documents_before'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
    print('Frozen all20 front-only histories, missing products and finite output-component budget',flush=True)


def requests(y,d,K,den):
    second=np.abs(y[:,:4])>=K[:,0,None]
    corr=np.column_stack(((d[:,:4]*y[:,:4]).sum(axis=1),(d[:,:4]*y[:,:4]*second).sum(axis=1)))
    rq=round_ratio(corr*np.array([-96,-288],dtype=np.int64),25*den)
    return rq,corr,second


def probes(words,acc,ys,raw,yq,rq,den,expected):
    _,cfg=fixed_setup(load(OLD/'source_protocol.json'));count=rc=0
    for w in (0,1024,2047):
        codes=export(tuple(map(int,acc[w])));ks=tuple(F(k,1024) for k in codes)
        cc=replace(cfg.cascade,stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=codes[:4]),
                   stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=codes[4:]))
        sums=[F(0),F(0)]
        for j in (0,1,2,3,59,119):
            q1,q2,sar,bits=map(int,words[w,j]);d1,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
            rd=readout(q1,q2,F(sar),d1,d2,ks,data_q3=True)
            formal=correct_two_stage_fixed_observed(DigitalCalibrationSample(q1,q2,sar,d1,d2),cc)
            assert formal.unclipped_output_scaled==8*rd.output and formal.stage1_raw_scaled==8*rd.raw1
            assert int(8*rd.y1)==int(yq[w,j]) and int(8*rd.raw1)==int(raw[w,j])
            assert nearest_even(rd.output)==int(ys[w,j])==int(expected[w,j])
            if j<4:
                for i in range(2):sums[i]+=d1*rd.y1*rd.gates[0][i]
            count+=1
        wanted=[round(-F(768*(1 if i==0 else 3),25*den)*sums[i]) for i in range(2)]
        assert wanted==list(map(int,rq[w]));rc+=1
    return count,rc


def output_stats(nums,y0,projector,old=None):
    allnum=sum(nums);scored=[projector.projected(u,y0,SCALE) for u in nums]
    actual=projector.projected(allnum,y0,SCALE)
    q=[[F(0) for _ in nums] for _ in nums]
    for i in range(5):
        q[i][i]=F(scored[i]['power']['exact'])
        for j in range(i):q[i][j]=q[j][i]=F(mulsum(nums[i],nums[j]),nums[i].size*SCALE*SCALE)
    b=[F(s['error_cross']['exact']) for s in scored]
    assert F(actual['net']['exact'])==sum(b)+sum(sum(z) for z in q)
    stage=[];cache={frozenset([i]):s for i,s in enumerate(scored)}
    cache[frozenset(range(5))]=actual
    for order in [list(range(5)),[1,0,2,3,4]]:
        accumulated=np.zeros_like(nums[0]);steps=[];ids=set()
        for i in order:
            accumulated+=nums[i]
            ids.add(i);key=frozenset(ids)
            if key not in cache:cache[key]=projector.projected(accumulated,y0,SCALE)
            ss=cache[key]
            steps.append({'added':TAGS[i],'net':ss['net'],'power':ss['power'],
                          'interval':ss['intersection_interval'],'sign_certified':ss['intersection_sign_certified']})
        stage.append(steps)
    if old is not None:assert F(actual['net']['exact'])==F(old)
    return {'components':{tag:scored[i] for i,tag in enumerate(TAGS)},
            'gram':[[str(z) for z in r] for r in q],'error_cross':[str(z) for z in b],
            'orders':stage,'actual':actual,'mean_plus_centered_cross':pack(2*q[0][1]),
            'frozen_drive_response_cross':pack(2*(q[0][2]+q[1][2]))}


def analyze(out):
    assert not (out/'results.json').exists(),'Refuse complete overwrite'
    assert digest(Path(__file__))==digest(out/'frozen_analysis.py')
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'));controls()
    projector=ExactProjector()
    prior={(r['seed'],r['rate'],r['initialization']):r for r in load(NEW/'results.json')['rows']}
    rows=[];pc=rc=0
    for seed in SEEDS:
        words=source(seed);q1,q2,sar,bits=(words[:,:,j].astype(np.int64) for j in range(4))
        d,d2=2*(bits&1)-1,2*((bits>>1)&1)-1
        for rate,den in (('base',1),('quarter',4)):
            stem=f'{seed}_{rate}'
            states=np.memmap(NEW/f'{stem}_q22.bin',dtype='<i4',mode='r',shape=(W+1,4,8))
            basestates=np.memmap(BASE/f'{stem}_q22.bin',dtype='<i4',mode='r',shape=(W+1,4,8))
            savedrq=np.memmap(NEW/f'{stem}_requests.bin',dtype='<i4',mode='r',shape=(W,4,8))
            savedY=np.memmap(NEW/f'{stem}_outputs.bin',dtype='<i2',mode='r',shape=(W,4,120))
            savedY0=np.memmap(BASE/f'{stem}_outputs.bin',dtype='<i2',mode='r',shape=(W,4,120))
            for h,init in ((0,'actual'),(2,'prefix')):
                aa=np.array(states[:,h],dtype=np.int64);a0=np.array(basestates[0,h],dtype=np.int64)
                assert np.array_equal(aa[0],a0) and np.all(aa[:,4:]==a0[4:]) and np.all(aa[:,2:4]==a0[2:4])
                rq=np.array(savedrq[:,h,:4],dtype=np.int64);assert not rq[:,2:].any()
                assert np.array_equal(aa[1:,:4]-aa[:-1,:4],rq)
                K=round_ratio(aa[:-1,:4],4096);K0=np.broadcast_to(round_ratio(a0[:4],4096),(W,4))
                rear=np.broadcast_to(round_ratio(a0[4:],4096),(W,4))
                raw=1024*q2+pwl_scaled(8*sar,rear,32)-128*d2
                yt=pwl_scaled(raw,K,128)-512*d;y0=pwl_scaled(raw,K0,128)-512*d
                outActual=16384+4096*q1+yt;outHeld=16384+4096*q1+y0
                assert np.all((outActual>=0)&(outActual<=4095*8)) and np.all((outHeld>=0)&(outHeld<=4095*8))
                yActual=round_ratio(outActual,8);yHeld=round_ratio(outHeld,8)
                assert np.array_equal(yActual,savedY[:,h]) and np.array_equal(yHeld,savedY0[:,h+1])
                actual,corrA,gA=requests(yt,d,K,den);frozen,corr0,g0=requests(y0,d,K0,den)
                assert np.array_equal(actual,rq[:,:2]) and np.array_equal(actual[0],frozen[0])
                gain=np.array([-96,-288],dtype=np.int64)
                roundA=actual*(25*den)-corrA*gain;round0=frozen*(25*den)-corr0*gain
                assert np.all(np.abs(roundA)<=12*den) and np.all(np.abs(round0)<=12*den)
                assert np.all(np.abs(roundA-round0)<=24*den)
                ss=(d[:,:4]*(yt[:,:4]-y0[:,:4])*g0).sum(axis=1)
                ga=(d[:,:4]*yt[:,:4]*(gA.astype(np.int64)-g0.astype(np.int64))).sum(axis=1)
                sa=(d[:,:4]*(yt[:,:4]-y0[:,:4])*gA).sum(axis=1)
                gf=(d[:,:4]*y0[:,:4]*(gA.astype(np.int64)-g0.astype(np.int64))).sum(axis=1)
                assert np.array_equal(corrA[:,1]-corr0[:,1],ss+ga) and np.array_equal(ss+ga,sa+gf)
                total=frozen.sum(axis=0,dtype=np.int64);w=np.arange(W+1)[:,None]
                mean=w*total;centered=W*prefix(frozen)-mean;response=W*prefix(actual-frozen)
                disp=aa[:,:2]-a0[:2]
                assert np.array_equal(mean+centered+response,W*disp) and not centered[-1].any()
                Kall=round_ratio(aa[:,:2],4096)
                exportrem=W*(4096*(Kall-round_ratio(a0[:2],4096))-disp)
                assert np.all(np.abs(exportrem)<=W*4096)
                assert np.all(aa+0>=0) and np.all(aa<=2047*4096)
                phi=[np.sign(raw)*np.minimum(np.maximum(np.abs(raw)-1024*j,0),1024) for j in range(2)]
                nums=[]
                for component in [mean[:-1],centered[:-1],response[:-1],exportrem[:-1]]:
                    nums.append(sum(component[:,j,None]*phi[j] for j in range(2)))
                gap=yActual-yHeld;rest=gap*SCALE-sum(nums);nums.append(rest)
                assert np.all(np.abs(rest)<=9*SCALE//8)
                assert np.array_equal(sum(nums),gap*SCALE)
                p=prior[seed,rate,init]
                stats=output_stats(nums,yHeld,projector,p['effects']['front_rear_held']['net_exact'])
                def request_summary(sl):
                    n=len(actual[sl]);rr=actual[sl]-frozen[sl]
                    cov=np.array([ss[sl],ga[sl],sa[sl],gf[sl]])
                    return {'mean_frozen_request':[pack(F(isum(frozen[sl,j]),n)) for j in range(2)],
                            'mean_actual_request':[pack(F(isum(actual[sl,j]),n)) for j in range(2)],
                            'mean_own_response':[pack(F(isum(rr[:,j]),n)) for j in range(2)],
                            'frozen_centered_request_power':[pack(F(mulsum(frozen[sl,j],frozen[sl,j]),n)-F(isum(frozen[sl,j]),n)**2) for j in range(2)],
                            'second_gate_switches':int(np.count_nonzero(gA[sl]!=g0[sl])),
                            'response_corr_orders':[pack(F(isum(z),n)) for z in cov],
                            'mean_request_difference_rounding':[pack(F(isum((roundA-round0)[sl,j]),25*den*n)) for j in range(2)]}
                row={'seed':seed,'rate':rate,'initialization':init,'stats':stats,'requests':request_summary(slice(None)),
                     'final_hidden_components_Q22':{tag:[pack(F(int(z),W)) for z in v[-1]] for tag,v in [('mean',mean),('centered',centered),('response',response),('export',exportrem)]},'blocks':[]}
                for bb in range(8):
                    sl=slice(256*bb,256*(bb+1))
                    row['blocks'].append({'block':128+bb,'stats':output_stats([u[sl] for u in nums],yHeld[sl],projector),
                                          'requests':request_summary(sl)})
                assert sum(F(b['stats']['actual']['net']['exact']) for b in row['blocks'])/8==F(stats['actual']['net']['exact'])
                for tag in TAGS:
                    for key in ('power','error_cross','net'):
                        assert sum(F(b['stats']['components'][tag][key]['exact']) for b in row['blocks'])/8==F(stats['components'][tag][key]['exact'])
                acc0=np.broadcast_to(a0,(W,8))
                for ac,yy,yq,rqq,expected in ((aa[:-1],yActual,yt,actual,savedY[:,h]),(acc0,yHeld,y0,frozen,savedY0[:,h+1])):
                    c,r=probes(words,ac,yy,raw,yq,rqq,den,expected);pc+=c;rc+=r
                record=np.column_stack((actual,frozen,gA.sum(axis=1),g0.sum(axis=1),corrA[:,0],corr0[:,0],corrA[:,1],corr0[:,1],K[:,:2],
                                        mean[:-1],centered[:-1],response[:-1],exportrem[:-1],ss,ga,sa,gf)).astype('<i8')
                assert record.shape==(W,len(COLS));record.tofile(out/f'{stem}_{init}_front_moments.bin')
                rows.append(row)
                print(seed,rate,init,'actual',stats['actual']['net']['value'],
                      'mean',stats['orders'][0][0]['net']['value'],'mean+centered',stats['orders'][0][1]['net']['value'],
                      'with_response',stats['orders'][0][2]['net']['value'],flush=True)
    assert len(rows)==20 and pc==720 and rc==120
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    write(out/'results.json',{'completed':True,'rows':rows})
    files=list(out.glob('*_front_moments.bin'))
    write(out/'moment_hashes.json',{str(p):digest(p) for p in files})
    write(out/'verification.json',{'passed':True,'cases':20,'blocks':160,'all_actual_requests_states_outputs_and_losses_exact':True,
          'all_cumulative_components_and_Gram_crosses_exact':True,'all_selected_signal_gate_orders_and_rounding_bounds_exact':True,
          'rational_and_formal_readouts_each':pc,'independent_Fraction_low_request_vectors':rc,
          'new_window_matrix_bytes':sum(p.stat().st_size for p in files),
          'source_files_preserved':len(load(out/'source_hashes.json')),'python_sources_preserved':len(load(out/'execution_hashes.json')),
          'new_learning_submissions_paths_analog_source_fft_holdout':0})
    print('All finite forcing/response histories, Gram losses and independent probes passed',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','analyze']);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    try:(prepare if args.mode=='prepare' else analyze)(args.out)
    except Exception:
        if args.out.exists():write(args.out/'failure.json',{'mode':args.mode,'traceback':traceback.format_exc()})
        raise
