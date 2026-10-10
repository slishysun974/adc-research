"""Static research figure; numeric data stay exact in the JSON artifacts."""
from fractions import Fraction as F
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main(folder):
    digital = json.loads((folder/'digital_gate_sources.json').read_text())['partitions']['fit']
    offline = json.loads((folder/'offline_target_bias.json').read_text())
    branches = digital['branches']
    zero = [b['gates'][1]['groups'][0]['count'] for b in branches]
    nonzero = [b['gates'][1]['groups'][1]['count'] for b in branches]
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 3, figsize=(13.5, 4.4), layout='constrained')
    axes[0].bar(['A', 'B'], zero, color='#b56b43', label='Second basis = 0')
    axes[0].bar(['A', 'B'], nonzero, bottom=zero, color='#368185', label='Second basis != 0')
    for i, (a, b) in enumerate(zip(zero, nonzero)):
        axes[0].text(i, a/2, str(a), ha='center', va='center', color='white')
        axes[0].text(i, a+b/2, str(b), ha='center', va='center', color='white')
        axes[0].text(i, a+b+220, str(a+b), ha='center')
    axes[0].set(ylabel='Samples opening the second update gate', ylim=(0, 12400),
                title='Inner samples dominate branch B')
    axes[0].legend(fontsize=8, loc='upper left')
    for i, b in enumerate(branches):
        values = [float(F(g['correlation'])) for g in b['gates'][1]['groups']]
        axes[1].barh([2*i, 2*i+0.65], values, height=0.5, color=['#b56b43', '#368185'])
        for y, v in zip((2*i, 2*i+0.65), values):
            axes[1].text(v/2, y, f'{v:+.2f}', va='center', ha='center',
                         color='white', fontsize=9)
    axes[1].axvline(0, color='#66737b', lw=0.8)
    axes[1].set(yticks=[0, .65, 2, 2.65], yticklabels=['A: zero', 'A: support', 'B: zero', 'B: support'],
                xlim=(-3100, 3100), xlabel='Contribution to mean D*Y (code squared)',
                title='Opposite terms cancel exactly')
    axes[1].invert_yaxis()
    mse = [float(F(b['continuous_mse'])) for b in offline['fit_branch_bias']]
    mse.append(float(F(offline['fit_only_projection']['minimum_continuous_mse'])))
    axes[2].bar(['A', 'B', 'Offline\nprojection'], mse, color=['#368185', '#b56b43', '#929aa1'])
    axes[2].set(yscale='log', ylabel='Continuous fit MSE (code squared)', ylim=(.3, 16000),
                title='Zero correlation does not minimize error')
    for i, v in enumerate(mse):
        axes[2].text(i, v*1.2, f'{v:.2f}', ha='center')
    fig.suptitle('Same 11,520 digital observations, same backend, two stable continuous mean roots', fontsize=12)
    fig.supxlabel('A/B are existing roots; the offline projection uses ideal targets and is not an online algorithm.', fontsize=9)
    fig.savefig(folder/'front_gate_sources.png', dpi=180)
    fig.savefig(folder/'front_gate_sources.svg')
    plt.close(fig)


if __name__ == '__main__':
    main(Path(sys.argv[1]))
