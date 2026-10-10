"""Readonly group tables and a standalone scientific figure for EXP-057."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from experiments.exp_057_static_two_stage_million.common import write


def summarize(folder):
    summary=json.loads((folder/"summary.json").read_text(encoding="utf-8"))
    rows=summary["rows"]
    cases=["ideal","front_linear","both_linear","front_smooth","both_smooth"]
    groups=[]
    for case in cases:
        for mode in ("continuous_reference","sar8"):
            for method in ("point30","full120"):
                group=[r for r in rows if r["case"]==case and r["backend"]==mode and r["method"]==method]
                end=[r["checkpoints"][-1] for r in group]
                unit=group[0]["checkpoints"][0]["frozen_tone"]["sndr_db"]
                online=np.array([p["online_tone"]["sndr_db"] for p in end])
                common=[next(p for p in r["checkpoints"] if p["windows"]==8334) for r in group]
                projection=[p["validation_projection"] for p in end]
                groups.append({"case":case,"backend":mode,"method":method,"seeds":len(group),
                    "unit_sndr_db":unit,"online_sndr_mean":float(np.mean(online)),
                    "online_sndr_values":online.tolist(),"online_sndr_min":float(np.min(online)),
                    "online_sndr_max":float(np.max(online)),"online_sndr_delta_mean":float(np.mean(online)-unit),
                    "seeds_improving_over_unit":int(np.sum(online>unit)),
                    "online_sfdr_mean":float(np.mean([p["online_tone"]["sfdr_dbc"] for p in end])),
                    "frozen_sndr_mean":float(np.mean([p["frozen_tone"]["sndr_db"] for p in end])),
                    "common_conversion_sndr_mean":float(np.mean([p["online_tone"]["sndr_db"] for p in common])),
                    "validation_mse_mean":float(np.mean([p["actual_validation_mse"] for p in projection])),
                    "fixed_rear_front_residual_mse_mean":float(np.mean([p["fixed_rear_front_projection_mse"] for p in projection])),
                    "front_coefficient_excess_mse_mean":float(np.mean([p["front_coefficient_excess_mse"] for p in projection])),
                    "front_third_gates":[r["gate_counts"][2] for r in group],
                    "rear_third_gates":[r["gate_counts"][6] for r in group],
                    "front_third_basis":[r["nonzero_basis_counts"][2] for r in group],
                    "rear_third_basis":[r["nonzero_basis_counts"][6] for r in group],
                    "front_third_gate_and_basis":[r["gate_and_nonzero_basis_counts"][2] for r in group],
                    "rear_third_gate_and_basis":[r["gate_and_nonzero_basis_counts"][6] for r in group],
                    "tail_coefficient_mean_across_seeds":np.mean([r["tail"]["mean"] for r in group],axis=0).tolist(),
                    "tail_coefficient_std_mean":np.mean([r["tail"]["standard_deviation"] for r in group],axis=0).tolist()})
    audit={"groups":groups,"largest_projection_cross_term":max(abs(p["validation_projection"]["projection_cross_term"])
               for r in rows for p in r["checkpoints"]),
           "online_coefficient_clips":sum(p["online_tone"]["coefficient_clips"] for r in rows for p in r["checkpoints"]),
           "online_output_clips":sum(p["online_tone"]["output_clips"] for r in rows for p in r["checkpoints"]),
           "all_fourth_gate_counts_zero":all(r["gate_counts"][3]==r["gate_counts"][7]==0 for r in rows),
           "all_fourth_basis_counts_zero":all(r["nonzero_basis_counts"][3]==r["nonzero_basis_counts"][7]==0 for r in rows)}
    write(folder/"group_statistics.json",audit)
    fig,axes=plt.subplots(1,3,figsize=(14,4.4),constrained_layout=True)
    colors={"point30":"#d27927","full120":"#246789"}
    labels=["Ideal","Front gain","Both gain","Front cubic","Both cubic"]
    for method,offset in (("point30",-.16),("full120",.16)):
        relevant=[g for g in groups if g["backend"]=="sar8" and g["method"]==method]
        axes[0].bar(np.arange(5)+offset,[g["online_sndr_mean"] for g in relevant],width=.29,
                    color=colors[method],alpha=.4,label=method)
        for i,g in enumerate(relevant):
            axes[0].scatter(i+offset+np.linspace(-.04,.04,5),g["online_sndr_values"],s=12,color=colors[method],zorder=3)
    units=[next(g["unit_sndr_db"] for g in groups if g["backend"]=="sar8" and g["case"]==c) for c in cases]
    axes[0].scatter(np.arange(5),units,marker="x",color="#222222",label="unit bank",zorder=4)
    axes[0].set_ylim(40,77);axes[0].set_xticks(np.arange(5),labels,rotation=24,ha="right")
    axes[0].set_ylabel("Online tone SNDR (dB)");axes[0].set_title("A. Full output after about 1M observations")
    axes[0].legend(fontsize=8,frameon=False,loc="upper right")

    selected=[g for g in groups if g["case"]=="both_smooth" and g["backend"]=="sar8"]
    for j,field,label in ((0,"front_third_basis","Nonzero basis"),
                          (1,"front_third_gates","Learning gate"),
                          (2,"front_third_gate_and_basis","Both")):
        vals=[float(np.mean(g[field])) for g in selected]
        positions=np.arange(2)+(j-1)*.22
        axes[1].bar(positions,[max(v,.5) for v in vals],width=.20,color=["#788b99","#d27927","#246789"][j],label=label)
        for x,v in zip(positions,vals):
            axes[1].text(x,max(v,.5)*1.3,"0" if v==0 else f"{v:,.0f}",ha="center",fontsize=8)
    axes[1].set_yscale("log");axes[1].set_ylim(.3,1e6)
    axes[1].set_xticks([0,1],["point30","full120"])
    axes[1].set_ylabel("Front third-slope observations (log scale)")
    axes[1].set_title("B. Readout support does not imply learning")
    axes[1].legend(fontsize=8,frameon=False,loc="upper right")

    residual=[g["fixed_rear_front_residual_mse_mean"] for g in selected]
    excess=[g["front_coefficient_excess_mse_mean"] for g in selected]
    axes[2].bar([0,1],residual,width=.55,color="#788b99",label="Fit residual at current rear")
    axes[2].bar([0,1],excess,width=.55,bottom=residual,color=colors["point30"],alpha=.6,label="Front coefficient excess")
    for x,a,b in zip([0,1],residual,excess):axes[2].text(x,a+b+.7,f"{a+b:.2f}",ha="center",fontsize=9)
    axes[2].set_xticks([0,1],["point30","full120"])
    axes[2].set_ylim(0,38);axes[2].set_ylabel("Validation MSE (code squared)")
    axes[2].set_title("C. State error exceeds fixed-rear fit residual")
    axes[2].legend(fontsize=8,frameon=False,loc="upper right")
    for ax in axes:
        ax.spines[["top","right"]].set_visible(False)
        ax.grid(axis="y",alpha=.15);ax.tick_params(axis="x",labelsize=9)
    fig.suptitle("EXP-057 | Static candidate, 8-bit SAR | About 1M learning observations per bank",fontsize=14)
    fig.savefig(folder/"cascade_statistics.png",dpi=160)
    fig.savefig(folder/"cascade_statistics.svg")
    plt.close(fig)
    print(json.dumps({k:v for k,v in audit.items() if k!="groups"}))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("folder",type=Path)
    summarize(p.parse_args().folder.resolve())
