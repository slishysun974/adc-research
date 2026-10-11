"""Predeclared read-only two-bank moment checks on delivered EXP-068 words.

This adds neither conversions nor training. Boundary polynomial values are
kept; derivative and finite-intervention checks have separate domain flags.
"""
import argparse
from dataclasses import replace
from fractions import Fraction as F
from hashlib import sha256
import json
from pathlib import Path
import traceback

import numpy as np

from adc_research.calibration.observation import DigitalCalibrationSample as Sample
from adc_research.theory.cascade_mean_output import cascade_loss_change
from adc_research.theory.coupled_stationarity import coupled_moments, correlation_polynomial_change
from adc_research.theory.static_fixed_contract import basis, export, nearest_even, readout
from adc_research.theory.window_mean_map import analyze_window_mean, certify_mean_cell

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT/'artifacts/runs/EXP_068/background_v1'
SOURCES = (
    'src/adc_research/theory/coupled_stationarity.py',
    'src/adc_research/theory/gated_mean_objective.py',
    'src/adc_research/theory/cascade_mean_output.py',
    'src/adc_research/theory/window_mean_map.py',
    'src/adc_research/theory/static_fixed_contract.py',
    'src/adc_research/calibration/observation.py',
    'tests/test_coupled_stationarity.py',
    'experiments/exp_068_dynamic_background/check_coupled_stationarity.py',
)


def digest(path):
    h = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def vector(values):
    return [str(x) for x in values]


def prepare(folder):
    folder.mkdir(parents=True, exist_ok=False)
    old = json.loads((DATA/'protocol.json').read_text(encoding='utf-8-sig'))
    n = old['budget']['windows_per_path']
    write(folder/'protocol.json', {
        'scope': 'Approved T3/T4 joint correlation/stationarity and visible-information conditions; old records only.',
        'source_data': str(DATA.relative_to(ROOT)),
        'source_protocol_sha256': digest(DATA/'protocol.json'),
        'cases': [c['name'] for c in old['cases']], 'histories': ['reset','hold'],
        'seeds': old['seeds'], 'methods': [m['name'] for m in old['methods']],
        'windows': [0,n//2-1,n-1], 'candidate_rows': 21600,
        'learning_laws': ['full_120','first_four'], 'evaluation_law': 'full_120',
        'joint_delta_rear_front': ['1/2048','-1/4096','1/8192','-1/8192',
                                  '-1/2048','1/4096','-1/8192','1/8192'],
        'target': '2048*(1+exact stored double tone), offline scoring only.',
        'prediction': 'C=E[V e]+leakage and analytic block-triangular correlation matrix agree exactly; Gram+residual curvature gives the quadratic loss term. Preserve cubic/quartic terms.',
        'boundaries': 'Keep every point moment. Flag open output and gate cells separately. Finite loss excludes original front selector/domain boundaries and segment-crossing rows; finite actual C tested only in certified whole-window protected cells.',
        'acceptance': 'All exact identities, saved Q3 integer outputs and independent continuous readouts agree; all original source and used data hashes unchanged.',
        'interpretation': 'Old state-dependent empirical windows do not identify fixed-state population roots, stationary laws, causal future gain, PRNG balance or chip behavior. No target feedback, root fitting, tuning or scan.',
    })
    write(folder/'source_hashes.json', {name:digest(ROOT/name) for name in SOURCES})


def run(folder):
    protocol = json.loads((folder/'protocol.json').read_text(encoding='utf-8'))
    sources = json.loads((folder/'source_hashes.json').read_text(encoding='utf-8'))
    assert all(digest(ROOT/name) == value for name,value in sources.items())
    assert digest(DATA/'protocol.json') == protocol['source_protocol_sha256']
    assert json.loads((DATA/'delivery_validation.json').read_text())['passed']
    frozen = {str(Path(entry['Path']).relative_to(ROOT)):entry['Hash'].lower()
              for entry in json.loads((DATA/'source_hashes.json').read_text(encoding='utf-8-sig'))}
    assert all(digest(ROOT/name) == value for name,value in frozen.items())
    delivery = json.loads((DATA/'delivery_hashes.json').read_text())
    used = {'protocol.json','tone.bin'}
    for case in protocol['cases']:
        for history in protocol['histories']:
            for seed in protocol['seeds']:
                stem = f'{case}_{history}_{seed}'
                used.update((stem+'_words.bin',stem+'_outputs.bin'))
                used.update(stem+'_'+method+'_q22.bin' for method in protocol['methods'])
    hashes = {name:digest(DATA/name) for name in sorted(used)}
    assert all(value == delivery[name] for name,value in hashes.items())
    write(folder/'data_hashes.json',hashes)
    old = json.loads((DATA/'protocol.json').read_text(encoding='utf-8-sig'))
    n = old['budget']['windows_per_path']
    tone = np.fromfile(DATA/'tone.bin',dtype='<f8')
    delta = tuple(F(x) for x in protocol['joint_delta_rear_front'])
    radius = max(abs(x) for x in delta)
    paths = []
    boundary_total, crossing_total, finite_total, protected_windows = 0,0,0,0
    for case in protocol['cases']:
        for history in protocol['histories']:
            for seed in protocol['seeds']:
                stem = f'{case}_{history}_{seed}'
                words = np.memmap(DATA/(stem+'_words.bin'),dtype='i1',mode='r',shape=(n,120,4))
                outputs = np.memmap(DATA/(stem+'_outputs.bin'),dtype='<i2',mode='r',shape=(n,120,3))
                for mi,method in enumerate(protocol['methods']):
                    states = np.memmap(DATA/(stem+'_'+method+'_q22.bin'),dtype='<f8',mode='r',shape=(n+1,8))
                    probes = []
                    for w in protocol['windows']:
                        samples = tuple(Sample(int(q1),int(q2),int(be),2*(int(bits)&1)-1,2*((int(bits)>>1)&1)-1)
                                        for q1,q2,be,bits in words[w])
                        acc = tuple(map(int,np.rint(states[w]*(1 << 22))))
                        front_rear = tuple(F(c,1024) for c in export(acc))
                        k = front_rear[4:]+front_rear[:4]
                        mean = analyze_window_mean(samples,k)
                        end_k = tuple(a+b for a,b in zip(k,delta))
                        coarse = tuple(F(2048+512*s.stage1_symbol) for s in samples)
                        targets = tuple(2048*(1+F.from_float(float(tone[(w*120+i)%len(tone)]))) for i in range(120))
                        direct_old, direct_end, products, jacobians = [],[],[],[]
                        for i,(s,row) in enumerate(zip(samples,mean.rows)):
                            args = (s.stage1_symbol,s.stage2_symbol,F(s.backend_centered_code),
                                    s.stage1_dither_symbol,s.stage2_dither_symbol)
                            actual = readout(*args,front_rear,data_q3=True)
                            base = readout(*args,front_rear,data_q3=False)
                            end = readout(*args,end_k[4:]+end_k[:4],data_q3=False)
                            assert nearest_even(actual.output) == int(outputs[w,i,mi+1])
                            assert (base.raw1,base.y1,base.y2) == (row.raw1,row.local1,row.local2)
                            direct_old.append(base); direct_end.append(end)
                            products.append(tuple(row.dither2*base.y2*int(g) for g in base.gates[1])+
                                            tuple(row.dither1*base.y1*int(g) for g in base.gates[0]))
                            j = min(int(abs(base.raw1)//128),3)
                            jacobians.append(tuple(k[4+j]*x for x in basis(F(s.backend_centered_code),32))+
                                             basis(base.raw1,128))
                        laws = []
                        for learn in (None,(1,)*4+(0,)*116):
                            m = coupled_moments(mean,coarse,targets,learning_weights=learn)
                            indices = range(120) if learn is None else range(4)
                            expected_c = tuple(sum((products[i][j] for i in indices),F(0))/len(indices) for j in range(8))
                            assert m.correlations == expected_c
                            assert all(c == a+b for c,a,b in zip(m.correlations,m.target_leakage,m.instrument_residual))
                            assert m.output_jacobians == tuple(jacobians)
                            errors = tuple(a.output-t for a,t in zip(direct_old,targets))
                            assert m.errors == errors
                            assert m.mse == sum((e*e for e in errors),F(0))/120
                            assert m.output_cross_moment == tuple(sum((e*j[a] for e,j in zip(errors,jacobians)),F(0))/120 for a in range(8))
                            if learn is None:
                                assert m.correlation_jacobian == mean.fixed_mask_jacobian
                            for a in range(8):
                                for b in range(8):
                                    direct_g = sum((j[a]*j[b] for j in jacobians),F(0))/120
                                    assert m.gram[a][b] == direct_g
                                    assert m.half_loss_hessian[a][b] == direct_g+m.residual_curvature[a][b]
                            laws.append({'learning':'full_120' if learn is None else 'first_four',
                                'C':vector(m.correlations),'target_leakage':vector(m.target_leakage),
                                'instrument_residual':vector(m.instrument_residual),
                                'correlation_matrix':[vector(row) for row in m.correlation_jacobian]})
                            if learn is None:
                                full = m
                        valid, boundaries, crossings = [],[],[]
                        for i,(row,end) in enumerate(zip(mean.rows,direct_end)):
                            if row.selector_margin1 == 0 or row.domain_margin1 == 0:
                                boundaries.append(i)
                            else:
                                v = sum((a*b for a,b in zip(row.basis2,delta[:4])),F(0))
                                predicted = tuple(x+(v if j == row.selector1 else 0) for j,x in enumerate(row.basis1))
                                if basis(end.raw1,128) != predicted:
                                    crossings.append(i)
                                else:
                                    valid.append(i)
                        finite = None
                        if valid:
                            subset = replace(mean,rows=tuple(mean.rows[i] for i in valid))
                            sm = coupled_moments(subset,tuple(coarse[i] for i in valid),tuple(targets[i] for i in valid))
                            change = cascade_loss_change(subset,delta,sm.errors)
                            exact_difference = sum(((direct_end[i].output-targets[i])**2-(direct_old[i].output-targets[i])**2
                                                    for i in valid),F(0))/len(valid)
                            quadratic = 2*sum((g*h for g,h in zip(sm.output_cross_moment,delta)),F(0))+sum(
                                (delta[a]*sm.half_loss_hessian[a][b]*delta[b] for a in range(8) for b in range(8)),F(0))
                            assert exact_difference == change.mse_difference
                            assert exact_difference == quadratic+change.linear_bilinear_cross+change.bilinear_square
                            finite = {'rows':len(valid),'quadratic':str(quadratic),'cubic':str(change.linear_bilinear_cross),
                                      'quartic':str(change.bilinear_square),'mse_difference':str(exact_difference)}
                        protected = certify_mean_cell(mean,radius).all_masks_and_domains_stable
                        if protected:
                            end_mean = analyze_window_mean(samples,end_k)
                            assert tuple(b-a for a,b in zip(full.correlations,end_mean.mean_products)) == correlation_polynomial_change(full,delta)
                            protected_windows += 1
                        boundary_total += len(boundaries); crossing_total += len(crossings); finite_total += len(valid)
                        probes.append({'window':w,'output_derivative_regular':full.output_derivative_regular,
                            'correlation_derivative_regular':full.correlation_derivative_regular,
                            'whole_window_protected_for_delta':protected,'base_boundary_rows':boundaries,'crossing_rows':crossings,
                            'g':vector(full.output_cross_moment),'gram':[vector(row) for row in full.gram],
                            'residual_curvature':[vector(row) for row in full.residual_curvature],
                            'half_loss_hessian':[vector(row) for row in full.half_loss_hessian],
                            'finite_continuous_loss':finite,'laws':laws})
                    paths.append({'case':case,'history':history,'seed':seed,'method':method,'probes':probes})
                    print('checked',stem,method,flush=True)
    assert all(digest(ROOT/name) == value for name,value in frozen.items())
    assert all(digest(ROOT/name) == value for name,value in sources.items())
    assert all(digest(DATA/name) == value for name,value in hashes.items())
    write(folder/'analysis.json',{'paths':paths})
    probes = [probe for path in paths for probe in path['probes']]
    assert len(probes)*120 == protocol['candidate_rows']
    validation = {'passed':True,'paths':len(paths),'window_probes':len(probes),'rows':len(probes)*120,
        'coupled_learning_laws':len(probes)*2,'q3_readouts_and_saved_integer_codes':len(probes)*120,
        'continuous_old_new_readouts':len(probes)*240,'finite_loss_rows':finite_total,
        'base_boundary_rows':boundary_total,'segment_crossing_rows':crossing_total,
        'open_output_windows':sum(p['output_derivative_regular'] for p in probes),
        'open_correlation_windows':sum(p['correlation_derivative_regular'] for p in probes),
        'certified_whole_window_correlation_changes':protected_windows,'exact_identity_residual':'0',
        'old_source_files_verified':len(frozen),'used_data_files_hashed':len(hashes),
        'new_conversions':0,'training':False,'frozen_sources_unchanged':True,'scope':protocol['interpretation']}
    write(folder/'validation.json',validation)
    print(json.dumps(validation,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--folder',type=Path,required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--prepare',action='store_true'); group.add_argument('--run',action='store_true')
    args = parser.parse_args()
    if args.prepare:
        prepare(args.folder)
    else:
        try:
            run(args.folder)
        except Exception:
            write(args.folder/'failure.json',{'traceback':traceback.format_exc()})
            raise
