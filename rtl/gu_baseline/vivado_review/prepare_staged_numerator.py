"""Freeze the localized numerator pipeline trial from an existing staged-v3 run.

The old run supplies published vectors, the physical wrapper, constraints and
scoreboards. Its sources and results are never modified. Run from repo root.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shutil

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_text(path, contents):
    path.write_bytes(contents.encode("utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    old, out = args.baseline.resolve(), args.output.resolve()
    assert not out.exists(), "refuse to overwrite evidence"
    previous = json.loads((old / "manifest.json").read_text())
    for name, expected in previous["source_sha256"].items():
        assert sha(old / "sources" / name) == expected, name
    assert sha(old / "online.txt") == previous["vectors_sha256"]
    checker = HERE / "prepare_timing_crosscheck.py"
    protected = [old / "manifest.json", old / "staged_result.json", old / "online.txt",
                 old / "negative.txt", *sorted((old / "sources").glob("*")),
                 old / "checkpoints/routed.dcp", old / "netlists/routed.v",
                 old / "netlists/routed_functional.v", old / "netlists/routed.sdf"]
    protected_hashes = {str(p): sha(p) for p in protected if p.is_file()}
    out.mkdir(parents=True)
    for name in ("sources", "tools", "logs", "before"):
        (out / name).mkdir()
    for p in (old / "sources").iterdir():
        if p.is_file():
            shutil.copyfile(p, out / "sources" / p.name)
    for name in ("online.txt", "negative.txt"):
        shutil.copyfile(old / name, out / name)
    for p in [ROOT / "rtl/gu_baseline/two_stage_staged_candidate_a.sv",
              ROOT / "rtl/gu_baseline/fixed_request_seed_staged_candidate_a.sv",
              HERE / "tb_staged_request_seed.sv"]:
        shutil.copyfile(p, out / "sources" / p.name)
    build = (out / "sources/build_staged.tcl").read_text()
    assert build.count("two_stage_staged_candidate_a.sv multicycle_cost_top.sv") == 1
    build = build.replace("two_stage_staged_candidate_a.sv multicycle_cost_top.sv",
                          "fixed_request_seed_staged_candidate_a.sv two_stage_staged_candidate_a.sv multicycle_cost_top.sv")
    write_text(out / "sources/build_staged.tcl", build)
    for relative in ("docs/STATUS.md", "docs/DECISIONS.md", "rtl/README.md",
                     "docs/reports/RTL_MULTICYCLE_TIMING_2026-10-16.md",
                     "docs/reports/PROJECT_PROGRESS_HISTORY_2026-10-10.md",
                     "rtl/gu_baseline/vivado_review/REPRODUCE.md"):
        target = out / "before" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    shutil.copyfile(old / "sources/two_stage_staged_candidate_a.sv", out / "before/core_v3.sv")
    shutil.copyfile(checker, out / "tools/check_timing_log.py")
    shutil.copyfile(__file__, out / "tools/prepare_staged_numerator.py")
    for name in ("run_staged_build.sh", "run_staged_netlist.sh", "prepare_staged_netlist.py"):
        text = (old / "tools" / name).read_text()
        if name == "prepare_staged_netlist.py":
            text = "import sys\n" + text
            text = text.replace("run=Path('/mnt/d/ADC/artifacts/research/circuit_review/timing_staged_20261017_v3')",
                                "run=Path(sys.argv[1]).resolve()")
            text = text.replace("then one64-row timing pilot", "then one222-row timing pilot")
        if name == "run_staged_netlist.sh":
            text = text.replace("checker=/mnt/d/ADC/artifacts/research/circuit_review/timing_crosscheck_20261017_v1/bundle_v3/prepare_timing_crosscheck.py",
                                'checker="$adc_stage_run/tools/check_timing_log.py"')
            text = text.replace("STAGED_SDF_PILOT_PASS rows=64", "STAGED_SDF_PILOT_PASS rows=222")
            anchor = "echo STAGED_SDF_PILOT_CONTROLS_PASS"
            pilot_negative = '''rc=0
timeout --kill-after=10s 600s xsim staged_timing_sim -tclbatch run_staged.tcl \\
    -testplusarg VECTORS=../row221_negative.txt -testplusarg PILOT -log ../logs/timing_pilot_negative.log \\
    > ../logs/timing_pilot_negative_console.log 2>&1 || rc=$?
[[ $rc -eq 0 || $rc -eq 1 ]] || exit "$rc"
python3 "$checker" check-log ../logs/timing_pilot_negative.log --marker 'FUNCTIONAL_INTERNAL_MISMATCH row=221' --reject STAGED_SDF_PILOT_PASS
'''
            assert text.count(anchor) == 1
            text = text.replace(anchor, pilot_negative + anchor)
        write_text(out / "tools" / name, text)
    bench = (out / "sources/tb_staged_cost_template.sv").read_text()
    assert bench.count('row==64') == 1
    bench = bench.replace('row==64', 'row==222').replace('PASS rows=64', 'PASS rows=222')
    write_text(out / "sources/tb_staged_cost_template.sv", bench)
    lines = (out / "online.txt").read_text().splitlines()
    fields = lines[221].split()
    fields[16] = str(int(fields[16]) ^ 1)
    lines[221] = " ".join(fields)
    write_text(out / "row221_negative.txt", "\n".join(lines) + "\n")
    rtl_script = '''#!/usr/bin/env bash
set -euo pipefail
cd "${1:?frozen run directory}"
python3 - <<'PY'
from pathlib import Path
import hashlib,json
m=json.loads(Path('manifest.json').read_text())
for name,h in m['source_sha256'].items(): assert hashlib.sha256((Path('sources')/name).read_bytes()).hexdigest()==h,name
for name,h in m['tool_sha256'].items(): assert hashlib.sha256((Path('tools')/name).read_bytes()).hexdigest()==h,name
assert hashlib.sha256(Path('online.txt').read_bytes()).hexdigest()==m['vectors_sha256']
print('STAGED_NUMERATOR_FREEZE_VERIFIED')
PY
clean() { python3 tools/check_timing_log.py check-log "$1"; }
iverilog -g2012 -s tb_staged_request_seed -o seed.vvp sources/tb_staged_request_seed.sv sources/fixed_request_seed_staged_candidate_a.sv > logs/seed_compile.log 2>&1
if [[ -s logs/seed_compile.log ]]; then clean logs/seed_compile.log; fi
timeout 300s vvp seed.vvp > logs/seed_positive.log 2>&1
python3 tools/check_timing_log.py check-log logs/seed_positive.log --marker 'STAGED_SEED_PASS exhaustive=524288 reset_depths=4 checks=524328'
rc=0
timeout 300s vvp seed.vvp +CORRUPT > logs/seed_negative.log 2>&1 || rc=$?
[[ $rc -eq 0 || $rc -eq 1 ]]
grep -q SEED_VALUE_MISMATCH logs/seed_negative.log
if grep -q STAGED_SEED_PASS logs/seed_negative.log; then exit 1; fi
iverilog -g2012 -Wimplicit -s tb_multicycle -o staged.vvp sources/tb_multicycle.sv sources/two_stage_staged_candidate_a.sv sources/fixed_request_seed_staged_candidate_a.sv sources/fixed_pwl_staged_candidate_a.sv sources/fixed_gated_lms_exact_candidate_a.sv > logs/rtl_compile.log 2>&1
python3 - <<'PY'
from pathlib import Path
import json
s=Path('logs/rtl_compile.log').read_text()
known='sources/fixed_pwl_staged_candidate_a.sv:28: warning: Attributes are not supported on net declaration assignments and will be discarded.'
assert s.strip() in ('',known),s
Path('icarus_compile_diagnostic.json').write_text(json.dumps({'message':s.strip(),'scope':'unchanged PWL synthesis KEEP attribute; preserved compiler diagnostic, not an SDF acceptance exception'},indent=2)+'\\n')
PY
timeout 600s vvp staged.vvp +VECTORS=online.txt > logs/rtl_positive.log 2>&1
python3 tools/check_timing_log.py check-log logs/rtl_positive.log --marker 'MULTICYCLE_PASS vectors=8263 replay=128 reset_phases=39 cycles=39'
rc=0
timeout 600s vvp staged.vvp +VECTORS=negative.txt > logs/rtl_negative.log 2>&1 || rc=$?
[[ $rc -eq 0 || $rc -eq 1 ]]
grep -q 'multicycle mismatch pass=0 row=0' logs/rtl_negative.log
if grep -q MULTICYCLE_PASS logs/rtl_negative.log; then exit 1; fi
echo STAGED_NUMERATOR_RTL_CONTROLS_PASS
'''
    write_text(out / "tools/run_numerator_rtl.sh", rtl_script)
    manifest = {
        "question": "Does a four-edge exact numerator pipeline repair the identified E17 input path while preserving the original recurrence and E39/40 interface?",
        "baseline": str(old),
        "contract": {**previous["contract"], "numerator_edges": [11, 12, 13, 14],
                     "numerator_arithmetic": "signed22 product; signed22 conditional negation/shift; low21 abs; low21 +62; preserve modular overflow",
                     "supported_core_compute_cycles": 16},
        "prediction": "E17 receives the exact original seed; row221 seed must be sign0/204734, request+1637 and state4219559. Success does not explain the old simulation context.",
        "validation_budget": "one exhaustive 524288 seed comparison plus reset/gap and negative controls <=300s; one8263+128 RTL/39abort plus row0negative <=600s; reuse unchanged standalone PWL evidence; one route <=1200s; one8263+128 functional netlist/38abort plus row0negative <=600s; one222row SDF pilot/38abort plus row221negative <=600s each; if all pass one8263+128 slowmax SDF <=3600s plus row0negative <=600s; stop failed gate, no options/mapping sweep or training; at most one <=900s same-snapshot bounded probe if a new failure needs localization",
        "source_sha256": {p.name: sha(p) for p in sorted((out / "sources").iterdir())},
        "tool_sha256": {p.name: sha(p) for p in sorted((out / "tools").iterdir())},
        "vectors_sha256": sha(out / "online.txt"),
        "negative_sha256": {n: sha(out / n) for n in ("negative.txt", "row221_negative.txt")},
        "vectors": len(lines),
        "pwl_reuse": {n: sha(out / "sources" / n) for n in ("fixed_pwl_staged_candidate_a.sv", "tb_staged_pwl.sv")},
        "original_protected_sha256": protected_hashes,
        "scope": "D-145; same hardware algorithm only, no source ADC conversions/training/scoring/FFT/holdouts; no old-netlist bug attribution or board/ASIC acceptance"
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps({"run": str(out), "frozen": True, "vectors": len(lines)}))


if __name__ == "__main__":
    main()
