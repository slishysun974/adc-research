"""Read-only EXP-072 readout analysis and a conditional sine target enclosure.

Never generates source words, submits learning requests, or selects a policy.
The two mixed-bank readouts use saved states and do not form new trajectories.
"""
import argparse
from dataclasses import replace
from fractions import Fraction as F
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

import numpy as np
import mpmath as mp

ROOT = Path('D:/ADC')
sys.path[:0] = [str(ROOT/'src'), str(ROOT)]
from experiments.exp_062_same_input_background.verify import digital, round_ratio
from experiments.exp_060_static_auxiliary_preflight.run import fixed_setup
from adc_research.theory.static_fixed_contract import readout, nearest_even, export
from adc_research.calibration.fixed_pwl import correct_two_stage_fixed_observed
from adc_research.calibration.observation import DigitalCalibrationSample

OLD = ROOT/'artifacts/runs/EXP_062/background_v1'
RUN = ROOT/'artifacts/runs/EXP_072/finite_v1'
N, W, START = 30720, 2048, 128*256
SEEDS = list(range(202610621, 202610626))
S = 1 << 160
ETA = F(1, 10**12)

def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p, d): p.write_text(json.dumps(d, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(4*1024*1024), b''): h.update(b)
    return h.hexdigest()
def guard(manifest):
    for p, h in manifest.items(): assert digest(Path(p)) == h, p
def floor(v): return v.numerator//v.denominator
def ceil(v): return -floor(-v)
def interval(v): return (floor(v*S), ceil(v*S))
def add(a,b): return (a[0]+b[0], a[1]+b[1])
def mul(a,b):
    vals = [a[0]*b[0], a[0]*b[1], a[1]*b[0], a[1]*b[1]]
    return (min(vals)//S, -((-max(vals))//S))
def div(a,d): return (a[0]//d, -((-a[1])//d))
def sine(a):
    """Directed fixed-point Taylor enclosure on [-4,4]."""
    assert -4*S <= a[0] <= a[1] <= 4*S
    sq = mul(a,a); term = a; total = a
    for k in range(1,45):
        t = div(mul(term,sq), (2*k)*(2*k+1))
        term = (-t[1], -t[0]); total = add(total,term)
    # All 45 terms through degree89. Taylor remainder <=4^91/91!<1/S.
    return (total[0]-1,total[1]+1)
def atan_bounds(d, terms):
    value = sum((F((-1)**k, (2*k+1)*d**(2*k+1)) for k in range(terms)), F(0))
    other = value + F((-1)**terms, (2*terms+1)*d**(2*terms+1))
    return min(value,other),max(value,other)
def pi_bounds():
    a,b=atan_bounds(5,70); c,d=atan_bounds(239,22)
    return 16*a-4*d,16*b-4*c
PI = pi_bounds()
def theta(m):
    a,b = F(2*m,N)*PI[0],F(2*m,N)*PI[1]
    return min(a,b),max(a,b)
def asin_bounds(r):
    """MP proposes a bracket; directed exact integer sine verifies it."""
    mp.mp.dps=80
    z=mp.asin(mp.mpf(r.numerator)/r.denominator)
    approx=F(str(z)); den=10**32
    lower=F(floor(approx*den)-1,den); upper=F(floor(approx*den)+2,den)
    assert F(sine(interval(lower))[1],S) < r
    assert F(sine(interval(upper))[0],S) > r
    return lower,upper

def prepare(out):
    assert not out.exists(), 'Refuse overwrite'
    out.mkdir(parents=True)
    assert load(RUN/'verification.json')['passed']
    files=[OLD/'tone.bin',OLD/'protocol.json',RUN/'results.json',RUN/'verification.json',RUN/'delivery_hashes.json',
           ROOT/'experiments/exp_062_same_input_background/verify.py',
           ROOT/'experiments/exp_060_static_auxiliary_preflight/run.py',
           ROOT/'src/adc_research/theory/static_fixed_contract.py',
           ROOT/'src/adc_research/calibration/fixed_pwl.py',
           ROOT/'src/adc_research/calibration/fixed_four_lane_window.py']
    for seed in SEEDS:
        files.append(OLD/f'both_smooth_{seed}_words.bin')
        for rate in ('base','quarter'):
            files.extend(RUN/f'{seed}_{rate}_{suffix}.bin' for suffix in ('outputs','q22','requests'))
    write(out/'source_hashes.json',{str(p):digest(p) for p in files})
    protocol={
        'date':'2026-10-13','authority':'D-136/current STATUS; continue approved research',
        'object':'Existing EXP072 both_smooth, all5 original seeds, rates1 and1/4, point30, same [128,136) horizon. Both actual and prefix continuation pairs retained.',
        'question':'Which saved bank/output changes enter the continuation loss, and what target conditions can a causal q1 prefix supply for a specified sine family?',
        'readout':'Two mixed-bank Q22 states per pair: saved continuing front/held rear and held front/saved continuing rear. These are same-word readouts, never independently updated branches.',
        'theory':'Reuse NG22/27/31/33 identities. Preserve cross and both replacement orders. New conditional relation derives phase/target enclosure from causal first-stage thresholds, known amplitude/frequency/clock, nominal noiseless flash, and <=1e-12 bounded source-table deviation.',
        'phase_information':'Known amplitude41/50, frequency127/30720, conversion origin, fixed phase over history/future; phase initially unspecified. Only prefix q1, not tone/targets/second-stage analog truth, constrains phase. Nominal source and target tables checked separately for inclusion.',
        'predictions':['Nonzero bank interactions restrict assigning a unique level contribution',
            'Negative cross can outweigh nonnegative output displacement even for the reversed3 actual-start pairs',
            'If the q1 phase envelope makes signed-loss intervals cross zero, leave that ordering uncertified',
            'A sufficiently tight sine envelope can certify retrospective paired ranking but cannot predict the unobserved future readouts or certify an online stop policy'],
        'budget':{'saved_output_codes_read':9830400,'saved_state_vectors':81960,'saved_request_vectors':81920,'active_request_vectors':40960,
            'future_source_words':1228800,'causal_prefix_source_words':1228800,'new_mixed_integer_readouts':4915200,
            'rational_and_formal_probe_readouts_each':1440,'probes_per_pair':'windows0,1024,2047; slots0,1,2,3,59,119; all4 bank combinations',
            'sine_grid_points_certified':30720,'new_source_conversions':0,'learning':0,'new_paths':0,'fft':0},
        'stop':'No extra seeds,models,horizon,rate,optimization,new trajectory,holdout or algorithm. Retain errors and every paired result.',
        'limits':'Hybrid losses conditional to saved states/words, not isolated feedback effects. Sine assumptions additional to arbitrary-input NG38. Existing output/source/Gu/RTL files immutable.'}
    write(out/'protocol.json',protocol)
    shutil.copyfile(Path(__file__),out/'frozen_analysis.py')
    docs=['docs/STATUS.md','docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md','docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md',
          'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md','docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
          'docs/theory/README.md','docs/reports/experiments/EXP_072_NORMAL_STATE_INTERVENTION_V1.md',
          'docs/reports/GU_ALGORITHM_EVALUATION_V1.md','docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
          'docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md']
    for p in docs:
        dest=out/'documents_before'/p;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/p,dest)
    print('Protocol frozen before new decomposition/phase results',flush=True)

def phase_certificate(out,tone,target):
    assert F(4)**91/F(math.factorial(91)) < F(1,S)
    assert F(sine(interval(F(1,6)))[0],S) > (F(1,8)+ETA)/F(41,50)
    A=F(41,50); inverse=pow(127,-1,N); constraints=[]; lo,hi=F(-1,6),F(1,6)
    for t in (F(-5,8),F(-3,8),F(-1,8),F(1,8),F(3,8),F(5,8)):
        beta=mp.asin(mp.mpf(t.numerator)/t.denominator/mp.mpf('0.82'))
        m0=int(mp.floor(beta*N/(2*mp.pi))); qlower=int(4*t-F(1,2))
        for m in (m0,m0+1):
            n=((m%N)*inverse)%N; thlo,thhi=theta(m)
            symbol=qlower if m==m0 else qlower+1
            if m==m0:
                rootlo,roothi=asin_bounds((t+ETA)/A); bound=roothi-thlo; hi=min(hi,bound); sense='upper'
            else:
                rootlo,roothi=asin_bounds((t-ETA)/A); bound=rootlo-thhi; lo=max(lo,bound); sense='lower'
            assert abs(thlo)+F(1,6)<F(3,2), 'Monotone sine branch required'
            constraints.append({'n':n,'grid_m':m,'threshold':str(t),'symbol':symbol,'sense':sense,
                'bound':str(bound),'asin_enclosure':[str(rootlo),str(roothi)],'theta_enclosure':[str(thlo),str(thhi)]})
    checks=[]
    for seed in SEEDS:
        word=np.memmap(OLD/f'both_smooth_{seed}_words.bin',dtype='i1',mode='r',shape=(65536,120,4))
        q=np.asarray(word[120*256:128*256,:,0]).ravel().reshape(8,N)
        assert np.all(q[:,0]==0) and np.all(q[:,N//4]==-3)
        for c in constraints: assert np.all(q[:,c['n']]==c['symbol'])
        assert np.all(q==q[0]), 'q1 period unchanged'
        checks.append({'seed':seed,'blocks_checked':8,'all_prefix_q1_periods_equal':True,'constraints_passed':12})
    assert lo<0<hi
    radius=F(ceil(max(-lo,hi)*(1<<40)),1<<40)
    tone_error=target_error=F(0)
    for n in range(N):
        m=(127*n)%N
        if m>N//2:m-=N
        thlo,thhi=theta(m); sb=sine((floor(thlo*S),ceil(thhi*S)))
        ab=(A*F(sb[0],S),A*F(sb[1],S))
        observed=F(float(tone[n])); scored=F(float(target[n]))
        tone_error=max(tone_error,abs(observed-ab[0]),abs(observed-ab[1]))
        target_error=max(target_error,abs(scored-2048*(1+ab[0])),abs(scored-2048*(1+ab[1])))
    assert tone_error<=ETA and target_error<=2048*ETA
    target_radius=2048*(A*radius+ETA)+target_error
    d={'phase_lower':str(lo),'phase_upper':str(hi),'phase_radius_dyadic':str(radius),
       'phase_interval_float':[float(lo),float(hi)],'target_radius':str(target_radius),'target_radius_float':float(target_radius),
       'source_deviation_allowance':str(ETA),'tone_grid_error_upper':str(tone_error),'tone_grid_error_upper_float':float(tone_error),
       'target_grid_error_upper':str(target_error),'target_grid_error_upper_float':float(target_error),
       'pi_enclosure':[str(v) for v in PI],'scale':S,'taylor_terms':45,'constraints':constraints,'prefix_checks':checks,
       'all30720_nominal_source_and_target_points_included':True,'future_words_used_to_infer_phase':False,
       'model':'x_n=(41/50)sin(2pi127n/30720+phi)+e_n, |e_n|<=1e-12; nominal first-stage flash; known origin/amplitude/frequency; fixed phase',
       'scope':'Necessary phase/target outer enclosure from12 prefix threshold constraints. No claim that all enclosed phases reproduce the complete source or have the same learning future.'}
    write(out/'phase_certificate.json',d);print('Phase',d['phase_interval_float'],'target radius',float(target_radius),flush=True)
    return target_radius

def exact_delta(y,z,target):
    """Exact paired difference for the declared binary64 target table."""
    ratios=[float(t).as_integer_ratio() for t in target]; den=max(d for a,d in ratios)
    a=[v*(den//d) for v,d in ratios]
    delta=y.astype(np.int64)-z.astype(np.int64)
    first=int(np.sum(delta*(y.astype(np.int64)+z.astype(np.int64)),dtype=np.int64))
    perphase=delta.reshape(8,N).sum(axis=0)
    dot=sum(int(v)*t for v,t in zip(perphase,a))
    return F(first*den-2*dot,8*N*den)

def comparison(y,z,target,rad):
    d=y.astype(np.int64)-z.astype(np.int64); e=z.astype(float)-np.tile(target,8)
    power=float(np.mean(d*d));cross=float(2*np.mean(e*d));net=exact_delta(y,z,target)
    bound=2*rad*F(int(np.sum(np.abs(d))),8*N)
    assert abs(float(net)-(power+cross))<1e-10
    return {'mse_change':float(net),'mse_change_exact':str(net),'displacement_power':power,'reference_error_cross':cross,
            'delta_mean':float(d.mean()),'delta_variance':float(d.var()),
            'dc_loss_change':float(2*e.mean()*d.mean()+d.mean()**2),
            'centered_cross':float(2*np.mean((e-e.mean())*(d-d.mean()))),
            'changed_codes':int(np.count_nonzero(d)),'max_abs_code_change':int(np.max(np.abs(d))),
            'target_uncertainty_halfwidth':float(bound),'target_uncertainty_halfwidth_exact':str(bound),
            'robust_signed_interval':[float(net-bound),float(net+bound)],
            'sign_certified':bool(net-bound>0 or net+bound<0)}

def probes(words,accs,ys):
    _,cfg=fixed_setup(load(OLD/'source_protocol.json')); count=0
    for w in (0,1024,2047):
        for j in (0,1,2,3,59,119):
            q1,q2,be,bits=map(int,words[w,j]);d1=2*(bits&1)-1;d2=2*((bits>>1)&1)-1
            for acc,y in zip(accs,ys):
                codes=export(tuple(map(int,acc[w])))
                rd=readout(q1,q2,F(be),d1,d2,tuple(F(k,1024) for k in codes),data_q3=True)
                cc=replace(cfg.cascade,stage1_pwl=replace(cfg.cascade.stage1_pwl,coefficient_codes=codes[:4]),
                           stage2_pwl=replace(cfg.cascade.stage2_pwl,coefficient_codes=codes[4:]))
                formal=correct_two_stage_fixed_observed(DigitalCalibrationSample(q1,q2,be,d1,d2),cc)
                assert formal.unclipped_output_scaled==8*rd.output and 0<=rd.output<=4095
                assert nearest_even(rd.output)==int(y.reshape(W,120)[w,j]);count+=1
    return count

def analyze(out):
    assert not (out/'results.json').exists(), 'Refuse completed result overwrite'
    assert digest(out/'frozen_analysis.py')==digest(Path(__file__))
    guard(load(out/'source_hashes.json'))
    tone=np.fromfile(OLD/'tone.bin',dtype='<f8');target=2048*(1+tone)
    rad=phase_certificate(out,tone,target);rows=[];probe_count=0
    oldrows={(r['seed'],r['rate']):r for r in load(RUN/'results.json')['rows']}
    for seed in SEEDS:
        words=np.memmap(OLD/f'both_smooth_{seed}_words.bin',dtype='i1',mode='r',shape=(65536,120,4))[START:START+W]
        for rate in ('base','quarter'):
            stem=f'{seed}_{rate}'
            states=np.fromfile(RUN/f'{stem}_q22.bin',dtype='<i4').reshape(W+1,4,8).astype(np.int64)
            outputs=np.fromfile(RUN/f'{stem}_outputs.bin',dtype='<i2').reshape(W,4,120)
            requests=np.fromfile(RUN/f'{stem}_requests.bin',dtype='<i4').reshape(W,4,8)
            for h,name in ((0,'actual'),(2,'prefix')):
                cont=states[:-1,h];held=states[:-1,h+1]
                assert np.all(held==held[0]) and np.array_equal(states[1:,h]-cont,requests[:,h])
                front=np.concatenate((cont[:,:4],held[:,4:]),axis=1)
                rear=np.concatenate((held[:,:4],cont[:,4:]),axis=1)
                y10=digital(words,front)[0].ravel();y01=digital(words,rear)[0].ravel()
                y00=outputs[:,h+1].ravel();y11=outputs[:,h].ravel()
                assert np.all((y10>=0)&(y10<=4095)) and np.all((y01>=0)&(y01<=4095))
                probe_count+=probes(words,[held,front,rear,cont],[y00,y10,y01,y11])
                comps={key:comparison(a,b,target,rad) for key,a,b in (
                    ('joint',y11,y00),('front_first',y10,y00),('rear_first',y01,y00),
                    ('rear_after_front',y11,y10),('front_after_rear',y11,y01))}
                baseline=oldrows[seed,rate]
                assert abs(comps['joint']['mse_change']-baseline[f'continued_minus_held_{name}'])<1e-10
                c=y11.astype(np.int64)-y10-y01+y00
                interaction=F(comps['joint']['mse_change_exact'])-F(comps['front_first']['mse_change_exact'])-F(comps['rear_first']['mse_change_exact'])
                k=round_ratio(states[:,h],4096);movement=[]
                for b in range(2):
                    sl=slice(4*b,4*b+4)
                    movement.append({'bank':b+1,'q22_changed_windows':int(np.count_nonzero(np.any(requests[:,h,sl]!=0,axis=1))),
                        'export_changed_windows':int(np.count_nonzero(np.any(k[1:,sl]!=k[:-1,sl],axis=1))),
                        'max_export_distance_from_initial':np.max(np.abs(k[:-1,sl]-k[0,sl]),axis=0).tolist(),
                        'export_range':[[int(k[:-1,i].min()),int(k[:-1,i].max())] for i in range(4*b,4*b+4)]})
                blocks=[]
                for block in range(8):
                    sl=slice(block*N,(block+1)*N);d=y11[sl].astype(np.int64)-y00[sl];e=y00[sl].astype(float)-target
                    blocks.append({'block':128+block,'displacement_power':float(np.mean(d*d)),
                        'cross':float(2*np.mean(e*d)),'mse_change':float(np.mean(d*d)+2*np.mean(e*d))})
                row={'seed':seed,'rate':rate,'initialization':name,'comparisons':comps,
                    'loss_interaction':float(interaction),'loss_interaction_exact':str(interaction),
                    'code_interaction_count':int(np.count_nonzero(c)),'max_code_interaction':int(np.max(np.abs(c))),
                    'movement':movement,'blocks':blocks,
                    'mse_grid':[float(np.mean((y.astype(float)-np.tile(target,8))**2)) for y in (y00,y10,y01,y11)]}
                rows.append(row)
                print(seed,rate,name,'net',comps['joint']['mse_change'],'power',comps['joint']['displacement_power'],
                      'cross',comps['joint']['reference_error_cross'],'grid',row['mse_grid'],'I',float(interaction),flush=True)
    guard(load(out/'source_hashes.json'))
    write(out/'results.json',{'rows':rows,'completed':True})
    write(out/'verification.json',{'passed':True,'rows':len(rows),'rational_and_formal_probes_each':probe_count,
        'mixed_integer_readouts':4915200,'saved_output_codes_read':9830400,'saved_state_vectors_read':81960,
        'saved_request_vectors_read':81920,'active_request_vectors_checked':40960,'prefix_q1_words':1228800,'future_source_words':1228800,
        'sin_grid_points_certified':30720,'source_files_preserved':len(load(out/'source_hashes.json')),
        'exact_signed_comparisons':100,'joint_signs_certified':sum(r['comparisons']['joint']['sign_certified'] for r in rows),
        'new_source_conversions':0,'new_learning':0,'new_state_commits':0,'new_trajectories':0,'fft':0,
        'future_holdout_used':False,'complete_original_replay_repeated':False,'new_algorithm':False})
    assert probe_count==1440
    print('All saved-path analyses and conditional enclosures passed',flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','analyze']);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    try:globals()[args.mode](args.out)
    except Exception:
        import traceback
        if args.out.exists():write(args.out/(args.mode+'_failure.json'),{'traceback':traceback.format_exc()})
        raise
