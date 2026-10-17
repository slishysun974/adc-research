"""Same-record front gate sources, accumulated migration, and held capacity.

Offline only: no request is committed and no policy is propagated.  Saved
window Gram matrices replace repeated word-level Gram products.
"""
import argparse
from fractions import Fraction as F
from math import isqrt
from pathlib import Path
import shutil
import traceback
import numpy as np

from experiments.exp_073_bank_feedback_intervention.analyze_front_history import (
    ROOT, BASE, NEW, OLD, SEEDS, W, load, write, digest, guard, ExactProjector,
    mulsum, pack, DOCS, round_ratio, pwl_scaled, source, readout,
)
from experiments.exp_073_bank_feedback_intervention.analyze_front_block_response import centered_prefix
from experiments.exp_073_bank_feedback_intervention.analyze_front_fixed_sampling import Budget, split_requests
from experiments.exp_073_bank_feedback_intervention.analyze_front_block_requests import B, D

HISTORY = ROOT/'artifacts/research/front_forcing_response_20261013_v2'
BASIS = ROOT/'artifacts/research/front_block_migration_20261014_v1'
FIRST = ROOT/'artifacts/research/front_fixed_sampling_20261014_v1'
BLOCK = ROOT/'artifacts/research/front_centered_requests_20261014_v1'
RESP = ROOT/'artifacts/research/front_centered_response_20261014_v1'
SCALE = D*500*(1 << 25)
TAGS = ['first_full', 'first_sampling', 'first_rounding',
        'second_full_ungated', 'second_full_gate_filter',
        'second_sampling_ungated', 'second_sampling_gate_filter',
        'second_rounding', 'own_response', 'export_rounding']
LIMITS = {'source_tuple_values': 4915200, 'basis_values': 9830400,
          'old24_values': 983040, 'first_pair6_values': 245760,
          'block8_values': 327680, 'response4_values': 163840,
          'window5_values': 204800, 'initial_Q22_values': 160,
          'held_output_values': 4915200, 'actual_output_values': 4915200,
          'rear_Q3_PWL': 4915200, 'fixed_front_Q3_PWL': 4915200, 'fixed_second_gate_tests': 4915200,
          'gate_product_word_inputs': 4915200,
          'profile_word_products': 442368000,
          'projected_score_word_inputs': 221184000,
          'history_Gram_scalar_products': 45383680,
          'readout_cross_word_products': 9830400,
          'info_group_word_inputs': 1228800,
          'held_loss_word_inputs': 4915200,
          'new_source_matrix_bytes': 3276800}


def scalar_pwl(raw, k, width):
    """Independent Fraction PWL, separately rounded offset and local product."""
    v = abs(int(raw)); j = min(v//(8*width), 3)
    z = round(F(8*width*sum(map(int, k[:j])), 1024))
    z += round(F((v-8*width*j)*int(k[j]), 1024))
    return z if raw >= 0 else -z


def controls():
    # Gate/selection interaction with fixed denominators, including no gates.
    for x, g in [([2, -1, 3, -4], [1, 0, 1, 0]),
                 ([1, 1, 1, 1], [0, 0, 0, 0]),
                 ([1, 1, 1, 1], [1, 1, 1, 1])]:
        a = F(sum(x), 4); ag = F(sum(z*h for z,h in zip(x,g)), 4)
        s = F(sum(x[:2]), 2); sg = F(sum(z*h for z,h in zip(x[:2],g[:2])), 2)
        assert a+(ag-a)+(s-a)+((sg-s)-(ag-a)) == sg
        p = F(sum(g),4)
        cov = ag-p*a
        assert ag == p*a+cov
    # Output-before-update: the last request has zero weight in the block mean.
    u = [F(1), F(2), F(-1), F(99)]
    states = [sum(u[:r]) for r in range(4)]
    assert sum(states)/4 == sum((3-r)*u[r]/4 for r in range(4))
    assert states == [0,1,3,2]
    # Restricted least squares and integer-mapping floors are distinct.
    assert min((F(1,5)-k)**2+(F(4,5)-k)**2 for k in [0,1]) == F(17,25)
    # A rounding error bound brackets a legal-output norm, not an exact optimum.
    assert abs(abs(F(2)+F(-1))-abs(F(2))) <= 1
    big=10**12
    hh=[[F(int(v),3) for v in row] for row in [[big,big//2],[big//2,big]]]
    assert hh[0][0]*hh[1][1]-hh[0][1]**2==F(big*big,12)
    return {'passed': True, 'exact_controls': 7, 'Python_integer_Fraction_Gram_control':True}


def freeze(out):
    assert not out.exists(), 'Refuse overwrite'
    out.mkdir(parents=True)
    files = dict(load(FIRST/'source_hashes.json'))
    for folder in (HISTORY, BASIS, FIRST, BLOCK, RESP):
        for name in ('results.json', 'verification.json', 'protocol.json'):
            p=folder/name; files[str(p)] = digest(p)
        p=folder/'new_moment_hashes.json'
        if p.exists(): files.update(load(p))
    files.update(load(FIRST/'qualification_matrix_hashes.json'))
    guard(files); write(out/'source_hashes.json', files)
    py=list((ROOT/'src/adc_research').rglob('*.py'))+list((ROOT/'experiments').rglob('*.py'))
    write(out/'execution_hashes.json', {str(p):digest(p) for p in py})
    shutil.copyfile(Path(__file__),out/'frozen_analysis.py')
    for name in DOCS:
        p=out/'documents_before'/name; p.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,p)
    write(out/'protocol.json', {
        'version':'EXP073-front-gate-migration-held-capacity-v2', 'date':'2026-10-14',
        'authority':'User explicitly continues three branches; D136..139, same original20/160.',
        'scope':'Original5 seeds, rates1 and1/4, two legal starts, [128,136), eight256-window blocks. Second low parameter belongs to FRONT bank.',
        'missing_quantity':'Fixed initial FRONT y_Q3 is not uniquely reconstructible from held integer output and q1/d1. Saved low2 basis saturates at raw magnitude2048 and does not specify high-segment local product. Therefore only the fixed full120 FRONT gate/product requires a rear and a front Q3 PWL per slot; do not regenerate moving readouts, requests, or policies.',
        'readout_method':'Reconstruct fixed raw1 from original q2/SAR/d2 and initial rear Q10; compute initial front y_Q3 and original second gate. Validate all saved basis/held integer outputs and selected fixed products. Save only10-column window sums, no full readout matrix.',
        'alternatives':['Four-word difference dominates both fixed low coordinates versus gate-filtered full background/coordinate cross reversing the first-coordinate result.',
                        'Block migration is cumulative actual requests versus independently inferred noise; fixed forcing and own response may cancel.',
                        'Held nonzero loss is all irreducible versus same-record fixed mapping and restricted legal-coefficient witnesses leaving provable space.'],
        'source_identity':'Let x=d*y_Q3, full sums F,Fg, selected S,Sg. Second unrounded request splits into -48F/(125m), -48(Fg-F)/(125m), -48(30S-F)/(125m), -48(30(Sg-S)-(Fg-F))/(125m); actual rounding completes it. Denominator remains120 or4 regardless of gate count.',
        'time_identity':'Output-before-state a_r=sum_{s<r}u_s. Block mean=sum_{s<bB}u_s+sum_r(B-1-r)u_br/B. Global mean, block-minus-global mean, and within-block centered prefix are linear maps of all source requests; export residual restores actual Q1.10.',
        'comparisons':'Both full/sampling orders in centered accumulation, with first/second interaction, original actual linear and own response; mean position and migration retain fixed-forcing/response and source cross. No unique physical shares.',
        'capacity':'Same current five-field word fixed integer mapping certificate for each seed. Fixed rear/high-front, two low-coordinate continuous least squares plus explicit9/8 output rounding bound gives restricted legal-coefficient witness bounds. No global eight-coefficient optimum or online attainability claimed.',
        'limits':LIMITS, 'independent_limits':{'formal_scalar_readouts':240,'Fraction_source_window_checks':40,'Fraction_time_Gram_checks':20,'exact_info_group_rechecks':5},
        'budget_enforcement':'Charge BEFORE operations; saved window Gram, offdiagonals once and mirrored; object integer products where needed. Bound failure stops without increasing budget.',
        'stop':'Same20/160. Reject source/domain/timing/normalization/budget/old-loss mismatch, preserve failure. No horizon, input, future source, policy, learner, FFT, or holdout.',
        'information':'Full120 costs30 times four-word observations. Fixed readout is shadow; all time means and target optimization are offline. NG38 broad input and NG39/43 extra sine conditions remain separate.'})
    write(out/'controls.json', controls())
    failed=ROOT/'artifacts/research/front_gate_migration_capacity_20261014_v1'
    if failed.exists() and failed!=out:
        prior=load(failed/'accounting_main.json')
        write(out/'retry_contract.json',{'previous_failure':'NumPy int64 Fraction Gram determinant overflow before any capacity result; convert saved Gram sums to Python ints. Objects, equations, references and limits unchanged.',
              'previous_actual':prior['used'],'retry_limits':LIMITS,
              'cumulative_limits':{k:prior['used'][k]+LIMITS[k] for k in LIMITS},
              'frozen_v1_sha256':digest(failed/'frozen_analysis.py'),'previous_failure_sha256':digest(failed/'failure.json')})


def profile(u, mode):
    """Numerator in D*500 Q22 units; u is numerator in 500 Q22 units."""
    a=np.vstack((np.zeros((1,2),dtype=np.int64),np.cumsum(u,axis=0)))[:-1]
    m=a.sum(axis=0)*(D//W)
    bm=np.repeat(a.reshape(8,B,2).sum(axis=1)[:,None,:],B,axis=1).reshape(W,2)*(D//B)
    if mode=='position':return np.broadcast_to(m,(W,2)).copy()
    if mode=='migration':return bm-m
    return centered_prefix(u)


def sqrt_out(v, upper):
    assert v>=0
    den=10**12; n=v.numerator*den*den//v.denominator; r=isqrt(n)
    if upper and F(r,den)**2 < v:r+=1
    return F(r,den)


def info_floor(words, p):
    groups={}; target=p.ti
    for j,row in enumerate(words.reshape(-1,4)):
        key=bytes(row.astype('i1')); t=target[j%len(target)]
        n,s,q=groups.get(key,(0,0,0)); groups[key]=(n+1,s+t,q+t*t)
    num=0
    for n,s,q in groups.values():
        k=min(4095,max(0,round(F(s,n*p.D))))
        num+=q-2*k*p.D*s+n*(k*p.D)**2
    return {'loss':pack(F(num,words.shape[0]*120*p.D*p.D)),
            'groups':len(groups),'samples':words.shape[0]*120,'class':'all fixed integer mappings of current digital word only'}


def capacity(mom, k0, held, p, floor):
    n=held.size; y=held.ravel(); ph=p.phase_sum(y)
    targetdot=sum(int(z)*t for z,t in zip(ph,p.ti))
    t2=F(sum(t*t for t in p.ti),len(p.ti)*p.D*p.D)
    hold=F(mulsum(y,y),n)-F(2*targetdot,n*p.D)+t2
    h=[[F(int(mom[:,0].sum()),64*n),F(int(mom[:,1].sum()),64*n)],
       [F(int(mom[:,1].sum()),64*n),F(int(mom[:,2].sum()),64*n)]]
    # The target weighted bases are obtained by the caller, not invented from h.
    b=capacity.target_cross
    det=h[0][0]*h[1][1]-h[0][1]**2;assert det>0
    c=[(-h[1][1]*b[0]+h[0][1]*b[1])/(2*det),
       (h[0][1]*b[0]-h[0][0]*b[1])/(2*det)]
    minimum=hold+sum(b[i]*c[i] for i in range(2))+sum(c[i]*h[i][j]*c[j] for i in range(2) for j in range(2))
    assert minimum>=0
    k=[min(2047,max(0,int(k0[i])+round(c[i]*1024))) for i in range(2)]
    delta=[F(k[i]-int(k0[i]),1024) for i in range(2)]
    lc=hold+sum(b[i]*delta[i] for i in range(2))+sum(delta[i]*h[i][j]*delta[j] for i in range(2) for j in range(2))
    lower=max(F(0),sqrt_out(minimum,False)-F(9,8))**2
    upper=(sqrt_out(lc,True)+F(9,8))**2
    assert all(0<=t<=4095*p.D for t in p.ti)
    radius=128*sum(abs(z) for z in delta)+F(9,8)
    assert int(held.min())-radius>=0 and int(held.max())+radius<=4095, 'Witness output range not certified'
    assert upper>=F(floor['loss']['exact'])
    return {'held_loss':pack(hold),'current_word_floor':floor['loss'],
            'continuous_two_coordinate_minimum':pack(minimum),
            'continuous_minimizer':list(map(str,c)), 'legal_low_Q10_witness':k,
            'continuous_witness_loss':pack(lc),'restricted_integer_optimum_interval':list(map(str,[max(lower,F(floor['loss']['exact'])),upper])),
            'guaranteed_available_reduction_nominal':pack(max(F(0),hold-upper)),
            'witness_output_rounding_bound':'9/8 code', 'witness_legal_output_range_certified':True,
            'exact_witness_readout_executed':False,
            'global_static_optimum_interval':list(map(str,[F(floor['loss']['exact']),min(hold,upper)])),
            'online_reachable':False}


def stats(profiles, phi, held, wm, residue, p, budget, score=True):
    n=held.size; z=[]; scored=[]
    for v in profiles:
        budget.charge('profile_word_products', n*2)
        assert sum(int(np.abs(v[:,j]).max())*1024 for j in range(2)) < 1<<63
        zz=v[:,0,None]*phi[:,:,0]+v[:,1,None]*phi[:,:,1];z.append(zz)
        budget.charge('projected_score_word_inputs',n)
        scored.append(p.projected(zz,held,SCALE))
    m=len(profiles);q=[[F(0) for _ in profiles] for _ in profiles]
    for i in range(m):
        for j in range(i+1):
            budget.charge('history_Gram_scalar_products',len(wm)*4)
            a=profiles[i].astype(object);b=profiles[j].astype(object)
            value=sum(a[:,0]*b[:,0]*wm[:,0]+(a[:,0]*b[:,1]+a[:,1]*b[:,0])*wm[:,1]+a[:,1]*b[:,1]*wm[:,2])
            q[i][j]=q[j][i]=F(int(value),n*SCALE*SCALE)
        assert q[i][i]==F(scored[i]['power']['exact'])
    bc=[F(s['error_cross']['exact']) for s in scored]
    radii=[min(F(s['shared_phase_radius']['exact']),
               (F(s['target_interval'][1])-F(s['target_interval'][0]))/2) for s in scored]
    def net(ids):return sum(bc[i] for i in ids)+sum(q[i][j] for i in ids for j in ids)
    def effect(ids,before):
        val=net(before+ids)-net(before); rad=sum(radii[i] for i in ids)
        return {**pack(val),'interval':list(map(str,[val-rad,val+rad])),
                'sign_certified':val-rad>0 or val+rad<0}
    return q,bc,radii,net,effect,scored,z


def analyze(out):
    assert not (out/'results.json').exists()
    assert digest(Path(__file__))==digest(out/'frozen_analysis.py')
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    assert load(out/'controls.json')['passed']
    budget=Budget(LIMITS);p=ExactProjector();rows=[];floors={}; probes=[]
    old={(r['seed'],r['rate'],r['initialization']):r for r in load(FIRST/'results.json')['rows']}
    times={(r['seed'],r['rate'],r['initialization']):r for r in load(BASIS/'results.json')['rows']}
    try:
        for seed in SEEDS:
            budget.charge('source_tuple_values',W*120*4)
            words=np.array(source(seed),dtype=np.int64)
            budget.charge('info_group_word_inputs',W*120)
            floors[seed]=info_floor(words,p)
            q1,q2,sar,bits=(words[:,:,j] for j in range(4));d=2*(bits&1)-1;d2=2*((bits>>1)&1)-1
            for rate,den in [('base',1),('quarter',4)]:
                stem=f'{seed}_{rate}'
                for idx,init in ((0,'actual'),(2,'prefix')):
                    name=f'{stem}_{init}';budget.charge('initial_Q22_values',8)
                    a0=np.array(np.memmap(BASE/f'{stem}_q22.bin',dtype='<i4',mode='r',shape=(W+1,4,8))[0,idx],dtype=np.int64)
                    k0=round_ratio(a0,4096)
                    budget.charge('old24_values',W*24);mom=np.fromfile(HISTORY/f'{name}_front_moments.bin',dtype='<i8').reshape(W,24)
                    budget.charge('first_pair6_values',W*6);pair=np.fromfile(FIRST/f'{name}_source_pair.bin',dtype='<i8').reshape(W,6)
                    budget.charge('block8_values',W*8);saved=np.fromfile(BLOCK/f'{name}_block_request_profiles.bin',dtype='<i8').reshape(W,8)
                    budget.charge('response4_values',W*4);rr=np.fromfile(RESP/f'{name}_block_response_profiles.bin',dtype='<i8').reshape(W,4)
                    budget.charge('window5_values',W*5);wm=np.fromfile(BASIS/f'{name}_basis_moments.bin',dtype='<i8').reshape(W,5)
                    budget.charge('basis_values',W*120*2);phi=np.fromfile(BASIS/f'{name}_basis.bin',dtype='<i2').reshape(W,120,2).astype(np.int64)
                    budget.charge('held_output_values',W*120);held=np.array(np.memmap(BASE/f'{stem}_outputs.bin',dtype='<i2',mode='r',shape=(W,4,120))[:,idx+1],dtype=np.int64)
                    budget.charge('actual_output_values',W*120);actual=np.array(np.memmap(NEW/f'{stem}_outputs.bin',dtype='<i2',mode='r',shape=(W,4,120))[:,idx],dtype=np.int64)
                    # Rear raw1 readout is intentionally the sole necessary
                    # rear PWL, charged in a separate counter in the protocol.
                    budget.charge('rear_Q3_PWL',W*120)
                    raw=1024*q2+pwl_scaled(8*sar,np.broadcast_to(k0[4:],(W,4)),32)-128*d2
                    assert np.all((raw>=-4096)&(raw<4096))
                    expected=np.stack([np.sign(raw)*np.minimum(np.maximum(abs(raw)-1024*j,0),1024) for j in range(2)],axis=2)
                    assert np.array_equal(phi,expected)
                    budget.charge('fixed_front_Q3_PWL',W*120)
                    y=pwl_scaled(raw,np.broadcast_to(k0[:4],(W,4)),128)-512*d
                    assert np.array_equal(round_ratio(16384+4096*q1+y,8),held)
                    budget.charge('fixed_second_gate_tests',W*120)
                    gate=abs(y)>=int(k0[0])  # 8*128*K1/1024 in Q3.
                    budget.charge('gate_product_word_inputs',W*120);x=d*y
                    full=x.sum(axis=1);fg=(x*gate).sum(axis=1);sel=x[:,:4].sum(axis=1);sg=(x[:,:4]*gate[:,:4]).sum(axis=1)
                    assert np.array_equal(full,pair[:,1]) and np.array_equal(sel,mom[:,7])
                    assert np.array_equal(sg,mom[:,9]) and np.array_equal(gate[:,:4].sum(axis=1),mom[:,5])
                    for ww,ss in [(0,0),(255,119),(256,3),(1023,64),(2047,0),(1536,119),(128,4),(511,60),(768,12),(1200,30),(1700,80),(2000,1)]:
                        sr=1024*int(q2[ww,ss])+scalar_pwl(8*int(sar[ww,ss]),k0[4:],32)-128*int(d2[ww,ss])
                        sy=scalar_pwl(sr,k0[:4],128)-512*int(d[ww,ss])
                        formal=readout(int(q1[ww,ss]),int(q2[ww,ss]),F(int(sar[ww,ss])),int(d[ww,ss]),int(d2[ww,ss]),tuple(F(int(k),1024) for k in k0),data_q3=True)
                        assert sy==int(y[ww,ss]) and bool(abs(sy)>=int(k0[0]))==bool(gate[ww,ss])
                        assert round(formal.output)==int(held[ww,ss]) and formal.gates[0][1]==bool(gate[ww,ss])
                        probes.append([seed,rate,init,ww,ss])
                    factor=4 if den==1 else 1
                    first=split_requests(sel,full,mom[:,2],den)
                    second=[-48*factor*full,-48*factor*(fg-full),48*factor*(full-30*sel),
                            -48*factor*(30*(sg-sel)-(fg-full)),500*mom[:,3]+1440*factor*sg]
                    assert np.array_equal(sum(second),500*mom[:,3]) and np.all(abs(second[-1])<=240)
                    coord=lambda v,j:np.column_stack((v,np.zeros(W,dtype=np.int64))) if j==0 else np.column_stack((np.zeros(W,dtype=np.int64),v))
                    streams=[coord(v,0) for v in first]+[coord(v,1) for v in second]
                    streams.append(500*(mom[:,:2]-mom[:,2:4]))
                    state=np.vstack((np.zeros((1,2),dtype=np.int64),np.cumsum(mom[:,:2],axis=0)))[:-1]
                    ep=500*(4096*(mom[:,10:12]-k0[:2])-state)
                    allstate=sum(profile(v,'position')+profile(v,'migration') for v in streams)
                    blockpos=4096*D*500*np.repeat((mom[:,10:12]-k0[:2]).reshape(8,B,2).sum(axis=1)[:,None,:],B,axis=1).reshape(W,2)//B
                    eb=np.repeat(ep.reshape(8,B,2).sum(axis=1)[:,None,:],B,axis=1).reshape(W,2)*(D//B)
                    assert np.array_equal(allstate+eb,blockpos)
                    accum=[profile(v,'centered') for v in streams]+[saved[:,4:6]*500]
                    assert np.array_equal(sum(accum),500*(saved[:,2:4]+saved[:,4:6]))
                    linear=saved[:,:2]*500
                    fullactual=4096*D*500*(mom[:,10:12]-k0[:2])
                    residue=(actual-held)*SCALE-(fullactual[:,0,None]*phi[:,:,0]+fullactual[:,1,None]*phi[:,:,1])
                    assert np.all(abs(residue)<=9*SCALE//8)
                    record=np.column_stack((full,fg,sel,sg,gate.sum(axis=1),mom[:,5],
                                            ((d*gate).sum(axis=1)),((d[:,:4]*gate[:,:4]).sum(axis=1)),mom[:,2:4]))
                    budget.charge('new_source_matrix_bytes',record.nbytes);record.astype('<i8').tofile(out/f'{name}_gate_sources.bin')
                    modes={};blocks=[]
                    for mode in ('centered','position','migration'):
                        pp=accum if mode=='centered' else [profile(v,mode) for v in streams]+[np.broadcast_to(ep.sum(axis=0)*(D//W),(W,2)).copy() if mode=='position' else eb-ep.sum(axis=0)*(D//W)]
                        if mode=='centered':base=[blockpos,linear]
                        elif mode=='position':base=[]
                        else:base=[np.broadcast_to(fullactual.sum(axis=0)//W,(W,2)).copy()]
                        # Migration's mean is rational: sum divisible by W
                        # since fullactual includes D and W divides D.
                        q,bc,rad,net,eff,scored,zz=stats(pp+base,phi,held,wm,residue,p,budget)
                        effects={}
                        fullids=[0,3,4];sampleids=[1,5,6];roundids=[2,7]
                        for ctx,extra in [('before_response',[]),('after_response',[8])]:
                            before=list(range(10,len(pp+base)))+extra
                            for key,ids,priorids in [('full_first',fullids,before),('sampling_after_full',sampleids,before+fullids),
                                                     ('sampling_first',sampleids,before),('full_after_sampling',fullids,before+sampleids),
                                                     ('rounding_after_sources',roundids,before+fullids+sampleids)]:
                                effects[ctx+'_'+key]=eff(ids,priorids)
                        # Gate's effect and ungated sampling have both orders.
                        context=list(range(10,len(pp+base)))+[0,1,2,8]
                        for key,ids,before in [('second_ungated_first',[3,5],context),('second_gate_after',[4,6],context+[3,5]),
                                                ('second_gate_first',[4,6],context),('second_ungated_after',[3,5],context+[4,6])]:effects[key]=eff(ids,before)
                        effects['own_response_after_fixed']=eff([8],list(range(8))+list(range(10,len(pp+base))))
                        effects['export_after_history']=eff([9],list(range(9))+list(range(10,len(pp+base))))
                        secondids=[3,4,5,6,7];firstids=[0,1,2]
                        effects['second_after_first']=eff(secondids,context)
                        effects['first_after_second']=eff(firstids,list(range(10,len(pp+base)))+[8]+secondids)
                        modes[mode]={'tags':TAGS+['context'+str(i) for i in range(len(base))],
                                     'gram':[[str(z) for z in row] for row in q],'error_cross':list(map(str,bc)),
                                     'effects':effects,'complete_continuous_loss_change':pack(net(list(range(len(pp+base))))),
                                     'first_second_cross':pack(2*sum(q[i][j] for i in firstids for j in secondids)),
                                     'full_sampling_cross':pack(2*sum(q[i][j] for i in fullids for j in sampleids))}
                        if mode=='position':
                            assert net(list(range(10)))==F(times[seed,rate,init]['stats']['components']['position']['net']['exact'])
                        if mode=='migration':
                            assert eff(list(range(10)),[10])['exact']==times[seed,rate,init]['stats']['effects']['migration_after_position']['exact']
                        if mode=='centered':
                            prev=old[seed,rate,init]['stats']
                            assert net(list(range(12)))==F(prev['linear_total']['net']['exact'])
                            # Crosses with the actual current readout are
                            # computed once at word level, not 12* per word.
                            budget.charge('readout_cross_word_products',held.size*2)
                            jmom=np.column_stack([np.array((phi[:,:,j].astype(object)*residue).sum(axis=1),dtype=object) for j in range(2)])
                            jc=[F(int(sum(ppi[:,0].astype(object)*jmom[:,0]+ppi[:,1].astype(object)*jmom[:,1])),held.size*SCALE*SCALE) for ppi in pp+base]
                            restored=net(list(range(12)))+F(prev['components']['current_readout']['net']['exact'])+2*sum(jc)
                            assert restored==F(prev['actual']['net']['exact'])
                            modes[mode]['current_readout_cross']=list(map(str,jc));modes[mode]['actual_integer_loss_change']=pack(restored)
                            # All160 block contrasts, using existing window
                            # moments. Their weighted means recover full Gram.
                            for bb in range(8):
                                sl=slice(bb*B,(bb+1)*B)
                                qb,bcb,rb,nb,efb,_,_=stats([v[sl] for v in pp+base],phi[sl],held[sl],wm[sl],residue[sl],p,budget)
                                ee={}
                                for ctx,extra in [('before_response',[]),('after_response',[8])]:
                                    before=[10,11]+extra
                                    for key,ids,bi in [('full_first',fullids,before),('sampling_after_full',sampleids,before+fullids),('sampling_first',sampleids,before),('full_after_sampling',fullids,before+sampleids)]:ee[ctx+'_'+key]=efb(ids,bi)
                                ee['second_gate_after']=efb([4,6],[0,1,2,8,10,11,3,5])
                                ee['second_after_first']=efb(secondids,[0,1,2,8,10,11])
                                blocks.append({'block':128+bb,'effects':ee,'gram':[[str(z) for z in row] for row in qb],'error_cross':list(map(str,bcb))})
                            for i in range(12):
                                assert bc[i]==sum(F(b['error_cross'][i]) for b in blocks)/8
                                for j in range(12):assert q[i][j]==sum(F(b['gram'][i][j]) for b in blocks)/8
                    # Reuse old basis target-error moments at c=0; no gradient
                    # recomputation or optimizer loop.
                    pm=times[seed,rate,init]['position_moments'];h=[[F(z) for z in row] for row in pm['Gram_H']]
                    mean=[F(z['exact']) for z in pm.get('mean_gap',[])] if 'mean_gap' in pm else [F(int((mom[:,10+j]-k0[j]).sum()),W*1024) for j in range(2)]
                    capacity.target_cross=[F(pm['gradient_at_mean_position'][i]['exact'])-2*sum(h[i][j]*mean[j] for j in range(2)) for i in range(2)]
                    budget.charge('held_loss_word_inputs',held.size);cap=capacity(wm,k0,held,p,floors[seed])
                    rows.append({'seed':seed,'rate':rate,'initialization':init,'modes':modes,'blocks':blocks,'capacity':cap,
                                 'gate_count_full':int(gate.sum()),'gate_count_selected':int(gate[:,:4].sum()),
                                 'gate_dither_full_sum':int((d*gate).sum()),'gate_dither_selected_sum':int((d[:,:4]*gate[:,:4]).sum())})
                    print(name,'centered sampling',modes['centered']['effects']['after_response_sampling_after_full']['value'],
                          'held',float(F(cap['held_loss']['exact'])),'available>=',cap['guaranteed_available_reduction_nominal']['value'],flush=True)
        assert len(rows)==20 and len(probes)==240
        write(out/'results.json',{'completed':True,'rows':rows,'info_floors':floors})
        write(out/'formal_probe_verification.json',{'passed':True,'count':len(probes),'probes':probes})
        write(out/'new_moment_hashes.json',{str(z):digest(z) for z in out.glob('*_gate_sources.bin')})
        guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
        write(out/'verification.json',{'passed':True,'cases':20,'blocks':160,'all_old_loss_and_window_Gram_exact':True,'new_learning_paths_source_fft_holdout':0})
    finally:
        write(out/'accounting_main.json',{'limits':LIMITS,'used':budget.used,'all_limits_met':all(budget.used[k]<=LIMITS[k] for k in LIMITS),'completed':len(rows)==20})


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['freeze','analyze']);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    try:{'freeze':freeze,'analyze':analyze}[a.mode](a.out)
    except Exception:
        if a.out.exists():write(a.out/'failure.json',{'mode':a.mode,'traceback':traceback.format_exc()})
        raise
