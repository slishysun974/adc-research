"""Plot measured XSim traces and existing behavioral metrics for the review."""
import argparse
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[3]

def read_vcd(path, limit_ps=124000):
    ids, widths, events = {}, {}, {}
    now = 0
    for line in path.read_text().splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == '$var':
            widths[parts[4]] = int(parts[2])
            ids[parts[3]] = parts[4]
            events[parts[4]] = []
        elif line.startswith('#'):
            now = int(line[1:])
            if now > limit_ps:
                break
        elif line.startswith('b') and len(parts) == 2 and parts[1] in ids:
            value = parts[0][1:]
            if not any(c in value.lower() for c in 'xz'):
                events[ids[parts[1]]].append((now/1000, int(value,2)))
        elif line[0] in '01' and line[1:] in ids:
            events[ids[line[1:]]].append((now/1000,int(line[0])))
    return events

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('run',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    plt.rcParams.update({'font.family':'Microsoft YaHei','font.size':12,'axes.spines.top':False,'axes.spines.right':False,'savefig.facecolor':'white'})
    events=read_vcd(args.run/'sim/online_repaired.vcd')
    tracks=[('clk','CLK',0),('valid_out','valid_out',0),('stage2_gate','stage2 gate mask',0),('final_code','final code',0),('a10','Stage 1 A0 − unity',4194304),('a20','Stage 2 A0 − unity',4194304)]
    fig,axes=plt.subplots(6,1,figsize=(11.8,5.5),sharex=True,gridspec_kw={'height_ratios':[.55,.55,.65,1,1,1]})
    colors=['#64748b','#087f8c','#087f8c','#172b4d','#c25b25','#087f8c']
    for ax,(name,label,offset),color in zip(axes,tracks,colors):
        pairs=events[name]
        t=[x[0] for x in pairs]+[124]
        y=[x[1]-offset for x in pairs]+[pairs[-1][1]-offset]
        ax.step(t,y,where='post',color=color,lw=1.6)
        ax.set_ylabel(label,rotation=0,ha='right',va='center',labelpad=12,fontsize=11)
        ax.set_xlim(58,124)
        ax.grid(axis='x',alpha=.18)
        ax.axvline(65,color='#c25b25',lw=1,ls='--',alpha=.7)
        ax.tick_params(axis='y',labelsize=9)
    axes[0].set_yticks([0,1]);axes[1].set_yticks([0,1]);axes[2].set_yticks([0,7,15])
    axes[0].set_title('XSim 实测：第 7–14 行输入、组合输出与时钟沿更新',loc='left',fontsize=15,pad=18)
    axes[-1].set_xlabel('仿真时间 / ns（测试激励间隔，不代表工作频率）')
    fig.subplots_adjust(left=.22,right=.985,top=.9,bottom=.12,hspace=.28)
    fig.savefig(args.output/'rtl_state_trace.png',dpi=180)
    fig.savefig(args.output/'rtl_state_trace.svg')
    plt.close(fig)
    summary=json.loads((ROOT/'simulink_adc/reduced_summary.json').read_text())
    checkpoint=summary['checkpoints']
    x=[int(k) for k in checkpoint]
    sndr=[checkpoint[str(k)]['floating']['sndr_db'] for k in x]
    sfdr=[checkpoint[str(k)]['floating']['sfdr_dbc'] for k in x]
    fig,ax=plt.subplots(figsize=(7.8,3.8))
    ax.plot(np.array(x)/1e6,sndr,'o-',color='#087f8c',lw=2,label='SNDR / dB')
    ax.plot(np.array(x)/1e6,sfdr,'s-',color='#c25b25',lw=2,label='SFDR / dBc')
    ax.set_xlabel('累计训练转换数 / 百万');ax.set_ylabel('指标 / dB');ax.set_ylim(40,85);ax.grid(alpha=.2);ax.legend(frameon=False,loc='lower right')
    ax.set_title('已有浮点 full120 行为结果',loc='left',fontsize=15)
    fig.tight_layout()
    fig.savefig(args.output/'behavior_metrics.png',dpi=180)
    fig.savefig(args.output/'behavior_metrics.svg')
    (args.output/'figure_provenance.json').write_text(json.dumps({'rtl_trace':'sim/online_repaired.vcd; XSim generated; ns scale from 1ps VCD','behavior_source':'simulink_adc/reduced_summary.json','checkpoints':x,'sndr_db':sndr,'sfdr_dbc':sfdr,'scope':'redrawn from frozen metrics; no training rerun'},indent=2))

if __name__=='__main__':
    main()
