"""Display every prespecified paired cell, including all losses."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def run(directory):
    summary = json.loads((directory/"summary.json").read_text())
    out = directory/"figures"
    out.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,
                        "figure.dpi":160,"savefig.dpi":160})
    fig,axes = plt.subplots(2,1,figsize=(11.8,7.5),layout="constrained")
    names = [(curve,inputs,history) for curve in ("weak_compression","expansion")
             for inputs in ("uniform","central") for history in ("reset","hold")]
    labels = [f"{'Weak' if c == 'weak_compression' else 'Expansion'}\n{i}\n{h}" for c,i,h in names]
    for ax,comparison in zip(axes,summary["paired_comparisons"]):
        values = np.zeros((3,8))
        for pair in comparison["pairs"]:
            case = next(c for c in summary["cases"] if c["name"] == pair["case"])
            column = names.index((case["curve_name"],case["input_name"],case["history_name"]))
            values[pair["trial"]-1,column] = pair["sndr_gain_db"]
        im = ax.imshow(values,cmap="RdBu",vmin=-21,vmax=21,aspect="auto")
        ax.set(xticks=range(8),xticklabels=labels,yticks=range(3),yticklabels=("Group 1","Group 2","Group 3"))
        name = "Rotation" if comparison["method"] == "rotate" else "32-bit pseudorandom phases"
        ax.set_title(f"{name}: mean {comparison['mean_online_sndr_gain_db']:+.2f} dB, {comparison['positive_cells']}/24 positive; screen FAILED",fontsize=12,pad=10)
        for row in range(3):
            for col in range(8):
                ax.text(col,row,f"{values[row,col]:+.2f}",ha="center",va="center",
                        color="white" if abs(values[row,col]) > 10 else "#1f2933",fontsize=11)
    fig.colorbar(im,ax=axes,label="Online SNDR gain vs fixed phase 0 (dB)",shrink=.85)
    fig.suptitle("Changing phase alone gives inconsistent final-code performance\nAll 24 paired cells; groups change both seeds and sine frequencies",fontsize=13)
    fig.savefig(out/"all_paired_phase_gains.png")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    run(parser.parse_args().directory.resolve())
