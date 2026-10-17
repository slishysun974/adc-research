"""One preselected legal witness per original case, with high-support envelopes."""
from pathlib import Path
from fractions import Fraction as F
import sys
import argparse
import numpy as np
ROOT=Path('D:/ADC');sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from experiments.exp_073_bank_feedback_intervention.analyze_front_history import (ROOT,BASE,OLD,SEEDS,W,source,round_ratio,pwl_scaled,ExactProjector,load,write,digest,guard,pack,mulsum)
from experiments.exp_073_bank_feedback_intervention.analyze_front_sources_and_capacity import scalar_pwl
ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);OUT=ap.parse_args().out.resolve()
BASIS=ROOT/'artifacts/research/front_block_migration_20261014_v1'
limits={'source_tuple_values':4915200,'basis_values':9830400,'held_values':4915200,'initial_Q22_values':160,
        'low_support_front_Q3_PWL':4915200,'candidate_envelope_round_inputs':9830400,
        'worst_loss_word_inputs':4915200,'Fraction_boundary_probes':240}
used=dict.fromkeys(limits,0)
def charge(k,n):
 assert used[k]+n<=limits[k],(k,used[k],n)
 used[k]+=n
assert not (OUT/'witness_bounds.json').exists()
write(OUT/'witness_protocol.json',{'scope':'Original all20 preselected low-Q10 witnesses from first frozen analytic two-coordinate solution; no candidate search or added inputs.',
 'necessity':'The universal9/8 difference bound is too broad for some held losses. Reuse saved low2 bases: raw is exactly known below second saturation; above it both changed coefficients enter only an exact Q3 offset. Enumerate the two extreme original Q3 values compatible with held integer code and nearest-even. Bound a SINGLE legal witness, not choose among candidates by its score.',
 'limits':limits,'source_results_sha256':digest(OUT/'results.json'),
 'predictions':'Below saturation exact candidate output; above it all possible old Q3 readouts contained in endpoint envelope, nearest-even parity preserved. Sum per-word worst target loss gives feasible witness upper bound, not exact witness loss.',
 'information':'Candidates and target are offline. Current-word fixed information floor and legal static family only; no online attainability or unknown-input guarantee. No rear PWL, gates, requests, learning, paths, source, FFT or holdout.'})
# Independent endpoint/nearest-even boundary control before original data.
for yy in range(6):
 for shift in range(-17,18):
  ts=[z for z in range(-4,5) if round(F(8*yy+z,8))==yy]
  lo=round(F(8*yy+ts[0]+shift,8));hi=round(F(8*yy+ts[-1]+shift,8))
  assert all(lo<=round(F(8*yy+z+shift,8))<=hi for z in ts)
write(OUT/'witness_controls.json',{'passed':True,'endpoint_parity_cases':210})
p=ExactProjector();results=load(OUT/'results.json');rows=[]
try:
 for seed in SEEDS:
  charge('source_tuple_values',W*120*4);words=np.array(source(seed),dtype=np.int64)
  q1=words[:,:,0];d=2*(words[:,:,3]&1)-1
  for row in [r for r in results['rows'] if r['seed']==seed]:
   rate,init=row['rate'],row['initialization'];idx=0 if init=='actual' else 2;stem=f'{seed}_{rate}';name=f'{stem}_{init}'
   charge('initial_Q22_values',8);a0=np.array(np.memmap(BASE/f'{stem}_q22.bin',dtype='<i4',mode='r',shape=(W+1,4,8))[0,idx],dtype=np.int64);k0=round_ratio(a0,4096)
   k=k0.copy();k[:2]=row['capacity']['legal_low_Q10_witness'];gap=k[:2]-k0[:2]
   charge('basis_values',W*120*2);phi=np.fromfile(BASIS/f'{name}_basis.bin',dtype='<i2').reshape(W,120,2).astype(np.int64)
   charge('held_values',W*120);held=np.array(np.memmap(BASE/f'{stem}_outputs.bin',dtype='<i2',mode='r',shape=(W,4,120))[:,idx+1],dtype=np.int64)
   low=abs(phi[:,:,1])<1024;sgn=np.sign(phi[:,:,0]);raw=sgn*(abs(phi[:,:,0])+abs(phi[:,:,1]))
   charge('low_support_front_Q3_PWL',int(low.sum()))
   # Vector geometry only reads the two active low segments here.
   rv=raw[low];ka=np.broadcast_to(k[:4],(len(rv),4))
   # pwl_scaled accepts a window dimension and a slot dimension.
   local=pwl_scaled(rv[:,None],ka,128).ravel()-512*d[low]
   exact=round_ratio(16384+4096*q1[low]+local,8)
   ylo=held.copy();yhi=held.copy();ylo[low]=exact;yhi[low]=exact
   high=~low;shift=sgn[high]*int(gap.sum());hh=held[high]
   # Odd held codes exclude both half-integer endpoints.
   radius=4-(hh&1)
   charge('candidate_envelope_round_inputs',int(high.sum())*2)
   ylo[high]=round_ratio(8*hh-radius+shift,8);yhi[high]=round_ratio(8*hh+radius+shift,8)
   assert np.all((ylo>=0)&(yhi<=4095)) and np.all(ylo<=yhi)
   target=np.array(p.ti,dtype=object);t=np.resize(target,held.size).reshape(held.shape)
   alo=ylo.astype(object)*p.D-t;ahi=yhi.astype(object)*p.D-t
   charge('worst_loss_word_inputs',held.size)
   upper=F(int(np.maximum(alo*alo,ahi*ahi).sum()),held.size*p.D*p.D)
   lower=F(int(np.minimum(alo*alo,ahi*ahi).sum()),held.size*p.D*p.D)
   # lower is merely an endpoint descriptor, not a witness lower certificate:
   # a target between endpoints might have a smaller interior loss.
   coarse=F(row['capacity']['restricted_integer_optimum_interval'][1])
   certified_upper=min(upper,coarse);hold=F(row['capacity']['held_loss']['exact'])
   for ww,lane in [(0,0),(255,119),(256,3),(1023,64),(2047,0),(1536,119),(128,4),(511,60),(768,12),(1200,30),(1700,80),(2000,1)]:
    charge('Fraction_boundary_probes',1)
    if low[ww,lane]:
     val=scalar_pwl(int(raw[ww,lane]),k[:4],128)-512*int(d[ww,lane])
     assert round(F(16384+4096*int(q1[ww,lane])+val,8))==int(ylo[ww,lane])
    else:
     yy=int(held[ww,lane]);dd=int(sgn[ww,lane])*int(gap.sum())
     for z in range(-4,5):
      if round(F(8*yy+z,8))==yy:
       assert ylo[ww,lane]<=round(F(8*yy+z+dd,8))<=yhi[ww,lane]
   rows.append({'seed':seed,'rate':rate,'initialization':init,'legal_low_Q10_witness':k[:2].tolist(),
                'low_support_exact_words':int(low.sum()),'high_support_envelope_words':int(high.sum()),
                'envelope_witness_upper':pack(upper),'certified_witness_upper':pack(certified_upper),
                'guaranteed_available_reduction_nominal':pack(max(F(0),hold-certified_upper)),
                'global_static_optimum_interval':[row['capacity']['current_word_floor']['exact'],str(min(hold,certified_upper))]})
   print(name,'upper<=',float(certified_upper),'available>=',float(max(F(0),hold-certified_upper)),flush=True)
 assert len(rows)==20
 write(OUT/'witness_bounds.json',{'passed':True,'rows':rows,'all_witness_ranges_legal':True,'bounds_only_not_exact_high_word_outputs':True})
finally:
 write(OUT/'accounting_witness.json',{'used':used,'limits':limits,'all_limits_met':all(used[k]<=limits[k] for k in limits),'completed':len(rows)==20})
