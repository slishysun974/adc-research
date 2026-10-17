"""Actual front-only export mean versus temporal changes; same-word references.

Reuse the completed forcing/response score and Q3 remainder. No front PWL
or learner replay: only reconstruct the missing fixed-rear digital bases.
"""
import argparse,shutil,traceback
from pathlib import Path
from fractions import Fraction as F
import numpy as np
from experiments.exp_073_bank_feedback_intervention.analyze_front_history import (
    ROOT,OLD,BASE,NEW,SEEDS,W,source,load,write,digest,guard,round_ratio,pwl_scaled,
    ExactProjector,SCALE,mulsum,pack,DOCS,
)

PRIOR=ROOT/'artifacts/research/front_forcing_response_20261013_v2'


def prepare(out):
    assert not out.exists(),'Refuse overwrite'
    assert load(PRIOR/'verification.json')['passed'] and load(PRIOR/'independent_control.json')['passed']
    out.mkdir(parents=True)
    files=dict(load(PRIOR/'source_hashes.json'));files.update(load(PRIOR/'moment_hashes.json'))
    for name in ['results.json','verification.json','protocol.json']:
        p=PRIOR/name;files[str(p)]=digest(p)
    guard(files);write(out/'source_hashes.json',files)
    sources=list((ROOT/'src/adc_research').rglob('*.py'))+list((ROOT/'experiments').rglob('*.py'))
    write(out/'execution_hashes.json',{str(p):digest(p) for p in sources})
    shutil.copyfile(Path(__file__),out/'frozen_analysis.py')
    write(out/'protocol.json',{
        'version':'EXP073-actual-export-position-variation-v1','date':'2026-10-13',
        'authority':'D136..139 and user continue, short-term remaining-error sources, approved same-record position/change analysis',
        'necessity':'Frozen forcing and own response strongly cancel; their individual powers cannot locate residual actual export-position/change loss. Prior Gram matrices do not contain unweighted raw basis moments needed for the time-mean position reference.',
        'scope':'Same20 front-only/held cases, five seeds/two rates/two starts/eight blocks128..135. No new word, output policy or horizon.',
        'reference':'Mean of actual2048 output-before-update Q1.10 front exports, high2 held. Whole-record offline mean; continuous coordinate difference from held output, not legal rounded coefficients, a future initializer or separately learned policy.',
        'relation':'Actual exported output gap splits into mean-export shift plus centered-export shift. Retain their output Gram cross and held-error projections, reuse old current-Q3/integer gap. Do not name the whole mean-reference advantage an independent variance cost.',
        'predictions':['All actual loss and old current-readout remainder scores reproduce exactly; all160 block sums close.',
                       'Mean and centered profiles are separated before scores; no sign/ranking assumed, cross retained.',
                       'Only fixed-rear Q3 reconstruction and two bases needed; no front PWL or request replay.'],
        'budget':{'source_unique_words':1228800,'initial_Q22_values':160,'actual_K_values_loaded':81920,
                  'saved_integer_outputs_loaded':9830400,'rear_Q3_PWL':4915200,'front_Q3_PWL':0,
                  'new_reference_score_code_inputs_total_and_blocks':29491200,'off_diagonal_Gram_word_products_total_and_blocks':29491200,
                  'new_learning_submissions_paths_source_fft_holdout':0},
        'stop':'Same20/160 only. Reject source/arithmetic/domain/old-remainder mismatch, preserve any failure. No legal-mean readout, policy, optimizer or matrix expansion.',
        'limits':'Position and change are descriptive continuous references of saved histories, not unique causal shares. Mean uses future record; target is offline. Temporal centering does not make output/error crosses vanish.'})
    for name in DOCS:
        p=out/'documents_before'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p)
    print('Frozen actual-export mean/variation reference and missing-basis budget',flush=True)


def inspect(p,v,rem,held,prior,projector):
    ps=projector.projected(p,held,SCALE);vs=projector.projected(v,held,SCALE)
    linear=projector.projected(p+v,held,SCALE)
    oldrem=prior['components']['current_readout_rounding'];actual=prior['actual']
    cross=2*F(mulsum(p,v),p.size*SCALE*SCALE)
    rP=2*F(mulsum(p,rem),p.size*SCALE*SCALE)
    rV=2*F(mulsum(v,rem),p.size*SCALE*SCALE)
    assert F(linear['net']['exact'])==F(ps['net']['exact'])+F(vs['net']['exact'])+cross
    assert F(actual['net']['exact'])==F(linear['net']['exact'])+F(oldrem['net']['exact'])+rP+rV
    # New exact target cross/power of remainder, independently compared to reuse.
    phase=projector.phase_sum(rem)
    power=F(mulsum(rem,rem),rem.size*SCALE*SCALE)
    bc=F(2*mulsum(rem,held),rem.size*SCALE)-F(2*sum(int(z)*t for z,t in zip(phase,projector.ti)),rem.size*SCALE*projector.D)
    assert power==F(oldrem['power']['exact']) and bc==F(oldrem['error_cross']['exact'])
    added=F(linear['net']['exact'])-F(ps['net']['exact'])
    actual_added=F(actual['net']['exact'])-F(ps['net']['exact'])
    return {'mean_position':ps,'centered_variation':vs,'linear_total':linear,'actual':actual,
            'position_variation_cross':pack(cross),'position_readout_cross':pack(rP),'variation_readout_cross':pack(rV),
            'variation_added_after_position':pack(added),'actual_minus_position_reference':pack(actual_added),
            'position_added_after_variation':pack(F(linear['net']['exact'])-F(vs['net']['exact'])),
            'current_readout_remainder_reused_exact':True}


def analyze(out):
    assert not (out/'results.json').exists(),'Refuse complete overwrite'
    assert digest(Path(__file__))==digest(out/'frozen_analysis.py')
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    prior={(r['seed'],r['rate'],r['initialization']):r for r in load(PRIOR/'results.json')['rows']}
    projector=ExactProjector();rows=[]
    for seed in SEEDS:
        words=source(seed);q2,sar,bits=(words[:,:,j].astype(np.int64) for j in (1,2,3));d2=2*((bits>>1)&1)-1
        for rate in ('base','quarter'):
            stem=f'{seed}_{rate}'
            initial=np.memmap(NEW/f'{stem}_q22.bin',dtype='<i4',mode='r',shape=(W+1,4,8))
            ys=np.memmap(NEW/f'{stem}_outputs.bin',dtype='<i2',mode='r',shape=(W,4,120))
            hs=np.memmap(BASE/f'{stem}_outputs.bin',dtype='<i2',mode='r',shape=(W,4,120))
            for h,init in ((0,'actual'),(2,'prefix')):
                a0=np.array(initial[0,h],dtype=np.int64);K0=round_ratio(a0[:2],4096)
                moments=np.memmap(PRIOR/f'{stem}_{init}_front_moments.bin',dtype='<i8',mode='r',shape=(W,24))
                delta=np.array(moments[:,10:12],dtype=np.int64)-K0
                mean_num=delta.sum(axis=0,dtype=np.int64);center_num=W*delta-mean_num
                assert not center_num.sum(axis=0).any()
                rear=np.broadcast_to(round_ratio(a0[4:],4096),(W,4))
                raw=1024*q2+pwl_scaled(8*sar,rear,32)-128*d2
                assert np.all((raw>=-4096)&(raw<4096))
                phi=[np.sign(raw)*np.minimum(np.maximum(np.abs(raw)-1024*j,0),1024) for j in range(2)]
                pn=4096*sum(mean_num[j]*phi[j] for j in range(2))
                vn=4096*sum(center_num[:,j,None]*phi[j] for j in range(2))
                actual=np.array(ys[:,h],dtype=np.int64);held=np.array(hs[:,h+1],dtype=np.int64)
                rem=(actual-held)*SCALE-pn-vn
                assert np.all(np.abs(rem)<=9*SCALE//8)
                prev=prior[seed,rate,init]
                stat=inspect(pn,vn,rem,held,prev['stats'],projector)
                row={'seed':seed,'rate':rate,'initialization':init,'mean_export_gap':[pack(F(int(z),W*1024)) for z in mean_num],
                     'stats':stat,'blocks':[]}
                for bb in range(8):
                    sl=slice(bb*256,(bb+1)*256)
                    row['blocks'].append({'block':128+bb,'stats':inspect(pn[sl],vn[sl],rem[sl],held[sl],prev['blocks'][bb]['stats'],projector)})
                for key in ['position_variation_cross','variation_added_after_position','actual_minus_position_reference']:
                    assert F(stat[key]['exact'])==sum(F(b['stats'][key]['exact']) for b in row['blocks'])/8
                rows.append(row)
                print(seed,rate,init,'position',stat['mean_position']['net']['value'],
                      'variation_added',stat['variation_added_after_position']['value'],'actual',stat['actual']['net']['value'],flush=True)
    assert len(rows)==20
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    write(out/'results.json',{'completed':True,'rows':rows})
    write(out/'verification.json',{'passed':True,'cases':20,'blocks':160,'all_current_remainders_and_losses_exact':True,
        'all_position_variation_Gram_crosses_and_block_sums_exact':True,
        'source_files_preserved':len(load(out/'source_hashes.json')),'python_sources_preserved':len(load(out/'execution_hashes.json')),
        'new_learning_submissions_paths_source_fft_holdout':0})
    print('All actual-profile position/variation and original remainder relations passed',flush=True)


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','analyze']);ap.add_argument('--out',type=Path,required=True);args=ap.parse_args()
    try:(prepare if args.mode=='prepare' else analyze)(args.out)
    except Exception:
        if args.out.exists():write(args.out/'failure.json',{'mode':args.mode,'traceback':traceback.format_exc()})
        raise
