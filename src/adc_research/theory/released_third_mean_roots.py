"""Exact local three-slope roots and one-dimensional fixed-gate root sets.

This certifies proposals inside the masks of a declared digital seed. It does
not enumerate the full three-dimensional gate arrangement or all roots.
"""
from fractions import Fraction as F

from adc_research.theory.gated_correlation_roots import stage_basis,stage_correlations
from adc_research.theory.window_excitation import exact_nullspace


def affine_correlations(rows,coefficients,width):
    coefficients=tuple(coefficients)
    # Reuse strict digital-domain/coefficient validation before constructing masks.
    values=stage_correlations(rows,coefficients,width)
    total=sum(row.count for row in rows)
    matrix=[[F(0)]*3 for _ in range(4)]
    constant=[F(0)]*4
    masks=[]
    for row in rows:
        basis=stage_basis(row.raw,width)
        y=sum((k*p for k,p in zip(coefficients,basis)),F(0))-row.dither
        gates=tuple(i==0 or abs(y)>=width*sum(coefficients[:i],F(0)) for i in range(4))
        masks.append(gates)
        for i,gate in enumerate(gates):
            if gate:
                weight=row.count*row.dither/total
                for j in range(3):
                    matrix[i][j]+=weight*basis[j]
                constant[i]+=weight*(coefficients[3]*basis[3]-row.dither)
    matrix=tuple(map(tuple,matrix))
    constant=tuple(constant)
    assert tuple(sum((a*k for a,k in zip(row,coefficients)),F(0))+b for row,b in zip(matrix,constant))==values
    return matrix,constant,tuple(masks)


def _parameter_interval(inequalities):
    # Every inequality is a*h+b>=0 (closed) or >0 (open).
    lo,hi=F(0),F(2)
    closed_lo=closed_hi=False
    for a,b,closed in inequalities:
        if not a:
            if b<0 or (b==0 and not closed):
                return None
            continue
        point=-b/a
        if a>0:
            if point>lo:
                lo,closed_lo=point,closed
            elif point==lo:
                closed_lo&=closed
        else:
            if point<hi:
                hi,closed_hi=point,closed
            elif point==hi:
                closed_hi&=closed
    if lo>hi or (lo==hi and not (closed_lo and closed_hi)):
        return None
    return lo,hi,closed_lo,closed_hi


def analyze_seed(rows,coefficients,width=F(32)):
    """Propose a root in this seed's masks, or certify a maximal line segment.

    First three slopes move; the fourth remains at the seed value. A family
    parameter is the third slope itself. All four masks are protected so the
    fourth correlation can be separately checked throughout the segment.
    """
    rows,coefficients=tuple(rows),tuple(coefficients)
    if not isinstance(width,F) or any(not isinstance(k,F) for k in coefficients):
        raise TypeError('exact explicit Fraction geometry and coefficients required')
    matrix,constant,masks=affine_correlations(rows,coefficients,width)
    nullspace=exact_nullspace(matrix[:3])
    result={'seed':coefficients,'seed_correlations':stage_correlations(rows,coefficients,width),
            'fixed_mask_matrix':matrix,'fixed_mask_constant':constant,
            'gate_counts':tuple(sum(row.count for row,mask in zip(rows,masks) if mask[i]) for i in range(4)),
            'matrix_rank_first3':3-len(nullspace),'global_search_complete':False}
    if not nullspace:
        augmented=tuple((*row,b) for row,b in zip(matrix[:3],constant[:3]))
        vector=exact_nullspace(augmented)[0]
        assert vector[3]
        proposed=tuple(x/vector[3] for x in vector[:3])+(coefficients[3],)
        result['proposed_coefficients']=proposed
        if any(not 0<k<2 for k in proposed):
            result['status']='proposal_outside_legal_domain'
            return result
        actual=stage_correlations(rows,proposed,width)
        _,_,candidate_masks=affine_correlations(rows,proposed,width)
        result['proposed_actual_correlations']=actual
        result['proposal_preserves_seed_masks']=candidate_masks==masks
        if actual[:3]!=(F(0),)*3 or candidate_masks!=masks:
            result['status']='proposal_rejected_at_gate_change'
            return result
        result['status']='certified_point_root_in_seed_masks'
        result['all_four_correlations_zero']=actual==(F(0),)*4
        return result
    if result['seed_correlations'][:3]!=(F(0),)*3:
        result['status']='seed_not_three_correlation_root'
        return result
    if len(nullspace)!=1 or not nullspace[0][2]:
        result['status']='higher_dimensional_or_fixed_third_family_not_certified'
        return result
    direction=tuple(v/nullspace[0][2] for v in nullspace[0])+(F(0),)
    intercept=tuple(k-a*coefficients[2] for k,a in zip(coefficients,direction))
    constraints=[]
    for a,b in zip(direction[:3],intercept[:3]):
        constraints.extend(((a,b,False),(-a,2-b,False)))
    readout_sensitivities=[]
    for row,gates in zip(rows,masks):
        basis=stage_basis(row.raw,width)
        ya=sum((a*p for a,p in zip(direction,basis)),F(0))
        yb=sum((b*p for b,p in zip(intercept,basis)),F(0))-row.dither
        seed_y=ya*coefficients[2]+yb
        readout_sensitivities.append((ya,row.count))
        for i in range(1,4):
            ta=width*sum(direction[:i],F(0))
            tb=width*sum(intercept[:i],F(0))
            if gates[i]:
                sign=(seed_y>0)-(seed_y<0)
                assert sign
                constraints.append((sign*ya-ta,sign*yb-tb,True))
            else:
                constraints.extend(((ta-ya,tb-yb,False),(ta+ya,tb+yb,False)))
    interval=_parameter_interval(constraints)
    assert interval is not None
    lo,hi,lc,hc=interval
    assert lo<=coefficients[2]<=hi
    result.update(status='certified_root_segment_in_seed_masks',direction=direction,intercept=intercept,
                  third_parameter_interval=interval,
                  nonunique_root_segment=lo<hi,
                  readout_varying_conversions=sum(count for a,count in readout_sensitivities if a),
                  maximum_local_readout_sensitivity=max(abs(a) for a,count in readout_sensitivities))
    fourth_slope=sum((a*v for a,v in zip(matrix[3],direction)),F(0))
    result['fourth_correlation_slope']=fourth_slope
    result['all_four_correlations_zero_on_segment']=result['seed_correlations'][3]==0 and fourth_slope==0
    checks=[coefficients[2],(lo+hi)/2,(3*lo+hi)/4,(lo+3*hi)/4]
    if lc:checks.append(lo)
    if hc:checks.append(hi)
    for h in set(checks):
        ks=tuple(a*h+b for a,b in zip(direction,intercept))
        actual=stage_correlations(rows,ks,width)
        assert actual[:3]==(F(0),)*3
        assert affine_correlations(rows,ks,width)[2]==masks
        if result['all_four_correlations_zero_on_segment']:
            assert actual==(F(0),)*4
    result['direct_rational_check_points']=len(set(checks))
    return result
