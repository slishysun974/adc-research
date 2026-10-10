"""Render exact saved cells; floating conversion is for display only."""

import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def draw(directory):
    summary = json.loads((directory/'summary.json').read_text())
    cases = {c['name']: c for c in summary['cases']}
    plt.rcParams.update({'font.size': 10, 'svg.fonttype': 'none'})
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), layout='constrained')
    plans = [('iid_reset', (1.055, 1.078), 'Random dither: jump without a zero'),
             ('periodic255_reset', (1.005, 1.020), 'Periodic dither: an isolated zero')]
    for ax, (name, limits, title) in zip(axes, plans):
        source = directory/(name+'.json')
        assert hashlib.sha256(source.read_bytes()).hexdigest() == cases[name]['output_sha256']
        scan = json.loads(source.read_text())['stage2_scan']
        for cell in scan['cells']:
            lo, hi = max(float(F(cell['low'])), limits[0]), min(float(F(cell['high'])), limits[1])
            if lo >= hi:
                continue
            a, b = F(cell['correlation_slope']), F(cell['correlation_intercept'])
            ax.plot([lo,hi], [float(a*F(lo)+b),float(a*F(hi)+b)], color='#254f78', linewidth=2)
        for boundary in scan['boundaries']:
            x = float(F(boundary['parameter']))
            if not limits[0] < x < limits[1]:
                continue
            left, right, value = (float(F(boundary[k])) for k in ('left_limit','right_limit','value'))
            ax.plot([x,x],[left,right],color='#738494',linestyle=':',linewidth=1)
            ax.scatter([x,x],[left,right],s=35,facecolor='white',edgecolor='#254f78',zorder=3)
            ax.scatter([x],[value],s=19,color='#254f78',zorder=4)
        for root in scan['roots']:
            x = float(F(root['parameter']))
            if limits[0] < x < limits[1]:
                ax.scatter([x],[0],marker='*',s=150,color='#bb5c22',zorder=5)
                ax.annotate(f'Exact zero\nk = {x:.6f}',(x,0),xytext=(-115,-45),textcoords='offset points',
                            color='#8f4318',fontsize=9,
                            arrowprops={'arrowstyle':'-','color':'#8f4318','linewidth':0.8})
        ax.axhline(0,color='#333333',linewidth=0.9)
        ax.set_xlim(*limits)
        ax.set_title(title,loc='left',fontsize=11,pad=12)
        ax.set_xlabel('Stage-2 second slope, on the first-correlation zero line')
        ax.set_ylabel('Second gated correlation (code squared)')
        ax.grid(axis='y',alpha=0.18)
        ax.spines[['top','right']].set_visible(False)
    fig.suptitle('EXP-042: gate jumps must be evaluated separately from open cells',fontsize=13)
    fig.savefig(directory/'gated_roots.png',dpi=200)
    fig.savefig(directory/'gated_roots.svg')
    plt.close(fig)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory',type=Path)
    directory = parser.parse_args().directory.resolve()
    directory.relative_to(Path(__file__).resolve().parents[2]/'artifacts/runs/EXP_042')
    draw(directory)
