"""Four predeclared bad full120 means: continuous fixed-state statistics.

Rear Q3 and high front coefficients remain at the original shared state.
No front Q3 rounding, Q22 reference/requests, scores or learner is introduced.
"""
import argparse
from fractions import Fraction as F
from math import lcm
from pathlib import Path
import hashlib
import json
import shutil
import traceback
import numpy as np

ROOT = Path('D:/ADC'); W = 2048; N = W*120; START = 128*256
OLD = ROOT/'artifacts/runs/EXP_062/background_v1'
MEAN = ROOT/'artifacts/research/full_front_mean_learning_20261014_v1'
ALIGN = ROOT/'artifacts/research/front_fixed_alignment_20261014_v2'
INFO = ROOT/'artifacts/research/discrepancy_information_20261014_v1'
BASIS = ROOT/'artifacts/research/front_block_migration_20261014_v1'
RUN = ROOT/'artifacts/runs/EXP_075/front_sampling_v1'
CASES = [(202610624, 'base', 'prefix'), (202610625, 'base', 'actual'),
         (202610625, 'quarter', 'actual'), (202610625, 'quarter', 'prefix')]
DOCS = ['docs/STATUS.md', 'docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md',
        'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md',
        'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
        'docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md',
        'docs/reports/GU_ALGORITHM_EVALUATION_V1.md',
        'docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
        'docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md',
        'docs/reports/experiments/EXP_075_FRONT_SAMPLING_INTERVENTION_V1.md',
        'experiments/exp_075_front_sampling_intervention/README.md']
META = [MEAN/'results.json', MEAN/'verification.json', MEAN/'independent_check.json',
        MEAN/'scalar_completion.json', ALIGN/'results.json', ALIGN/'verification.json',
        INFO/'results.json', INFO/'verification.json', RUN/'summary.json', RUN/'verification.json']


def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))


def write(p, x): p.write_text(json.dumps(x, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def digest(p):
    h = hashlib.sha256()
    with p.open('rb') as stream:
        for block in iter(lambda: stream.read(4194304), b''): h.update(block)
    return h.hexdigest()


class Budget:
    def __init__(self, limits): self.limits, self.used = limits, dict.fromkeys(limits, 0)

    def charge(self, name, n=1):
        assert self.used[name]+n <= self.limits[name], (name, self.used[name], n)
        self.used[name] += n

    def add(self, a, b): self.charge('scalar_add'); return a+b
    def sub(self, a, b): self.charge('scalar_add'); return a-b
    def mul(self, a, b): self.charge('scalar_mul'); return a*b
    def div(self, a, b): self.charge('scalar_div'); return a/b

    def total(self, values):
        z = F(0)
        for value in values: z = self.add(z, value)
        return z

    def dot(self, a, b): return self.add(self.mul(a[0], b[0]), self.mul(a[1], b[1]))
    def mv(self, a, b): return [self.dot(row, b) for row in a]

    def va(self, a, b):
        self.charge('vector_add', int(np.prod(np.broadcast_shapes(np.shape(a), np.shape(b))))); return a+b

    def vs(self, a, b):
        self.charge('vector_add', int(np.prod(np.broadcast_shapes(np.shape(a), np.shape(b))))); return a-b

    def vm(self, a, b):
        self.charge('vector_mul', int(np.prod(np.broadcast_shapes(np.shape(a), np.shape(b))))); return a*b

    def isum(self, a):
        a = np.asarray(a, dtype=np.int64)
        assert int(np.max(abs(a), initial=0))*a.size < 1 << 63
        self.charge('reduction_inputs', a.size); return int(a.sum(dtype=np.int64))

    def accounting(self, out, name, done):
        write(out/name, {'completed': done, 'used': self.used, 'limits': self.limits,
                        'all_limits_met': all(self.used[k] <= v for k, v in self.limits.items())})


def pack(z, bounds=None):
    out = {'exact': str(z), 'value': float(z)}
    if bounds is not None:
        out.update(interval=list(map(str, bounds)), sign_certified=bounds[0] > 0 or bounds[1] < 0)
    return out


def vector_rear(raw, codes):
    # Reviewed EXP062 Q3 primitive, implemented locally so no source generator
    # or platform code is imported. One declared PWL kernel includes its internals.
    assert np.all((raw >= -1024) & (raw < 1024))
    mag = abs(raw); seg = np.minimum(mag//256, 3)
    cumulative = np.array([0, *np.cumsum(np.asarray(codes[:3], dtype=np.int64))], dtype=np.int64)
    def even(num):
        quotient, remainder = np.divmod(num, 1024)
        return quotient+((2*remainder > 1024) | ((2*remainder == 1024) & (quotient % 2 != 0)))
    return np.sign(raw)*(even(256*cumulative[seg])+even((mag-256*seg)*np.asarray(codes)[seg]))


def scalar_rear(sar, codes, q=None):
    # Independent segment scalar Fraction, including separate offset rounding.
    raw = 8*int(sar); mag = abs(raw); j = min(mag//256, 3)
    if q is None:
        z = round(F(256*sum(codes[:j]), 1024))+round(F((mag-256*j)*codes[j], 1024))
    else:
        cumulative = q.total(F(int(z)) for z in codes[:j])
        offset = q.div(q.mul(F(256), cumulative), F(1024))
        product = q.div(q.mul(F(mag-256*j), F(int(codes[j]))), F(1024))
        z = q.add(round(offset), round(product))
    return z if raw >= 0 else -z


def basis(raw):
    # A declared four-coordinate geometry kernel, not a fitted sensitivity.
    return np.stack([np.sign(raw)*np.minimum(np.maximum(abs(raw)-1024*j, 0), 1024) for j in range(4)], axis=2)


def controls():
    codes = [1089, 1103, 1024, 1024]
    sar = np.array([-128, -96, -64, -32, -1, 0, 1, 31, 32, 64, 96, 127], dtype=np.int64)
    assert vector_rear(8*sar, codes).tolist() == [scalar_rear(int(z), codes) for z in sar]
    assert basis(np.array([[1024, 1280, -1280]], dtype=np.int64)).tolist() == [[[1024, 0, 0, 0], [1024, 256, 0, 0], [-1024, -256, 0, 0]]]
    # Mean is a rational continuous coefficient, not a rounded legal export.
    k = [F(1), F(2049, 2048), F(1), F(1)]
    phi = [F(128), F(64), F(0), F(0)]
    y = sum(phi[j]*k[j] for j in range(4))-64
    assert y == F(4097, 32) and abs(y) > 128*k[0]
    assert sum(phi[j] for j in range(4))-64 == 128
    assert sum(phi[j]*[F(1), F(2047,2048), F(1),F(1)][j] for j in range(4))-64 < 128
    # Exact correlation identity and rank do not imply target compatibility.
    a = [[F(1), F(0)], [F(0), F(2)]]; kk = [F(1), F(2)]; b = [F(-2), F(-3)]
    c = [sum(a[i][j]*kk[j] for j in range(2))+b[i] for i in range(2)]
    assert c == [-1, 1] and a[0][0]*a[1][1]-a[0][1]*a[1][0] == 2
    assert F(-1)*F(-1)+F(-1)*F(-3) > 0
    return {'passed': True, 'exact_controls': 6, 'rear_scalar_vector_probes': 12,
            'nonlegal_dyadic_coefficient_gate_and_equality_controls': True,
            'algebra_only_no_new_physical_source': True}


def freeze(out):
    assert not out.exists(), 'Refuse overwrite'
    for p in META:
        if p.name in ('verification.json', 'independent_check.json', 'scalar_completion.json'): assert load(p)['passed']
    files = META.copy()
    files += [OLD/f'both_smooth_{seed}_words.bin' for seed in (202610624, 202610625)]
    files += [BASIS/f'{seed}_{rate}_{init}_basis.bin' for seed, rate, init in CASES]
    out.mkdir(parents=True)
    hashes = {str(p): digest(p) for p in files}; write(out/'source_hashes.json', hashes)
    shutil.copyfile(Path(__file__), out/'frozen_analysis.py')
    for name in DOCS:
        target = out/'documents_before'/name; target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, target)
    shared = {'fingerprint_bytes': 2*sum(p.stat().st_size for p in files),
              'metadata_json_bytes': sum(p.stat().st_size for p in META), 'case_objects': 4,
              'source_values': 2*N*3}
    main = {**shared, 'basis_values': 4*N*2, 'tag_decode_cells': 4*N*2,
            'rear_Q3_PWL_cells': 4*N, 'front_continuous_cells': 4*N,
            'basis_geometry_cells': 4*N*4, 'gate_tests': 4*N,
            'margin_ratio_cells': 4*9216,
            'vector_add': 4*N*10, 'vector_mul': 4*N*20, 'reduction_inputs': 4*N*8,
            'scalar_add': 10000, 'scalar_mul': 10000, 'scalar_div': 3000}
    independent = {**shared, 'result_json_bytes': 200000,
                   'group_word_inputs': 4*N, 'digital_group_cells': 4*9216,
                   'rear_Fraction_PWL_cells': 4*256,
                   'scalar_add': 3000000, 'scalar_mul': 4000000, 'scalar_div': 100000}
    write(out/'protocol.json', {
        'date': '2026-10-14', 'version': 'EXP075-four-fixed-continuous-means-v1',
        'authority': 'User continues D136..140, latest STATUS explicitly asks minimal same-state C/A/b and gate conditions at the four bad means.',
        'cases': CASES, 'scope': 'Exactly four previously identified positive-J mean cases; other16 original cases kept as already-completed context. Original digital records/fixed rear/high2/eight blocks, no new source/model/horizon/algorithm.',
        'question': 'Is the fixed continuous full120 low-two Gu direction at each bad actual mean uphill or downhill on the SAME true continuous output target?',
        'state': 'Low2 are saved output-before mean_kappa, no grid rounding or Q22 hidden reference. Front high2 and rear complete Q1.10 codes equal original initial_codes. Rear Q3 separate offset/product nearest-even is retained. Front learning y*=sum(phi_j*kappa_j)/8-64*d1 with its own G2=abs(y*)>=128*kappa1, G1=1; no front Q3 or Q22 request.',
        'moments': 'C=E[d1*G*y*], A=E[d1*G*psi_low], b=E[d1*G*a_high], all full N denominator. Assert C=A*kappa_low+b. Reuse H and true gradient intervals/pd/tp from prior independently checked results; no target tables or MSE scoring.',
        'gate': 'Exact >= at rational mean. Gap=abs(abs(y_num)-1024*k1_num); rho=min gap/[D*(abs(phi1)+abs(phi2)+1024)] capped by legal low2 distances. Equality ->rho0; only positive radius permits A derivative/constant b in open cell. Old insufficient certificate is not presumed crossing.',
        'prediction': 'Direct D=g dot (-lambda diag(1,3)C), lambda=3072/(25*m*2^22). Positive certified D supports same-state target mismatch; negative certified D leaves actual weighted-history/time/gate/quantization explanation. Full-rank or nonzero C is not target correctness/root/arrival.',
        'metric': 'If A invertible, M=H*A^-1, S=sym(M^T diag(1,3)), w=M*C, r=g/2-w=pd-M*b-tp. Report Dmetric+Dr=D; S positivity and gate cell are distinct conditions. No inverse used to implement an online policy.',
        'main_limits': main, 'independent_limits': independent,
        'units': 'Scientific scalar binary add/sub/mul/div use wrappers (integer and Fraction distinguished from word kernels). All explicit outer vector add/sub/mul and reduction INPUTS charged before execution, including mask products. Rear PWL cell includes its internal segment/offset/product/sign/ties-to-even operations, not duplicated as vector ops; basis/tag/margin geometry cell units cover their fixed-scale operations. Fraction construction/parsing, fixed denominators/index/unary/compare/display/gcd excluded. Big matrix algebra uses Python Fraction/int, never NumPy integer-times-Fraction. Audit units, not chip costs.',
        'validation': 'Six fixed algebra controls/12 independent rear probes before records. Main integer dyadic y/gates/C/A/b, saved low bases exactly agree. Independent group DIGITAL q2/SAR/tags, scalar rear Fraction, four bases and rational y/gates reconstruct C/A/b/H/pd/rho without reading saved bases or main masks. Independent elimination verifies metric transform and derivative intervals.',
        'stop': 'Four whole-record same-state diagnoses or preserve failure. No block matrix sweep, new legal fixed readout, Q3 front/Q22 reference/request, actual learner, policy, roots, target precision chase, FFT or6007/8009.'})
    write(out/'preparation_accounting.json', {'fingerprint_bytes': sum(p.stat().st_size for p in files),
                                            'qualified_metadata_bytes': sum(p.stat().st_size for p in META if p.name in ('verification.json','independent_check.json','scalar_completion.json')),
                                            'new_scientific_word_calculations': 0})
    write(out/'controls.json', controls())
    print('Frozen four non-grid continuous means; target and old20 context reused.', flush=True)


def guard(out, q):
    assert digest(Path(__file__)) == digest(out/'frozen_analysis.py')
    for name, expected in load(out/'source_hashes.json').items():
        p = Path(name); q.charge('fingerprint_bytes', p.stat().st_size); assert digest(p) == expected, p


def inputs(q):
    values = {}
    for p in META:
        q.charge('metadata_json_bytes', p.stat().st_size); values[str(p)] = load(p)
    means = {(r['seed'],r['rate'],r['initialization']): r for r in values[str(MEAN/'results.json')]['rows']}
    infos = {(r['seed'],r['rate'],r['initialization']): r for r in values[str(INFO/'results.json')]['rows']}
    fixed = {(r['seed'],r['rate'],r['initialization']): r for r in values[str(ALIGN/'results.json')]['rows'] if r['reference'] == 'mean'}
    assert len(means) == 20 and {k for k,r in means.items() if F(r['position_J']['exact']) > 0} == set(CASES)
    return means, infos, fixed


def word_sources(q):
    out = {}
    for seed in (202610624,202610625):
        q.charge('source_values', N*3)
        out[seed] = np.array(np.memmap(OLD/f'both_smooth_{seed}_words.bin', dtype='i1', mode='r', shape=(65536,120,4))[START:START+W,:,1:], dtype=np.int64)
        assert np.all((out[seed][:,:,0] >= -4) & (out[seed][:,:,0] <= 4))
        assert np.all((out[seed][:,:,2] >= 0) & (out[seed][:,:,2] <= 3))
    return out


def diagnose(a, b, c, mean, info, q):
    low = list(map(F, mean['mean_kappa'])); ac = q.mv(a, low)
    assert [q.add(ac[j], b[j]) for j in range(2)] == c
    g = [F(z['exact']) for z in mean['gradient_L']]
    intervals = [list(map(F, z['interval'])) for z in mean['gradient_L']]
    mrate = 1 if mean['rate'] == 'base' else 4
    lam = F(3072, 25*mrate*(1 << 22))
    v = [q.mul(-lam, c[0]), q.mul(q.mul(-lam, F(3)), c[1])]
    derivative = q.dot(g, v); bounds = [F(0), F(0)]
    for j in range(2):
        values = [q.mul(z, v[j]) for z in intervals[j]]
        bounds[0] = q.add(bounds[0], min(values)); bounds[1] = q.add(bounds[1], max(values))
    det = q.sub(q.mul(a[0][0],a[1][1]),q.mul(a[0][1],a[1][0]))
    result = {'C': list(map(str,c)), 'A': [[str(z) for z in line] for line in a],
              'b': list(map(str,b)), 'A_determinant': str(det), 'A_rank': 2 if det else (1 if any(z for line in a for z in line) else 0),
              'C_nonzero': any(c), 'direction': list(map(str,v)), 'D': pack(derivative,bounds)}
    if det:
        h = [[F(z) for z in line] for line in mean['H']]
        m = [[q.div(q.sub(q.mul(line[0],a[1][1]),q.mul(line[1],a[1][0])),det),
              q.div(q.sub(q.mul(line[1],a[0][0]),q.mul(line[0],a[0][1])),det)] for line in h]
        for i in range(2):
            for j in range(2): assert q.dot(m[i], [a[0][j],a[1][j]]) == h[i][j]
        w = q.mv(m,c); r = [q.sub(q.div(g[j],F(2)),w[j]) for j in range(2)]
        mb = q.mv(m,b); rd = [q.sub(F(info['pd'][j]),mb[j]) for j in range(2)]
        assert [q.sub(rd[j],F(info['tp'][j])) for j in range(2)] == r
        sym = [[m[0][0], q.div(q.add(m[0][1],q.mul(F(3),m[1][0])),F(2))], [F(0),q.mul(F(3),m[1][1])]]
        sym[1][0] = sym[0][1]
        sd = q.sub(q.mul(sym[0][0],sym[1][1]),q.mul(sym[0][1],sym[1][0]))
        dm = q.mul(F(2),q.dot(w,v)); dr = q.mul(F(2),q.dot(r,v)); assert q.add(dm,dr) == derivative
        ri = [[q.sub(q.div(z,F(2)),w[j]) for z in intervals[j]] for j in range(2)]
        result['metric'] = {'M': [[str(z) for z in line] for line in m], 'w': list(map(str,w)),
            'r': list(map(str,r)), 'r_intervals': [[str(z) for z in line] for line in ri],
            'r_nonzero_certified': any(line[0] > 0 or line[1] < 0 for line in ri),
            'digital_residual': list(map(str,rd)), 'S': [[str(z) for z in line] for line in sym],
            'S_determinant': str(sd), 'S_positive_definite': sym[0][0] > 0 and sd > 0,
            'D_metric': pack(dm), 'D_residual': pack(dr, [q.sub(z,dm) for z in bounds])}
    return result


def analyze(out):
    assert not (out/'results.json').exists()
    q = Budget(load(out/'protocol.json')['main_limits']); done = []
    try:
        guard(out,q); means,infos,fixed = inputs(q); words = word_sources(q)
        for key in CASES:
            q.charge('case_objects'); mean = means[key]; k0 = fixed[key]['initial_codes']
            low = list(map(F,mean['mean_kappa'])); k = low+[F(z,1024) for z in k0[2:4]]
            den = lcm(*(z.denominator for z in k)); kn = [int(z.numerator*(den//z.denominator)) for z in k]
            ww = words[key[0]]; q2,sar,bits = (ww[:,:,j] for j in range(3))
            q.charge('tag_decode_cells',2*N); d,d2 = 2*(bits&1)-1,2*((bits>>1)&1)-1
            q.charge('rear_Q3_PWL_cells',N)
            rear = vector_rear(q.vm(8,sar),k0[4:])
            raw = q.vs(q.va(q.vm(1024,q2),rear),q.vm(128,d2)); assert np.all((raw >= -4096) & (raw < 4096))
            q.charge('basis_geometry_cells',4*N); phi = basis(raw)
            q.charge('basis_values',2*N)
            assert np.array_equal(phi[:,:,:2],np.fromfile(BASIS/f'{key[0]}_{key[1]}_{key[2]}_basis.bin',dtype='<i2').reshape(W,120,2))
            q.charge('front_continuous_cells',N)
            high = q.vs(q.va(q.vm(phi[:,:,2],kn[2]),q.vm(phi[:,:,3],kn[3])),q.vm(d,512*den))
            yn = q.va(q.va(q.vm(phi[:,:,0],kn[0]),q.vm(phi[:,:,1],kn[1])),high)
            q.charge('gate_tests',N); g2 = abs(yn) >= 1024*kn[0]
            z = [q.vm(d,phi[:,:,j]) for j in range(2)]
            aa = [[q.isum(z[j]) for j in range(2)], [q.isum(q.vm(z[j],g2)) for j in range(2)]]
            xc,xh = q.vm(d,yn),q.vm(d,high)
            cc = [q.isum(xc),q.isum(q.vm(xc,g2))]; bb = [q.isum(xh),q.isum(q.vm(xh,g2))]
            a = [[F(z,8*N) for z in line] for line in aa]; c = [F(z,8*N*den) for z in cc]; b = [F(z,8*N*den) for z in bb]
            gap = abs(q.vs(abs(yn),1024*kn[0])); lip = q.va(q.va(abs(phi[:,:,0]),abs(phi[:,:,1])),1024)
            pairs = np.unique(np.column_stack((gap.ravel(),q.vm(den,lip).ravel())),axis=0)
            q.charge('margin_ratio_cells',len(pairs))
            legal = min(low+[q.sub(F(2047,1024),z) for z in low])
            rho = min([F(int(a),int(b)) for a,b in pairs]+[legal])
            item = diagnose(a,b,c,mean,infos[key],q)
            done.append({'seed':key[0],'rate':key[1],'initialization':key[2],
                'continuous_kappa':list(map(str,k)), 'original_rear_codes':k0[4:],
                'rho_sufficient':str(rho),'open_continuous_cell_certified':rho > 0,
                'gate_equalities':int(np.count_nonzero(gap == 0)), 'gate2_count':int(np.count_nonzero(g2)),
                'actual_Q3_Q22_mapping_defined':False, **item})
            print(key,'D=',item['D']['value'],'certified=',item['D']['sign_certified'],'rho=',rho,flush=True)
        guard(out,q); write(out/'results.json',{'completed':True,'rows':done})
        write(out/'verification.json',{'passed':True,'cases':4,'same_state_C_A_b_and_gradient_exact':True,
            'saved_low_bases_match':True,'new_legal_readouts_Q3_front_Q22_requests_learning_scores_fft':0})
    except Exception:
        write(out/'partial_results.json',{'completed':False,'rows':done}); raise
    finally: q.accounting(out,'accounting_main.json',len(done) == 4)


def check(out):
    assert not (out/'independent_check.json').exists()
    q = Budget(load(out/'protocol.json')['independent_limits']); count = 0
    try:
        guard(out,q); means,infos,fixed = inputs(q); words = word_sources(q)
        q.charge('result_json_bytes',(out/'results.json').stat().st_size)
        results = {(r['seed'],r['rate'],r['initialization']):r for r in load(out/'results.json')['rows']}
        group_counts = []; rear_counts = []
        for key in CASES:
            q.charge('case_objects'); k0 = fixed[key]['initial_codes']; k = list(map(F,results[key]['continuous_kappa']))
            q.charge('group_word_inputs',N)
            cells,counts = np.unique(words[key[0]].reshape(N,3),axis=0,return_counts=True)
            vals = sorted(set(int(z[1]) for z in cells)); q.charge('rear_Fraction_PWL_cells',len(vals))
            lookup = {z:scalar_rear(z,k0[4:],q) for z in vals}
            sums_a = [[F(0),F(0)],[F(0),F(0)]]; sums_b = [F(0),F(0)]; sums_c = [F(0),F(0)]
            sums_h = [F(0)]*3; sums_pd = [F(0),F(0)]; rho = min(k[:2]+[q.sub(F(2047,1024),z) for z in k[:2]])
            ties = gate_count = 0
            for cell,multiplicity in zip(cells,counts):
                q.charge('digital_group_cells'); q2,sar,bits = map(int,cell); n = F(int(multiplicity)); d = 2*(bits&1)-1; d2 = 2*((bits>>1)&1)-1
                raw = q.sub(q.add(q.mul(1024,q2),lookup[sar]),q.mul(128,d2)); raw = int(raw)
                assert -4096 <= raw < 4096
                sg = 1 if raw >= 0 else -1
                psi = [F(sg*min(max(abs(raw)-1024*j,0),1024),8) for j in range(4)]
                high = q.sub(q.add(q.mul(psi[2],k[2]),q.mul(psi[3],k[3])),F(64*d))
                y = q.add(q.add(q.mul(psi[0],k[0]),q.mul(psi[1],k[1])),high)
                threshold = q.mul(F(128),k[0]); g = abs(y) >= threshold
                rho = min(rho,q.div(abs(q.sub(abs(y),threshold)),q.add(q.add(abs(psi[0]),abs(psi[1])),F(128))))
                if abs(y) == threshold: ties += int(multiplicity)
                if g: gate_count += int(multiplicity)
                for i,gate in enumerate((True,g)):
                    if gate:
                        weight = q.mul(n,F(d))
                        sums_c[i] = q.add(sums_c[i],q.mul(weight,y))
                        sums_b[i] = q.add(sums_b[i],q.mul(weight,high))
                        for j in range(2): sums_a[i][j] = q.add(sums_a[i][j],q.mul(weight,psi[j]))
                for i,(j,l) in enumerate(((0,0),(0,1),(1,1))): sums_h[i] = q.add(sums_h[i],q.mul(n,q.mul(psi[j],psi[l])))
                for j in range(2): sums_pd[j] = q.add(sums_pd[j],q.mul(n,q.mul(psi[j],high)))
            a = [[q.div(z,F(N)) for z in line] for line in sums_a]; b = [q.div(z,F(N)) for z in sums_b]; c = [q.div(z,F(N)) for z in sums_c]
            old = results[key]
            assert [[str(z) for z in line] for line in a] == old['A'] and list(map(str,b)) == old['b'] and list(map(str,c)) == old['C']
            assert str(rho) == old['rho_sufficient'] and ties == old['gate_equalities'] and gate_count == old['gate2_count']
            h = [q.div(z,F(N)) for z in sums_h]; hh = [[h[0],h[1]],[h[1],h[2]]]
            assert [[str(z) for z in line] for line in hh] == means[key]['H']
            assert [str(q.div(z,F(N))) for z in sums_pd] == infos[key]['pd']
            # Independent Gaussian elimination gives w, not main inverse algebra.
            if old['A_rank'] == 2:
                aa = [line.copy() for line in a]; rhs = c.copy()
                if not aa[0][0]: aa.reverse(); rhs.reverse()
                f = q.div(aa[1][0],aa[0][0]); pivot = q.sub(aa[1][1],q.mul(f,aa[0][1]))
                x1 = q.div(q.sub(rhs[1],q.mul(f,rhs[0])),pivot)
                x0 = q.div(q.sub(rhs[0],q.mul(aa[0][1],x1)),aa[0][0])
                ww = q.mv(hh,[x0,x1]); assert list(map(str,ww)) == old['metric']['w']
            # Independent output half-gradient from grouped DIGITAL H/pd and
            # the previously certified target projection, not main diagnose().
            pd = [q.div(z,F(N)) for z in sums_pd]
            hk = q.mv(hh,k[:2])
            gg = [q.mul(F(2),q.sub(q.add(hk[j],pd[j]),F(infos[key]['tp'][j]))) for j in range(2)]
            assert list(map(str,gg)) == [z['exact'] for z in means[key]['gradient_L']]
            mrate = 1 if key[1] == 'base' else 4
            vv = [q.mul(F(-3072*factor,25*mrate*(1 << 22)),c[j]) for j,factor in enumerate((1,3))]
            assert list(map(str,vv)) == old['direction']
            dd = q.total(q.mul(gg[j],vv[j]) for j in range(2))
            bounds = [q.total(q.mul(F(means[key]['gradient_L'][j]['interval'][end if vv[j] >= 0 else 1-end]),vv[j]) for j in range(2)) for end in (0,1)]
            assert pack(dd,bounds) == old['D']
            if old['A_rank'] == 2:
                dm = q.mul(F(2),q.total(q.mul(ww[j],vv[j]) for j in range(2)))
                dr = q.sub(dd,dm)
                assert str(dm) == old['metric']['D_metric']['exact']
                assert pack(dr,[q.sub(z,dm) for z in bounds]) == old['metric']['D_residual']
                rr = [q.sub(q.div(gg[j],F(2)),ww[j]) for j in range(2)]
                assert list(map(str,rr)) == old['metric']['r']
                mm = [[F(z) for z in line] for line in old['metric']['M']]
                for i in range(2):
                    for j in range(2): assert q.total(q.mul(mm[i][l],a[l][j]) for l in range(2)) == hh[i][j]
                ss = [[mm[0][0],q.div(q.add(mm[0][1],q.mul(F(3),mm[1][0])),F(2))],[F(0),q.mul(F(3),mm[1][1])]]
                ss[1][0] = ss[0][1]
                sd = q.sub(q.mul(ss[0][0],ss[1][1]),q.mul(ss[0][1],ss[1][0]))
                assert [[str(z) for z in line] for line in ss] == old['metric']['S']
                assert str(sd) == old['metric']['S_determinant']
                assert (ss[0][0] > 0 and sd > 0) == old['metric']['S_positive_definite']
            group_counts.append(len(cells)); rear_counts.append(len(vals)); count += 1
        guard(out,q)
        write(out/'independent_check.json',{'passed':True,'cases':count,
            'grouped_scalar_C_A_b_H_pd_gate_radius_exact':True,
            'independent_elimination_and_direction_intervals_exact':True,
            'group_cells_per_case':group_counts,'rear_scalar_lookups_per_case':rear_counts,
            'no_saved_basis_or_main_masks_read':True})
        rows = list(results.values())
        write(out/'summary.json',{'passed':True,'cases':4,
            'uphill':sum(F(r['D']['exact']) > 0 for r in rows),'downhill':sum(F(r['D']['exact']) < 0 for r in rows),
            'certified':sum(r['D']['sign_certified'] for r in rows),
            'rank2':sum(r['A_rank'] == 2 for r in rows),'positive_rho':sum(r['open_continuous_cell_certified'] for r in rows),
            'positive_definite_metric':sum(r.get('metric',{}).get('S_positive_definite',False) for r in rows),
            'all20_context_retained':True,'new_legal_integer_readouts_or_paths':0})
    finally: q.accounting(out,'accounting_independent.json',count == 4)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('mode',choices=['freeze','analyze','check'])
    parser.add_argument('--out',type=Path,required=True); args = parser.parse_args()
    try: {'freeze':freeze,'analyze':analyze,'check':check}[args.mode](args.out)
    except Exception:
        if args.out.exists(): write(args.out/(args.mode+'_failure.json'),{'traceback':traceback.format_exc()})
        raise
