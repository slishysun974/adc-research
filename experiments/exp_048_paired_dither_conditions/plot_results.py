"""Research figure for exact counterexample and finite pair support."""
from fractions import Fraction as F
import json
from pathlib import Path
import sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from experiments.exp_048_paired_dither_conditions.examples import periodic_cubic_error


def main(folder):
    data = json.loads((folder/'pair_examples.json').read_text())
    counter = data['single_magnitude_counterexample']
    centers = tuple(map(F, counter['centers']))
    errors = [float(F(row[0])) for row in counter['offline_score']['continuous_output_errors']]
    residuals = [float(F(v)) for v in counter['digital_fit']['contrast_residuals']]
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10,
                         'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(12.4, 4.7), layout='constrained')
    grid = tuple(F(i, 4) for i in range(-1760, 1761))
    axes[0].plot([float(v) for v in grid], [float(periodic_cubic_error(v-64)) for v in grid],
                 color='#ac653f', lw=1.5, label='Surviving periodic output error')
    axes[0].scatter([float(v) for v in centers], errors, color='#ac653f', s=15)
    axes[0].plot([float(v) for v in centers], residuals, color='#287f83', lw=2, label='Paired contrast residual = 0')
    axes[0].set(xlabel='Matched pre-dither target (stage codes)', ylabel='Output error / contrast residual (codes)',
                ylim=(-5, 5), title='An odd, monotone C1 transfer still passes')
    axes[0].legend(fontsize=8, loc='upper left')
    axes[0].text(.04, .06, 'All four digital slopes identified\n67 pairs; contrast MSE = 0\nOutput MSE = 5.0001 codes squared',
                 transform=axes[0].transAxes, fontsize=9, va='bottom',
                 bbox={'facecolor': 'white', 'edgecolor': '#d2d6d8', 'alpha': .92})
    graphs = data['finite_constraint_graphs']
    labels = ['D=64\nwide support', 'D=64,80\nwide support', 'D=64,65\nwide support', 'D=64,65\nnarrow support']
    values = [g['component_count'] for g in graphs]
    axes[1].bar(range(4), values, color=['#ac653f', '#689694', '#287f83', '#929aa1'])
    for i, value in enumerate(values):
        axes[1].text(i, value+3, str(value), ha='center')
    axes[1].set(xticks=range(4), xticklabels=labels, ylim=(0, 154),
                ylabel='Independent unanchored error constants', title='More amplitudes also need enough support')
    fig.suptitle('Paired dither cancels matched signal; it does not certify correct calibration', fontsize=13)
    fig.supxlabel('Exact synthetic examples. Graph counts precede anchor / symmetry constraints. No chip performance claim.', fontsize=9)
    fig.savefig(folder/'paired_dither_limits.png', dpi=180)
    fig.savefig(folder/'paired_dither_limits.svg')
    plt.close(fig)


if __name__ == '__main__':
    main(Path(sys.argv[1]))
