"""Saved full120 history: mean-export, centered change and integer remainder.

Uses the already-certified fixed-rear bases. No PWL, gates, requests,
learner, new legal position or ADC score is generated.
"""
import argparse
from fractions import Fraction as F
from pathlib import Path
import json
import shutil
import traceback
import numpy as np

ROOT=Path('D:/ADC');W=2048;N=W*120;P=30720;S=W*8192
RUN=ROOT/'artifacts/runs/EXP_075/front_sampling_v1'
BASE=ROOT/'artifacts/runs/EXP_072/finite_v1'
BASIS=ROOT/'artifacts/research/front_block_migration_20261014_v1'
POINT=ROOT/'artifacts/research/front_position_variation_20261013_v1'
OLD=ROOT/'artifacts/runs/EXP_062/background_v1'
PHASE=ROOT/'artifacts/research/normal_future_readout_20261013_v1/phase_certificate.json'
DOCS=['docs/STATUS.md','docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md',
 'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md','docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md',
 'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md','docs/reports/GU_ALGORITHM_EVALUATION_V1.md',
 'docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md','docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md',
 'docs/reports/experiments/EXP_075_FRONT_SAMPLING_INTERVENTION_V1.md',
 'experiments/exp_075_front_sampling_intervention/README.md']

def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def digest(p):
    import hashlib
    h=hashlib.sha256()
    with p.open('rb') as f:
        for z in iter(lambda:f.read(4*1024*1024),b''):h.update(z)
    return h.hexdigest()

class Budget:
    def __init__(self,limits):self.limits,self.used=limits,dict.fromkeys(limits,0)
    def charge(self,k,n=1):
        assert self.used[k]+n<=self.limits[k],(k,self.used[k],n,self.limits[k]);self.used[k]+=n
    def add(self,a,b):self.charge('fraction_add');return a+b
    def sub(self,a,b):self.charge('fraction_add');return a-b
    def mul(self,a,b):self.charge('fraction_mul');return a*b
    def div(self,a,b):self.charge('fraction_div');return a/b
    def total(self,vals):
        z=F(0)
        for v in vals:z=self.add(z,v)
        return z
    def report(self,out,name,done):
        write(out/name,{'completed':done,'used':self.used,'limits':self.limits,
                       'all_limits_met':all(self.used[k]<=v for k,v in self.limits.items())})

def pack(z):return {'exact':str(z),'value':float(z)}
def ranged(z,lo,hi):return {**pack(z),'interval':list(map(str,(lo,hi))),'sign_certified':lo>0 or hi<0}
def dot(a,b,q):
    a=np.asarray(a,dtype=np.int64).ravel();b=np.asarray(b,dtype=np.int64).ravel();assert a.shape==b.shape
    q.charge('bigint_word_products',a.size);q.charge('bigint_reduction_inputs',a.size)
    total=0
    for i in range(0,len(a),16384):
        q.charge('bigint_chunk_adds')
        total+=int((a[i:i+16384].astype(object)*b[i:i+16384].astype(object)).sum())
    return total

def controls():
    # Coefficient centering does not eliminate weighted output/error crosses.
    phi=[F(1),F(2)];dk=[F(0),F(2)];m=sum(dk)/2
    pp=[z*m for z in phi];vv=[z*(k-m) for z,k in zip(phi,dk)]
    assert sum(k-m for k in dk)==0 and sum(a*b for a,b in zip(pp,vv))/2==F(3,2)
    e=[F(-2),F(1)];r=[F(1,8),F(-1,8)]
    power=lambda a,b:sum(x*y for x,y in zip(a,b))/2
    net=lambda z:power(z,z)+2*power(e,z)
    linear=[a+b for a,b in zip(pp,vv)];actual=[a+b for a,b in zip(linear,r)]
    assert net(actual)==net(pp)+net(vv)+2*power(pp,vv)+net(r)+2*power(pp,r)+2*power(vv,r)
    assert net(linear)-net(pp)==power(vv,vv)+2*power(e,vv)+2*power(pp,vv)
    # A helpful mean position can be outweighed by changes; the reverse is possible.
    assert F(-1)+F(2)>0 and F(2)+F(-3)<0
    # Nearest-even exported mean differs from a new rounded legal state.
    assert round(F(3,2))==2 and round(F(5,2))==2
    assert F(1,2)!=round(F(1,2))
    return {'passed':True,'exact_controls':6,'new_physical_source':False}

def freeze(out):
    assert not out.exists(),'Refuse overwrite'
    for n in ('verification.json','independent_check.json','summary.json'):assert load(RUN/n)['passed']
    qual=load(RUN/'summary.json');assert qual['high_request_nonzero_total']==qual['high_export_changed_windows_total']==qual['state_clipped_components_total']==0
    files=[RUN/'results.json',RUN/'verification.json',RUN/'independent_check.json',RUN/'summary.json',
           POINT/'results.json',POINT/'verification.json',OLD/'tone.bin',PHASE]
    for seed in range(202610621,202610626):
        for rate in ('base','quarter'):
            files.extend(RUN/f'{seed}_{rate}_{s}.bin' for s in ('q22','outputs'))
            files.append(BASE/f'{seed}_{rate}_outputs.bin')
            for init in ('actual','prefix'):files.append(BASIS/f'{seed}_{rate}_{init}_basis.bin')
    manifest={str(p):digest(p) for p in files}
    expected=load(ROOT/'artifacts/research/front_fixed_alignment_20261014_v2/source_hashes.json')
    for p,z in manifest.items():
        if p in expected:assert expected[p]==z,p
    out.mkdir(parents=True);write(out/'source_hashes.json',manifest)
    sources=list((ROOT/'src/adc_research').rglob('*.py'))+list((ROOT/'experiments').rglob('*.py'))
    write(out/'execution_hashes.json',{str(p):digest(p) for p in sources})
    shutil.copyfile(Path(__file__),out/'frozen_analysis.py')
    for name in DOCS:
        p=out/'documents_before'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
    common={'basis_values':20*N*2,'Q22_low_values':20*(W+1)*2,'saved_output_values':20*N*2,
            'export_round_checks':20*W*2,'tone_values':P,'binary64_target_ops':2*P,'center_round_cells':P,
            'fingerprint_bytes':2*sum(p.stat().st_size for p in files)+2*sum(p.stat().st_size for p in sources),
            'fraction_add':200000,'fraction_mul':200000,'fraction_div':50000,'cases':20,'blocks':160}
    meta=(RUN/'results.json').stat().st_size+(POINT/'results.json').stat().st_size
    main={**common,'metadata_json_bytes':meta,'profile_products':20*N*6,'profile_additions':20*N*5,
          'coefficient_center_inputs':20*W*2,'bigint_word_products':20*N*9*2,
          'bigint_reduction_inputs':20*N*9*2,'bigint_chunk_adds':20*9*(16+8*2),
          'phase_inputs':20*N*3*2,'absolute_profile_inputs':20*N*3*2,
          'target_integer_products':20*9*P*9,'target_integer_reduction_inputs':20*9*P*9}
    independent={**common,'metadata_json_bytes':meta+12000000,
        'profile_reconstruction_word_cells':20*N,'direct_residual_inputs':20*N*4,
        'direct_residual_bigint_products':20*N*4*4,'polarization_square_inputs':20*N*6,
        'direct_tone_products':20*N*3*2,'absolute_profile_inputs':20*N*3,
        'profile_pair_add_inputs':20*N*4}
    write(out/'protocol.json',{'date':'2026-10-14','version':'EXP075-saved-position-variation-v1',
        'authority':'User continues D136..140 mainline; latest STATUS six full120 uphill cases mean-position/change question.',
        'scope':'All20 EXP075 full120 cases and160 blocks, original5 seeds/two rates/two starts/eight blocks. Original point30 decomposition reused for comparison; six uphill cases are explanatory subset only.',
        'reference':'Y0 is saved held INTEGER output; psi is old fixed-rear low2 Q3 basis/8. Actual OUTPUT-BEFORE exported K_w (nearest-even Q22/4096); delta=(K_w-K0)/1024. p=psi dot mean(delta),v=psi dot centered(delta),r=Yfull-Y0-p-v. This is the old held-integer-plus-continuous-difference family, not the true continuous-front output or a new legal rounded mean readout.',
        'identity':'Actual loss=sum b_i+sum Q_ij for p,v,r, b_i=2E[(Y0-T)s_i]. Position first=Qpp+bp; variation after position=Qvv+bv+2Qpv; integer remainder after both=Qrr+br+2Qpr+2Qvr. Keep opposite p/v order, full crosses, radius per added component. Remainder bound9/8 under already-verified no-saturation and held high/rear.',
        'minimal_missing':'New mean/centered export projections, p-v and remainder Gram/errors/target moments. All required outputs/states/bases already saved; no PWL, source word load, gates, requests, learner, legal fixed readout, optimizer, FFT or new experiment.',
        'target':'Original dyadic target used offline only. Reuse NG39 target box and NG43 shared sine/cosine bound with same phase/nu/eta and exact target-round offset; retain intervals crossing0. Does not certify future policy or unknown input.',
        'predictions':['Every20/160 decomposition recovers EXP075 integer effect exactly and coordinate means center to0.',
            'Bad position with small/nonpositive variation supports remaining mean-location limitation; helpful position overcome by changes retains time-history explanation.',
            'Full-point improvement splits into differences of same-defined position/change/remainder additions; no independent physical fractions or deleted-term causal policy.',
            'Both orders/Gram crosses/quantization remain; mean coefficient centering is not output or target orthogonality.'],
        'budget_units':'Integer profile data products/additions, counted bigint dot/reduction inputs and chunks, phase/absolute inputs, target integer products/reductions, explicit binary Fraction add/sub/mul/div wrappers. Fraction construction/parsing, unary/compare, denominator and fixed-scale/index arithmetic, geometric kernel and display counters excluded or included in their declared word/cell kernels. Independent direct residual squares/polarization/time-order tone contractions use separate word/product units. Fingerprint full-file bytes separate; scientific memmap reads only low2 state/output slots. Offline audit units, not hardware cost.',
        'main_limits':main,'independent_limits':independent,
        'validation':'Six rational controls; main Gram and stored total/block exact recovery. Independent scalar quotient/remainder export, absolute-coefficient reconstruction, direct bigint residual squared scores and polarization Gram, time-order sine/cosine contractions. Sources/control/count failures stop, no budget reset or performance repair.',
        'stop':'All20/160 or preserve failure. No next legal fixed positions, policy, source/model/horizon, small-item precision chase, algorithm/hardware or future6007/8009.'})
    write(out/'controls.json',controls());print('Frozen full120 saved history mean/change; no new readout',flush=True)

def guard(out,q):
    assert digest(Path(__file__))==digest(out/'frozen_analysis.py')
    for n in ('source_hashes.json','execution_hashes.json'):
        for p,z in load(out/n).items():
            q.charge('fingerprint_bytes',Path(p).stat().st_size);assert digest(Path(p))==z,p

class Target:
    def __init__(self,q):
        q.charge('tone_values',P);tone=np.fromfile(OLD/'tone.bin',dtype='<f8')
        q.charge('binary64_target_ops',2*P);targets=2048*(1+tone)
        tr=[float(z).as_integer_ratio() for z in targets];xr=[float(z).as_integer_ratio() for z in tone]
        self.D=max(b for a,b in tr);self.XD=max(b for a,b in xr)
        self.ti=[a*(self.D//b) for a,b in tr];self.xi=[a*(self.XD//b) for a,b in xr]
        self.ci=[self.xi[(i+3*P//4)%P] for i in range(P)]
        q.charge('center_round_cells',P)
        cr=max(abs(t*self.XD-2048*self.D*(self.XD+x)) for t,x in zip(self.ti,self.xi))
        cert=load(PHASE);assert cert['all30720_nominal_source_and_target_points_included']
        self.rho=F(cert['phase_radius_dyadic']);self.rad=F(cert['target_radius'])
        self.noise=q.add(q.add(F(cert['source_deviation_allowance']),q.mul(F(cert['tone_grid_error_upper']),q.add(F(1),self.rho))),F(cr,self.D*self.XD*2048))
        self.rho2=q.div(q.mul(self.rho,self.rho),F(2))

    def projected(self,num,held,power,q):
        n=num.size;q.charge('phase_inputs',n);q.charge('absolute_profile_inputs',n)
        assert int(np.max(abs(num),initial=0))*(n//P)<1<<63
        ph=num.reshape(-1,P).sum(axis=0,dtype=np.int64)
        vals=[]
        for table,den in ((self.ti,self.D),(self.xi,self.XD),(self.ci,self.XD)):
            q.charge('target_integer_products',P);q.charge('target_integer_reduction_inputs',P)
            vals.append(F(sum(int(a)*b for a,b in zip(ph,table)),n*S*den))
        ma=F(int(np.abs(num).astype(object).sum()),n*S)
        b=q.sub(F(2*dot(num,held,q),n*S),q.mul(F(2),vals[0]))
        center=q.add(power,b)
        box=q.mul(q.mul(F(2),self.rad),ma)
        sine=q.mul(F(4096),q.add(q.add(q.mul(self.rho,abs(vals[2])),q.mul(self.rho2,abs(vals[1]))),q.mul(self.noise,ma)))
        radius=min(box,sine)
        return {'power':pack(power),'error_cross':pack(b),'net':ranged(center,q.sub(center,radius),q.add(center,radius)),
                'radius':str(radius),'box_radius':str(box),'shared_phase_radius':str(sine),
                'tone_projection':list(map(str,vals[1:])), 'mean_abs':str(ma)}

def input_metadata(q,out=None):
    files=[RUN/'results.json',POINT/'results.json']+([out/'results.json'] if out else [])
    vals=[]
    for p in files:q.charge('metadata_json_bytes',p.stat().st_size);vals.append(load(p)['rows'])
    return vals

def old_effects(stats,q):
    p=stats['mean_position'];v=stats['centered_variation'];cross=F(stats['position_variation_cross']['exact'])
    pc=F(p['net']['exact']);vc=F(stats['variation_added_after_position']['exact'])
    pv=ranged(pc,*map(F,p['intersection_interval']))
    vv=ranged(vc,q.add(F(v['intersection_interval'][0]),cross),q.add(F(v['intersection_interval'][1]),cross))
    actual=stats['actual'];linear=stats['linear_total'];rc=q.sub(F(actual['net']['exact']),F(linear['net']['exact']))
    rr=ranged(rc,q.sub(F(actual['intersection_interval'][0]),F(linear['intersection_interval'][1])),
                    q.sub(F(actual['intersection_interval'][1]),F(linear['intersection_interval'][0])))
    return {'position':pv,'variation_after_position':vv,'integer_after_linear':rr}

def inspect(nums,held,target,legacy,pointstats,q):
    n=held.size;gram=[[F(0)]*3 for _ in range(3)]
    for i in range(3):
        for j in range(i+1):gram[i][j]=gram[j][i]=F(dot(nums[i],nums[j],q),n*S*S)
    components=[target.projected(nums[i],held,gram[i][i],q) for i in range(3)]
    b=[F(z['error_cross']['exact']) for z in components];powers=[gram[i][i] for i in range(3)]
    def effect(i,previous):
        center=q.add(q.add(powers[i],b[i]),q.mul(F(2),q.total(gram[i][j] for j in previous)))
        r=F(components[i]['radius']);return ranged(center,q.sub(center,r),q.add(center,r))
    effects={'position':effect(0,[]),'variation_after_position':effect(1,[0]),'integer_after_linear':effect(2,[0,1]),
             'variation_first':effect(1,[]),'position_after_variation':effect(0,[1])}
    total=q.total(F(effects[k]['exact']) for k in ('position','variation_after_position','integer_after_linear'))
    assert total==F(legacy['pairs']['full_minus_held']['exact'])
    gramtotal=q.add(q.total(b),q.total(z for row in gram for z in row));assert gramtotal==total
    oe=old_effects(pointstats,q);difference={}
    for k in oe:
        a,e=effects[k],oe[k];z=q.sub(F(a['exact']),F(e['exact']))
        difference[k]=ranged(z,q.sub(F(a['interval'][0]),F(e['interval'][1])),q.sub(F(a['interval'][1]),F(e['interval'][0])))
    assert q.total(F(z['exact']) for z in difference.values())==F(legacy['pairs']['full_minus_point']['exact'])
    return {'components':dict(zip(('position','variation','integer_remainder'),components)),
            'gram':[[str(z) for z in row] for row in gram], 'error_cross':list(map(str,b)),
            'effects':effects,'point_effects':oe,'full_minus_point_components':difference,
            'actual':legacy['pairs']['full_minus_held'],'full_minus_point':legacy['pairs']['full_minus_point'],
            'actual_minus_position':pack(q.sub(total,F(effects['position']['exact'])))}

def arrays(row,q,independent=False):
    seed,rate,init=row['seed'],row['rate'],row['initialization'];h=0 if init=='actual' else 1
    q.charge('Q22_low_values',(W+1)*2)
    aa=np.array(np.memmap(RUN/f'{seed}_{rate}_q22.bin',dtype='<i4',mode='r',shape=(W+1,2,8))[:,h,:2],dtype=np.int64)
    q.charge('export_round_checks',W*2)
    if independent:
        kk=np.array([[a//4096+int(a%4096>2048 or (a%4096==2048 and (a//4096)%2!=0)) for a in map(int,line)] for line in aa[:-1]],dtype=np.int64)
    else:
        quotient=aa[:-1]//4096;rem=aa[:-1]-4096*quotient
        kk=quotient+((rem>2048)|((rem==2048)&(quotient%2!=0)))
    k0=[round(F(int(a),4096)) for a in row['initial_Q22'][:2]]
    assert np.array_equal(aa[0],row['initial_Q22'][:2]) and np.array_equal(kk[0],k0)
    q.charge('basis_values',N*2);phi=np.fromfile(BASIS/f'{seed}_{rate}_{init}_basis.bin',dtype='<i2').reshape(W,120,2).astype(np.int64)
    q.charge('saved_output_values',2*N)
    y=np.array(np.memmap(RUN/f'{seed}_{rate}_outputs.bin',dtype='<i2',mode='r',shape=(W,2,120))[:,h],dtype=np.int64)
    held=np.array(np.memmap(BASE/f'{seed}_{rate}_outputs.bin',dtype='<i2',mode='r',shape=(W,4,120))[:,2*h+1],dtype=np.int64)
    if not independent:
        delta=kk-k0;q.charge('coefficient_center_inputs',W*2)
        mean=delta.sum(axis=0,dtype=np.int64);center=W*delta-mean
        assert not center.sum(axis=0).any()
        q.charge('profile_products',N*6);q.charge('profile_additions',N*5)
        sn=W*(delta[:,0,None]*phi[:,:,0]+delta[:,1,None]*phi[:,:,1])
        pn=mean[0]*phi[:,:,0]+mean[1]*phi[:,:,1];vn=sn-pn
        rn=S*(y-held)-sn
    else:
        q.charge('profile_reconstruction_word_cells',N)
        sums=[sum(map(int,kk[:,j])) for j in range(2)]
        constant=k0[0]*phi[:,:,0]+k0[1]*phi[:,:,1]
        sn=W*(kk[:,0,None]*phi[:,:,0]+kk[:,1,None]*phi[:,:,1]-constant)
        pn=sums[0]*phi[:,:,0]+sums[1]*phi[:,:,1]-W*constant
        vn=sn-pn;rn=S*(y-held)-sn
        mean=[sums[j]-W*k0[j] for j in range(2)]
    assert np.all(abs(rn)<=9*S//8) and np.array_equal(pn+vn+rn,S*(y-held))
    return [pn,vn,rn],held,mean

def analyze(out):
    assert not (out/'results.json').exists();q=Budget(load(out/'protocol.json')['main_limits']);done=[]
    try:
        guard(out,q);assert load(out/'controls.json')['passed'];new,point=input_metadata(q)
        old={(r['seed'],r['rate'],r['initialization']):r for r in point};target=Target(q)
        for row in new:
            q.charge('cases');key=(row['seed'],row['rate'],row['initialization'])
            nums,held,mean=arrays(row,q)
            stat=inspect(nums,held,target,row['total'],old[key]['stats'],q)
            blocks=[]
            for i in range(8):
                q.charge('blocks');sl=slice(i*256,(i+1)*256)
                blocks.append({'block':128+i,'stats':inspect([z[sl] for z in nums],held[sl],target,row['blocks'][i],old[key]['blocks'][i]['stats'],q)})
            for k in stat['effects']:assert F(stat['effects'][k]['exact'])==q.div(q.total(F(b['stats']['effects'][k]['exact']) for b in blocks),F(8))
            for i in range(3):
                for j in range(3):assert F(stat['gram'][i][j])==q.div(q.total(F(b['stats']['gram'][i][j]) for b in blocks),F(8))
            done.append({'seed':key[0],'rate':key[1],'initialization':key[2],
                         'mean_export_gap':list(map(str,(F(int(z),W*1024) for z in mean))), 'stats':stat,'blocks':blocks})
            print(*key,'position',stat['effects']['position']['value'],'variation',stat['effects']['variation_after_position']['value'],
                  'round',stat['effects']['integer_after_linear']['value'],'actual',stat['actual']['value'],flush=True)
        guard(out,q);write(out/'results.json',{'completed':True,'rows':done})
        write(out/'verification.json',{'passed':True,'cases':20,'blocks':160,'all_Gram_and_integer_and_treatment_effects_exact':True,
            'new_PWL_gates_requests_source_updates_readouts_scores_fft':0})
    finally:q.report(out,'accounting_main.json',len(done)==20)

def direct_interval(num,center,target,q):
    n=num.size;q.charge('direct_tone_products',n*2);q.charge('absolute_profile_inputs',n)
    x=np.tile(np.array(target.xi,dtype=object),n//P);c=np.tile(np.array(target.ci,dtype=object),n//P)
    a=np.asarray(num,dtype=object).ravel()
    v=F(int(np.dot(a,x)),n*S*target.XD);cc=F(int(np.dot(a,c)),n*S*target.XD)
    ma=F(int(abs(a).sum()),n*S)
    box=q.mul(q.mul(F(2),target.rad),ma)
    shared=q.mul(F(4096),q.add(q.add(q.mul(target.rho,abs(cc)),q.mul(target.rho2,abs(v))),q.mul(target.noise,ma)))
    return min(box,shared),[str(v),str(cc)]

def check(out):
    assert not (out/'independent_check.json').exists();q=Budget(load(out/'protocol.json')['independent_limits']);count=0
    try:
        guard(out,q);new,point,main=input_metadata(q,out);target=Target(q)
        mapping={(r['seed'],r['rate'],r['initialization']):r for r in main}
        for row in new:
            q.charge('cases');key=(row['seed'],row['rate'],row['initialization']);result=mapping[key]
            nums,held,mean=arrays(row,q,True);assert result['mean_export_gap']==[str(F(z,W*1024)) for z in mean]
            allgrams=[];allb=[];alleffects=[]
            for i,block in enumerate(result['blocks']):
                q.charge('blocks');sl=slice(i*256,(i+1)*256)
                ns=[z[sl].ravel().astype(object) for z in nums];yy=held[sl].ravel().astype(object)
                gram=[[F(0)]*3 for _ in range(3)];powers=[]
                for a in ns:
                    q.charge('polarization_square_inputs',P);powers.append(F(int(np.dot(a,a)),P*S*S))
                for j in range(3):gram[j][j]=powers[j]
                for j in range(3):
                    for k in range(j):
                        q.charge('profile_pair_add_inputs',P);q.charge('polarization_square_inputs',P)
                        z=ns[j]+ns[k];power=F(int(np.dot(z,z)),P*S*S)
                        gram[j][k]=gram[k][j]=q.div(q.sub(q.sub(power,powers[j]),powers[k]),F(2))
                assert [[str(z) for z in rr] for rr in gram]==block['stats']['gram']
                losses=[];ti=np.array(target.ti,dtype=object);base=F(row['blocks'][i]['losses']['held']['exact'])
                q.charge('profile_pair_add_inputs',P)
                for a in ns+[ns[0]+ns[1]]:
                    q.charge('direct_residual_inputs',P);q.charge('direct_residual_bigint_products',4*P)
                    residual=(S*yy+a)*target.D-S*ti
                    losses.append(q.sub(F(int(np.dot(residual,residual)),P*S*S*target.D*target.D),base))
                b=[q.sub(losses[j],powers[j]) for j in range(3)]
                assert list(map(str,b))==block['stats']['error_cross']
                es={'position':losses[0],'variation_first':losses[1],
                    'variation_after_position':q.sub(losses[3],losses[0]),
                    'position_after_variation':q.sub(losses[3],losses[1]),
                    'integer_after_linear':q.sub(F(row['blocks'][i]['pairs']['full_minus_held']['exact']),losses[3])}
                for j,a in enumerate(ns):
                    radius,proj=direct_interval(a,losses[j],target,q)
                    comp=block['stats']['components'][('position','variation','integer_remainder')[j]]
                    assert comp['radius']==str(radius) and comp['tone_projection']==proj
                    names=(('position','position_after_variation'),('variation_after_position','variation_first'),('integer_after_linear',))[j]
                    for name in names:
                        expected=ranged(es[name],q.sub(es[name],radius),q.add(es[name],radius))
                        assert expected==block['stats']['effects'][name]
                allgrams.append(gram);allb.append(b);alleffects.append(es);count+=1
            for j in range(3):
                assert str(q.div(q.total(b[j] for b in allb),F(8)))==result['stats']['error_cross'][j]
                for k in range(3):assert str(q.div(q.total(g[j][k] for g in allgrams),F(8)))==result['stats']['gram'][j][k]
            for name in alleffects[0]:assert str(q.div(q.total(e[name] for e in alleffects),F(8)))==result['stats']['effects'][name]['exact']
        guard(out,q);write(out/'independent_check.json',{'passed':True,'cases':20,'blocks':count,
            'independent_export_direct_residual_polarization_and_target_projections_exact':True,
            'whole_record_centers_by_block_average':True,'whole_record_radii': 'Main whole-record direct projection; independent all block radii verified, not a second whole-record contraction.',
            'new_readouts_learning_scores_fft':0})
        summary={}
        for name in ('position','variation_after_position','integer_after_linear','position_after_variation','variation_first'):
            vals=[r['stats']['effects'][name] for r in main]
            summary[name]={'positive':sum(F(z['exact'])>0 for z in vals),'negative':sum(F(z['exact'])<0 for z in vals),
                           'certified':sum(z['sign_certified'] for z in vals)}
        bad=[r for r in main if F(r['stats']['actual']['exact'])>0]
        write(out/'summary.json',{'passed':True,'effects':summary,'six_uphill_cases':[
            {'seed':r['seed'],'rate':r['rate'],'initialization':r['initialization'],'effects':r['stats']['effects'],
             'actual':r['stats']['actual'],'gram':r['stats']['gram']} for r in bad],
            'bad_count':len(bad),'variation_smaller_than_point_count':sum(F(r['stats']['full_minus_point_components']['variation_after_position']['exact'])<0 for r in main),
            'new_PWL_gates_requests_updates_source_legal_positions_fft':0})
        print(json.dumps({'passed':True,'effects':summary,'bad_count':len(bad),
            'variation_smaller_than_point':load(out/'summary.json')['variation_smaller_than_point_count']}),flush=True)
    finally:q.report(out,'accounting_independent.json',count==160)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['freeze','analyze','check']);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    try:globals()[a.mode](a.out)
    except Exception:
        if a.out.exists():write(a.out/f'failure_{a.mode}.json',{'traceback':traceback.format_exc()})
        raise
