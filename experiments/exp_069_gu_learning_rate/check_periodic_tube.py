"""NG-35 exact comparison controls and read-only existing guard evidence.

No new ADC experiment, readout, update, fit, frequency score or holdout use.
The existing grouped audit supplies only necessary-condition information.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

from adc_research.theory.triangular_cascade_bounds import periodic_cascade_tube


ROOT = Path(__file__).resolve().parents[2]
PREVIOUS = ROOT/'artifacts/research/grouped_normal_loss_20261012_v1'
SOURCES = (
    'experiments/exp_069_gu_learning_rate/check_periodic_tube.py',
    'src/adc_research/theory/triangular_cascade_bounds.py',
    'tests/test_triangular_cascade_bounds.py',
    'tests/test_finite_observation_limits.py',
)
DOCUMENTS = (
    'docs/STATUS.md', 'docs/DECISIONS.md', 'docs/README.md',
    'docs/RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md',
    'docs/theory/README.md',
    'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
    'docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md',
    'docs/theory/WINDOW_MEAN_AND_GATE_MARGIN_CONDITIONS_V1.md',
    'docs/reports/GU_ALGORITHM_EVALUATION_V1.md',
    'docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, data):
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def check_hashes(manifest):
    for name, expected in manifest.items():
        if digest(ROOT/name) != expected:
            raise AssertionError(f'frozen input changed: {name}')


def prepare(folder):
    folder.mkdir(parents=True,exist_ok=False)
    prior = load(PREVIOUS/'delivery_hashes.json')
    inputs = {}
    for name in ('results.json','protocol.json','delivery_validation.json'):
        path = PREVIOUS/name
        if digest(path) != prior[name]:
            raise AssertionError(f'previous delivery mismatch: {name}')
        inputs[path.relative_to(ROOT).as_posix()] = prior[name]
    write(folder/'protocol.json', {
        'version':'NG35-periodic-comparison-tube-v1', 'date':'2026-10-12',
        'authority':'User continues prior four-direction research and explicitly excludes new algorithm design. D-129 task2 analytical extension; D-132 prior batch remains complete.',
        'question':'Can ordered phase bounds give a protected periodic tube without a common root or per-window contraction? When do existing boundary records prevent this certificate?',
        'maps':'Declared deterministic triangular comparison recurrence in slope units. Phase-uniform whole-rectangle factors and all update/reference defects are assumptions, not fitted or certified Gu factors.',
        'positive_control':{
            'phase_rows':[['2','1/2','1','1/8','1/16'],['1/4','1/2','0','1/8','1/16']],
            'expected_period':['1/2','1/4','1/4','5/32','3/32'],
            'expected_radii_front':['3/8','1','3/8'],
            'expected_radii_rear':['1/8','1/8','1/8']},
        'exact_tests':8,
        'enumeration':'4 initial corners x 256 disturbance-sign strings x 4 simultaneous two-stage steps =4096 transitions per test invocation; at most targeted plus full regression,8192 transitions. Other hand/cycle controls under128 short compositions per invocation.',
        'negative_controls':['A cycle product at least1 is rejected',
            'Endpoints fitting protected caps do not replace phase1 protection',
            'Moving-center residual cannot be omitted',
            'Normal gate/segment equalities fail strict smooth-margin certification'],
        'reuse':'Read the old results conditions ONLY: all240 path-interval rows, no raw words,coefficients,scores,FFT or new derivation from observations. Compare original six gate-equality counts and front-segment-equality counts.',
        'guard_rule':'A recorded continuous equality makes the strict-margin sufficient test fail. It does not prove nonsmoothness in all active directions, actual instability, or impossibility of other invariant sets. A row with no equality is not certified.',
        'initial_and_future_conditions':'Initial state lies in phase0 tube; all future windows satisfy the declared phase bounds and protected closed rectangles. Source/PRNG/analog history is conditioned on or included in the state. Not asserted by a finite input period.',
        'stop':'No extra matrix,period search,Gu tuning,new holdout,or source generation. Preserve failures and refreeze changed implementation before rerunning.',
        'new_adc_conversions':0,'new_learning_observations':0,
        'new_online_outputs':0,'new_offline_readouts':0,'new_fft':0,
        'new_performance_scores':0,
    })
    write(folder/'original_data_hashes.json',inputs)
    write(folder/'execution_hashes.json',{name:digest(ROOT/name) for name in SOURCES})
    for name in DOCUMENTS:
        dest=folder/'documents_before'/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(ROOT/name,dest)
    write(folder/'environment.json', {'python':sys.version,'platform':sys.platform})
    print('Frozen: 8 exact tests; 240 old condition summaries; zero new ADC work.')


def run(folder):
    check_hashes(load(folder/'execution_hashes.json'))
    check_hashes(load(folder/'original_data_hashes.json'))
    rows = load(PREVIOUS/'results.json')['paths']
    assert len(rows) == 240
    identities = [(r['case'],r['seed'],r['rate'],r['method'],r['interval']) for r in rows]
    assert len(set(identities)) == 240
    gate_totals=[0]*6
    segment_total=0
    blocked=[]
    grouped={}
    for row,identity in zip(rows,identities,strict=True):
        conditions=row['conditions']
        gates=conditions['continuous_gate_equalities']
        segment=conditions['continuous_front_segment_equalities']
        assert len(gates)==6 and all(isinstance(x,int) and x>=0 for x in gates)
        assert isinstance(segment,int) and segment>=0
        gate_totals=[a+b for a,b in zip(gate_totals,gates,strict=True)]
        segment_total+=segment
        has_gate=any(gates)
        has_segment=segment>0
        if has_gate or has_segment: blocked.append(identity)
        key=(row['case'],row['rate'],row['method'],row['interval'])
        counts=grouped.setdefault(key,{'rows':0,'gate_equality_rows':0,
                                      'segment_equality_rows':0,'either_rows':0})
        counts['rows']+=1
        counts['gate_equality_rows']+=int(has_gate)
        counts['segment_equality_rows']+=int(has_segment)
        counts['either_rows']+=int(has_gate or has_segment)
    # Frozen published NG-33 counts are reproduced from old condition fields.
    assert sum(gate_totals)==38408 and segment_total==7937 and len(blocked)==223
    positive=periodic_cascade_tube((('2','1/2','1','1/8','1/16'),
                                   ('1/4','1/2','0','1/8','1/16')))
    result={
        'mathematical_status':'Conditional ordered periodic tube; complete proof in window theory section8. No actual Gu contraction/tube certification.',
        'positive_control':{key:[str(x) for x in value] if isinstance(value,tuple) else str(value)
                            for key,value in vars(positive).items()},
        'old_conditions':{'rows':len(rows),'continuous_gate_equalities_by_gate':gate_totals,
            'continuous_gate_equalities':sum(gate_totals),
            'continuous_front_segment_equalities':segment_total,
            'strict_margin_test_blocked_rows':len(blocked),
            'remaining_rows_not_certified':len(rows)-len(blocked),
            'blocked_identities':blocked,
            'groups':[dict(zip(('case','rate','method','interval'),key,strict=True),**value)
                      for key,value in grouped.items()]},
        'interpretation':'The periodic comparison result removes the common-root/per-step-contraction requirement, but does not remove whole-phase gate/domain protection, quantization/selection/reference defects or future coverage. Existing equalities reject one sufficient certificate, not actual stability.',
        'counts':{'old_condition_rows_read':240,'new_adc_conversions':0,
            'new_learning_observations':0,'new_online_outputs':0,
            'new_offline_readouts':0,'new_fft':0,'new_performance_scores':0},
    }
    check_hashes(load(folder/'execution_hashes.json'))
    check_hashes(load(folder/'original_data_hashes.json'))
    write(folder/'results.json',result)
    print(f'Exact phase radii front={positive.front},rear={positive.rear}; strict-margin test blocked223/240; other17 not certified.')


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('prepare','run'))
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    (prepare if args.action=='prepare' else run)(args.output.resolve())
