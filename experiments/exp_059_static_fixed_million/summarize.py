"""Descriptive tables of all seeds; no selection or optimization."""
import argparse
import csv
from pathlib import Path
import json
import numpy as np
from experiments.exp_057_static_two_stage_million.common import write


def summarize(folder):
    data=json.loads((folder/'summary.json').read_text(encoding='utf-8'));rows=data['rows']
    groups=[];paired=[];support=[];decomposition=[]
    for case in dict.fromkeys(r['case'] for r in rows):
        for method in ('point30','full120'):
            group={'case':case,'method':method}
            for layer in ('float','q3','export','q22'):
                rr=[r for r in rows if (r['case'],r['method'],r['layer'])==(case,method,layer)]
                for kind in ('online','frozen'):
                    for output in ('continuous','integer'):
                        values=[r['checkpoints'][-1][kind][output]['sndr_db'] for r in rr]
                        group[f'{layer}_{kind}_{output}_sndr_mean']=float(np.mean(values))
                        group[f'{layer}_{kind}_{output}_sndr_range']=[min(values),max(values)]
                if layer=='q22':
                    group['unit_integer_sndr']=rr[0]['checkpoints'][0]['frozen']['integer']['sndr_db']
                    support.append({'case':case,'method':method,'gates':np.sum([r['gates'] for r in rr],axis=0).tolist(),
                                    'basis':np.sum([r['basis'] for r in rr],axis=0).tolist(),
                                    'both':np.sum([r['both'] for r in rr],axis=0).tolist()})
                dc={'case':case,'method':method,'layer':layer}
                for key in ('projection_residual_mse','mean_state_excess_mse','state_variance_mse','average_continuous_mse',
                            'subset_joint_mean_output_mse','subset_joint_output_variance_mse','subset_arithmetic_cross','subset_arithmetic_power'):
                    dc[key]=float(np.mean([r['fixed_rear_mean_covariance'][key] for r in rr]))
                decomposition.append(dc)
            groups.append(group)
            for seed in sorted({r['seed'] for r in rows}):
                rr={r['layer']:r for r in rows if (r['case'],r['method'],r['seed'])==(case,method,seed)}
                def score(layer):return rr[layer]['checkpoints'][-1]['online']['integer']['sndr_db']
                paired.append({'case':case,'method':method,'seed':seed,'q22_minus_float':score('q22')-score('float'),
                    'q3_minus_float':score('q3')-score('float'),'export_minus_q3':score('export')-score('q3'),
                    'q22_minus_export':score('q22')-score('export')})
    q22=[r for r in rows if r['layer']=='q22']
    counts={key:np.sum([r[key] for r in q22],axis=0).tolist() for key in ('hidden_changed','export_changed','zero_request')}
    counts['hidden_change_without_export']=(np.array(counts['hidden_changed'])-counts['export_changed']).tolist()
    out={'groups':groups,'paired':paired,'support_q22':support,'decomposition':decomposition,'q22_update_counts':counts,
         'maximum_increment_balance_error':max(r['finite_hidden_increment_balance']['maximum_balance_error'] for r in rows),
         'maximum_subset_mean_covariance_error':max(abs(r['fixed_rear_mean_covariance']['subset_identity_difference']) for r in rows),
         'pairwise_final_online_integer_q22_minus_float_range':[min(r['q22_minus_float'] for r in paired),max(r['q22_minus_float'] for r in paired)]}
    write(folder/'tables.json',out)
    columns=['case','method','unit_integer_sndr']+[f'{layer}_online_integer_sndr_mean' for layer in ('float','q3','export','q22')]
    with (folder/'online_integer_sndr.csv').open('w',newline='',encoding='utf-8-sig') as file:
        writer=csv.DictWriter(file,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(groups)
    print(json.dumps({'paired_range':out['pairwise_final_online_integer_q22_minus_float_range'],
                      'maximum_identity_error':out['maximum_subset_mean_covariance_error'],'counts':counts}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('folder',type=Path);summarize(parser.parse_args().folder.resolve())
