"""Plot exact certified segments; floats are display-only."""
from fractions import Fraction as F
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main(folder):
    summary=json.loads((folder/'summary.json').read_text())
    rows=[]
    for case in summary['cases']:
        for index,r in enumerate(case['certified_results']):
            if r['status']=='certified_root_segment_in_seed_masks':
                rows.append((case['name']+(' / '+str(index+1) if len(case['certified_results'])>1 else ''),r))
    fig,axes=plt.subplots(1,2,figsize=(11.6,4.4),layout='constrained')
    ax=axes[0]
    colors=['#126b6f','#448d90','#a35431','#8da849','#b89a54']
    for i,(label,r) in enumerate(rows):
        lo,hi,lc,hc=r['third_parameter_interval']
        lo,hi=float(F(lo)),float(F(hi))
        ax.plot((lo,hi),(i,i),color=colors[i],lw=5,solid_capstyle='butt')
        for x,closed in ((lo,lc),(hi,hc)):
            ax.scatter([x],[i],s=45,edgecolor=colors[i],facecolor=colors[i] if closed else 'white',zorder=3)
    ax.axvline(1,color='#68747b',ls='--',lw=1,label='Unity third slope')
    ax.set_yticks(range(len(rows)),[r[0] for r in rows])
    ax.set(xlabel='Free third slope',title='Certified fixed-gate root segments')
    ax.invert_yaxis()
    ax.legend(fontsize=8,loc='lower left')
    r=rows[0][1]
    low,high=map(F,r['third_parameter_interval'][:2])
    parameter=[low+(high-low)*F(i,100) for i in range(101)]
    direction=tuple(map(F,r['direction']))
    intercept=tuple(map(F,r['intercept']))
    ax=axes[1]
    for j,label,color in ((0,'First slope','#126b6f'),(1,'Second slope','#a35431')):
        ax.plot([float(h) for h in parameter],[float(direction[j]*h+intercept[j]) for h in parameter],label=label,color=color,lw=2)
    ax.set(xlabel='Free third slope',ylabel='Compensating low slope',title='iid_reset: all four correlations remain zero')
    ax.legend()
    fig.suptitle('Released third slope: local nonunique empirical roots (fourth fixed at 1)',fontsize=13)
    fig.savefig(folder/'released_third_segments.png',dpi=180)
    fig.savefig(folder/'released_third_segments.svg')
    plt.close(fig)


if __name__=='__main__':
    main(Path(sys.argv[1]))
