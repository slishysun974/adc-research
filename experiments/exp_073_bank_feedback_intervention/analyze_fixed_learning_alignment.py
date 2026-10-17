"""Offline same-position learning/output comparison, original EXP073 records.

No policy is propagated. The two references are prescribed by D140; targets
enter only loss and derivative evaluation. Frozen budgets include block scores.
"""
import argparse
from fractions import Fraction as F
from pathlib import Path
import shutil
import sys
import traceback
import numpy as np

ROOT = Path('D:/ADC')
sys.path[:0] = [str(ROOT), str(ROOT/'src')]
from experiments.exp_073_bank_feedback_intervention.analyze_front_history import (
    BASE, NEW, OLD, SEEDS, W, load, write, digest, guard, ExactProjector,
    pack, DOCS, round_ratio, pwl_scaled, source,
)
from experiments.exp_073_bank_feedback_intervention.analyze_front_fixed_sampling import Budget

CAP = ROOT/'artifacts/research/front_gate_migration_capacity_20261014_v2'
HISTORY = ROOT/'artifacts/research/front_forcing_response_20261013_v2'
BASIS = ROOT/'artifacts/research/front_block_migration_20261014_v1'
B, N, ZS = 256, W*120, 8192
MULT = np.array([1, 3, 6, 12], dtype=np.int64)
LIMITS = {
    'source_tuple_values': 5*N*4, 'initial_Q22_values': 20*8,
    'old24_values': 20*W*24, 'basis_values': 20*N*2,
    'window5_values': 20*W*5, 'held_output_values': 20*N,
    'old_gate10_values': 20*W*10,
    'rear_Q3_PWL': 20*N, 'front_Q3_PWL': 40*N,
    'continuous_front_PWL': 40*N, 'gate_tests': 40*N*8,
    'gate_product_word_components': 40*N*8,
    'request_roundings': 40*W*8,
    'loss_word_inputs': 40*N*4, 'dot_word_products': 40*N*8,
    'phase_reduction_inputs': 40*N*12,
    'target_scalar_products': 40*9*30720*12,
    'target_radius_word_inputs': 40*N*8,
    'new_output_bytes': 40*N*2, 'new_moment_bytes': 40*W*24*8,
}
INDEPENDENT_LIMITS = {
    'source_tuple_values': 5*N*4, 'initial_Q22_values': 20*8,
    'old24_values': 20*W*24, 'saved_output_values': 40*N,
    'held_output_values': 20*N,
    'saved_moment_values': 40*W*24,
    'rear_Fraction_PWL_lookup': 20*256,
    'front_Fraction_PWL_lookup': 40*8192,
    'gate_tests': 40*N*8, 'gate_product_word_components': 40*N*8,
    'continuous_basis_components': 40*N*4,
    'request_Fraction_roundings': 40*W*8,
    'exact_loss_word_inputs': 40*N*2,
    'exact_dot_word_products': 40*N*4,
    'target_scalar_products': 40*30720*4,
    'formal_readouts': 40*3*6,
    'formal_front_bank_probes': 40*3,
    'Fraction_after_step_PWL': 40*3*120,
    'local_step_integer_score_inputs': 40*3*120,
    'local_step_target_products': 40*3*120,
}


def controls():
    # Opposite learning/output directions persist at arbitrarily small steps.
    g, u, h = F(2), F(1,100), F(3)
    assert g*u+h*u*u > 0 and g*(-u)+h*u*u < 0
    # A selected subset can reverse a full-record correlation.
    x = [F(2), F(2), F(-3), F(-3)]
    assert sum(x)/4 < 0 < sum(x[:2])/2
    # Output loss is quadratic; an integer plateau has no ordinary derivative.
    assert round(F(8,10)) == round(F(81,100)) == 1
    assert (F(81,100)-F(7,10))**2 > (F(8,10)-F(7,10))**2
    # Same exported value has different one-step effective exports.
    assert round(F(4096,4096)) == round(F(6000,4096)) == 1
    assert round(F(4096+200,4096)) == 1 and round(F(6000+200,4096)) == 2
    # Mean export rounding is exact and differs from averaging hidden states.
    assert round(F(1024+1025,2)) == 1024
    assert round(F(-3,2)) == -2 and round(F(3,2)) == 2
    # Separately rounded offsets/products cannot be combined in the rear PWL.
    assert round(F(1,2))+round(F(1,2)) != round(F(1))
    # Safe int64 chunk reductions agree with Python integer products.
    a = np.array([1<<25, -(1<<25), 3], dtype=np.int64)
    assert int((a*a).sum()) == 2*(1<<50)+9
    return {'passed': True, 'exact_controls': 7, 'new_physical_source': False}


def freeze(out):
    assert not out.exists(), 'Refuse overwrite'
    out.mkdir(parents=True)
    files = dict(load(CAP/'source_hashes.json'))
    files.update(load(CAP/'new_moment_hashes.json'))
    for folder in (CAP, BASIS, HISTORY):
        for name in ('results.json', 'verification.json', 'protocol.json'):
            files[str(folder/name)] = digest(folder/name)
    for name in ('witness_bounds.json', 'witness_protocol.json', 'delivery_verification.json'):
        files[str(CAP/name)] = digest(CAP/name)
    guard(files)
    write(out/'source_hashes.json', files)
    paths = list((ROOT/'src/adc_research').rglob('*.py'))+list((ROOT/'experiments').rglob('*.py'))
    write(out/'execution_hashes.json', {str(p):digest(p) for p in paths})
    shutil.copyfile(Path(__file__), out/'frozen_analysis.py')
    checker = Path(__file__).with_name('check_fixed_learning_alignment.py')
    shutil.copyfile(checker, out/'frozen_checker.py')
    for name in DOCS+['docs/DECISIONS.md']:
        p = out/'documents_before'/name
        p.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, p)
    write(out/'controls.json', controls())
    write(out/'protocol.json', {
        'version': 'EXP073-same-fixed-position-learning-output-v1', 'date': '2026-10-14',
        'authority': 'User continues approved mainline; D136..140.',
        'scope': 'All original5 seeds/rates1,1/4/actual,prefix/8 blocks128..135; 20 cases, 40 prescribed positions; no new main-record positions.',
        'references': 'mean: nearest-even(mean actual OUTPUT-BEFORE-UPDATE low2 Q1.10 codes over2048 windows); witness: existing CAP legal_low_Q10_witness. Rear and high-front remain initial exported codes. Each diagnostic Q22 is K*4096, including unchanged coordinates; original hidden residuals are not inferred.',
        'missing': 'Old initial gate10 and basis/Gram/history/target moments are available. New-position full/selected Q3 and continuous-front correlations, moving gates, exact legal integer outputs and same-position loss derivative were not computed. Rear PWL is needed to recover full raw1, since low2 saturated bases do not recover high-segment raw.',
        'contract': 'Original5 fields: q1,q2,SAR,d1,d2 (two tags packed in file). Fixed Q1.10 eight codes0..2047; Q3 rear separate offset/local rounding, fixed raw1; Q3 front separate rounding; dither64/16, original >= gates. Output saturated0..4095 before nearest-even (range must be safe here). Four selected slots0..3, normalized4; full120 normalized120. No commits in main analysis.',
        'requests': 'x=d1*y1_Q3. Four-word Q22 request_i=round_even(-96*[1,3,6,12]_i*sum4(x*G_i)/(25*m)); full120 diagnostic=round_even(-16*[1,3,6,12]_i*sum120(x*G_i)/(125*m)), m=1,4. All front4 computed; rear held. Hypothetical low2 continuous directions use exact unrounded or mean rounded requests/2^22; do not propagate them.',
        'continuous_output': 'Fixed actual Q3 rear raw1, remove FRONT Q3 and final integer rounding only: Z*=2048+512q1+sum(front k_j*psi_j(raw1))-64d1. True continuous-reference gradient2E[psi_low*(Z*-t)] and H use same full evaluation record. It differs from previous held-integer-plus-delta reference by explicit rounding residual; check independent identity.',
        'directions': 'For both selected4 and full120, compare continuous-front learning with its own >= continuous gates, actual Q3 unrounded requests, and rounded Q22 requests. D=gradient dot v; one mean hypothetical low2 increment has exact continuous change D+v^T H v. Negative D is local compatibility only, never a future or integer-MSE guarantee.',
        'target': 'Saved nominal binary64 real target from original tone; exact rational scoring and NG39/43 common-phase/box enclosures. Targets, future mean and witness remain offline.',
        'local_step_controls': 'Independent only: each position at windows0,1024,2047, original selected4 request/all front4, centered Q22 commit with saturation, new Q1.10 export, full120 same-window integer before/after scores. 120 local windows, no future propagation and no extra main-record positions. Six formal probes per window at slots0,1,2,3,59,119.',
        'predictions': ['All old basis and initial selected-product source pairing must reproduce; independently verified initial full products are reused under hashes.',
            'If full120 direction is uphill even without front/output rounding, the same-record discrepancy is not solely four-word selection or front/output rounding.',
            'Full downhill/selected uphill supports selection-induced local incompatibility at that fixed position.',
            'Witness better than hold but learning away from it establishes representable same-record space without online reachability.',
            'No root, stationary distribution, unique physical shares or future benefit inferred from fixed mean directions.'],
        'limits': LIMITS, 'independent_limits': INDEPENDENT_LIMITS,
        'accounting': 'Charge before read, PWL, gates, products, request rounding, score, dot, phase/target contractions and output storage. Full plus all8 block scores counted; final totals are exact means of blocks.',
        'stop': 'Reject source/normalization/range/budget/independent mismatch; preserve failure, no automatic retry or expansion. No input, learner, path, FFT, new algorithm, global optimizer or future6007/8009.',
    })
    previous = ROOT/'artifacts/research/front_fixed_alignment_20261014_v1'
    if out.resolve()!=previous.resolve() and (previous/'failure.json').exists():
        spent = load(previous/'accounting_main.json')['used']
        write(out/'retry_contract.json', {
            'reason': 'First position direction multiplication rejected: Fraction(np.int64) retained a NumPy numerator. Convert NumPy request sums to Python int before Fraction; no change to objects, equations or comparisons.',
            'previous_failure_sha256': digest(previous/'failure.json'),
            'previous_frozen_source_sha256': digest(previous/'frozen_analysis.py'),
            'previous_actual': spent, 'retry_limits': LIMITS,
            'cumulative_limits': {k:spent[k]+LIMITS[k] for k in LIMITS},
            'scope_change': False,
        })


def dot(a, b, budget):
    a, b = np.asarray(a,dtype=np.int64).ravel(), np.asarray(b,dtype=np.int64).ravel()
    budget.charge('dot_word_products', a.size)
    bound = int(np.max(abs(a),initial=0))*int(np.max(abs(b),initial=0))
    chunk = min(65536, ((1<<63)-1)//max(1,bound))
    assert chunk > 0
    return sum(int((a[i:i+chunk]*b[i:i+chunk]).sum()) for i in range(0,a.size,chunk))


def phase(a, p, budget):
    budget.charge('phase_reduction_inputs', a.size)
    return p.phase_sum(a)


def targetdot(ph, table, budget):
    budget.charge('target_scalar_products', len(ph))
    return sum(int(a)*int(b) for a,b in zip(ph,table))


def radius(a, scale, ph, p, budget):
    budget.charge('target_radius_word_inputs', a.size)
    ma = F(int(np.abs(a).sum()), a.size*scale)
    v = F(targetdot(ph,p.xi,budget), a.size*scale*p.XD)
    c = F(targetdot(ph,p.ci,budget), a.size*scale*p.XD)
    noise = p.eta+p.nu*(1+p.rho)+p.center_round/2048
    return min(2*p.rad*ma, 4096*(p.rho*abs(c)+p.rho**2*abs(v)/2+noise*ma))


def interval(center, rad):
    return {**pack(center), 'interval': [str(center-rad),str(center+rad)],
            'sign_certified': center-rad>0 or center+rad<0}


def score(z, scale, p, budget):
    budget.charge('loss_word_inputs', z.size)
    ph = phase(z,p,budget)
    return F(dot(z,z,budget),z.size*scale*scale)-F(2*targetdot(ph,p.ti,budget),z.size*scale*p.D)+p.t2


def directions(g, gr, h, sums, den, selected):
    n = len(sums)
    base = F(-96,25*den) if selected else F(-16,125*den)
    # sums contains Q3*dither-tag products, or rational continuous equivalents.
    vv = [base*int(MULT[j])*sum(z if isinstance(z,F) else F(int(z)) for z in sums[:,j])/(n*(1<<22)) for j in range(2)]
    d = sum(g[j]*vv[j] for j in range(2))
    r = sum(gr[j]*abs(vv[j]) for j in range(2))
    curve = sum(vv[i]*h[i][j]*vv[j] for i in range(2) for j in range(2))
    return {'mean_step_low2': list(map(str,vv)), 'derivative': interval(d,r),
            'mean_step_continuous_loss_change': interval(d+curve,r)}


def inspect(ynum, output, held, phi, wm, data, cont_sums, den, p, budget):
    n = output.size
    h = [[F(int(wm[:,0].sum()),64*n),F(int(wm[:,1].sum()),64*n)],
         [F(int(wm[:,1].sum()),64*n),F(int(wm[:,2].sum()),64*n)]]
    g, gr = [], []
    for j in range(2):
        ph = phase(phi[:,:,j],p,budget)
        g.append(F(2*dot(phi[:,:,j],ynum,budget),n*8*ZS)-F(2*targetdot(ph,p.ti,budget),n*8*p.D))
        gr.append(radius(phi[:,:,j],8,ph,p,budget))
    li, lc = score(output,1,p,budget), score(ynum,ZS,p,budget)
    diffs = [output-held, ynum-ZS*held]
    contrasts = []
    for diff, scale, loss in zip(diffs,(1,ZS),(li,lc)):
        ph = phase(diff,p,budget)
        # Held MSE from old exact data is supplied by caller; radius only here.
        contrasts.append({'loss':pack(loss),'difference_radius':str(radius(diff,scale,ph,p,budget))})
    dirs = {}
    for method, col, rc, continuous in [('selected',4,16,cont_sums[1]),('full',0,20,cont_sums[0])]:
        dirs[method+'_Q3'] = directions(g,gr,h,data[:,col:col+4],den,method=='selected')
        dirs[method+'_continuous_front'] = directions(g,gr,h,continuous,den,method=='selected')
        v = [F(int(data[:,rc+j].sum()),len(data)*(1<<22)) for j in range(2)]
        d = sum(g[j]*v[j] for j in range(2));r = sum(gr[j]*abs(v[j]) for j in range(2))
        curve = sum(v[i]*h[i][j]*v[j] for i in range(2) for j in range(2))
        dirs[method+'_rounded_Q22'] = {'mean_step_low2':list(map(str,v)), 'derivative':interval(d,r),
                                      'mean_step_continuous_loss_change':interval(d+curve,r)}
    return {'integer_loss':pack(li),'continuous_loss':pack(lc),'contrasts':contrasts,
            'gradient':[interval(a,b) for a,b in zip(g,gr)],'H':[[str(z) for z in row] for row in h],
            'directions':dirs,'correlation_Q3_tag_y_code':{
                'full':[str(F(int(z),n*8)) for z in data[:,:4].sum(axis=0)],
                'selected':[str(F(int(z),len(data)*4*8)) for z in data[:,4:8].sum(axis=0)]},
            'high_request_nonzero':{'selected':int(np.count_nonzero(data[:,18:20])),
                                    'full':int(np.count_nonzero(data[:,22:24]))}}


def analyze(out):
    assert not (out/'results.json').exists()
    assert digest(Path(__file__)) == digest(out/'frozen_analysis.py')
    guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
    assert load(out/'controls.json')['passed']
    budget = Budget(LIMITS);p = ExactProjector()
    p.t2 = F(sum(t*t for t in p.ti),len(p.ti)*p.D*p.D)
    caps = {(r['seed'],r['rate'],r['initialization']):r for r in load(CAP/'results.json')['rows']}
    rows = []
    try:
        for seed in SEEDS:
            budget.charge('source_tuple_values',N*4);words = np.array(source(seed),dtype=np.int64)
            q1,q2,sar,bits = (words[:,:,j] for j in range(4))
            d,d2 = 2*(bits&1)-1,2*((bits>>1)&1)-1
            for rate,den in [('base',1),('quarter',4)]:
                stem = f'{seed}_{rate}'
                for idx,init in ((0,'actual'),(2,'prefix')):
                    name = f'{stem}_{init}'
                    budget.charge('initial_Q22_values',8)
                    a0 = np.array(np.memmap(BASE/f'{stem}_q22.bin',dtype='<i4',mode='r',shape=(W+1,4,8))[0,idx],dtype=np.int64)
                    k0 = round_ratio(a0,4096)
                    budget.charge('old24_values',W*24);mom = np.fromfile(HISTORY/f'{name}_front_moments.bin',dtype='<i8').reshape(W,24)
                    budget.charge('basis_values',N*2);phi = np.fromfile(BASIS/f'{name}_basis.bin',dtype='<i2').reshape(W,120,2).astype(np.int64)
                    budget.charge('window5_values',W*5);wm = np.fromfile(BASIS/f'{name}_basis_moments.bin',dtype='<i8').reshape(W,5)
                    budget.charge('held_output_values',N);held = np.array(np.memmap(BASE/f'{stem}_outputs.bin',dtype='<i2',mode='r',shape=(W,4,120))[:,idx+1],dtype=np.int64)
                    budget.charge('old_gate10_values',W*10);oldgate = np.fromfile(CAP/f'{name}_gate_sources.bin',dtype='<i8').reshape(W,10)
                    assert np.array_equal(oldgate[:,2],mom[:,7]) and np.array_equal(oldgate[:,3],mom[:,9])
                    cap = caps[seed,rate,init]['capacity']
                    budget.charge('rear_Q3_PWL',N)
                    raw = 1024*q2+pwl_scaled(8*sar,np.broadcast_to(k0[4:],(W,4)),32)-128*d2
                    assert np.array_equal(phi,np.stack([np.sign(raw)*np.minimum(np.maximum(abs(raw)-1024*j,0),1024) for j in range(2)],axis=2))
                    refs = [('mean',round_ratio(mom[:,10:12].sum(axis=0),W)),
                            ('witness',np.array(cap['legal_low_Q10_witness'],dtype=np.int64))]
                    for tag,low in refs:
                        key = f'{name}_{tag}';k = k0.copy();k[:2] = low
                        assert np.all((k>=0)&(k<=2047))
                        budget.charge('front_Q3_PWL',N)
                        y = pwl_scaled(raw,np.broadcast_to(k[:4],(W,4)),128)-512*d
                        q3 = 16384+4096*q1+y
                        assert np.all((q3>=0)&(q3<=4095*8))
                        output = round_ratio(q3,8)
                        budget.charge('continuous_front_PWL',N)
                        mag = abs(raw);seg = np.minimum(mag//1024,3)
                        cum = np.concatenate(([0],np.cumsum(k[:3])))
                        ynum_local = np.sign(raw)*(1024*cum[seg]+(mag-1024*seg)*k[seg])-512*1024*d
                        ynum = (16384+4096*q1)*1024+ynum_local
                        assert np.all(abs(ynum-ZS*output)<=4608) # 1/16+1/2 codes
                        thresh = np.concatenate(([0],np.cumsum(k[:3])))
                        budget.charge('gate_tests',N*8)
                        gate = abs(y[:,:,None])>=thresh
                        cg = abs(ynum_local[:,:,None])>=1024*thresh
                        budget.charge('gate_product_word_components',N*8)
                        products = d[:,:,None]*y[:,:,None]*gate
                        cp = d[:,:,None]*ynum_local[:,:,None]*cg
                        fs, ss = products.sum(axis=1),products[:,:4].sum(axis=1)
                        # Continuous equivalents are exact rational Q3-tag products.
                        cfs = cp.sum(axis=1).astype(object)/F(1024)
                        css = cp[:,:4].sum(axis=1).astype(object)/F(1024)
                        budget.charge('request_roundings',W*8)
                        rs = round_ratio(-96*ss*MULT,25*den)
                        rf = round_ratio(-16*fs*MULT,125*den)
                        data = np.column_stack((fs,ss,gate.sum(axis=1),gate[:,:4].sum(axis=1),rs,rf))
                        budget.charge('new_output_bytes',output.astype('<i2').nbytes);output.astype('<i2').tofile(out/f'{key}_outputs.bin')
                        budget.charge('new_moment_bytes',data.nbytes);data.astype('<i8').tofile(out/f'{key}_moments.bin')
                        total = inspect(ynum,output,held,phi,wm,data,(cfs,css),den,p,budget)
                        holdloss = F(cap['held_loss']['exact'])
                        for c in total['contrasts']:
                            c['change_from_hold'] = interval(F(c['loss']['exact'])-holdloss,F(c['difference_radius']))
                        blocks = []
                        for b in range(8):
                            s = slice(b*B,(b+1)*B)
                            blocks.append({'block':128+b,**inspect(ynum[s],output[s],held[s],phi[s],wm[s],data[s],(cfs[s],css[s]),den,p,budget)})
                        for metric in ('integer_loss','continuous_loss'):
                            assert F(total[metric]['exact']) == sum(F(b[metric]['exact']) for b in blocks)/8
                        for j in range(2):
                            assert F(total['gradient'][j]['exact']) == sum(F(b['gradient'][j]['exact']) for b in blocks)/8
                        rows.append({'seed':seed,'rate':rate,'initialization':init,'reference':tag,
                                     'initial_codes':k0.tolist(),'codes':k.tolist(),'diagnostic_Q22':(k*4096).tolist(),
                                     'held_loss':cap['held_loss'],'total':total,'blocks':blocks,
                                     'gate_Q3_vs_continuous_differences':int(np.count_nonzero(gate!=cg)),
                                     'output_range':[int(q3.min()),int(q3.max())]})
                        print(key,'loss',float(F(total['integer_loss']['exact'])),'Dsel/full',
                              total['directions']['selected_Q3']['derivative']['value'],
                              total['directions']['full_Q3']['derivative']['value'],flush=True)
        assert len(rows)==40
        write(out/'results.json',{'completed':True,'rows':rows})
        write(out/'new_moment_hashes.json',{str(p):digest(p) for p in out.glob('*.bin')})
        guard(load(out/'source_hashes.json'));guard(load(out/'execution_hashes.json'))
        write(out/'verification.json',{'passed':True,'positions':40,'blocks':320,'all_block_sums_exact':True,
                                        'new_learning_submissions_paths_source_fft_holdout':0})
    finally:
        write(out/'accounting_main.json',{'limits':LIMITS,'used':budget.used,'all_limits_met':all(budget.used[k]<=LIMITS[k] for k in LIMITS),'completed':len(rows)==40})


if __name__ == '__main__':
    ap = argparse.ArgumentParser();ap.add_argument('mode',choices=['freeze','analyze']);ap.add_argument('--out',type=Path,required=True)
    a = ap.parse_args()
    try:
        {'freeze':freeze,'analyze':analyze}[a.mode](a.out)
    except Exception:
        if a.out.exists():write(a.out/'failure.json',{'mode':a.mode,'traceback':traceback.format_exc()})
        raise
