"""Recorded update variance, final-code gains and fixed-budget checkpoints."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def run(directory):
    summary = json.loads((directory/"summary.json").read_text())
    out = directory/"figures"
    out.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,
                        "figure.dpi":160,"savefig.dpi":160,"axes.spines.top":False,"axes.spines.right":False})
    colors = {"baseline":"#687481","quarter_step":"#186a92","ema_quarter":"#c66627"}
    labels = {"baseline":"Baseline","quarter_step":"Step / 4","ema_quarter":"EMA alpha = 1/4"}
    fig,axes = plt.subplots(1,2,figsize=(12.2,4.8),layout="constrained")
    for comparison in summary["comparisons"]:
        method = comparison["method"]
        axes[0].scatter([p["first_delta_variance_ratio"] for p in comparison["pairs"]],
            [p["sndr_gain_db"] for p in comparison["pairs"]],color=colors[method],s=34,alpha=.75,label=labels[method])
    axes[0].axhline(0,color="#687481",ls=":",lw=1)
    axes[0].set(xlabel="Recorded k1-update variance / baseline",ylabel="Online SNDR gain vs baseline (dB)",
                title="Lower update variance does not ensure better codes",xlim=(0.045,0.245))
    axes[0].grid(alpha=.18)
    axes[0].legend(fontsize=9)
    points = (0,32,64,96,128)
    for method in ("baseline","quarter_step","ema_quarter"):
        methods = [m for c in summary["cases"] for m in c["methods"] if m["method"] == method]
        gains = [sum(m["frozen_checkpoint_sine"][str(w)]["sndr_db"]-m["frozen_checkpoint_sine"]["0"]["sndr_db"] for m in methods)/len(methods) for w in points]
        axes[1].plot(points,gains,"o-",color=colors[method],label=labels[method])
    axes[1].axhline(0,color="#969da5",ls=":",lw=1)
    axes[1].set(xlabel="Training checkpoint (window)",ylabel="Mean frozen SNDR gain vs unit coefficients (dB)",
                title="Same training budget, no best-stop selection",xticks=points)
    axes[1].grid(alpha=.18)
    axes[1].legend(fontsize=9)
    fig.suptitle("Four selected samples per 120 conversions: noise, learning and final-code tradeoffs\nAll 24 prespecified cells; ordinary floating-point spectral scoring",fontsize=12)
    fig.savefig(out/"variance_gain_and_checkpoints.png")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    run(parser.parse_args().directory.resolve())
