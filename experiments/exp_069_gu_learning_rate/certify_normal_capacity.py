"""Exact feasible upper certificates for the already frozen read-only bracket.

Select no new references: certify the30 feasible winners saved by the prior
diagnostic. Integer sums and dyadic targets yield exact squared losses.
"""

import argparse
from fractions import Fraction as F
import json
from pathlib import Path
import traceback

import numpy as np

from adc_research.theory.static_fixed_contract import export, nearest_even, readout
from experiments.exp_062_same_input_background.verify import round_ratio
from .check_normal_loss_limits import (ROOT, OLD, NEW, N, NW, INTERVALS,
                                      digest, load, output_only, verify_hashes, write)


def certify(folder):
    folder = folder.resolve()
    assert not (folder/'exact_capacity.json').exists()
    protocol_path = folder/'capacity_certificate_protocol.json'
    assert not protocol_path.exists()
    inputs = {str((folder/'results.json').relative_to(ROOT)).replace('\\','/'):
              digest(folder/'results.json'),
              'experiments/exp_069_gu_learning_rate/certify_normal_capacity.py':
              digest(Path(__file__)),
              **load(folder/'execution_hashes.json')}
    write(protocol_path, {'date':'2026-10-12','purpose':'Exact feasible Gu upper certificate, no new reference selection',
          'inputs':inputs,'rows':30,'integer_readouts':30*3*N,'rational_readouts':30*3*2,
          'target':'same exact binary64 ideal level as frozen diagnostic',
          'lower':'original dyadic integer certificate unchanged',
          'failure_rule':'retain failure; no reference or block change',
          'new_adc_conversions':0,'new_learning_observations':0,'new_online_outputs':0,'new_fft':0})
    verify_hashes(inputs)
    verify_hashes(load(folder/'original_data_hashes.json'))
    data = load(folder/'results.json')
    paths = {(r['case'],r['seed'],r['rate'],r['method'],r['interval']):r for r in data['paths']}
    target = 2048*(1+np.fromfile(OLD/'tone.bin',dtype='<f8'))
    ratios = [float(t).as_integer_ratio() for t in target]
    den = max(d for _,d in ratios)
    aa = [a*(den//d) for a,d in ratios]*3
    total_a2 = sum(a*a for a in aa)
    certificates = []
    for row in data['static_capacity']:
        stem = f"{row['case']}_{row['seed']}"
        blocks = INTERVALS[row['interval']][2]
        words = np.memmap(OLD/(stem+'_words.bin'),dtype='i1',mode='r',shape=(NW,120,4))
        sampled = np.concatenate([words[b*256:(b+1)*256] for b in blocks])
        if row['upper_reference'] == 'unit':
            ref = np.full(8,1 << 22,dtype=np.int64)
        else:
            name,reference = row['upper_reference'].split('/')
            rate,method = name.split('_',1)
            ref = np.array(paths[row['case'],row['seed'],rate,method,row['interval']]['references'][reference]['state_q22'],dtype=np.int64)
        y = output_only(sampled,np.broadcast_to(ref,(768,8))).ravel()
        sum_y2 = int(np.dot(y,y))
        sum_ya = sum(int(v)*a for v,a in zip(y,aa,strict=True))
        numerator = sum_y2*den**2-2*den*sum_ya+total_a2
        upper = F(numerator,len(y)*den**2)
        lower = F(int(row['lower_numerator']),int(row['lower_denominator']))
        assert lower <= upper
        assert abs(float(upper)-row['upper_mse']) < 1e-8
        ks = tuple(F(k,1024) for k in export(tuple(map(int,ref))))
        for pos in [i*N+j for i in range(3) for j in (0,N-1)]:
            w,j = divmod(pos,120)
            q1,q2,be,bits = map(int,sampled[w,j])
            expected = nearest_even(readout(q1,q2,F(be),2*(bits&1)-1,2*((bits>>1)&1)-1,ks,data_q3=True).output)
            assert int(y[pos]) == expected
        certificates.append({**row,'upper_numerator':str(numerator),
            'upper_denominator':str(len(y)*den**2),'exact_width_numerator':str((upper-lower).numerator),
            'exact_width_denominator':str((upper-lower).denominator)})
    verify_hashes(inputs)
    verify_hashes(load(folder/'original_data_hashes.json'))
    write(folder/'exact_capacity.json',{'certificates':certificates,
          'validation':{'rows':30,'integer_readouts':30*3*N,'rational_readouts':30*3*2,
                        'lower_and_upper_exact':True,'original_files_unchanged':185}})
    print('30 exact empirical Gu capacity brackets certified;2764800 integer/180 rational readouts',flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder',type=Path)
    args = parser.parse_args()
    try:
        certify(args.folder)
    except Exception:
        (args.folder/'capacity_failure.txt').write_text(traceback.format_exc(),encoding='utf-8')
        raise
