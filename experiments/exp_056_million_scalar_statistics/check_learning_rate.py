"""Predeclared analytic rate controls; no generated ADC/training records.

Run prepare before controls, then analyze, then deliver after doc updates.
The original EXP-056 protocol, source, states and summary stay unchanged.
"""

import argparse
from dataclasses import asdict
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import os

ROOT = Path(__file__).resolve().parents[2]
DOCS = ["docs/STATUS.md", "docs/DECISIONS.md", "docs/README.md",
        "docs/RESEARCH_PLAN_STATIC_FIXED_POINT_DIAGNOSTICS_2026-10-10.md",
        "docs/reports/GU_ALGORITHM_EVALUATION_V1.md",
        "docs/reports/RESEARCH_SYNTHESIS_2026-10-10.md",
        "docs/theory/README.md", "docs/theory/STAGE2_CLAIM_EVIDENCE_LEDGER_V1.md",
        "docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md",
        "docs/theory/MILLION_SAMPLE_SCALAR_MEAN_NOISE_AND_QUANTIZATION_V1.md"]
BASE = F(1, 262144000)
RATIOS = (F(1, 4), F(1, 2), F(1), F(2))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str)+"\n",
                    encoding="utf-8")


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    guarded = set()
    for folder in ("src/adc_research/calibration", "src/adc_research/platform", "rtl",
                   "experiments/exp_056_million_scalar_statistics"):
        for path in (ROOT/folder).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts and path.name != Path(__file__).name:
                guarded.add(path)
    for relative in ("src/adc_research/theory/scalar_quantized_dither.py",
                     "artifacts/runs/EXP_056/million_v1/summary.json",
                     "artifacts/runs/EXP_056/million_v1/protocol.json",
                     "references/local/OJSSCS2026_Gu.pdf"):
        guarded.add(ROOT/relative)
    save(out/"guard_hashes.json", {str(p.relative_to(ROOT)): sha(p) for p in sorted(guarded)})
    for relative in DOCS:
        dest = out/"before"/relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT/relative, dest)
    save(out/"protocol.json", {
        "date": "2026-10-11", "authority": "User requests Gu LMS learning-rate/convergence study before new algorithms",
        "scope": "Analytic scalar controls, exact finite outcome enumeration, Gu vector/gate/quantization conditions; no tuning or new online policy",
        "model": "EXP-056 iid memoryless single slope; X uniform [-256,256], a=39/40, D=+/-64 independent; continuous fresh score",
        "base_step": str(BASE), "rate_ratios": list(map(str, RATIOS)),
        "window_contracts": [[4, 30], [120, 1]], "conversion_slots_per_window": 120,
        "checkpoints_windows": [128, 2500, 250000], "mean_relative_error_target": 0.01,
        "quantized_control": "X uniform [-1/4,1/4], a=39/40, D=+/-64, unit floor; compare root at each declared step",
        "exact_controls": "all 4096 paths of three two-sample iid toy windows; mean stable/second unstable; critical second moment; zero variance; moving gate boundary; nearest-even request",
        "independent_numeric_check": "existing scalar_window_law direct recurrence, at n=0,1,128,2500,4096; absolute errors <1e-12",
        "plot": "point30 means and fresh continuous output MSE, 501 predetermined window counts from 0 to10000",
        "failures": "retain all logs; no replacement parameters, seeds, horizon or best-stop selection",
        "new_adc_conversions": 0, "new_training_observations": 0, "new_fft": 0,
        "limits": "iid scalar distributions are controls, not fitted Gu chip or eight-state convergence; no SNDR/SFDR prediction or physical claim",
    })
    sources = [Path(__file__), ROOT/"src/adc_research/theory/gu_step_stability.py",
               ROOT/"tests/test_gu_step_stability.py"]
    save(out/"source_hashes.json", {str(p.relative_to(ROOT)): sha(p) for p in sources})
    print(json.dumps({"prepared": str(out), "guard_files": len(guarded)}, ensure_ascii=False))


def guards(out):
    expected = json.loads((out/"guard_hashes.json").read_text(encoding="utf-8"))
    bad = [p for p, digest in expected.items() if not (ROOT/p).exists() or sha(ROOT/p) != digest]
    if bad:
        raise AssertionError(f"guarded sources changed: {bad}")
    sources = json.loads((out/"source_hashes.json").read_text(encoding="utf-8"))
    if any(sha(ROOT/p) != digest for p, digest in sources.items()):
        raise AssertionError("control source changed since preparation")
    return len(expected)


def analyze(out):
    from adc_research.theory.gu_step_stability import scalar_step_law, continuous_net_mse_u_upper
    from adc_research.theory.scalar_quantized_dither import scalar_population, scalar_window_law
    guards(out)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT/"src")
    with (out/"controls.log").open("w", encoding="utf-8") as log:
        result = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests",
                                 "-p", "test_gu_step_stability.py", "-v"],
                                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError("controls failed; see controls.log")
    gain, d = F(39, 40), F(64)
    pop = scalar_population(gain=gain, dither=d, low=F(-256), high=F(256), quantized=False)
    narrow = scalar_population(gain=gain, dither=d, low=F(-1, 4), high=F(1, 4), quantized=True)
    rows, maximum_error = [], 0.0
    old_summary = json.loads((ROOT/"artifacts/runs/EXP_056/million_v1/summary.json").read_text(encoding="utf-8"))
    for m, p in ((4, 30), (120, 1)):
        for ratio in RATIOS:
            step = BASE*ratio
            law = scalar_step_law(correlation=pop.correlation,
                product_second_moment=pop.product_second_moment, dither=d,
                step=step, selected=m, multiplier=F(p))
            old = scalar_window_law(pop, dither=64, step=float(step), selected=m, multiplier=p)
            for n in (0, 1, 128, 2500, 4096):
                actual, expected = law.float_moments(n), old.mean_variance(n)
                maximum_error = max(maximum_error, *(abs(x-y) for x, y in zip(actual, expected)))
            var = law.stationary_variance
            stationary_mse = pop.raw_second_moment*var  # continuous exact inverse root
            checkpoints = {}
            for n in (128, 2500, 250000):
                mean, variance = law.float_moments(n)
                mse = float(pop.raw_second_moment)*(variance+(mean-float(law.equilibrium))**2)
                checkpoints[str(n)] = {"mean": mean, "variance": variance, "fresh_mse": mse}
            nq = scalar_step_law(correlation=narrow.correlation,
                product_second_moment=narrow.product_second_moment, dither=d,
                step=step, selected=m, multiplier=F(p))
            net_upper = continuous_net_mse_u_upper(gain=gain, gamma=law.gamma)
            count = law.mean_error_windows(.01)
            row = {"selected": m, "multiplier": p, "ratio": str(ratio),
                   "exact_law": asdict(law), "stationary_variance": str(var),
                   "stationary_std": float(var)**.5,
                   "stationary_fresh_mse": float(stationary_mse),
                   "mean_1pct_windows": count, "inferred_conversion_slots": count*120,
                   "learning_observations": count*m,
                   "net_mse_step_ratio_upper": str(net_upper/(BASE*p*m*pop.correlation)),
                   "quantized_root": str(nq.equilibrium), "checkpoints": checkpoints}
            if ratio == 1:
                name = "point30" if m == 4 else "full120"
                references = [x for x in old_summary["rows"] if x["input"] == "wide_uniform"
                              and x["gain"] == "39/40" and x["quantizer"] == "continuous"
                              and x["method"] == name]
                assert len(references) == 5, (name, len(references))
                error = max(abs(x["stationary_expected_population_mse"]-float(stationary_mse))
                            for x in references)
                assert error < 1e-9, error
                row["old_summary_reference_rows"] = 5
                row["old_summary_mse_max_error"] = error
            rows.append(row)
    assert maximum_error < 1e-12, maximum_error
    result = {"model": "prespecified iid scalar analytic control",
              "unit_fresh_mse": float((gain-1)**2*pop.target_second_moment), "rows": rows,
              "independent_recurrence_max_error": maximum_error,
              "new_conversions": 0, "new_training": 0, "new_fft": 0}
    save(out/"analysis.json", result)

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    counts = [20*n for n in range(501)]
    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.2), constrained_layout=True)
    for ratio in RATIOS:
        law = scalar_step_law(correlation=pop.correlation,
            product_second_moment=pop.product_second_moment, dither=d,
            step=BASE*ratio, selected=4, multiplier=F(30))
        moments = [law.float_moments(n) for n in counts]
        axes[0].plot(counts, [abs(mean-float(law.equilibrium))/abs(1-float(law.equilibrium))
                            for mean, var in moments], label=f"step x {ratio}")
        axes[1].plot(counts, [float(pop.raw_second_moment)*(var+(mean-float(law.equilibrium))**2)
                            for mean, var in moments], label=f"step x {ratio}")
    axes[0].set(yscale="log", ylim=(1e-8, 1.2), ylabel="Relative ensemble mean error")
    axes[1].axhline(result["unit_fresh_mse"], color="#555555", ls="--", lw=1, label="Unity / no update")
    axes[1].set(ylabel="Expected fresh continuous-code MSE (code squared)")
    for ax in axes:
        ax.set_xlabel("120-slot windows (inferred duration)")
        ax.grid(alpha=.2)
        ax.legend(frameon=False, fontsize=9)
    fig.suptitle("Fixed step: faster mean settling trades against sustained variance\n"
                 "IID single slope, 4 selected x 30; analytic controls, no ADC simulation", fontsize=12)
    fig.savefig(out/"learning_rate_controls.png", dpi=180)
    plt.close(fig)
    save(out/"validation.json", {"passed": True, "exact_control_tests": 11,
        "old_summary_rows_checked": 10, "guard_files_unchanged": guards(out),
        "independent_recurrence_max_error": maximum_error})
    print(json.dumps({"passed": True, "unit_mse": result["unit_fresh_mse"], "rows": [
        {k: r[k] for k in ("selected", "ratio", "stationary_fresh_mse", "mean_1pct_windows",
                           "net_mse_step_ratio_upper")} for r in rows]}, ensure_ascii=False))


def deliver(out):
    bad_links = []
    for relative in DOCS:
        path = ROOT/relative
        content = path.read_text(encoding="utf-8")
        for url in re.findall(r"\]\(([^)]+)\)", content):
            if "://" in url or url.startswith("#"):
                continue
            dest = url.split("#")[0]
            if dest and not (path.parent/dest).exists():
                bad_links.append([relative, url])
    assert not bad_links, bad_links
    save(out/"delivery_validation.json", {"passed": True, "guard_files_unchanged": guards(out),
        "docs_checked": DOCS, "missing_local_links": bad_links,
        "new_adc_conversions": 0, "new_training": 0, "new_fft": 0,
        "source_hashes": {r: sha(ROOT/r) for r in DOCS}})
    print(json.dumps({"delivery_passed": True, "guard_files": guards(out), "docs": len(DOCS)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "analyze", "deliver"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    {"prepare": prepare, "analyze": analyze, "deliver": deliver}[args.mode](args.output.resolve())
