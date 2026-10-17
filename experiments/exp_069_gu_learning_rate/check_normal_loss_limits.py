"""D-129: frozen read-only normal-path diagnostics, never a new learner.

Full intervals reuse saved scores; six prespecified complete blocks receive
legal reference readouts and finite current-word information certificates.
"""

import argparse
from collections import defaultdict
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import shutil
import traceback

import numpy as np

from adc_research.theory.finite_observation_limits import observation_loss, reference_loss
from adc_research.theory.joint_selection_output import four_grid_loss
from adc_research.theory.static_fixed_contract import export, nearest_even, readout
from experiments.exp_062_same_input_background.verify import digital, pwl_scaled, round_ratio

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT/'artifacts/runs/EXP_062/background_v1'
NEW = ROOT/'artifacts/runs/EXP_069/background_v1'
N = 30720
NW = 65536
INTERVALS = {'startup': (0,24,(0,8,16)), 'tail': (128,256,(128,184,248))}
DOCS = ['docs/STATUS.md', 'docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md',
        'docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md',
        'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md', 'docs/theory/README.md',
        'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
        'docs/reports/GU_ALGORITHM_EVALUATION_V1.md',
        'docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md']


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def digest(path):
    h = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4*1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def relative(path):
    return path.relative_to(ROOT).as_posix()


def verify_hashes(manifest):
    for name, expected in manifest.items():
        assert digest(ROOT/name) == expected, name


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=False)
    protocol = {
        'version': 'D129-normal-loss-limits-read-only-v1', 'date': '2026-10-12',
        'authority': 'D-129 tasks1/2/3; user asks to continue approved plan',
        'cases': ['ideal','both_linear','both_smooth'],
        'seeds': list(range(202610621,202610626)),
        'rates': ['quarter','half','base','double'], 'methods': ['point30','full120'],
        'paths': 120, 'intervals': INTERVALS,
        'block_selection': 'First complete30720-code block of first/middle/last eight-block group. Startup groups0/1/2; tail groups0/7/15. Zero-based blocks0,8,16,128,184,248. Never selected from scores.',
        'full_score_blocks': 120*(24+128), 'sample_actual_codes': 120*6*N,
        'source_word_records': 15*6*N, 'unit_readouts': 15*6*N,
        'additional_reference_readouts': 120*6*N*9,
        'references': ['nearest-even mean hidden Q22 over FULL interval window-start states',
                       'nearest-even mean exported Q1.10 over FULL interval, embedded as legal Q22',
                       'actual window-start state at middle conversion of FULL interval'],
        'four_grids': '00 actual;10 reference front/actual rear;01 actual front/reference rear;11 both reference. Every grid uses SAME words and full Q3/integer arithmetic. No gate or segment protection is silently imposed.',
        'target': 'Exact binary64 value of2048*(1+stored tone), matching old real ideal-level scoring. FINAL output is integer; target is NOT floor/rounded code. All targets offline.',
        'information': 'Current five fields q1,q2,SAR,d1,d2 only, bijectively packed as four stored bytes; no phase, global index, state or history. Exact empirical integer-map optimum per seed/model/interval on THREE selected blocks; not a causal online/population bound.',
        'static_capacity': 'Same-record empirical Gu fixed-state optimum bracket: exact word-only lower certificate and minimum feasible legal reference/unit loss over all declared paths. No optimizer/global Gu optimum or generalization claim.',
        'scalar_probes': 'First/middle/last word of EACH selected block and all three references/four grids; rational readout, exact four-grid/reference identities; first120-word window per block also compared with old digital verifier.',
        'scalar_readout_budget': 120*6*3*3*4,
        'precision': 'Exact integer loss lower-bound certificate with dyadic targets; float64 centered descriptive moments checked within1e-8. Exact Fraction controls at prescribed probes. FFT not computed.',
        'predictions': ['actual corner exactly equals stored output; all references legal',
                        'reference decomposition retains signed cross and loss interaction',
                        'integer-map lower certificate is no greater than each legal static reference',
                        'online outputs need not be a fixed map of current words; covariance cannot be discarded',
                        'triangular diagonal contraction alone permits transient front growth and does not imply output benefit'],
        'stopping': 'Fixed blocks/references/all seeds. Preserve any failure; no generated substitutes, new learning or extension.',
        'new_adc_conversions': 0, 'new_learning_observations': 0,
        'new_online_outputs': 0, 'new_fft': 0,
        'limits': 'Seen static controls. Switch/dynamic and new holdouts remain later steps; sampled block effects do not provide unique whole-tail causal percentages.',
    }
    write(folder/'protocol.json', protocol)
    manifest = {}
    for source, names in ((OLD, ['tone.bin','protocol.json']),
                          (NEW, ['protocol.json','analysis.json','summary.json'])):
        expected = load(source/'delivery_hashes.json')
        names = list(names)
        for case in protocol['cases']:
            for seed in protocol['seeds']:
                stem = f'{case}_{seed}'
                if source == OLD:
                    names += [stem+'_words.bin',stem+'_outputs.bin']
                    names += [stem+'_'+m+'_q22.bin' for m in protocol['methods']]
                else:
                    names += [stem+'.json',stem+'_outputs.bin']
                    names += [stem+'_'+r+'_'+m+'_q22.bin' for r in ('quarter','half','double') for m in protocol['methods']]
        for name in names:
            path = source/name
            assert path.is_file(), relative(path)
            manifest[relative(path)] = expected[name]
    write(folder/'original_data_hashes.json', manifest)
    for name in DOCS:
        dest = folder/'documents_before'/name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/name, dest)
    sources = ['experiments/exp_069_gu_learning_rate/check_normal_loss_limits.py',
               'experiments/exp_062_same_input_background/verify.py',
               'src/adc_research/theory/static_fixed_contract.py',
               'src/adc_research/theory/finite_observation_limits.py',
               'src/adc_research/theory/triangular_cascade_bounds.py',
               'src/adc_research/theory/joint_selection_output.py',
               'tests/test_finite_observation_limits.py']
    write(folder/'execution_hashes.json', {name:digest(ROOT/name) for name in sources})
    verify_hashes(manifest)
    print('Frozen:120 paths,six blocks/each,three legal references; original files verified', flush=True)


def output_only(words, acc):
    q1,q2,be,bits = (words[:,:,i].astype(np.int64) for i in range(4))
    d1,d2 = 2*(bits&1)-1,2*((bits>>1)&1)-1
    k = round_ratio(acc,4096)
    assert np.all((k >= 0)&(k <= 2047))
    p2 = pwl_scaled(8*be,k[:,4:],32)
    raw1 = 1024*q2+p2-128*d2
    y1 = pwl_scaled(raw1,k[:,:4],128)-512*d1
    y = round_ratio(16384+4096*q1+y1,8)
    assert np.all((y >= 0)&(y <= 4095))
    return y


def info_certificate(keys, scaled_targets, denominator):
    stats = defaultdict(lambda:[0,0,0])
    for key,t in zip(keys,scaled_targets,strict=True):
        s = stats[int(key)]
        s[0] += 1; s[1] += t; s[2] += t*t
    total = 0
    for n,s,q in stats.values():
        a,r = divmod(s,n*denominator)
        best = min(4095,max(0,a+int(2*r > n*denominator or
                                   (2*r == n*denominator and a%2))))
        total += q-2*best*denominator*s+n*(best*denominator)**2
    den = len(keys)*denominator**2
    return {'count':len(keys), 'groups':len(stats),
            'lower_numerator':str(total), 'lower_denominator':str(den),
            'information_mse':float(F(total,den))}


def conditional_terms(keys, target, output):
    _, inverse = np.unique(keys,return_inverse=True)
    count = np.bincount(inverse)
    # A fixed integer anchor per group prevents cancellation of large code squares.
    _, first = np.unique(inverse,return_index=True)
    anchor = np.floor(target[first])
    dt,dy = target-anchor[inverse],output-anchor[inverse]
    mt = np.bincount(inverse,weights=dt)/count
    my = np.bincount(inverse,weights=dy)/count
    ct,cy = dt-mt[inverse],dy-my[inverse]
    vt,vy,cov,mean_error = (float(np.mean(ct*ct)),float(np.mean(cy*cy)),
                          float(np.mean(ct*cy)),float(np.mean((my-mt)[inverse]**2)))
    loss = float(np.mean((output-target)**2))
    assert abs(loss-(vt+vy-2*cov+mean_error)) < 1e-8
    return {'target_variance':vt,'output_variance':vy,'target_output_covariance':cov,
            'conditional_mean_error_square':mean_error,'actual_mse':loss,
            'fixed_current_word_mapping':vy == 0}


def analyze(folder):
    assert not (folder/'results.json').exists()
    p = load(folder/'protocol.json')
    assert p['intervals'] == {k:list((a,b,list(c))) for k,(a,b,c) in INTERVALS.items()}
    verify_hashes(load(folder/'execution_hashes.json'))
    verify_hashes(load(folder/'original_data_hashes.json'))
    prior = load(NEW/'analysis.json')['paths']
    assert len(prior) == 120
    prior = {(r['case'],r['seed'],r['rate'],r['method']):r for r in prior}
    tone = np.fromfile(OLD/'tone.bin',dtype='<f8')
    target = 2048*(1+tone)
    ratios = [float(t).as_integer_ratio() for t in target]
    denominator = max(d for _,d in ratios)
    scaled = [a*(denominator//d) for a,d in ratios]
    rows, capacity, exact_controls = [],[],[]
    actual_codes = additional = scalar_reads = vector_probes = 0
    max_score_difference = 0.0
    for case in p['cases']:
        for seed in p['seeds']:
            stem = f'{case}_{seed}'
            meta = load(NEW/(stem+'.json'))
            words = np.memmap(OLD/(stem+'_words.bin'),dtype='i1',mode='r',shape=(NW,120,4))
            old = np.memmap(OLD/(stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(NW,120,3))
            new = np.memmap(NEW/(stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(NW,120,6))
            for interval,(start,stop,blocks) in INTERVALS.items():
                sample_words = np.concatenate([words[b*256:(b+1)*256] for b in blocks])
                unit = output_only(sample_words,np.full((768,8),1 << 22,dtype=np.int64)).ravel()
                unit_saved = np.concatenate([old[b*256:(b+1)*256,:,0].ravel() for b in blocks])
                assert np.array_equal(unit,unit_saved)
                target3 = np.tile(target,3)
                q1,q2,be,bits = (sample_words[:,:,i].ravel().astype(np.int64) for i in range(4))
                keys = (((q1+4)*9+(q2+4))*256+(be+128))*4+bits
                certificate = info_certificate(keys,scaled*3,denominator)
                candidates = [('unit',float(np.mean((unit-target3)**2)))]
                assert candidates[0][1]+1e-8 >= certificate['information_mse']
                for rate in p['rates']:
                    for method in p['methods']:
                        pathname = rate+'_'+method
                        if rate == 'base':
                            state = np.memmap(OLD/(stem+'_'+method+'_q22.bin'),dtype='<f8',mode='r',shape=(NW+1,8))
                            hidden = np.rint(np.asarray(state[start*256:stop*256])*(1 << 22)).astype(np.int64)
                            acc = np.concatenate([np.rint(np.asarray(state[b*256:(b+1)*256])*(1 << 22)).astype(np.int64) for b in blocks])
                            saved = np.concatenate([old[b*256:(b+1)*256,:,1+p['methods'].index(method)].ravel() for b in blocks])
                        else:
                            state = np.memmap(NEW/(stem+'_'+pathname+'_q22.bin'),dtype='<i4',mode='r',shape=(NW+1,8))
                            hidden = np.asarray(state[start*256:stop*256],dtype=np.int64)
                            acc = np.concatenate([np.asarray(state[b*256:(b+1)*256],dtype=np.int64) for b in blocks])
                            saved = np.concatenate([new[b*256:(b+1)*256,:,meta['Paths'].index(pathname)].ravel() for b in blocks])
                        effective = round_ratio(hidden,4096)
                        refs = {'mean_hidden':round_ratio(hidden.sum(axis=0),len(hidden)),
                                'mean_export':round_ratio(effective.sum(axis=0),len(hidden))*4096,
                                'middle_state':hidden[len(hidden)//2]}
                        y = output_only(sample_words,acc).ravel()
                        assert np.array_equal(y,saved),(stem,pathname,interval)
                        actual_codes += len(y)
                        # Compare output-only algebra with existing vector replay at each block prefix.
                        for i in (0,256,512):
                            assert np.array_equal(output_only(sample_words[i:i+1],acc[i:i+1]),
                                                  digital(sample_words[i:i+1],acc[i:i+1])[0])
                            vector_probes += 120
                        record = prior[case,seed,rate,method]
                        scores = record['block_scores'][start:stop]
                        mse = float(np.mean([s['mse_codes_squared'] for s in scores]))
                        dc = np.array([s['mean_error_codes'] for s in scores])
                        full = {'mse':mse,'dc_square':float(dc.mean()**2),
                                'block_mean_variance':float(np.var(dc)),
                                'within_block_error_variance':float(np.mean([s['mse_codes_squared'] for s in scores])-np.mean(dc*dc))}
                        assert abs(mse-sum(v for k,v in full.items() if k != 'mse')) < 1e-8
                        sample_mse = np.mean([record['block_scores'][b]['mse_codes_squared'] for b in blocks])
                        max_score_difference = max(max_score_difference,abs(float(np.mean((y-target3)**2))-sample_mse))
                        row = {'case':case,'seed':seed,'rate':rate,'method':method,'interval':interval,
                               'full_interval':full,'conditional_current_word':conditional_terms(keys,target3,y),
                               'export_mean_vs_hidden_mean_coordinates':int(np.count_nonzero(round_ratio(refs['mean_hidden'],4096)!=refs['mean_export']//4096)),
                               'references':{}}
                        for name,ref in refs.items():
                            grids = [y]
                            banks = (np.column_stack((np.broadcast_to(ref[:4],(768,4)),acc[:,4:])),
                                     np.column_stack((acc[:,:4],np.broadcast_to(ref[4:],(768,4)))),
                                     np.broadcast_to(ref,(768,8)))
                            for bank in banks:
                                grids.append(output_only(sample_words,bank).ravel())
                                additional += len(y)
                            losses = [float(np.mean((z-target3)**2)) for z in grids]
                            x,z,c = grids[1]-y,grids[2]-y,grids[3]-grids[1]-grids[2]+y
                            e = y-target3
                            interaction = float(np.mean(2*x*z+2*e*c+2*x*c+2*z*c+c*c))
                            assert abs((losses[3]-losses[1]-losses[2]+losses[0])-interaction) < 1e-8
                            d = y-grids[3]; er = grids[3]-target3
                            power = float(np.mean(d*d)); cross = float(2*np.mean(er*d))
                            assert abs(losses[0]-losses[3]-power-cross) < 1e-8
                            assert losses[3]+1e-8 >= certificate['information_mse']
                            candidates.append((pathname+'/'+name,losses[3]))
                            row['references'][name] = {'state_q22':list(map(int,ref)),
                                'losses_00_10_01_11':losses,'actual_minus_reference':losses[0]-losses[3],
                                'displacement_power':power,'reference_error_cross':cross,
                                'loss_interaction':interaction,'output_interaction_nonzero':int(np.count_nonzero(c)),
                                'output_interaction_maximum':int(np.max(np.abs(c)))}
                            positions = [i*N+j for i in range(3) for j in (0,N//2,N-1)]
                            exact_grids = [[] for _ in range(4)]
                            for pos in positions:
                                w,j = divmod(pos,120)
                                word = tuple(map(int,sample_words[w,j]))
                                aa = tuple(map(int,acc[w])); rr = tuple(map(int,ref))
                                for h,state_tuple in enumerate((aa,rr[:4]+aa[4:],aa[:4]+rr[4:],rr)):
                                    k = tuple(F(a,1024) for a in export(state_tuple))
                                    value = nearest_even(readout(word[0],word[1],F(word[2]),2*(word[3]&1)-1,
                                        2*((word[3]>>1)&1)-1,k,data_q3=True).output)
                                    assert value == int(grids[h][pos])
                                    exact_grids[h].append(value);scalar_reads += 1
                            ts = tuple(F(float(target3[pos])) for pos in positions)
                            exact = four_grid_loss(*exact_grids,ts)
                            reference_loss(exact_grids[0],exact_grids[3],ts)
                            exact_info = observation_loss(tuple(int(keys[pos]) for pos in positions),ts,tuple(exact_grids[3]))
                            small = info_certificate(keys[positions],[scaled[pos%N] for pos in positions],denominator)
                            assert F(int(small['lower_numerator']),int(small['lower_denominator'])) == exact_info.information_bound
                            exact_controls.append(str(exact.loss_interaction))
                        rows.append(row)
                best_name,best = min(candidates,key=lambda v:v[1])
                capacity.append({'case':case,'seed':seed,'interval':interval,**certificate,
                                 'upper_mse':best,'upper_reference':best_name,'interval_width':best-certificate['information_mse'],
                                 'candidates':candidates})
            print('checked',stem,'all eight paths,startup/tail',flush=True)
    assert actual_codes == p['sample_actual_codes']
    assert additional == p['additional_reference_readouts']
    assert scalar_reads == p['scalar_readout_budget']
    assert max_score_difference < 1e-8
    groups = []
    for case in p['cases']:
        for method in p['methods']:
            for rate in p['rates']:
                for interval in INTERVALS:
                    rr = [r for r in rows if (r['case'],r['method'],r['rate'],r['interval']) == (case,method,rate,interval)]
                    assert len(rr) == 5
                    mean = lambda f:float(np.mean([f(r) for r in rr]))
                    groups.append({'case':case,'method':method,'rate':rate,'interval':interval,
                        'full_mse':mean(lambda r:r['full_interval']['mse']),
                        'full_dc_square':mean(lambda r:r['full_interval']['dc_square']),
                        'sample_mse':mean(lambda r:r['conditional_current_word']['actual_mse']),
                        'conditional_output_variance':mean(lambda r:r['conditional_current_word']['output_variance']),
                        'conditional_target_output_covariance':mean(lambda r:r['conditional_current_word']['target_output_covariance']),
                        'reference_mse':mean(lambda r:r['references']['mean_export']['losses_00_10_01_11'][3]),
                        'actual_minus_reference':mean(lambda r:r['references']['mean_export']['actual_minus_reference']),
                        'displacement_power':mean(lambda r:r['references']['mean_export']['displacement_power']),
                        'reference_error_cross':mean(lambda r:r['references']['mean_export']['reference_error_cross']),
                        'loss_interaction':mean(lambda r:r['references']['mean_export']['loss_interaction']),
                        'reference_loss_range_mean':mean(lambda r:max(v['losses_00_10_01_11'][3] for v in r['references'].values())-min(v['losses_00_10_01_11'][3] for v in r['references'].values()))})
    verify_hashes(load(folder/'original_data_hashes.json'))
    verify_hashes(load(folder/'execution_hashes.json'))
    result = {'groups':groups,'paths':rows,'static_capacity':capacity,
              'validation':{'actual_saved_codes_equal':actual_codes,'additional_reference_integer_readouts':additional,
                'unit_integer_readouts':p['unit_readouts'],'exact_rational_readouts':scalar_reads,
                'exact_four_grid_reference_information_controls':len(exact_controls),
                'old_vector_output_probe_codes':vector_probes,'full_saved_score_blocks':p['full_score_blocks'],
                'maximum_sample_score_difference':max_score_difference,
                'original_data_files_unchanged':len(load(folder/'original_data_hashes.json')),
                'execution_files_unchanged':len(load(folder/'execution_hashes.json')),
                'new_adc_conversions':0,'new_learning_observations':0,'new_online_outputs':0,'new_fft':0}}
    write(folder/'results.json',result)
    write(folder/'summary.json',{'groups':groups,'static_capacity':capacity,'validation':result['validation']})
    print(json.dumps(result['validation']),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder',type=Path)
    parser.add_argument('--prepare',action='store_true')
    args = parser.parse_args()
    try:
        if args.prepare: prepare(args.folder)
        else: analyze(args.folder)
    except Exception:
        if args.folder.exists():
            (args.folder/'failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
