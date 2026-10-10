"""Static research figures for the verified unit-start experiment."""

import argparse
from pathlib import Path
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def run(directory):
    summary = json.loads((directory/"summary.json").read_text())
    verification = json.loads((directory/"verification_and_propagation.json").read_text())
    out = directory/"figures"
    out.mkdir(exist_ok=True)
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.spines.top":False,
                        "axes.spines.right":False,"figure.dpi":160,"savefig.dpi":160})
    fig,axes = plt.subplots(1,2,figsize=(12,4.8),layout="constrained")
    checkpoints = (0,32,64,96,128)
    for ax,case_name,title in zip(axes,("weak_compression__uniform__reset","expansion__uniform__reset"),
                                ("Weak compression / uniform / reset","Expansion / uniform / reset")):
        case = next(c for c in summary["cases"] if c["name"] == case_name)
        unit = case["methods"][0]["frozen_checkpoint_sine"]["0"]["sndr_db"]
        ax.axhline(unit,color="#969da5",ls=":",label="Unit coefficients")
        for method,color,label in (("all_products","#186a92","All 120 products"),("point_products","#c66627","Fixed 4-point selection")):
            m = next(m for m in case["methods"] if m["method"] == method)
            ax.plot(checkpoints,[m["frozen_checkpoint_sine"][str(w)]["sndr_db"] for w in checkpoints],
                    "o-",color=color,label=label)
            ax.scatter([144],[m["online_sine"]["sndr_db"]],marker="D",s=48,color=color)
            ax.annotate(f"{m['online_sine']['sndr_db']:.2f}",(144,m["online_sine"]["sndr_db"]),
                        xytext=(4,5 if method == "all_products" else -13),textcoords="offset points",color=color)
        ax.set(title=title,xlabel="Training checkpoint (window)",ylabel="Approximate SNDR (dB)",xticks=(*checkpoints,144))
        ax.set_xticklabels(("0","32","64","96","128","online"))
        ax.grid(axis="y",alpha=.18)
    axes[0].legend(loc="upper left",fontsize=9)
    fig.suptitle("Frozen checkpoint scores and continued-online sine scores\nSame 3,840 sine observations; diamonds are full-record online scores",fontsize=12)
    fig.savefig(out/"checkpoint_and_online_sndr.png")
    plt.close(fig)
    cases = [c for c in verification["interventions"] if c["section"] == "holdout" and c["method"] == "point_products" and "__uniform__" in c["case"]]
    labels = ("Weak / reset","Weak / hold","Expansion / reset","Expansion / hold")
    fig,axes = plt.subplots(1,2,figsize=(12,4.6),layout="constrained")
    names = ("trained_both","current_front","current_backend","current_both")
    colors = ("#616b76","#c66627","#529483","#186a92")
    for k,(name,color) in enumerate(zip(names,colors)):
        axes[0].bar([i+(k-1.5)*.19 for i in range(4)],[c["scores"][name]["mse_codes_squared"] for c in cases],width=.18,color=color,label=name.replace("_"," "))
    axes[0].set(xticks=range(4),xticklabels=labels,ylabel="Final integer-code MSE (code squared)",title="Trained/current bank interventions")
    axes[0].legend(fontsize=8)
    axes[0].grid(axis="y",alpha=.18)
    for k,(key,color) in enumerate(zip(("front_only_sse","backend_only_sse","interaction_sse"),("#c66627","#529483","#969da5"))):
        axes[1].bar([i+(k-1)*.24 for i in range(4)],[c["exact_sse_effects"][key]/3840 for c in cases],width=.23,color=color,label=key.replace("_sse","").replace("_"," "))
    axes[1].axhline(0,color="#616b76",lw=.8)
    axes[1].set(xticks=range(4),xticklabels=labels,ylabel="MSE change from trained banks (code squared)",title="Exact additive error effects, interaction retained")
    axes[1].legend(fontsize=8)
    axes[1].grid(axis="y",alpha=.18)
    for ax in axes:
        ax.tick_params(axis="x",labelrotation=15)
    fig.suptitle("Fixed 4-point selection: front-bank changes explain the main loss in these four cells",fontsize=12)
    fig.savefig(out/"sine_bank_interventions.png")
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    run(parser.parse_args().directory.resolve())
