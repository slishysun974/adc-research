"""Read-only first-coordinate response and common-phase target projections.

All forty EXP074 gate pairs and their eight original blocks are retained.
No learner is propagated and no target enters an update or selection.
"""
import argparse
from dataclasses import replace
from fractions import Fraction as F
from pathlib import Path
import shutil
import traceback
import numpy as np

from experiments.exp_074_learning_signal_gate_intervention.analyze_gates import (
    ROOT, OLD, CHANNEL, PHASE, SEEDS, N, W, DOCS, source, original,
    load, write, digest, guard, Scorer, isum, mulsum, pack,
)
from experiments.exp_073_bank_feedback_intervention.run import evaluate, round_ratio, fixed_setup
from experiments.exp_062_same_input_background.verify import pwl_scaled
from adc_research.theory.static_fixed_contract import readout, export
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.observation import DigitalCalibrationSample

PRIOR = ROOT / 'artifacts/research/second_gate_history_20261013_v1'
SHIFT = 3 * N // 4


def controls():
    # The first response reduces displacement power, but may worsen target loss.
    s1, s2 = F(-1), F(2)
    added_power = s1*s1 + 2*s1*s2
    assert added_power == -3
    assert added_power + 2*F(0)*s1 == -3
    assert added_power + 2*F(-2)*s1 == 1
    assert (s1+s2)**2 - s2**2 == added_power
    # Same-sign digital bases have nonnegative Gram weight; dither moments
    # need not have that sign. This is algebra, not a physical source example.
    p1, p2, d = [F(1), F(1)], [F(0), F(1)], [1, -1]
    assert sum(a*b for a,b in zip(p1,p2)) == 1
    assert sum(a*b for a,b in zip(d,p2)) == -1
    assert (127*SHIFT) % N == N//4
    # Exact common-phase identity and its elementary radius bound.
    t, rho = F(1,10000), F(1,4000)
    sn, cs = 2*t/(1+t*t), (1-t*t)/(1+t*t)
    assert abs(sn) <= rho and 1-cs <= rho*rho/2
    for v,c in ((F(3),F(-2)), (F(-1),F(4)), (F(0),F(0))):
        change = (cs-1)*v + sn*c
        assert abs(change) <= rho*abs(c) + rho*rho*abs(v)/2
    assert F(96,25)*(F(1,8)*8) == F(96,25)
    return {'passed': True, 'exact_controls': 9,
            'physical_counterexample_or_new_source': False}


def prepare(out):
    assert not out.exists(), 'Refuse overwrite'
    assert load(PRIOR/'verification.json')['passed']
    out.mkdir(parents=True)
    files = dict(load(PRIOR/'source_hashes.json'))
    for p in [PRIOR/'results.json', PRIOR/'verification.json', PRIOR/'protocol.json']:
        files[str(p)] = digest(p)
    for p in PRIOR.glob('*_requests.bin'):
        files[str(p)] = digest(p)
    guard(files)
    write(out/'source_hashes.json', files)
    sources = list((ROOT/'src/adc_research').rglob('*.py')) + list((ROOT/'experiments').rglob('*.py'))
    write(out/'execution_hashes.json', {str(p):digest(p) for p in sources})
    shutil.copyfile(Path(__file__), out/'frozen_analysis.py')
    write(out/'controls.json', controls())
    write(out/'protocol.json', {
        'version':'EXP074-first-response-common-phase-v1', 'date':'2026-10-13',
        'authority':'D136..139, user continue research, current STATUS steps1/2',
        'object':'Original all5 seeds, two rates, actual/prefix, two signal sources:40 gate pairs,320 blocks128..135. No new paths.',
        'alternatives':[
            'First-history response cancels second-coordinate displacement power, versus merely having opposite signs without sufficient magnitude.',
            'Reduced displacement power also reduces target loss, versus first response opposing a useful second correction.',
            'Prior small effects remain ambiguous under target boxes, versus common fixed phase allowing a smaller projection enclosure.'],
        'derivation':'H1 is signed-dither moments of the two exported gaps plus Q3/request remainder, not the output Gram/target moment. First addition to displacement is Q11+2Q12; to loss add2E[e*s1]. Common-phase uncertainty uses sin/cos projection and the original NG39 prefix phase and certified source table.',
        'predictions':[
            'Exact response reconstruction, Q22 history, prior40 losses and all320 block sums must hold.',
            'Negative coordinate cross alone does not imply power reduction; compare Q11+2Q12 on every block.',
            'Power-reduction and loss-reduction signs may differ; no score threshold or selected block.',
            'Common-phase and old target-box ranges both contain allowed target losses; use their intersection, retain any unclassified result.'],
        'budget':{'normal_baseline_vector_readouts':9830400,'held_baseline_vector_readouts':4915200,
                  'treated_front_Q3_pwl_evaluations':9830400,'paired_output_words_scored':9830400,
                  'selected_request_window_pairs':81920,'selected_learning_word_pairs':327680,
                  'rational_and_formal_readouts_each':2160,'rational_first_response_checks':120,
                  'new_source_learning_submissions_paths_fft_holdout':0},
        'stopping':'Fixed40/320 only. Arithmetic, source or domain mismatch rejects and archives. No event intervention, horizon, model, algorithm or hardware change.',
        'limits':'Continuous coordinates are references, not separately learned policies. Common phase is extra NG39 input knowledge; ranges evaluate saved outputs, not future policy ranking. No independent-sample probabilities or unique causal percentages.'})
    for name in DOCS + ['docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md']:
        dst=out/'documents_before'/name; dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,dst)
    print('Frozen all40 pairs/320 blocks and finite readout/probe limits', flush=True)


class Projector(Scorer):
    def __init__(self):
        super().__init__()
        tone=np.fromfile(OLD/'tone.bin',dtype='<f8')
        rr=[float(v).as_integer_ratio() for v in tone]
        self.XD=max(b for _,b in rr)
        self.xi=[a*(self.XD//b) for a,b in rr]
        self.ci=[self.xi[(j+SHIFT)%N] for j in range(N)]
        p=load(PHASE)
        assert p['all30720_nominal_source_and_target_points_included']
        self.rho=F(p['phase_radius_dyadic'])
        self.nu=F(p['tone_grid_error_upper'])
        self.eta=F(p['source_deviation_allowance'])
        self.center_round=max(abs(F(self.ti[i],self.D)-2048*(1+F(self.xi[i],self.XD))) for i in range(N))

    def projected(self,u,y,scale=1):
        r=self.score(u,y,scale)
        phase_sum=np.asarray(u,dtype=np.int64).reshape(-1,N).sum(axis=0,dtype=np.int64)
        v=F(sum(int(z)*self.xi[i] for i,z in enumerate(phase_sum)),u.size*scale*self.XD)
        c=F(sum(int(z)*self.ci[i] for i,z in enumerate(phase_sum)),u.size*scale*self.XD)
        ma=F(isum(np.abs(u)),u.size*scale)
        noise=self.eta+self.nu*(1+self.rho)+self.center_round/2048
        rad=4096*(self.rho*abs(c)+self.rho**2*abs(v)/2+noise*ma)
        center=F(r['net']['exact']); box=[F(z) for z in r['target_interval']]
        new=[center-rad,center+rad]
        both=[max(box[0],new[0]),min(box[1],new[1])]
        assert both[0]<=both[1]
        r.update({'sine_tone_projection':pack(v),'cosine_tone_projection':pack(c),
                  'shared_phase_radius':pack(rad),'shared_phase_interval':[str(z) for z in new],
                  'intersection_interval':[str(z) for z in both],
                  'intersection_sign_certified':both[0]>0 or both[1]<0})
        return r


def bases(raw):
    mag=np.abs(raw);sgn=np.sign(raw)
    return sgn*np.minimum(mag,1024),sgn*np.minimum(np.maximum(mag-1024,0),1024)


def inspect(s1,s2,d,y,projector):
    q1=projector.projected(s1,y,8192);q2=projector.projected(s2,y,8192)
    cross=F(2*mulsum(s1,s2),s1.size*8192**2)
    dp=F(q1['power']['exact'])+cross
    add=F(q1['net']['exact'])+cross
    ri=[F(z)+cross for z in q1['intersection_interval']]
    total=projector.projected(s1+s2,y,8192)
    integer=projector.projected(d,y)
    assert F(total['net']['exact'])==F(q1['net']['exact'])+F(q2['net']['exact'])+cross
    return {'first':q1,'second':q2,'cross':pack(cross),'first_added_displacement_power':pack(dp),
            'first_added_loss':pack(add),'first_added_loss_interval':[str(z) for z in ri],
            'first_added_loss_sign_certified':ri[0]>0 or ri[1]<0,
            'continuous':total,'integer':integer,
            'integer_remainder_loss':pack(F(integer['net']['exact'])-F(total['net']['exact']))}


def probes(words,bst,tst,rear,held,aa,yr,yt,sig_b,sig_t,response,den):
    _,cfg=fixed_setup(load(OLD/'source_protocol.json'));count=checks=0
    for w in (0,1024,2047):
        values={}
        for tag,rr in [('normal',rear[w])]+([('held',held[w])] if not aa else []):
            for branch,ff in enumerate((bst[w],tst[w])):
                old=tuple(map(int,np.concatenate((ff,rr))));kk=export(old)
                cc=replace(cfg.cascade,stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=kk[:4]),
                           stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=kk[4:]))
                yy=[]
                for j in (0,1,2,3,59,119):
                    q1,q2,be,bits=map(int,words[w,j]);d1=2*(bits&1)-1;d2=2*((bits>>1)&1)-1
                    rd=readout(q1,q2,F(be),d1,d2,tuple(F(k,1024) for k in kk),data_q3=True)
                    formal=correct_two_stage_fixed_observed(DigitalCalibrationSample(q1,q2,be,d1,d2),cc)
                    assert formal.unclipped_output_scaled==8*rd.output
                    assert formal.unclipped_output_scaled-16384-4096*q1==8*rd.y1
                    if tag=='normal':
                        assert round_ratio(np.array([int(8*rd.output)]),8)[0]==(yr if branch==0 else yt)[w,j]
                    if tag==('normal' if aa else 'held'):
                        assert int(8*rd.y1)==(sig_b if branch==0 else sig_t)[w,j]
                    yy.append(int(8*rd.y1));count+=1
                values[tag,branch]=yy[:4]
        tag='normal' if aa else 'held'
        rq=[]
        for branch in (0,1):
            m=sum((2*(int(words[w,j,3])&1)-1)*values[tag,branch][j] for j in range(4))
            val=-F(96,25*den)*m
            # Python Fraction nearest-even is independent of vector round_ratio.
            rq.append(round(val))
        assert rq[1]-rq[0]==int(response[w,0]);checks+=1
    return count,checks


def analyze(out):
    assert not (out/'results.json').exists(), 'Refuse complete overwrite'
    assert digest(Path(__file__))==digest(out/'frozen_analysis.py')
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'));controls()
    projector=Projector();prior={(r['seed'],r['rate'],r['initialization'],r['context']):r for r in load(PRIOR/'results.json')['rows']}
    rows=[];scalar=checks=0
    for seed in SEEDS:
        words=source(seed)
        for rate,den in (('base',1),('quarter',4)):
            stem=f'{seed}_{rate}';a,b,ay,by,_,_=original(seed,rate)
            fs=np.fromfile(CHANNEL/f'{stem}_front_q22.bin',dtype='<i4').reshape(W+1,4,4).astype(np.int64)
            fy=np.fromfile(CHANNEL/f'{stem}_outputs.bin',dtype='<i2').reshape(W,4,120)
            for h,init in ((0,'actual'),(2,'prefix')):
                for aa,context in ((1,'gate_signal_moving'),(0,'gate_signal_held')):
                    if aa:bst,tst,yr,yt=fs[:,h],a[:,h,:4],fy[:,h],ay[:,h]
                    else:bst,tst,yr,yt=b[:,h,:4],fs[:,h+1],by[:,h//2],fy[:,h+1]
                    rear=a[:-1,h,4:];held=np.broadcast_to(a[0,h,4:],(W,4))
                    normal=evaluate(words,np.column_stack((bst[:-1],rear)))
                    assert np.array_equal(normal[0],yr)
                    learn=normal if aa else evaluate(words,np.column_stack((bst[:-1],held)))
                    K=round_ratio(tst[:-1],4096)-round_ratio(bst[:-1],4096)
                    assert not K[:,2:].any()
                    phi1,phi2=bases(normal[4]);s1=phi1*K[:,0,None];s2=phi2*K[:,1,None]
                    sig_b=learn[5]
                    sig_t=pwl_scaled(learn[4],round_ratio(tst[:-1],4096),128)-512*(2*(words[:,:,3].astype(np.int64)&1)-1)
                    lp1,lp2=bases(learn[4][:,:4]);dd=2*(words[:,:4,3].astype(np.int64)&1)-1
                    c1=np.sum(dd*lp1,axis=1)*K[:,0];c2=np.sum(dd*lp2,axis=1)*K[:,1]
                    rem=(sig_t[:,:4]-sig_b[:,:4])*1024-lp1*K[:,0,None]-lp2*K[:,1,None]
                    assert np.all(np.abs(rem)<=1024)
                    rq=round_ratio(np.sum(dd*sig_t[:,:4],axis=1)*(-96),25*den)-round_ratio(np.sum(dd*sig_b[:,:4],axis=1)*(-96),25*den)
                    saved=np.fromfile(PRIOR/f'{stem}_{init}_{aa}_requests.bin',dtype='<i4').reshape(W,5,4)
                    response=saved[:,4];assert np.array_equal(rq,response[:,0])
                    gap=tst-bst;assert np.array_equal(gap[1:,0],np.cumsum(response[:,0]))
                    residual=rq*(25*den*1024)+96*(c1+c2)
                    q3corr=96*np.sum(dd*rem,axis=1)
                    request_round=residual+q3corr
                    assert np.all(np.abs(request_round)<=F(24,25)*25*den*1024)
                    d=yt.astype(np.int64)-yr.astype(np.int64)
                    assert np.all(np.abs(d*8192-s1-s2)<=9216)
                    p=prior[seed,rate,init,context];stats=inspect(s1,s2,d,yr,projector)
                    assert F(stats['integer']['net']['exact'])==F(p['gate_loss']['net']['exact'])
                    for oldkey,newkey in (('first_coordinate_reference','first'),('second_coordinate_reference','second'),('continuous_gap_reference','continuous')):
                        assert F(p[oldkey]['net']['exact'])==F(stats[newkey]['net']['exact'])
                    x,z=probes(words,bst,tst,rear,held,aa,yr,yt,sig_b,sig_t,response,den);scalar+=x;checks+=z
                    row={'seed':seed,'rate':rate,'initialization':init,'context':context,'stats':stats,'blocks':[]}
                    for bb in range(8):
                        sl=slice(bb*256,(bb+1)*256);bs=inspect(s1[sl],s2[sl],d[sl],yr[sl],projector)
                        assert F(bs['integer']['net']['exact'])==F(p['blocks'][bb]['loss']['net']['exact'])
                        q=25*den*1024
                        terms=[F(-96*isum(c1[sl]),q),F(-96*isum(c2[sl]),q),F(isum(residual[sl]),q)]
                        assert sum(terms)==isum(response[sl,0])
                        row['blocks'].append({'block':128+bb,'stats':bs,'first_response_Q22_sum':isum(response[sl,0]),
                            'first_response_terms_Q22':[pack(v) for v in terms],
                            'Q3_readout_response_term_Q22':pack(F(-isum(q3corr[sl]),q)),
                            'request_rounding_response_term_Q22':pack(F(isum(request_round[sl]),q))})
                    for key in ('first','second','continuous','integer'):
                        assert sum(F(z['stats'][key]['net']['exact']) for z in row['blocks'])/8==F(stats[key]['net']['exact'])
                    rows.append(row)
                    print(seed,rate,init,aa,'power add',stats['first_added_displacement_power']['value'],
                          'loss add',stats['first_added_loss']['value'],'shared certified',stats['integer']['intersection_sign_certified'],flush=True)
    assert len(rows)==40 and scalar==2160 and checks==120
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    write(out/'results.json',{'completed':True,'rows':rows})
    write(out/'verification.json',{'passed':True,'pairs':40,'blocks':320,'all_response_history_losses_and_block_sums_exact':True,
        'rational_and_formal_readouts_each':scalar,'rational_first_response_checks':checks,
        'normal_vector_readouts':9830400,'held_vector_readouts':4915200,'treated_front_Q3_pwl_evaluations':9830400,
        'paired_words_scored':9830400,'selected_request_window_pairs':81920,'selected_learning_word_pairs':327680,
        'source_files_preserved':len(load(out/'source_hashes.json')),'python_sources_preserved':len(load(out/'execution_hashes.json')),
        'new_source_learning_submissions_paths_fft_holdout':0,'center_target_round_error':str(projector.center_round)})
    print('All exact response, coordinate, common-phase and independent probes passed',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','analyze']);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    try:(prepare if args.mode=='prepare' else analyze)(args.out)
    except Exception:
        if args.out.exists():(args.out/f'{args.mode}_failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
