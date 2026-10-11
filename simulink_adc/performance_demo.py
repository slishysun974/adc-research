"""Frozen performance demonstration, original-core reference and offline scoring.

Simulink consumes only stimuli and physical/digital configuration, initializes
unity and carries its own banks. Python results are used only AFTER simulation.
"""
from __future__ import annotations
import argparse
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import time

import python_reference as ref
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
GROUPS = ref.names()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def read_binary(folder, name, group, rows):
    a = np.fromfile(folder / f"{name}_{group}.bin", dtype="<f8")
    return a.reshape(rows, len(GROUPS[group]))


def prepare(run, protocol=None):
    if run.exists():
        raise FileExistsError(f"Preserve existing run: {run}")
    run.mkdir(parents=True)
    folder = run / "reference"
    folder.mkdir()
    protocol = (protocol or HERE / "performance_protocol.json").resolve()
    protocol_bytes = protocol.read_bytes()
    (run / "protocol.json").write_bytes(protocol_bytes)
    p = json.loads(protocol_bytes)
    architecture, effects, steps = ref.configurations()
    base = next(s for s in ref.cases(architecture, effects, steps) if s["name"] == "both_smooth")
    # Physical truth is configured only in the platform, never in the learner.
    base["nonideal"] = ref.StaticPipelineNonidealities(*[
        ref.StaticStageNonidealities(cubic_truth=ref.StaticCubicTruthConfig(*p[f"stage{s}_truth"]))
        for s in (1,2)])
    assert p["training"]["digital_mode"] == 4 and p["test"]["digital_mode"] == 1
    assert p["training"]["initial_coefficients"] == [1]*8
    assert p["training"]["chunk_samples"] % 120 == 0
    # The performance protocol owns this run's learning rates. Keep the
    # historical EXP-057 file unchanged; configure only this in-memory copy.
    numerators = p["training"]["step_numerators"]
    assert len(numerators) == 4 and all(isinstance(v, int) and v > 0 for v in numerators)
    steps["steps"]["numerators"] = list(numerators)
    for s in (1, 2):
        denominator = p["training"][f"stage{s}_step_denominator"]
        assert isinstance(denominator, int) and denominator > 0
        steps["steps"][f"stage{s}_denominator"] = denominator
    sources = list((ROOT / "src/adc_research/platform").glob("*.py"))
    sources += list((ROOT / "src/adc_research/calibration").glob("*.py"))
    sources += [HERE / "adc_behavioral.slx", HERE / "python_reference.py",
                protocol, Path(__file__),
                HERE / "run_adc_performance.m", HERE / "render_adc_performance.m",
                HERE / "verify_adc_performance_metrics.m",
                ROOT / "experiments/exp_057_static_two_stage_million/protocol.json",
                ROOT / "configs/architectures/gu_behavioral_v1.yaml",
                ROOT / "configs/nonidealities/gu_gate_d_static_v0_1.yaml",
                ROOT / "src/adc_research/metrics/spectral.py"]
    if "harmonic_analysis" in p:
        sources.append(HERE / "render_adc_harmonics.m")
    hashes = {str(s.relative_to(ROOT)): hashlib.sha256(s.read_bytes()).hexdigest() for s in sources}
    write_json(run / "source_sha256.json", hashes)
    n = p["training"]["conversions"]
    x = np.random.default_rng(p["training"]["input_seed"]).uniform(-.82, .82, n)
    tags = np.random.default_rng(p["training"]["dither_seed"]).choice([-1, 1], (n, 2))
    tn = p["test"]["samples"]
    tone = p["test"]["amplitude"] * np.sin(2*np.pi*p["test"]["fundamental_bin"]*np.arange(tn)/tn)
    test_tags = np.random.default_rng(p["test"]["dither_seed"]).choice([-1, 1], (tn, 2))
    entries, states = [], []

    def execute(name, kind, inputs, dithers, state, offset=0):
        spec = dict(base, name=name, x=inputs, tags=dithers, digital_mode=4 if kind in ("preflight", "train") else 1,
                    initial1=tuple(state[:4]), initial2=tuple(state[4:]))
        started = time.perf_counter()
        C, traces = ref.reference_case(spec, architecture, steps)
        for group, a in traces.items():
            assert a.shape == (len(inputs), len(GROUPS[group]))
            assert np.isfinite(a).all()
            np.asarray(a, dtype="<f8").tofile(folder / f"{name}_{group}.bin")
        np.savetxt(folder / f"{name}_input.csv", traces["stimulus_trace"], delimiter=",", fmt="%.17g")
        # Never supply Python learned banks to the independent native runner.
        C["initial1"] = [1]*4
        C["initial2"] = [1]*4
        entries.append(dict(name=name, kind=kind, samples=len(inputs), offset=offset, parameters=C))
        after = traces["learning_trace"][-1, 8:16].copy()
        print(f"Python {name}: {len(inputs)} conversions, {time.perf_counter()-started:.1f}s", flush=True)
        return traces, after

    unity = np.ones(8)
    whole, final = execute("preflight_whole", "preflight", x[:480], tags[:480], unity)
    split1, half = execute("preflight_a", "preflight", x[:240], tags[:240], unity)
    split2, finish = execute("preflight_b", "preflight", x[240:480], tags[240:480], half)
    for g in ("physical_trace", "digital_trace"):
        assert np.array_equal(whole[g], np.vstack((split1[g], split2[g]))), g
    assert np.array_equal(final, finish)
    assert np.array_equal(whole["learning_trace"][:, 8:16], np.vstack((split1["learning_trace"][:, 8:16], split2["learning_trace"][:, 8:16])))
    write_json(run / "python_preflight.json", dict(chunk_equivalent=True, samples=480))
    state = unity

    def checkpoint(offset):
        states.append(dict(conversions=offset, coefficients=state.tolist()))
        execute(f"test_{offset:07d}", "test", tone, test_tags, state, offset)

    checkpoint(0)
    chunk = p["training"]["chunk_samples"]
    for begin in range(0, n, chunk):
        end = min(begin + chunk, n)
        assert (end-begin) % 120 == 0
        _, state = execute(f"train_{begin:07d}", "train", x[begin:end], tags[begin:end], state, begin)
        if end in p["training"]["checkpoints"]:
            checkpoint(end)
    write_json(run / "reference_states.json", states)
    write_json(folder / "manifest.json", dict(version=p["version"], generated_at=datetime.now().isoformat(),
               cases=entries, columns=GROUPS, protocol_sha256=hashlib.sha256(protocol_bytes).hexdigest(),
               numpy_version=np.__version__, python_version=sys.version))
    print(f"Reference complete: {run}", flush=True)


def analyze(run):
    manifest = json.loads((run / "reference/manifest.json").read_text(encoding="utf-8"))
    p = json.loads((run / "protocol.json").read_text(encoding="utf-8"))
    actual_folder, expected_folder = run / "simulink", run / "reference"
    plots = run / "figures"
    plots.mkdir(exist_ok=True)
    checks, scalar_count, exact = [], 0, True
    windows, counts = [], np.zeros(8)
    overload_counts = np.zeros(14, dtype=int)
    tests = {}
    for e in manifest["cases"]:
        actual = {}
        for g, columns in GROUPS.items():
            a = read_binary(actual_folder, e["name"], g, e["samples"])
            b = read_binary(expected_folder, e["name"], g, e["samples"])
            assert np.isfinite(a).all() and np.isfinite(b).all()
            difference = np.abs(a-b)
            maximum = difference.max(axis=0)
            for j, column in enumerate(columns):
                limit = ref.tolerance(g, column)
                checks.append(dict(case=e["name"], group=g, column=column,
                                   max_abs_error=float(maximum[j]), tolerance=limit, passed=bool(maximum[j] <= limit)))
            scalar_count += a.size
            exact = exact and bool(np.array_equal(a, b))
            actual[g] = a
        if e["kind"] == "train":
            l = actual["learning_trace"]
            select = l[:, -1] == 1
            windows.append(np.column_stack((e["offset"] + np.flatnonzero(select) + 1, l[select, 8:16])))
            counts += l[-1, 40:48]
            overload_counts += actual["physical_trace"][:, 44:58].sum(axis=0).astype(int)
        elif e["kind"] == "test":
            tests[e["offset"]] = actual
    states = json.loads((actual_folder / "states.json").read_text(encoding="utf-8"))
    py_states = json.loads((run / "reference_states.json").read_text(encoding="utf-8"))
    state_error = max(float(np.max(np.abs(np.asarray(a["coefficients"])-np.asarray(b["coefficients"]))))
                      for a, b in zip(states, py_states))
    source_hashes = json.loads((run / "source_sha256.json").read_text(encoding="utf-8"))
    changed = [s for s, h in source_hashes.items() if hashlib.sha256((ROOT/s).read_bytes()).hexdigest() != h]
    verification = dict(all_fields_passed=all(c["passed"] for c in checks), all_traces_exact=exact,
         scalar_comparisons=scalar_count, field_checks=len(checks), checkpoint_max_error=state_error,
         source_changed=changed, all_finite=True, checks=checks)
    write_json(run / "verification.json", verification)
    assert verification["all_fields_passed"] and state_error <= 1e-11 and not changed
    assert not np.any(overload_counts), overload_counts
    np.savetxt(plots / "coefficient_windows.csv", np.vstack((np.r_[0, np.ones(8)], *windows)), delimiter=",", fmt="%.17g")
    summary_rows, metrics, spectrum = [], {}, None
    for offset in p["training"]["checkpoints"]:
        d = tests[offset]["digital_trace"]
        values = d[:, 0]
        ideal = 2048*(tests[offset]["stimulus_trace"][:, 1]+1)
        metric = ref.analyze_coherent_tone(values, sample_rate_hz=p["test"]["sample_rate_hz"],
                        fundamental_bin=p["test"]["fundamental_bin"], full_scale_peak=2048)
        integer = np.clip(np.floor(values+.5), 0, 4095)
        integer_metric = ref.analyze_coherent_tone(integer, sample_rate_hz=p["test"]["sample_rate_hz"],
                        fundamental_bin=p["test"]["fundamental_bin"], full_scale_peak=2048)
        metrics[str(offset)] = dict(floating=asdict(metric.metrics), integer=asdict(integer_metric.metrics),
                  mse_code2=float(np.mean((values-ideal)**2)), dc_error_code=float(np.mean(values-ideal)))
        summary_rows.append([offset, metric.metrics.sndr_db, metric.metrics.sfdr_dbc, metric.metrics.enob_bits,
                             integer_metric.metrics.sndr_db, integer_metric.metrics.sfdr_dbc])
        if offset in (0, p["training"]["conversions"]):
            dbfs = 10*np.log10(np.maximum(np.asarray(metric.rms_power)/(2048**2/2), 1e-20))
            if offset == 0:
                spectrum = np.column_stack((metric.frequencies_hz, dbfs))
            else:
                spectrum = np.column_stack((spectrum, dbfs))
    final = tests[p["training"]["conversions"]]
    before = tests[0]
    assert np.array_equal(before["digital_trace"][:, 0], before["digital_trace"][:, 1])
    assert np.array_equal(before["digital_trace"][:, 1], final["digital_trace"][:, 1])
    test_overloads = sum((a["physical_trace"][:, 44:58].sum(axis=0).astype(int) for a in tests.values()), np.zeros(14, dtype=int))
    assert not np.any(test_overloads), test_overloads
    np.savetxt(plots / "spectra.csv", spectrum, delimiter=",", fmt="%.17g")
    np.savetxt(plots / "checkpoint_metrics.csv", summary_rows, delimiter=",", fmt="%.17g")
    st, phys, dig = (final[g] for g in ("stimulus_trace", "physical_trace", "digital_trace"))
    ideal = 2048*(st[:, 1]+1)
    py = read_binary(expected_folder, f"test_{p['training']['conversions']:07d}", "digital_trace", len(st))
    # index,input,r1main,r1aux,r2,raw,corrected,ideal,Python,difference
    display = np.column_stack((st[:, 0], st[:, 1], phys[:, 10], phys[:, 19], phys[:, 29],
                               dig[:, 1], dig[:, 0], ideal, py[:, 0], dig[:, 0]-py[:, 0]))
    np.savetxt(plots / "signal_trace.csv", display, delimiter=",", fmt="%.17g")
    summary = dict(protocol_version=p["version"], training_conversions=p["training"]["conversions"],
         training_windows=p["training"]["conversions"]//120, observations_per_bank=p["training"]["conversions"],
         gate_counts=counts.astype(int).tolist(), training_overload_clip_counts=overload_counts.tolist(),
         test_overload_clip_counts=test_overloads.tolist(), checkpoints=metrics,
         final_coefficients=states[-1]["coefficients"], all_traces_exact=exact,
         scalar_comparisons=scalar_count, checkpoint_max_error=state_error,
         source_hash_count=len(source_hashes), max_trace_error=max(c["max_abs_error"] for c in checks),
         preflight_conversions=960, test_conversions=p["test"]["samples"]*len(metrics))
    if "harmonic_analysis" in p:
        summary["harmonic_analysis"] = harmonic_analysis(before["digital_trace"][:,0], dig[:,0], p, plots)
    write_json(run / "summary.json", summary)
    summary_file = p.get("summary_file", "performance_summary.json")
    assert Path(summary_file).name == summary_file and summary_file.endswith(".json")
    (HERE / summary_file).write_bytes((run / "summary.json").read_bytes())
    print(json.dumps({k: v for k,v in summary.items() if k != "checkpoints"}, ensure_ascii=False, indent=2), flush=True)
    for offset, m in metrics.items():
        print(f"Checkpoint {offset}: floating SNDR={m['floating']['sndr_db']:.4f}, SFDR={m['floating']['sfdr_dbc']:.4f}; integer SNDR={m['integer']['sndr_db']:.4f}", flush=True)


def harmonic_analysis(before, after, p, plots):
    """Offline folded-bin amplitudes; keep the declared orders, not just winners."""
    from adc_research.metrics.spectral import folded_bin
    orders = tuple(p["harmonic_analysis"]["orders"])
    n, k, fs = (p["test"][key] for key in ("samples", "fundamental_bin", "sample_rate_hz"))
    bins = [folded_bin(h,k,n) for h in orders]
    assert len(set(bins)) == len(bins) and not any(b in (0,k) for b in bins)
    results = {}
    for label in ("floating", "integer"):
        arrays = [before, after]
        if label == "integer":
            arrays = [np.clip(np.floor(v+.5),0,4095) for v in arrays]
        power = [np.asarray(ref.analyze_coherent_tone(v,sample_rate_hz=fs,fundamental_bin=k,
                      full_scale_peak=2048).rms_power) for v in arrays]
        rows=[]
        for h,b in zip(orders,bins):
            dbfs = [float(10*np.log10(max(v[b]/(2048**2/2),1e-200))) for v in power]
            dbc = [float(10*np.log10(max(v[b]/v[k],1e-200))) for v in power]
            rows.append(dict(order=h,bin=b,frequency_hz=b*fs/n,before_dbfs=dbfs[0],after_dbfs=dbfs[1],
                before_dbc=dbc[0],after_dbc=dbc[1],suppression_db=dbfs[0]-dbfs[1],
                suppression_dbc=dbc[0]-dbc[1]))
        array = [[r[key] for key in ("order","bin","frequency_hz","before_dbfs","after_dbfs",
                  "before_dbc","after_dbc","suppression_db","suppression_dbc")] for r in rows]
        np.savetxt(plots / ("harmonics.csv" if label=="floating" else "harmonics_integer.csv"),array,delimiter=",",fmt="%.17g")
        thd = [float(10*np.log10(sum(v[b] for b in bins)/v[k])) for v in power]
        odd = [r for r in rows if r["order"]%2]
        strongest = max(odd,key=lambda r:r["before_dbfs"])
        results[label] = dict(thd_orders=orders,thd_before_db=thd[0],thd_after_db=thd[1],
            strongest_uncalibrated_odd_order=strongest["order"],harmonics=rows)
    print("Harmonics HD2..HD31 retained; odd-harmonic zoom selected by BEFORE amplitude only.",flush=True)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "analyze"))
    parser.add_argument("run", type=Path)
    parser.add_argument("--protocol", type=Path, help="Frozen protocol for prepare; analyze uses the saved run protocol")
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.run.resolve(), args.protocol)
    else:
        analyze(args.run.resolve())
