"""Exact local front-root curves driven by an affine backend coefficient line.

The backend line's zero-correlation property is an external, separately
verified premise. This module certifies front basis frames, gates, rational
coefficient functions and correlations; it is not an online updater.
"""
from collections import Counter
from fractions import Fraction as F

from adc_research.calibration.observation import DigitalCalibrationSample
from adc_research.theory.gated_correlation_roots import stage_basis


def trim(p):
    p=list(p)
    while len(p)>1 and not p[-1]:p.pop()
    return tuple(p)


def add(p,q):
    return trim(tuple((p[i] if i<len(p) else F(0))+(q[i] if i<len(q) else F(0))
                      for i in range(max(len(p),len(q)))))


def scale(p,s):return trim(tuple(s*x for x in p))


def multiply(p,q):
    values=[F(0)]*(len(p)+len(q)-1)
    for i,a in enumerate(p):
        for j,b in enumerate(q):values[i+j]+=a*b
    return trim(values)


def value(p,t):
    result=F(0)
    for a in reversed(p):result=result*t+a
    return result


def interval_multiply(a,b):
    products=tuple(x*y for x in a for y in b)
    return min(products),max(products)


def interval_value(p,interval):
    result=(F(0),F(0))
    for a in reversed(p):
        lo,hi=interval_multiply(result,interval)
        result=lo+a,hi+a
    return result


def divide_intervals(numerator,denominator):
    if denominator[0]<=0<=denominator[1]:raise ValueError('possible zero denominator')
    values=tuple(a/b for a in numerator for b in denominator)
    return min(values),max(values)


def curve_coefficients(model,h):
    t=h-model['seed_parameter']
    denominator=value(model['denominator'],t)
    return (value(model['numerator_u'],t)/denominator,value(model['numerator_v'],t)/denominator,F(1),F(1))


def build_front_curve(samples,back_direction,back_intercept,h0,front_coefficients):
    samples=tuple(samples)
    back_direction,back_intercept,front_coefficients=tuple(back_direction),tuple(back_intercept),tuple(front_coefficients)
    if not samples or any(not isinstance(s,DigitalCalibrationSample) for s in samples):
        raise TypeError('nonempty decoded digital record required')
    if any(not isinstance(v,int) or isinstance(v,bool) for s in samples for v in
           (s.stage1_symbol,s.stage2_symbol,s.backend_centered_code,s.stage1_dither_symbol,s.stage2_dither_symbol)):
        raise TypeError('digital words must be integers')
    if not isinstance(h0,F) or any(not isinstance(k,F) for k in (*back_direction,*back_intercept,*front_coefficients)):
        raise TypeError('explicit Fraction coefficients required')
    if len(back_direction)!=4 or len(back_intercept)!=4 or len(front_coefficients)!=4:
        raise ValueError('four digital slopes per bank required')
    if front_coefficients[2:]!=(F(1),F(1)):
        raise ValueError('front high slopes must be fixed at unity')
    if any(not 0<k<2 for k in front_coefficients):raise ValueError('illegal front coefficient')
    back0=tuple(a*h0+b for a,b in zip(back_direction,back_intercept))
    if any(not 0<k<2 for k in back0):raise ValueError('illegal backend seed coefficient')
    counts=Counter((s.stage2_symbol,s.backend_centered_code,s.stage1_dither_symbol,s.stage2_dither_symbol) for s in samples)
    total=len(samples)
    matrix=[[(F(0),)]*2 for _ in range(4)]
    constant=[(F(0),)]*4
    frames=[]
    for (q2,raw2,d1symbol,d2symbol),count in counts.items():
        if d1symbol not in (-1,1) or d2symbol not in (-1,1):raise ValueError('aligned +/-1 dither symbols required')
        basis2=stage_basis(F(raw2),F(32))
        slope=sum((a*p for a,p in zip(back_direction,basis2)),F(0))
        raw0=128*q2+sum((k*p for k,p in zip(back0,basis2)),F(0))-16*d2symbol
        stage_basis(raw0,F(128)) # strict domain check, including the negative endpoint
        segment=min(abs(raw0)//128,3)
        sign=(raw0>0)-(raw0<0)
        basis=[]
        for j in range(4):
            basis.append((F(sign*128),) if j<segment else ((raw0-sign*j*128,slope) if j==segment else (F(0),)))
        dither=F(64*d1symbol)
        local0=sum((k*value(p,F(0)) for k,p in zip(front_coefficients,basis)),F(0))-dither
        gates=tuple(i==0 or abs(local0)>=128*sum(front_coefficients[:i],F(0)) for i in range(4))
        weight=F(count)*dither/total
        for i,gate in enumerate(gates):
            if gate:
                for j in range(2):matrix[i][j]=add(matrix[i][j],scale(basis[j],weight))
                constant[i]=add(constant[i],scale(add(add(basis[2],basis[3]),(-dither,)),weight))
        frames.append({'raw':(raw0,slope),'segment':int(segment),'sign':sign,'basis':tuple(basis),
                       'dither':dither,'gates':gates,'local0':local0,'count':count})
    determinant=add(multiply(matrix[0][0],matrix[1][1]),scale(multiply(matrix[0][1],matrix[1][0]),F(-1)))
    if not value(determinant,F(0)):
        return {'status':'singular_front_low_matrix','seed_parameter':h0}
    numerator_u=add(multiply(matrix[0][1],constant[1]),scale(multiply(matrix[1][1],constant[0]),F(-1)))
    numerator_v=add(multiply(matrix[1][0],constant[0]),scale(multiply(matrix[0][0],constant[1]),F(-1)))
    model={'status':'constructed','seed_parameter':h0,'denominator':determinant,
           'numerator_u':numerator_u,'numerator_v':numerator_v,'frames':tuple(frames)}
    if curve_coefficients(model,h0)!=front_coefficients:
        raise ValueError('seed does not solve both front low correlations')
    residuals=tuple(add(add(multiply(row[0],numerator_u),multiply(row[1],numerator_v)),multiply(b,determinant))
                    for row,b in zip(matrix,constant))
    assert residuals[:2]==((F(0),),(F(0),))
    model['front_correlation_numerators']=residuals
    model['front_all_four_correlations_identically_zero']=all(p==(F(0),) for p in residuals)
    model['gate_counts']=tuple(sum(f['count'] for f in frames if f['gates'][i]) for i in range(4))
    constraints=[]
    for frame in frames:
        psi=frame['basis']
        yn=add(add(multiply(numerator_u,psi[0]),multiply(numerator_v,psi[1])),
               multiply(add(add(psi[2],psi[3]),(-frame['dither'],)),determinant))
        for i in range(1,4):
            tn=scale(add(add(numerator_u,numerator_v if i>=2 else (F(0),)),determinant if i>=3 else (F(0),)),F(128))
            if frame['gates'][i]:
                sign=(frame['local0']>0)-(frame['local0']<0)
                constraints.append((add(scale(yn,F(sign)),scale(tn,F(-1))),False))
            else:
                constraints.extend(((add(tn,scale(yn,F(-1))),True),(add(tn,yn),True)))
    model['gate_constraints']=tuple(constraints)
    return model


def certify_interval(model,low,high):
    if not isinstance(low,F) or not isinstance(high,F) or low>=high:
        raise ValueError('an ordered nontrivial exact parameter interval is required')
    if model['status']!='constructed':return False
    t=(low-model['seed_parameter'],high-model['seed_parameter'])
    den=interval_value(model['denominator'],t)
    if den[0]<=0<=den[1]:return False
    for name in ('numerator_u','numerator_v'):
        coefficient=divide_intervals(interval_value(model[name],t),den)
        if not 0<coefficient[0]<=coefficient[1]<2:return False
    for frame in model['frames']:
        raw=interval_value(frame['raw'],t)
        if raw[0]<-512 or raw[1]>=512:return False
        segment=frame['segment']
        if segment==0:
            if raw[0]<-128 or raw[1]>128:return False
        else:
            magnitude=raw if frame['sign']>0 else (-raw[1],-raw[0])
            if magnitude[0]<segment*128 or magnitude[1]>(segment+1)*128:return False
    for numerator,strict in model['gate_constraints']:
        if numerator==(F(0),):
            if strict:return False
            continue
        margin=divide_intervals(interval_value(numerator,t),den)
        if margin[0]<0 or (strict and margin[0]==0):return False
    return True


def certify_local_curve(model,back_interval,max_halvings=60):
    if model['status']!='constructed':return {'status':model['status']}
    h0=model['seed_parameter']
    lo,hi=back_interval[:2]
    radius=min(F(1,1024),(h0-lo)/2,(hi-h0)/2)
    if radius<=0:return {'status':'no_interior_backend_neighborhood'}
    for attempt in range(max_halvings):
        for mode,left,right in (('symmetric',h0-radius,h0+radius),('right',h0,h0+radius),('left',h0-radius,h0)):
            if certify_interval(model,left,right):
                return {'status':'certified_front_root_curve','parameter_interval':(left,right),
                        'radius':radius,'halvings':attempt,'mode':mode,
                        'front_all_four_zero':model['front_all_four_correlations_identically_zero'],
                        'identity_open_gate_constraints':sum(p==(F(0),) and not strict for p,strict in model['gate_constraints'])}
        radius/=2
    return {'status':'neighborhood_not_certified','halvings':max_halvings}
