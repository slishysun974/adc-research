"""Plot certified pooled cycles. Float conversion is only for display."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from adc_research.theory.quantized_mean_dynamics import export_code


def main(folder):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,
                         'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(2,2,figsize=(11.6,6.8),layout='constrained')
    for row,name in enumerate(('iid_reset','iid_two_phase')):
        data=json.loads((folder/(name+'.json')).read_text())
        orbit=data['pooled_orbit']
        assert orbit['status']=='cycle' and orbit['cycle_period_verified_by_every_integer_step']
        states=[]
        for event in orbit['events'][orbit['cycle_event_start']:]:
            states.extend(tuple(z+j*d for z,d in zip(event['state'],event['deltas']))
                          for j in range(event['constant_request_steps']))
        assert len(states)==orbit['period']
        closed=states+[states[0]]
        x=list(range(len(closed)))
        accumulator=[z[1]/2**22 for z in closed]
        exported=[export_code(z[1])/1024 for z in closed]
        ax=axes[row,0]
        ax.plot(x,accumulator,color='#126b6f',lw=1.1,label='Q22 accumulator')
        ax.step(x,exported,where='post',color='#c36237',lw=1.0,label='Q1.10 exported slope')
        ax.axhline(17/16,color='#525b62',ls=':',lw=1,label='Q3 gate opens: 17/16')
        ax.set(title=f'{name}: exact period {orbit["period"]}',xlabel='Pooled mean-map update',ylabel='Second slope')
        ax.legend(fontsize=8,loc='upper right')
        ax=axes[row,1]
        baseline=closed[0]
        ax.plot([z[0]-baseline[0] for z in closed],[z[1]-baseline[1] for z in closed],color='#126b6f',lw=0.8)
        ax.scatter([0],[0],color='#c36237',s=25,zorder=3,label='Repeated full integer state')
        ax.set(title='Full integer-state cycle',xlabel='First accumulator change (Q22 LSB)',ylabel='Second accumulator change (Q22 LSB)')
        ax.legend(fontsize=8)
    fig.suptitle('Frozen empirical mean map: proven cycles, not phase-varying Gu steady state',fontsize=13)
    fig.savefig(folder/'mean_cycles.png',dpi=180)
    fig.savefig(folder/'mean_cycles.svg')
    plt.close(fig)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('folder',type=Path)
    main(parser.parse_args().folder)
