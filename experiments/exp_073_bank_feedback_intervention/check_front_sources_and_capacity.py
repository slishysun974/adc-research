"""Scalar integer prefixes, Fraction window contractions, and exact floors."""
from pathlib import Path
from fractions import Fraction as F
import sys
import argparse
import numpy as np
ROOT=Path('D:/ADC');sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from experiments.exp_073_bank_feedback_intervention.analyze_front_history import ExactProjector,load,write
from experiments.exp_073_bank_feedback_intervention.run import source
ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);OUT=ap.parse_args().out.resolve()
W=2048;B=256;D=B*B;S=D*500*(1<<25)
HISTORY=ROOT/'artifacts/research/front_forcing_response_20261013_v2'
BASIS=ROOT/'artifacts/research/front_block_migration_20261014_v1'
BLOCK=ROOT/'artifacts/research/front_centered_requests_20261014_v1'
limits={'gate10_values':409600,'old24_values':983040,'old8_values':327680,'window5_values':204800,
        'basis_values':9830400,'basis_target_products':9830400,'window_Gram_contractions':8155136,
        'window_error_contractions':1351680,'source_tuple_values':4915200,'independent_info_word_inputs':1228800}
used=dict.fromkeys(limits,0)
def charge(k,n):
 assert used[k]+n<=limits[k],(k,used[k],n)
 used[k]+=n
assert not (OUT/'independent_check.json').exists()
write(OUT/'independent_protocol.json',{'limits':limits,'scope':'Same20; independent Python integer prefix/time maps, every time-profile Gram and target-error contraction; all5 exact current-word floors via sorted observation grouping.',
 'new_PWL_gate_request_learning_paths_source_fft_holdout':0})
p=ExactProjector();result=load(OUT/'results.json');cases=0
try:
 # Independent grouping: sort tuples, then aggregate consecutive observations.
 for seed in range(202610621,202610626):
  charge('source_tuple_values',W*120*4);words=np.array(source(seed),dtype=np.int64).reshape(-1,4)
  charge('independent_info_word_inputs',len(words))
  order=np.lexsort(tuple(words[:,j] for j in (3,2,1,0)))
  prev=None;n=ss=qq=num=ng=0
  def finish(n,ss,qq):
   kk=max(0,min(4095,round(F(ss,n*p.D))))
   return qq-2*kk*p.D*ss+n*(kk*p.D)**2
  for ii in order:
   i=int(ii);key=tuple(map(int,words[i]));t=int(p.ti[i%len(p.ti)])
   if prev is not None and key!=prev:num+=finish(n,ss,qq);ng+=1;n=ss=qq=0
   prev=key;n+=1;ss+=t;qq+=t*t
  num+=finish(n,ss,qq);ng+=1
  old=result['info_floors'][str(seed)]
  assert F(num,len(words)*p.D*p.D)==F(old['loss']['exact']) and ng==old['groups']
 for row in result['rows']:
  seed,rate,init=(row[k] for k in ('seed','rate','initialization'));name=f'{seed}_{rate}_{init}';m=1 if rate=='base' else 4
  charge('gate10_values',W*10);gate=np.fromfile(OUT/f'{name}_gate_sources.bin',dtype='<i8').reshape(W,10)
  charge('old24_values',W*24);mom=np.fromfile(HISTORY/f'{name}_front_moments.bin',dtype='<i8').reshape(W,24)
  charge('old8_values',W*8);saved=np.fromfile(BLOCK/f'{name}_block_request_profiles.bin',dtype='<i8').reshape(W,8)
  streams=[[] for _ in range(9)]
  for w in range(W):
   full,fg,sel,sg,gn,gs,dgn,dgs,rq1,rq2=map(int,gate[w]);assert (rq1,rq2)==tuple(map(int,mom[w,2:4]))
   one=[F(-16*full,125*m),F(-96*sel,25*m)+F(16*full,125*m),F(rq1)+F(96*sel,25*m)]
   two=[F(-48*full,125*m),F(-48*(fg-full),125*m),F(-48*(30*sel-full),125*m),
        F(-48*(30*(sg-sel)-(fg-full)),125*m),F(rq2)+F(288*sg,25*m)]
   assert sum(one)==rq1 and sum(two)==rq2 and abs(one[-1])<=F(12,25) and abs(two[-1])<=F(12,25)
   for j,v in enumerate(one):streams[j].append([int(v*500),0])
   for j,v in enumerate(two):streams[3+j].append([0,int(v*500)])
   streams[8].append([500*(int(mom[w,j])-int(mom[w,2+j])) for j in range(2)])
  states=[]
  for stream in streams:
   cur=[0,0];a=[]
   for z in stream:a.append(cur[:]);cur=[cur[j]+z[j] for j in range(2)]
   states.append(a)
  actual=[];cur=[0,0]
  for w in range(W):actual.append(cur[:]);cur=[cur[j]+int(mom[w,j]) for j in range(2)]
  k0=list(map(int,mom[0,10:12]))
  ep=[[500*(4096*(int(mom[w,10+j])-k0[j])-actual[w][j]) for j in range(2)] for w in range(W)]
  pm=[];mg=[];ce=[]
  for a,u in zip(states,streams):
   total=[sum(z[j] for z in a)*(D//W) for j in range(2)]
   pm.append([total[:] for _ in range(W)]);mv=[];cv=[]
   for bb in range(8):
    sl=slice(bb*B,(bb+1)*B);asum=[sum(z[j] for z in a[sl]) for j in range(2)];usum=[sum(z[j] for z in u[sl]) for j in range(2)]
    # Direct triangular weights recover block output-before-state mean.
    for j in range(2):
     triangular=B*a[bb*B][j]+sum((B-1-r)*u[bb*B+r][j] for r in range(B))
     assert triangular==asum[j]
    bv=[asum[j]*(D//B)-total[j] for j in range(2)]
    for rr in range(B):
     mv.append(bv[:]);cv.append([D*a[bb*B+rr][j]-B*rr*usum[j]-B*asum[j]+B*(B-1)//2*usum[j] for j in range(2)])
   mg.append(mv);ce.append(cv)
  em=[sum(z[j] for z in ep)*(D//W) for j in range(2)]
  pm.append([em[:] for _ in range(W)])
  ev=[]
  for bb in range(8):
   b=[sum(z[j] for z in ep[bb*B:(bb+1)*B])*(D//B)-em[j] for j in range(2)]
   ev.extend([b[:] for _ in range(B)])
  mg.append(ev);ce.append((saved[:,4:6]*500).tolist())
  blockpos=[]
  for bb in range(8):
   blockpos.extend([[4096*(D//B)*500*sum(int(z)-k0[j] for z in mom[bb*B:(bb+1)*B,10+j]) for j in range(2)]]*B)
  ce.extend([blockpos,(saved[:,:2]*500).tolist()])
  mean=[4096*(D//W)*500*sum(int(z)-k0[j] for z in mom[:,10+j]) for j in range(2)]
  mg.append([mean[:] for _ in range(W)])
  charge('window5_values',W*5);wm=np.fromfile(BASIS/f'{name}_basis_moments.bin',dtype='<i8').reshape(W,5).tolist()
  charge('basis_values',W*120*2);phi=np.fromfile(BASIS/f'{name}_basis.bin',dtype='<i2').reshape(W,120,2)
  charge('basis_target_products',W*120*2)
  targets=[[sum(int(phi[w,l,j])*int(p.ti[(w*120+l)%len(p.ti)]) for l in range(120)) for j in range(2)] for w in range(W)]
  for mode,prof in [('centered',ce),('position',pm),('migration',mg)]:
   stat=row['modes'][mode]
   for i,ai in enumerate(prof):
    charge('window_error_contractions',W)
    bc=F(2,W*120*S)*sum(ai[w][0]*(F(wm[w][3])-F(targets[w][0],p.D))+ai[w][1]*(F(wm[w][4])-F(targets[w][1],p.D)) for w in range(W))
    assert bc==F(stat['error_cross'][i])
    for j in range(i+1):
     charge('window_Gram_contractions',W)
     aj=prof[j]
     q=F(sum(ai[w][0]*aj[w][0]*wm[w][0]+(ai[w][0]*aj[w][1]+ai[w][1]*aj[w][0])*wm[w][1]+ai[w][1]*aj[w][1]*wm[w][2] for w in range(W)),W*120*S*S)
     assert q==F(stat['gram'][i][j])
  cases+=1;print(name,'all scalar time maps and Gram/target projections exact',flush=True)
 assert cases==20
 write(OUT/'independent_check.json',{'passed':True,'cases':cases,'all_time_maps_Grams_and_target_projections_exact':True,'all5_current_word_integer_floors_exact':True})
finally:
 write(OUT/'accounting_independent.json',{'used':used,'limits':limits,'all_limits_met':all(used[k]<=limits[k] for k in limits),'completed':cases==20})
