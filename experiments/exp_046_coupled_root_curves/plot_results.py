"""Certified local curve pieces and independently frozen integer-code scores."""
from fractions import Fraction as F
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from adc_research.theory.coupled_root_curve import curve_coefficients


def main(folder):
    summary=json.loads((folder/'summary.json').read_text())
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,
                         'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,2,figsize=(11.6,4.6),layout='constrained')
    palette={'iid_reset':'#126b6f','iid_two_phase':'#4b9295',
             'periodic255_reset':'#a35431','periodic255_two_phase':'#839b48'}
    all_curves=[]
    for case in summary['cases']:
        data=json.loads((folder/(case['name']+'.json')).read_text())
        if not data['candidates']:continue
        color=palette[case['name']]
        for index,c in enumerate(data['candidates']):
            model={k:tuple(map(F,c['curve_model'][k])) for k in ('denominator','numerator_u','numerator_v')}
            model['seed_parameter']=F(c['seed_parameter'])
            lo,hi=map(F,c['certificate']['parameter_interval'])
            hs=[lo+(hi-lo)*F(i,20) for i in range(21)]
            axes[0].plot([float(h) for h in hs],[float(curve_coefficients(model,h)[0]) for h in hs],color=color,lw=2)
            h=float(F(c['seed_parameter']))
            p=float(F(c['seed_coefficients'][4]))
            sndr=c['offline_frozen_scores']['online_sine']['spectrum_float']['sndr_db']
            axes[0].scatter([h],[p],s=32,color=color,label=case['name'] if index==0 else None)
            axes[1].scatter([h],[sndr],s=32,color=color,label=case['name'] if index==0 else None)
            all_curves.append((case['name'],index,h,sndr))
    axes[0].set(xlabel='Backend third slope',ylabel='Front first slope',title='Local joint zero-correlation curves')
    axes[0].legend(fontsize=8,loc='lower left')
    axes[1].set(xlabel='Backend third slope at seed',ylabel='Frozen sine SNDR (dB)',title='All correlations zero does not select one score')
    axes[1].legend(fontsize=8,loc='lower left')
    selected=[r for r in all_curves if r[0]=='periodic255_reset' and r[1] in (4,5)]
    x=selected[0][2]
    lower,upper=sorted(r[3] for r in selected)
    axes[1].annotate('',xy=(x,upper),xytext=(x,lower),arrowprops={'arrowstyle':'<->','color':'#343f46','lw':1})
    axes[1].text(x-0.12,(upper+lower)/2,'16.97 dB\nsame backend',fontsize=9,ha='right',va='center')
    fig.suptitle('17 certified continuous mean-root pieces; integer correction scored separately',fontsize=13)
    fig.savefig(folder/'coupled_roots_and_scores.png',dpi=180)
    fig.savefig(folder/'coupled_roots_and_scores.svg')
    plt.close(fig)


if __name__=='__main__':main(Path(sys.argv[1]))
