"""Compare two saved shadow trajectories to the existing legal witness.

Metadata-only arithmetic: no ADC/source/PWL/learner/output scoring is imported.
Frozen same-target outer intervals need no extra target precision or readout.
"""
import argparse
from fractions import Fraction as F
from pathlib import Path
import hashlib
import json
import shutil
import traceback

ROOT=Path(__file__).resolve().parents[2]
ALIGN=ROOT/'artifacts/research/front_fixed_alignment_20261014_v2'
CAP=ROOT/'artifacts/research/front_gate_migration_capacity_20261014_v2'
MEAN=ROOT/'artifacts/runs/EXP_076/fixed_mean_gate_v1'
INIT=ROOT/'artifacts/runs/EXP_077/initial_gate_v1'
FILES=[ALIGN/n for n in ('results.json','protocol.json','verification.json','independent_check.json','source_hashes.json')]
FILES += [CAP/'results.json']
FILES += [MEAN/n for n in ('results.json','protocol.json','verification.json','independent_check.json','source_hashes.json')]
FILES += [INIT/n for n in ('results.json','protocol.json','verification.json','independent_check.json','source_hashes.json','accounting_correction.json')]
DOCS=['docs/STATUS.md','docs/DECISIONS.md','docs/RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md',
      'docs/theory/STATIC_CASCADE_MILLION_SUPPORT_AND_PROJECTION_V1.md',
      'docs/theory/OBSERVATION_CORRECTION_LIMITS_V1.md','docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md',
      'docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md',
      'docs/reports/experiments/EXP_077_INITIAL_GATE_INTERVENTION_V1.md',
      'docs/reports/GU_ALGORITHM_EVALUATION_V1.md','docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md',
      'docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md']
KEY=(202610625,'quarter','prefix')
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def key(r):return r['seed'],r['rate'],r['initialization']
def select(d,witness=False):return next(r for r in d['rows'] if key(r)==KEY and (not witness or r['reference']=='witness'))

class Budget:
    def __init__(self,limits):self.limits=limits;self.used=dict.fromkeys(limits,0)
    def charge(self,k,n=1):
        assert self.used[k]+n<=self.limits[k],(k,self.used[k],n,self.limits[k])
        self.used[k]+=n
    def add(self,a,b):self.charge('scalar_add_sub');return a+b
    def sub(self,a,b):self.charge('scalar_add_sub');return a-b
    def div(self,a,b):self.charge('scalar_div');return a/b
    def read(self,p):self.charge('old_json_bytes',p.stat().st_size);return load(p)
    def sha(self,p):self.charge('fingerprint_bytes',p.stat().st_size);return hashlib.sha256(p.read_bytes()).hexdigest()
    def finish(self,out,name,done):write(out/f'accounting_{name}.json',{'completed':done,'limits':self.limits,'used':self.used,'all_limits_met':all(self.used[k]<=self.limits[k] for k in self.used)})

def mapping(d):
    return {str((Path(n) if Path(n).is_absolute() else ROOT/Path(n)).resolve()):z for n,z in d.items()}

def read_inputs(q):return {str(p):q.read(p) for p in FILES}

def contract(data,q):
    witness=select(data[str(ALIGN/'results.json')],True)
    mean=select(data[str(MEAN/'results.json')]);initial=select(data[str(INIT/'results.json')])
    codes=[round(F(z,4096)) for z in initial['initial_Q22']]
    q.charge('initial_export_cells',8)
    assert codes==witness['initial_codes']==[1048,1067,1024,1024,1081,1089,1024,1024]
    assert mean['initial_Q22']==initial['initial_Q22']
    assert witness['codes'][2:]==codes[2:] and witness['codes'][:2]==[1050,1087]
    assert all(0<=z<=2047 for z in witness['codes'])
    assert witness['diagnostic_Q22']==[z*4096 for z in witness['codes']]
    assert witness['held_loss']['exact']==mean['total']['losses']['held']['exact']==initial['total']['losses']['held']['exact']
    assert mean['total']['losses']['candidate']['exact']==initial['total']['losses']['mean']['exact']
    assert data[str(MEAN/'protocol.json')]['case']==data[str(INIT/'protocol.json')]['case']==list(KEY)
    assert 'final integer' in data[str(ALIGN/'protocol.json')]['continuous_output']
    for folder in (ALIGN,MEAN,INIT):
        for n in ('verification.json','independent_check.json'):assert data[str(folder/n)]['passed']
    assert not data[str(INIT/'accounting_correction.json')]['entire_frozen_cost_contract_passed']
    maps=[mapping(data[str(folder/'source_hashes.json')]) for folder in (ALIGN,MEAN,INIT)]
    shared=set(maps[0])&set(maps[1])&set(maps[2])
    critical=[n for n in shared if Path(n).name in ('both_smooth_202610625_words.bin','tone.bin','phase_certificate.json','source_protocol.json')]
    assert len(critical)==4
    for n in critical:assert len({m[n] for m in maps})==1,n
    cap=select(data[str(CAP/'results.json')])['capacity']
    assert cap['legal_low_Q10_witness']==witness['codes'][:2]
    assert maps[0][str(CAP/'results.json')]==hashlib.sha256((CAP/'results.json').read_bytes()).hexdigest()
    # Above cross-generation qualification hash is a real extra full-file read.
    q.charge('fingerprint_bytes',(CAP/'results.json').stat().st_size)
    floor=data[str(CAP/'results.json')]['info_floors'][str(KEY[0])]
    assert floor['samples']==245760 and cap['current_word_floor']['exact']==floor['loss']['exact']
    assert [b['block'] for b in witness['blocks']]==[b['block'] for b in mean['blocks']]==[b['block'] for b in initial['blocks']]==list(range(128,136))
    for r in (mean,initial):
        assert r['high_requested_components_nonzero']==r['high_export_changed_windows']==r['state_clipped_components']==0
        assert r['coefficient_export_min'][2:]==r['coefficient_export_max'][2:]==codes[2:]
    return witness,mean,initial,F(floor['loss']['exact']),critical

def guards(out,p,q):
    for name,z in p['source_hashes'].items():assert q.sha(Path(name))==z,name
    assert q.sha(Path(__file__))==p['execution_sha256']
    assert q.sha(out/'frozen_analysis.py')==p['execution_sha256']

def controls(q):
    a,h,w=F(3),F(2),F(1)
    assert q.sub(q.sub(a,h),q.sub(w,h))==q.sub(a,w)
    # Shared uncertain target: a conservative interval need not attain both endpoints.
    assert (q.sub(F(1),F(-3)),q.sub(F(2),F(-4)))==(4,6)
    assert q.sub(F(0),F(1,2))==-F(1,2) # moving output can beat a fixed-family optimum
    assert q.sub(F(2),F(1))<=q.sub(F(2),F(1,10))
    assert [1050,1087]!=[1048,1067] and [1024,1024,1081,1089,1024,1024]==[1024,1024,1081,1089,1024,1024]
    assert q.sub(q.add(F(1),F(2)),F(2))==1
    return {'passed':True,'controls':6,'no_ADC_readout':True,'signed_excess_and_common_target_enclosures':True}

def prepare(out):
    assert not out.exists(),'Refuse overwrite'
    oldbytes=sum(p.stat().st_size for p in FILES);codebytes=Path(__file__).stat().st_size;capbytes=(CAP/'results.json').stat().st_size
    limits={'old_json_bytes':oldbytes,'fingerprint_bytes':oldbytes+2*codebytes+capbytes,'initial_export_cells':8,'scalar_add_sub':64,'scalar_div':0}
    q=Budget(limits);data=read_inputs(q);contract(data,q);ctrl=controls(q)
    hashes={str(p):q.sha(p) for p in FILES};codehash=q.sha(Path(__file__))
    out.mkdir(parents=True);shutil.copyfile(Path(__file__),out/'frozen_analysis.py');assert q.sha(out/'frozen_analysis.py')==codehash
    guards_bytes=2*(oldbytes+2*codebytes)
    common={'old_json_bytes':oldbytes,'fingerprint_bytes':guards_bytes+capbytes,'initial_export_cells':8}
    protocol={'version':'EXP077-existing-witness-shadow-space-v1','date':'2026-10-14','case':list(KEY),
        'authority':'User continues research; D136..140 and current STATUS require same-constrained existing witness comparison after EXP077.',
        'scope':'Exactly two saved shadow paths versus one pre-existing legal low2 witness, total plus original8 blocks. Rear/high/source/target/time/quantization equal; static witness does not share low2 initial hidden state and is not a reachable policy.',
        'prediction':'Both shadow paths still have positive representable loss improvement to this prior fixed witness; original target outer intervals can reject or leave unresolved. Keep all8 blocks.',
        'derivation':'For common held output H: P-W=(P-H)-(W-H). If old contrast intervals are [a,b],[c,d], use [a-d,b-c]. Reuse witness block radii and saved absolute scores; no new word scoring, target knowledge or PWL.',
        'family':'All legal fixed front low2 codes with same rear/high. Stored current-word fixed mapping lower bound <= family infimum <= witness actual integer MSE. Signed excess to this fixed-family infimum is between P-W and P-current_word_floor, for nominal target only. This does not lower-bound moving or general causal outputs.',
        'units':'Old JSON full-file bytes, all explicit SHA read bytes including self/frozen qualification, initial-export kernels, scalar Fraction add/sub/div kernels, 18 relation objects and 2 nominal bound objects. Kernel internals include bigint normalization; parse, constants, comparisons, formatting, indices excluded. No ADC/source/word/target-table readout, score or learning. Administrative generated protocol/results reading, doc snapshots and delivery checks separately retained.',
        'source_hashes':hashes,'execution_sha256':codehash,'preparation_limits':limits,
        'main_limits':{**common,'scalar_add_sub':256,'scalar_div':8,'relation_objects':18,'nominal_bound_objects':2},
        'independent_limits':{**common,'scalar_add_sub':320,'scalar_div':48,'relation_objects':18,'nominal_bound_objects':2},
        'stop':'All18 bounds and2 nominal bound objects or explicit mismatch/failure. No automatic precision/targets/witnesses/inputs/horizon/optimization/new path/algorithm/holdout. Existing EXP077 cost failure remains.',
    }
    write(out/'protocol.json',protocol);write(out/'controls.json',ctrl);q.finish(out,'preparation',True)
    docbytes=0
    for name in DOCS:
        p=out/'documents_before'/name;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,p);docbytes+=(ROOT/name).stat().st_size
    write(out/'administrative_preparation.json',{'document_snapshot_bytes':docbytes,'files':len(DOCS),'scientific_calculations_before_freeze':0,'schema_inspection_before_freeze':'Existing JSON schemas/contracts and saved scores read for necessity; no new contrast/bound/output/target/learning calculations.'})
    print('Frozen metadata-only existing witness comparison; no new readouts or learning.')

def pack(z):return {'exact':str(z),'value':float(z)}

def analyze(out):
    p=load(out/'protocol.json');assert not (out/'results.json').exists();q=Budget(p['main_limits']);done=False
    try:
        guards(out,p,q);w,mean,initial,floor,critical=contract(read_inputs(q),q)
        rows=[]
        contexts=[('total',w['total'],mean['total'],initial['total'])]+[(str(a['block']),a,b,c) for a,b,c in zip(w['blocks'],mean['blocks'],initial['blocks'])]
        for record,ww,mm,ii in contexts:
            wl=F(ww['integer_loss']['exact']);held=F(mm['losses']['held']['exact']);wc=q.sub(wl,held);wr=F(ww['contrasts'][0]['difference_radius'])
            wb=[q.sub(wc,wr),q.add(wc,wr)]
            if record=='total':assert [str(z) for z in wb]==ww['contrasts'][0]['change_from_hold']['interval']
            for tag,source in (('mean_shadow',mm),('initial_shadow',ii)):
                q.charge('relation_objects');a=source['pairs']['candidate_minus_held'];center=q.sub(F(a['exact']),wc)
                lo=q.sub(F(a['interval'][0]),wb[1]);hi=q.sub(F(a['interval'][1]),wb[0])
                direct=q.sub(F(source['losses']['candidate']['exact']),wl);assert center==direct and lo<=center<=hi
                rows.append({'record':record,'path':tag,'gap':pack(center),'interval':list(map(str,(lo,hi))),'witness_better_certified':lo>0})
        nominal=[]
        for tag,source in (('mean_shadow',mean),('initial_shadow',initial)):
            q.charge('nominal_bound_objects');lp=F(source['total']['losses']['candidate']['exact']);lw=F(w['total']['integer_loss']['exact'])
            nominal.append({'path':tag,'signed_excess_to_fixed_low2_infimum_interval':list(map(str,(q.sub(lp,lw),q.sub(lp,floor))))})
        guards(out,p,q)
        write(out/'results.json',{'completed':True,'rows':rows,'nominal_fixed_family_bounds':nominal,
            'witness_codes':w['codes'],'witness_MSE':w['total']['integer_loss'],'current_word_nominal_floor':pack(floor),
            'matched_source_manifest_keys':critical,'all_original8_blocks_preserved':True,
            'previous_full_cost_contract_failure_preserved':True,'new_word_readouts_learning_paths_targets_FFT':0})
        done=True;print('Completed 18 outer comparisons and 2 nominal fixed-family bounds.')
    finally:q.finish(out,'main',done)

def check(out):
    p=load(out/'protocol.json');assert not (out/'independent_check.json').exists();q=Budget(p['independent_limits']);done=False
    try:
        guards(out,p,q);w,mean,initial,floor,_=contract(read_inputs(q),q);r=load(out/'results.json')
        lookup={(v['record'],v['path']):v for v in r['rows']}
        contexts=[('total',w['total'],mean['total'],initial['total'])]+[(str(a['block']),a,b,c) for a,b,c in zip(w['blocks'],mean['blocks'],initial['blocks'])]
        for record,ww,mm,ii in contexts:
            wl=F(ww['integer_loss']['exact']);wr=F(ww['contrasts'][0]['difference_radius'])
            for tag,source in (('mean_shadow',mm),('initial_shadow',ii)):
                q.charge('relation_objects');pair=source['pairs']['candidate_minus_held'];lo,hi=map(F,pair['interval'])
                radius=q.add(q.div(q.sub(hi,lo),F(2)),wr)
                center=q.sub(F(source['losses']['candidate']['exact']),wl)
                endpoints=[q.sub(center,radius),q.add(center,radius)]
                rr=lookup[record,tag];assert str(center)==rr['gap']['exact'] and list(map(str,endpoints))==rr['interval']
        for obj,(tag,source) in zip(r['nominal_fixed_family_bounds'],(('mean_shadow',mean),('initial_shadow',initial))):
            q.charge('nominal_bound_objects');lp=F(source['total']['losses']['candidate']['exact']);lw=F(w['total']['integer_loss']['exact'])
            # Opposite signed static-best range, then reverse its endpoints.
            reverse=[q.sub(floor,lp),q.sub(lw,lp)]
            assert list(map(str,(-reverse[1],-reverse[0])))==obj['signed_excess_to_fixed_low2_infimum_interval']
        guards(out,p,q);write(out/'independent_check.json',{'passed':True,'direct_absolute_loss_and_summed_radius_recovers_all18':True,'fixed_family_signed_bound_reverse_check':True,'new_scientific_readouts_scores_learning':0})
        totals=[v for v in r['rows'] if v['record']=='total']
        write(out/'summary.json',{'passed':True,'prediction_supported':all(v['witness_better_certified'] for v in totals),
            'total_comparisons':totals,'all18_comparisons_certified':all(v['witness_better_certified'] for v in r['rows']),
            'static_family_floor_is_not_a_lower_bound_on_causal_or_moving_policy':True,'online_reachability_or_new_algorithm_proved':False})
        done=True;print('Independent absolute-loss / radius check passed; primary comparison supported=',all(v['witness_better_certified'] for v in totals))
    finally:q.finish(out,'independent',done)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=('prepare','analyze','check'));parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    try:globals()[args.mode](args.out)
    except Exception:
        if args.out.exists():write(args.out/f'failure_{args.mode}.json',{'traceback':traceback.format_exc()})
        raise
