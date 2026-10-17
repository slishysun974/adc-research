"""Exact offline output moments under observation and block partitions.

Block labels are analytical partitions, not newly available online signals.
No independence, population law or unique causal allocation is assumed.
"""
from collections import defaultdict
from dataclasses import dataclass
from fractions import Fraction as F


def _records(observations, blocks, targets, outputs):
    rows = tuple(zip(tuple(observations), tuple(blocks), tuple(map(F, targets)),
                     tuple(map(F, outputs)), strict=True))
    if not rows:
        raise ValueError('nonempty equally sized records required')
    return rows


@dataclass(frozen=True)
class NestedMoments:
    output_variance: F
    within_block_output_variance: F
    between_block_output_variance: F
    target_output_covariance: F
    within_block_covariance: F
    between_block_covariance: F


def nested_moments(observations, blocks, targets, outputs):
    rows = _records(observations, blocks, targets, outputs)
    coarse, fine = defaultdict(list), defaultdict(list)
    for o,b,t,y in rows:
        coarse[o].append((t,y)); fine[o,b].append((t,y))
    mean = lambda values: sum(values,F(0))/len(values)
    means = {o:(mean([t for t,_ in values]),mean([y for _,y in values]))
             for o,values in coarse.items()}
    variance = covariance = within = within_cov = between = between_cov = F(0)
    for o,values in coarse.items():
        mt,my = means[o]
        variance += sum((y-my)**2 for _,y in values)
        covariance += sum((t-mt)*(y-my) for t,y in values)
    for (o,b),values in fine.items():
        mt,my = mean([t for t,_ in values]),mean([y for _,y in values])
        within += sum((y-my)**2 for _,y in values)
        within_cov += sum((t-mt)*(y-my) for t,y in values)
        ot,oy = means[o]
        between += len(values)*(my-oy)**2
        between_cov += len(values)*(mt-ot)*(my-oy)
    n = len(rows)
    assert variance == within+between and covariance == within_cov+between_cov
    return NestedMoments(*(v/n for v in (variance,within,between,covariance,within_cov,between_cov)))


@dataclass(frozen=True)
class SubsetLossShift:
    full_loss: F
    subset_loss: F
    observation_composition: F
    conditional_loss_change: F
    full_mass_of_unseen_observations: F


def subset_loss_shift(observations, targets, outputs, selected_indices):
    obs,targets,outputs = tuple(observations),tuple(map(F,targets)),tuple(map(F,outputs))
    if not obs or len(obs) != len(targets) or len(obs) != len(outputs):
        raise ValueError('nonempty equally sized records required')
    selected = tuple(selected_indices)
    if (not selected or len(set(selected)) != len(selected)
            or any(not isinstance(i,int) or i < 0 or i >= len(obs) for i in selected)):
        raise ValueError('distinct valid nonempty subset indices required')
    n,ns = len(obs),len(selected)
    full,sub = defaultdict(list),defaultdict(list)
    for o,t,y in zip(obs,targets,outputs,strict=True):
        full[o].append((y-t)**2)
    for i in selected:
        sub[obs[i]].append((outputs[i]-targets[i])**2)
    composition = conditional = missing = F(0)
    for o,values in full.items():
        q = F(len(values),n); p = F(len(sub[o]),ns)
        lf = sum(values,F(0))/len(values)
        composition += (p-q)*lf
        if sub[o]:
            conditional += p*(sum(sub[o],F(0))/len(sub[o])-lf)
        else:
            missing += q
    full_loss = sum(((y-t)**2 for y,t in zip(outputs,targets,strict=True)),F(0))/n
    sub_loss = sum(((outputs[i]-targets[i])**2 for i in selected),F(0))/ns
    assert sub_loss-full_loss == composition+conditional
    return SubsetLossShift(full_loss,sub_loss,composition,conditional,missing)
