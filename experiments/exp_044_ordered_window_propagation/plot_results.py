"""Static figures for finite chronology and high-slope effects."""
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main(root):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
    support={c['name']:c for c in json.loads((root/'gate_support.json').read_text())['cases']}
    fig,axes=plt.subplots(2,2,figsize=(11.6,6.8),layout='constrained')
    for row,name in enumerate(('iid_direct_hold','periodic255_direct_hold')):
        data=json.loads((root/(name+'.json')).read_text())
        ax=axes[row,0]
        tube=data['tubes'][1]
        x=list(range(161))
        boxes=[tube['initial_box']]+[w['next_box'] for w in tube['rows']]
        lower=[b['stage2_accumulators'][2]['lower']/2**22 for b in boxes]
        upper=[b['stage2_accumulators'][2]['upper']/2**22 for b in boxes]
        y=[z[2]/2**22 for z in data['trajectory_q22']['unchanged_gu']]
        ax.fill_between(x,lower,upper,color='#a8c9cc',alpha=0.7,label='Proved box: initial +/- half coefficient LSB')
        ax.plot(x,y,color='#126b6f',lw=1.5,label='Unchanged Gu third accumulator')
        ax.axhline(1,color='#a35431',ls='--',lw=1,label='Clamped-high control')
        ax.axvline(128,color='#68747b',ls=':',lw=1)
        ax.set(title=name,xlabel='Chronological window (120 conversions)',ylabel='Stage-2 third coefficient (Q22 value)')
        ax.legend(fontsize=8,loc='upper left')
        ax=axes[row,1]
        g=support[name]
        d=data['high_code_decomposition']['online_sine']
        labels=['Third gate\nall records','Gate with zero\nown basis','Direct high\nsine code','Indirect low\nsine code','Total\nsine code']
        heights=[g['third_gate_conversions'],g['gated_zero_third_basis_conversions'],
                 d['direct_high']['nonzero_count'],d['indirect_low_history']['nonzero_count'],d['total']['nonzero_count']]
        bars=ax.bar(labels,heights,color=['#68747b','#a8c9cc','#126b6f','#8da849','#a35431'],width=0.65)
        ax.bar_label(bars,padding=3)
        ax.set(title='Gate activity and output changes are different quantities',ylabel='Conversion count',ylim=(0,max(heights)*1.2))
        ax.tick_params(axis='x',labelsize=8)
    fig.suptitle('Finite original window sequence: state coverage and high-slope effects',fontsize=13)
    fig.savefig(root/'ordered_window_results.png',dpi=180)
    fig.savefig(root/'ordered_window_results.svg')
    plt.close(fig)


if __name__=='__main__':
    main(Path(sys.argv[1]))
