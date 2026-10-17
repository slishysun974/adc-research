"""Read-only sampling/source/basis/target audit of the NG43 first gap.

The moment identities specialize NG21; no new theory identifier or learner.
"""
import argparse
from fractions import Fraction as F
from pathlib import Path
import shutil
import traceback
import numpy as np
from experiments.exp_074_learning_signal_gate_intervention.analyze_response import (
    ROOT, OLD, CHANNEL, SEEDS, N, W, DOCS, source, original, load, write,
    digest, guard, Scorer, isum, mulsum, pack, evaluate, round_ratio,
    pwl_scaled, bases, probes,
)

PRIOR=ROOT/'artifacts/research/first_response_projection_20261013_v1'
GATES=ROOT/'artifacts/research/second_gate_history_20261013_v1'
TERM_NAMES=['selected_correlation','sampling_correction','rear_source_correction',
            'basis_weight_correction','integer_rounding','local_target']


def controls():
    d=[1,-1,1,-1];psi=[F(64),F(-64),F(128),F(-128)]
    yn=list(map(F,[2,-3,4,-5]));yl=list(map(F,[3,-1,5,-2]))
    tau=list(map(F,[-10,20,-30,40]));er=list(map(F,[F(1,8),0,F(-1,8),0]))
    mean=lambda a:sum(a)/len(a)
    selected=mean([d[j]*yl[j] for j in (0,1)])
    full_l=mean([d[j]*yl[j] for j in range(4)])
    full_n=mean([d[j]*yn[j] for j in range(4)])
    terms=[64*selected,64*(full_l-selected),64*(full_n-full_l),
           mean([(psi[j]-64*d[j])*yn[j] for j in range(4)]),
           mean([psi[j]*er[j] for j in range(4)]),
           -mean([psi[j]*tau[j] for j in range(4)])]
    direct=mean([psi[j]*(yn[j]-tau[j]+er[j]) for j in range(4)])
    assert sum(terms)==direct
    assert mean([d[j]*yl[j] for j in range(4)])-full_l==0
    assert mean([d[j]*(yn[j]-yn[j]) for j in range(4)])==0
    assert sum((64*d[j]-64*d[j])*yn[j] for j in range(4))==0
    assert abs(mean([psi[j]*tau[j] for j in range(4)]))<=256*mean([abs(p) for p in psi])
    # A declared coarse first-flash cell allows opposite target preferences.
    z,y,lo,hi=F(2050),F(2048),F(1792),F(2304)
    assert (z-lo)**2-(y-lo)**2>0 and (z-hi)**2-(y-hi)**2<0
    return {'passed':True,'controls':['six moment terms','full selection degeneracy',
        'same rear degeneracy','matched basis degeneracy','first-flash target enclosure',
        'opposite target preferences in one coarse cell'],
        'physical_full_history_counterexample':False}


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
        'version':'EXP074-first-moment-audit-v1','date':'2026-10-13',
        'authority':'D136..139, user continue research, current STATUS next steps1/2',
        'scope':'Original all40 gate pairs/320 blocks; first gap versus each baseline B, all5 seeds, two rates, two starts, two signal contexts,128..136 only.',
        'derivation':'Specialize existing NG21 moment mismatch to NG43 first-coordinate cross, using fixed architecture dither64 (no fit). Six terms: selected correlation, sampling, rear source, basis, final rounding, local target. First-flash nominal interior cell gives |T-2048-512q1|<=256. Existing NG43 common-phase certification reused.',
        'alternatives':['Sampling/source corrections suffice for the actual target-loss sign, versus remaining basis/target terms being necessary.',
                        'Four-word first response and normalized120-slot response have the same direction, versus differing signed dither moments.',
                        'Nominal first-flash target enclosure alone certifies the first addition, versus requiring finer input/target knowledge.'],
        'predictions':['All old first error crosses and first-added losses reproduce exactly, and every block sum closes.',
                       'Moving learner source has zero rear-source term; only held source may require it.',
                       'All first responses and Q22 differences reproduce; normalized full-slot moment is not a propagated policy or equal-cost update.',
                       'Retain every zero/ambiguous enclosure and truncated-expression sign; no score-gated acceptance or causal percentages.'],
        'budget':{'normal_vector_readouts':9830400,'held_vector_readouts':4915200,
                  'treated_front_Q3_pwl_evaluations':9830400,'paired_words_analyzed':9830400,
                  'selected_request_window_pairs':81920,'request_selected_learning_word_pairs':327680,
                  'normalized_full_slot_response_word_pairs':9830400,
                  'rational_and_formal_readouts_each':2160,'rational_first_response_checks':120,
                  'integer_output_values_loaded':24576000,'Q22_values_loaded':1639200,
                  'corner_request_values_loaded':1638400,'legacy_request_values_loaded':1310720,
                  'new_learning_commits_paths_source_fft_holdout':0},
        'limits':'Moment terms and truncated algebra are not losses of independent algorithms. Coarse target box is an outer enclosure, not physically reachable corners or complete-history impossibility. Target stays offline. NG21/43 are reused; do not renumber their identities.',
        'stopping':'Fixed original scope only; arithmetic/source/domain mismatch stops and is archived; no parameter, model, horizon or policy adjustment.'})
    for name in DOCS+['docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md']:
        p=out/'documents_before'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
    print('Frozen first-moment audit: all40 pairs/320 blocks, no new policy',flush=True)


def target_dot(num,scorer):
    per=np.asarray(num).reshape(-1,N).sum(axis=0,dtype=np.int64)
    return F(sum(int(v)*scorer.ti[i] for i,v in enumerate(per)),scorer.D)


def analyze(out):
    assert not (out/'results.json').exists(),'Refuse complete overwrite'
    assert digest(Path(__file__))==digest(out/'frozen_analysis.py')
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'));controls()
    scorer=Scorer();prior={(r['seed'],r['rate'],r['initialization'],r['context']):r for r in load(PRIOR/'results.json')['rows']}
    rows=[];scalar=checks=0
    for seed in SEEDS:
        words=source(seed)
        assert np.all(np.abs(words[:,:,0].astype(np.int64))<=3),'Coarse bound requires interior nominal flash cells'
        for rate,den in (('base',1),('quarter',4)):
            stem=f'{seed}_{rate}';a,b,ay,by,_,_=original(seed,rate)
            fs=np.fromfile(CHANNEL/f'{stem}_front_q22.bin',dtype='<i4').reshape(W+1,4,4).astype(np.int64)
            fy=np.fromfile(CHANNEL/f'{stem}_outputs.bin',dtype='<i2').reshape(W,4,120)
            for h,init in ((0,'actual'),(2,'prefix')):
                for aa,ctx in ((1,'gate_signal_moving'),(0,'gate_signal_held')):
                    if aa:bst,tst,yr,yt=fs[:,h],a[:,h,:4],fy[:,h],ay[:,h]
                    else:bst,tst,yr,yt=b[:,h,:4],fs[:,h+1],by[:,h//2],fy[:,h+1]
                    rear=a[:-1,h,4:];held=np.broadcast_to(a[0,h,4:],(W,4))
                    normal=evaluate(words,np.column_stack((bst[:-1],rear)))
                    assert np.array_equal(normal[0],yr)
                    learn=normal if aa else evaluate(words,np.column_stack((bst[:-1],held)))
                    kk=round_ratio(tst[:-1],4096)-round_ratio(bst[:-1],4096)
                    assert not kk[:,2:].any()
                    d=2*(words[:,:,3].astype(np.int64)&1)-1
                    yn,yl=normal[5],learn[5]
                    yp=pwl_scaled(learn[4],round_ratio(tst[:-1],4096),128)-512*d
                    delta=yp-yl
                    selected_sum=np.sum(d[:,:4]*delta[:,:4],axis=1)
                    full_sum=np.sum(d*delta,axis=1)
                    saved=np.fromfile(GATES/f'{stem}_{init}_{aa}_requests.bin',dtype='<i4').reshape(W,5,4)
                    response=saved[:,4]
                    assert np.array_equal(response[:,0],round_ratio(-96*np.sum(d[:,:4]*yp[:,:4],axis=1),25*den)-round_ratio(-96*np.sum(d[:,:4]*yl[:,:4],axis=1),25*den))
                    assert np.array_equal((tst-bst)[1:,0],np.cumsum(response[:,0]))
                    p1,p2=bases(normal[4]);s1=p1*kk[:,0,None];s2=p2*kk[:,1,None]
                    coarse=2048+512*words[:,:,0].astype(np.int64)
                    rounding=8*yr.astype(np.int64)-8*coarse-yn
                    assert np.all(np.abs(rounding)<=4)
                    base=d*yl;selected=np.zeros_like(base);selected[:,:4]=30*base[:,:4]
                    nums=[kk[:,0,None]*512*selected,
                          kk[:,0,None]*512*(base-selected),
                          kk[:,0,None]*512*d*(yn-yl),
                          kk[:,0,None]*(p1-512*d)*yn,
                          s1*rounding]
                    if aa:assert not nums[2].any()
                    x,z=probes(words,bst,tst,rear,held,aa,yr,yt,yl,yp,response,den);scalar+=x;checks+=z
                    old=prior[seed,rate,init,ctx]
                    def one(sl,pr):
                        size=s1[sl].size
                        terms=[F(2*isum(n[sl]),size*65536) for n in nums]
                        tcoarse=F(mulsum(s1[sl],coarse[sl]))
                        local_target=-F(2,size*8192)*(target_dot(s1[sl],scorer)-tcoarse)
                        terms.append(local_target)
                        truecross=F(pr['first']['error_cross']['exact'])
                        assert sum(terms)==truecross
                        ap=F(pr['first_added_displacement_power']['exact'])
                        exact=F(pr['first_added_loss']['exact']);assert ap+sum(terms)==exact
                        stages=[];cur=ap
                        for term in terms:cur+=term;stages.append(pack(cur))
                        digital=ap+sum(terms[:-1]);rad=F(512*isum(np.abs(s1[sl])),size*8192)
                        interval=[digital-rad,digital+rad]
                        assert interval[0]<=exact<=interval[1]
                        ss,ff=selected_sum[sl],full_sum[sl]
                        return {'terms':{name:pack(v) for name,v in zip(TERM_NAMES,terms)},
                          'truncated_expression_stages':stages,'exact_first_added_loss':pack(exact),
                          'coarse_flash_target_interval':[str(v) for v in interval],
                          'coarse_flash_sign_certified':interval[0]>0 or interval[1]<0,
                          'selected_full_response_strict_opposite_windows':int(np.count_nonzero(ss*ff<0)),
                          'selected_response_zero_windows':int(np.count_nonzero(ss==0)),
                          'full_response_zero_windows':int(np.count_nonzero(ff==0)),
                          'selected_unrounded_response_Q22_sum':pack(F(-96*isum(ss),25*den)),
                          'full_normalized_unrounded_response_Q22_sum':pack(F(-96*isum(ff),25*den*30))}
                    row={'seed':seed,'rate':rate,'initialization':init,'context':ctx,'moments':one(slice(None),old['stats']),'blocks':[]}
                    for bb in range(8):
                        sl=slice(bb*256,(bb+1)*256)
                        row['blocks'].append({'block':128+bb,'moments':one(sl,old['blocks'][bb]['stats'])})
                    for name in TERM_NAMES:
                        assert sum(F(z['moments']['terms'][name]['exact']) for z in row['blocks'])/8==F(row['moments']['terms'][name]['exact'])
                    rows.append(row)
                    print(seed,rate,init,aa,'terms',[row['moments']['terms'][n]['value'] for n in TERM_NAMES],
                          'coarse certified',row['moments']['coarse_flash_sign_certified'],flush=True)
    assert len(rows)==40 and scalar==2160 and checks==120
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    write(out/'results.json',{'completed':True,'rows':rows})
    write(out/'verification.json',{'passed':True,'pairs':40,'blocks':320,'exact_moment_cross_losses_block_sums_and_Q22_response':True,
        'moving_source_correction_zero_all20':True,'interior_first_flash_cells_all_source_words':True,
        'rational_and_formal_readouts_each':scalar,'rational_first_response_checks':checks,
        'source_files_preserved':len(load(out/'source_hashes.json')),'python_sources_preserved':len(load(out/'execution_hashes.json')),
        'new_learning_commits_paths_source_fft_holdout':0})
    print('All moment chains, coarse enclosures and independent probes passed',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','analyze']);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    try:(prepare if args.mode=='prepare' else analyze)(args.out)
    except Exception:
        if args.out.exists():(args.out/f'{args.mode}_failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
