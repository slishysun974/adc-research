"""Prepare a frozen v10 SDF crosscheck; never starts Vivado or changes RTL.

The generated Linux entry point accepts explicit Vivado settings and the
reference 2022.1 installation. It must be calibrated on the failing baseline
before a different installation's results can be interpreted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


CARRY_SHA256 = "a9fbbf068a2f99d44b6293053c526a2af9efd9ce42c8ef5ddde2a897194d413e"
VECTOR_SHA256 = "c64faa81c5346ffe381cfc54e591654d9a8e050c89dab301185a6c37a345f82b"
SDF_SHA256 = "fa45d604ce8a46285f3c8b0a623a698b56f2b69a3bd75daae379eddb202a8d83"
FROZEN = {
    "netlists/routed.v": "f25193010efb336c933b5867d300083b4a6ecbc51a6b91abe9e8315a3fad2767",
    "checkpoints/routed.dcp": "01c61f8bb924b7a0e4795986e2ec7a5450111f14d7507c46e7f26161cd5714db",
    "testsources/tb_functional_full.sv": "116cffb404f3dbe39907ad881ad6e712ecbb51324241f182425b04cfebd5bf6d",
}
BAD_LOG = re.compile(
    r"warning\s*:|error\s*:|fatal\s*:|timing violation|\$setuphold|\$recrem|"
    r"SDF_PILOT_FAILED|annotation.*(?:skipped|failed)|backannotation.*failed",
    re.IGNORECASE,
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_text(path: Path, contents: str) -> None:
    path.write_bytes(contents.encode("utf-8"))


def check_log(path: Path, marker: str | None, sdf: str | None,
              reject: str | None = None) -> None:
    if reject is not None and marker is None:
        raise ValueError("negative control requires an expected fatal marker")
    contents = path.read_text(encoding="utf-8", errors="replace")
    if not contents.strip():
        raise ValueError(f"empty log: {path}")
    expected_line = (re.compile(r"^Fatal:\s*" + re.escape(marker) + r"(?:\s|$)")
                     if marker and reject else None)
    if marker is None and BAD_LOG.search(contents):
        raise ValueError(f"diagnostic in {path}")
    if marker is not None:
        found = (any(expected_line.search(line) for line in contents.splitlines())
                 if expected_line else marker in contents.splitlines())
        if not found:
            raise ValueError(f"missing expected marker in {path}: {marker}")
        # Only negative controls may contain the expected fatal diagnostic.
        if reject is None and BAD_LOG.search(contents):
            raise ValueError(f"diagnostic alongside PASS in {path}")
    if reject:
        remainder = "\n".join(line for line in contents.splitlines()
                              if not expected_line.search(line))
        if BAD_LOG.search(remainder):
            raise ValueError(f"unrelated diagnostic in negative control: {path}")
    if reject and reject in contents:
        raise ValueError(f"unexpected success marker in {path}: {reject}")
    if sdf and not re.search(
        r"SDF backannotation was successful[^\n]*" + re.escape(sdf), contents
    ):
        raise ValueError(f"unconfirmed SDF annotation in {path}: {sdf}")


def verify(bundle: Path) -> dict:
    manifest = json.loads((bundle / "protocol.json").read_text(encoding="utf-8"))
    for relative, expected in manifest["bundle_sha256"].items():
        path = bundle / relative
        if sha(path) != expected:
            raise ValueError(f"changed frozen input: {relative}")
    return manifest


def prepare(source: Path, out: Path) -> dict:
    if out.exists():
        raise FileExistsError(f"output must not exist: {out}")
    files = {
        "design/routed.v": "netlists/routed.v",
        "design/routed.sdf": "netlists/routed.sdf",
        "design/online.txt": "online.txt",
        "design/negative.txt": "negative.txt",
        "primitive/events.txt": "carry_replay_ps/events.txt",
        "primitive/carry_probe.sdf": "carry_replay_ps/carry_probe.sdf",
        "primitive/carry_replay_v2.sv": "carry_replay_ps/carry_replay_v2.sv",
    }
    for relative in files.values():
        if not (source / relative).is_file():
            raise FileNotFoundError(source / relative)
    if sha(source / "online.txt") != VECTOR_SHA256:
        raise ValueError("not the frozen 8263-vector source")
    if sha(source / "netlists/routed.sdf") != SDF_SHA256:
        raise ValueError("not the diagnosed v10 SDF")
    for relative, expected in FROZEN.items():
        if sha(source / relative) != expected:
            raise ValueError(f"not the diagnosed v10 source: {relative}")
    rows = (source / "online.txt").read_text().splitlines()
    if len(rows) != 8263 or any(len(row.split()) != 19 for row in rows):
        raise ValueError("invalid vector shape")
    original_bench = source / "testsources/tb_functional_full.sv"
    bench = original_bench.read_text()
    # Observe exactly the registered E16 result, with no shadow or feedback.
    needle = "                    if(n<LATENCY && (done_out !== 0 || valid_out !== 0 || ready_in !== 0))"
    if bench.count(needle) != 1:
        raise ValueError("unexpected benchmark structure")
    if "wire [183:0] debug_banks=" not in bench or "wire [52:0] debug_pending=" not in bench:
        raise ValueError("missing complete internal comparison")
    hook = '''                    if($test$plusargs("PILOT") && pass==0 && row==34 && n==16) begin
                        if(debug_pending !== {ev[0],ec[11:0],g1[3:0],g2[3:0],y1[15:0],y2[15:0]})
                            $fatal(1,"CROSSCHECK_ROW34_MISMATCH row=34 actual=%h expected=%h",debug_pending,
                                {ev[0],ec[11:0],g1[3:0],g2[3:0],y1[15:0],y2[15:0]});
                        $display("CROSSCHECK_ROW34_PASS row=34 E16 pending_bits=53");
                        $finish;
                    end
'''
    bench = bench.replace(needle, hook + needle)
    # Preserve the prior 34 rows; corrupt only row34's expected learning1.
    negative_rows = rows.copy()
    row34 = negative_rows[34].split()
    row34[9] = str(int(row34[9]) ^ 1)
    negative_rows[34] = " ".join(row34)
    out.mkdir(parents=True)
    for destination, relative in files.items():
        path = out / destination
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, path)
    write_text(out / "design/tb_crosscheck.sv", bench)
    write_text(out / "design/row34_negative.txt", "\n".join(negative_rows) + "\n")
    write_text(out / "design/run.tcl", "run all\nquit\n")
    write_text(out / "run_xsim.sh", RUNNER)
    shutil.copyfile(Path(__file__), out / "prepare_timing_crosscheck.py")
    source_hashes = {relative: sha(source / relative) for relative in files.values()}
    source_hashes.update(FROZEN)
    source_hashes[str(original_bench.relative_to(source))] = sha(original_bench)
    manifest = {
        "purpose": "same v10 netlist/SDF crosscheck on an explicitly selected XSim installation",
        "status": "prepared_only; no new HDL compile or simulation",
        "reference_carry4_sha256": CARRY_SHA256,
        "source_sha256": source_hashes,
        "pilot": "same reset history and rows0..33; check all 53 pending bits at row34 E16; stop",
        "negative": "after pilot PASS, toggle only expected learning1 bit0 at row34; require exact rejection",
        "full": "only after primitive and pilot controls pass; 8263 rows,128 reset replay,38 abort phases,184 bank bits and53 pending bits; row0 negative",
        "budget": "per installation: at most two invocations (pilot then optional full); each invocation one 35101-event primitive replay,one pilot positive and negative; full phase adds one full positive and one row0 negative; wall limits600/900/3600seconds",
        "comparison": "run same harness on baseline2022.1 first; require original discrepancy before interpreting a candidate; other precompiled vendor libraries may differ and are not isolated engine-only evidence",
        "source_protected": "no source conversions,training,scoring,FFT,holdout,RTL,DCP or SDF modification",
        "bundle_sha256": {str(p.relative_to(out)).replace("\\", "/"): sha(p)
                          for p in sorted(out.rglob("*")) if p.is_file()},
    }
    write_text(out / "protocol.json", json.dumps(manifest, indent=2) + "\n")
    verify(out)
    return manifest


RUNNER = r'''#!/usr/bin/env bash
set -euo pipefail
# Linux, selected installation; no installation, synthesis or source mutation.
settings=${1:?absolute path to candidate settings64.sh}
reference=${2:?absolute path to reference Vivado2022.1 root}
result=${3:?absolute path to a NEW result directory}
phase=${4:-pilot}
[[ "$phase" == pilot || "$phase" == full ]] || exit 2
[[ "$settings" == /* && "$reference" == /* && "$result" == /* ]] || exit 2
bundle=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
python3 "$bundle/prepare_timing_crosscheck.py" verify "$bundle"
model="$reference/data/verilog/src/unisims/CARRY4.v"
[[ $(sha256sum "$model" | cut -d' ' -f1) == a9fbbf068a2f99d44b6293053c526a2af9efd9ce42c8ef5ddde2a897194d413e ]] || exit 3
mkdir -- "$result" # atomic refusal to overwrite an earlier attempt
result=$(cd -- "$result" && pwd)
mkdir "$result/design" "$result/primitive"
cp -- "$bundle/design/"* "$result/design/"
cp -- "$bundle/primitive/"* "$result/primitive/"
cp -- "$bundle/protocol.json" "$result/input_protocol.json"
set +u
source "$settings"
set -u
printf '%s\n' "$settings" "$reference" "$phase" > "$result/environment.txt"
xvlog -version >> "$result/environment.txt" 2>&1
xelab -version >> "$result/environment.txt" 2>&1
sha256sum "$model" "$reference/data/verilog/src/glbl.v" >> "$result/environment.txt"
printf '%s\n' "${XILINX_VIVADO:-unset}" >> "$result/environment.txt"
command -v xvlog xelab xsim >> "$result/environment.txt"
if [[ -f "${XILINX_VIVADO:-}/data/xsim/xsim.ini" ]]; then
    sha256sum "$XILINX_VIVADO/data/xsim/xsim.ini" >> "$result/environment.txt"
fi
checker="$bundle/prepare_timing_crosscheck.py"
clean() { python3 "$checker" check-log "$1"; }
positive() { python3 "$checker" check-log "$1" --marker "$2"; }
annotation() { python3 "$checker" check-log "$1" --sdf "$2"; }
negative() { python3 "$checker" check-log "$1" --marker "$2" --reject "$3"; }
elaborate() {
    timeout --kill-after=10s 900s xelab "$@" -L reference_primitives -L simprims_ver -L secureip \
        -debug all -O0 -mt 2 -maxdelay -transport_int_delays \
        -pulse_r 0 -pulse_int_r 0 -pulse_e 0 -pulse_int_e 0
}
cd "$result/primitive"
xvlog -work reference_primitives -d XIL_TIMING "$model" > compile_model.log 2>&1
clean compile_model.log
xvlog --sv carry_replay_v2.sv "$reference/data/verilog/src/glbl.v" > compile.log 2>&1
clean compile.log
elaborate carry_replay glbl -s cross_primitive > elaborate.log 2>&1
annotation elaborate.log carry_probe.sdf
timeout --kill-after=10s 600s xsim cross_primitive -runall -log simulate.log > console.log 2>&1
positive simulate.log 'CARRY_REPLAY_PASS events=35101 stable_checks=79'
clean console.log
cd "$result/design"
xvlog -work reference_primitives -d XIL_TIMING "$model" > compile_model.log 2>&1
clean compile_model.log
xvlog --sv -work cross_work tb_crosscheck.sv routed.v > compile.log 2>&1
clean compile.log
elaborate cross_work.tb_multicycle_cost cross_work.glbl -s cross_design > elaborate.log 2>&1
annotation elaborate.log routed.sdf
simulate() {
    local tag=$1 vectors=$2 limit=$3
    shift 3
    timeout --kill-after=10s "${limit}s" xsim cross_design -tclbatch run.tcl \
        -testplusarg "VECTORS=$vectors" "$@" -log "${tag}.log" > "${tag}_console.log" 2>&1
}
simulate pilot online.txt 900 -testplusarg PILOT
positive pilot.log 'CROSSCHECK_ROW34_PASS row=34 E16 pending_bits=53'
clean pilot_console.log
# Permit an HDL-fatal exit only; timeouts/launch failures remain errors.
rc=0
simulate pilot_negative row34_negative.txt 900 -testplusarg PILOT || rc=$?
[[ $rc -eq 0 || $rc -eq 1 ]] || exit "$rc"
negative pilot_negative.log 'CROSSCHECK_ROW34_MISMATCH row=34' 'CROSSCHECK_ROW34_PASS'
echo CROSSCHECK_PILOT_CONTROLS_PASS | tee "$result/pilot_status.txt"
if [[ "$phase" == full ]]; then
    simulate full online.txt 3600
    positive full.log 'MULTICYCLE_COST_PASS vectors=8263 replay=128 reset_phases=38'
    clean full_console.log
    rc=0
    simulate full_negative negative.txt 900 || rc=$?
    [[ $rc -eq 0 || $rc -eq 1 ]] || exit "$rc"
    negative full_negative.log 'FUNCTIONAL_INTERNAL_MISMATCH row=0' 'MULTICYCLE_COST_PASS'
    echo CROSSCHECK_SLOW_MAX_CONTROLS_PASS | tee "$result/full_status.txt"
fi
python3 "$checker" verify "$bundle"
'''


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("prepare")
    make.add_argument("source", type=Path)
    make.add_argument("out", type=Path)
    check = commands.add_parser("verify")
    check.add_argument("bundle", type=Path)
    log = commands.add_parser("check-log")
    log.add_argument("path", type=Path)
    log.add_argument("--marker")
    log.add_argument("--sdf")
    log.add_argument("--reject")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare(args.source.resolve(), args.out.resolve())
        print("CROSSCHECK_PREPARED_ONLY")
    elif args.command == "verify":
        verify(args.bundle.resolve())
        print("CROSSCHECK_INPUTS_UNCHANGED")
    else:
        check_log(args.path, args.marker, args.sdf, args.reject)


if __name__ == "__main__":
    main()
