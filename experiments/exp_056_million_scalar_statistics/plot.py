"""Standalone scientific summary figure from the frozen EXP-056 results."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def plot(folder):
    summary=json.loads((folder/"summary.json").read_text(encoding="utf-8"))
    rows=summary["rows"]
    fig,axes=plt.subplots(1,3,figsize=(13,4.1),constrained_layout=True)
    colors={"point30":"#d27927","full120":"#246789"}
    for method in colors:
        group=[r for r in rows if r["input"]=="wide_uniform" and r["gain"]=="39/40"
               and r["quantizer"]=="continuous" and r["method"]==method]
        values=[r["tail"]["standard_deviation"] for r in group]
        x=list(colors).index(method)
        axes[0].bar(x,group[0]["law"]["stationary_variance"]**.5,
                    width=.55,color=colors[method],alpha=.4,label=method)
        axes[0].scatter(x+np.linspace(-.1,.1,5),values,color=colors[method],s=24,zorder=3)
    axes[0].set_xticks([0,1],["4 samples x30","120 samples x1"])
    axes[0].set_ylabel("Coefficient standard deviation")
    axes[0].set_title("A. Noise remains after long learning")
    axes[0].text(.97,.88,"bars: analytic; dots: five seeds",transform=axes[0].transAxes,
                 fontsize=9,ha="right")

    inputs=["wide_uniform","narrow_uniform","dc"]
    for method,offset in (("point30",-.08),("full120",.08)):
        means,errors=[],[]
        for inp in inputs:
            group=[r for r in rows if r["input"]==inp and r["gain"]=="39/40"
                   and r["quantizer"]=="floor10" and r["method"]==method]
            means.append(1000*(np.mean([r["tail"]["mean"] for r in group])-40/39))
            errors.append(1000*group[0]["tail"]["predicted_correlated_mean_standard_error"]/np.sqrt(5))
        axes[1].errorbar(np.arange(3)+offset,means,yerr=errors,fmt="o",capsize=3,
                         color=colors[method],label=method)
    expected=[1000*next(r["inverse_gain_offset"] for r in rows if r["input"]==inp
              and r["gain"]=="39/40" and r["quantizer"]=="floor10") for inp in inputs]
    axes[1].scatter(np.arange(3),expected,marker="x",color="#252c32",zorder=5,label="analytic root")
    axes[1].axhline(0,color="#888888",linewidth=.8)
    axes[1].set_xticks(np.arange(3),["Wide uniform","Narrow uniform","DC"])
    axes[1].set_ylabel("Mean minus inverse gain (x 0.001)")
    axes[1].set_title("B. Quantization shifts the mean")
    axes[1].legend(fontsize=8,frameon=False,loc="lower left")
    axes[1].text(.5,.97,"error bars: one correlated standard error",transform=axes[1].transAxes,
                 fontsize=8,ha="center",va="top")

    for method,offset in (("point30",-.17),("full120",.17)):
        deltas=[]
        for inp in inputs:
            group=[r for r in rows if r["input"]==inp and r["gain"]=="39/40"
                   and r["quantizer"]=="floor10" and r["method"]==method]
            delta=[r["checkpoints"][-1]["online_tone"]["sndr_db"]-
                   r["checkpoints"][0]["frozen_tone"]["sndr_db"] for r in group]
            deltas.append(np.mean(delta))
            axes[2].scatter(np.arange(1)*0+len(deltas)-1+offset+np.linspace(-.045,.045,5),
                            delta,color=colors[method],s=13,zorder=3)
        axes[2].bar(np.arange(3)+offset,deltas,width=.29,color=colors[method],alpha=.4)
    axes[2].axhline(0,color="#888888",linewidth=.8)
    axes[2].set_xticks(np.arange(3),["Wide uniform","Narrow uniform","DC"])
    axes[2].set_ylabel("Online tone SNDR change from unit k (dB)")
    axes[2].set_title("C. Mean learning is not output success")
    axes[2].text(.5,.04,"bars: mean; dots: five seeds",transform=axes[2].transAxes,
                 fontsize=9,ha="center")
    for ax in axes:
        ax.spines[["top","right"]].set_visible(False)
        ax.tick_params(axis="x",labelsize=9)
        ax.grid(axis="y",alpha=.15)
    fig.suptitle("EXP-056 | Static one-slope controls | Assumed step and 10-bit backend",fontsize=14)
    fig.savefig(folder/"statistics_summary.png",dpi=160)
    fig.savefig(folder/"statistics_summary.svg")
    plt.close(fig)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder",type=Path)
    plot(parser.parse_args().folder.resolve())
