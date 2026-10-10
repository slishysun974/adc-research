"""Replay Yosys primitive netlists locally with a small native gate evaluator.

Reject unresolved/unsupported primitives, multiple drivers, and combinational
cycles. Compare all 13 exposed output bits with the existing Python records.
This provides finite zero-delay functional validation, not formal equivalence.
"""
from __future__ import annotations

import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess

from .run import ROOT, TOPS, _relative


def prepare(name: str, output: Path) -> dict:
    gate_path = output / "gates.json"
    module = json.loads(gate_path.read_text(encoding="utf-8"))["modules"][TOPS[name]]
    ids = {}

    def bit_id(bit) -> int:
        if isinstance(bit, str):
            return {"0": 0, "1": 1, "x": 2, "z": 2}[bit]
        if bit not in ids:
            ids[bit] = len(ids) + 3
        return ids[bit]

    ports = module["ports"]
    input_ports = {p: [bit_id(b) for b in v["bits"]] for p, v in ports.items()
                   if v["direction"] == "input"}
    input_ids = [b for bits in input_ports.values() for b in bits]
    output_ids = [bit_id(b) for p in ("valid_out", "final_code") for b in ports[p]["bits"]]
    available = {0, 1, 2, *input_ids}
    drivers = {}
    gates, ffs = [], []
    opcodes = {"$_AND_": 0, "$_OR_": 1, "$_XOR_": 2, "$_NOT_": 3, "$_MUX_": 4}
    for cell in module["cells"].values():
        kind, connections = cell["type"], cell["connections"]

        def pin(p):
            if len(connections[p]) != 1:
                raise ValueError(f"Non-bitwise cell: {kind} {p}")
            return bit_id(connections[p][0])

        if kind in opcodes:
            y = pin("Y")
            if y in drivers or y in available:
                raise ValueError("Multiple drivers or driven constant/input")
            drivers[y] = len(gates)
            gates.append((opcodes[kind], y, pin("A"),
                          pin("B") if kind != "$_NOT_" else 0,
                          pin("S") if kind == "$_MUX_" else 0))
        elif kind in ("$_SDFFE_PP0P_", "$_SDFFE_PP1P_"):
            q = pin("Q")
            if q in available or q in drivers:
                raise ValueError("Multiple state drivers")
            if pin("C") != input_ports["clk"][0]:
                raise ValueError("Only one explicitly driven positive-edge clock is supported")
            available.add(q)
            ffs.append((q, pin("D"), pin("R"), pin("E"), int(kind == "$_SDFFE_PP1P_")))
        else:
            raise ValueError(f"Unsupported primitive: {kind}")
    dependents = [[] for _ in gates]
    degree = []
    for index, gate in enumerate(gates):
        parents = set()
        for b in gate[2:]:
            if b not in available:
                if b not in drivers:
                    raise ValueError(f"Undriven input bit: {b}")
                parents.add(drivers[b])
        degree.append(len(parents))
        for parent in parents:
            dependents[parent].append(index)
    pending = deque(i for i, d in enumerate(degree) if not d)
    ordered = []
    while pending:
        index = pending.popleft()
        ordered.append(gates[index])
        for child in dependents[index]:
            degree[child] -= 1
            if not degree[child]:
                pending.append(child)
    if len(ordered) != len(gates):
        raise ValueError("Combinational cycle in mapped netlist")
    for b in [*output_ids, *(b for ff in ffs for b in ff[1:4])]:
        if b not in available and b not in drivers:
            raise ValueError("Undriven output or FF input")
    online = name == "online"
    header = (0xADC03401, len(ids)+3, len(ordered), len(ffs), len(input_ids), len(output_ids),
              input_ports["valid_in"][0], input_ports.get("reset", [0])[0],
              input_ports.get("clk", [0])[0], int(online))
    with (output / "replay_netlist.bin").open("wb") as stream:
        stream.write(struct.pack("<10I", *header))
        for instruction in [*ordered, *ffs]:
            stream.write(struct.pack("<5I", *instruction))
        stream.write(struct.pack(f"<{len(input_ids)}I", *input_ids))
        stream.write(struct.pack("<13I", *output_ids))
    reference = ROOT / ("artifacts/runs/EXP_032/candidate_a_q22/vectors.txt" if online else
                        "artifacts/runs/EXP_031/candidate_a_default_dither/vectors.txt")
    count = 0
    with reference.open(encoding="utf-8") as records, (output / "replay_vectors.bin").open("wb") as stream:
        stream.write(b"\0" * 4)
        for line in records:
            row = [int(x) for x in line.split()]
            if len(row) != (19 if online else 21):
                raise ValueError("Malformed Python reference record")
            q1, q2, backend, d1, d2 = row[:5]
            values = dict(valid_in=1, stage1_symbol=q1, stage2_symbol=q2,
                          backend_raw_code=backend, stage1_dither_positive=d1,
                          stage2_dither_positive=d2, clk=0, reset=0)
            if online:
                valid, code = row[5:7]
            else:
                valid, code = row[13], row[18]
                for stage in (1, 2):
                    for coefficient in range(4):
                        values[f"stage{stage}_coefficient{coefficient}_q10"] = row[5+(stage-1)*4+coefficient]
            payload = [((values[p] >> k) & 1) for p, bits in input_ports.items()
                       for k in range(len(bits))]
            stream.write(bytes(payload + [valid] + [(code >> k) & 1 for k in range(12)]))
            count += 1
        stream.seek(0)
        stream.write(struct.pack("<I", count))
    if count != (8263 if online else 18432):
        raise ValueError(f"Unexpected number of reviewed reference records: {count}")
    return {"reference_rows": count, "source_vectors": _relative(reference),
            "source_vector_sha256": hashlib.sha256(reference.read_bytes()).hexdigest(),
            "gate_netlist_sha256": hashlib.sha256(gate_path.read_bytes()).hexdigest(),
            "combination_cells": len(gates), "state_bits": len(ffs), "value_slots": len(ids)+3}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--top", choices=(*TOPS, "all"), default="all")
    parser.add_argument("--cc", default="gcc")
    args = parser.parse_args()
    output = (ROOT / args.output).resolve()
    _relative(output)
    compiler = shutil.which(args.cc)
    if not compiler:
        raise RuntimeError("A local C compiler is required; no installer is run")
    source = ROOT / "experiments/exp_034_generic_synthesis/replay_gates.c"
    executable = output / "replay_gates.exe"
    subprocess.run([compiler, "-std=c11", "-O3", "-Wall", "-Wextra", "-Werror",
                    str(source), "-o", str(executable)], check=True, cwd=ROOT)
    compiler_version = subprocess.check_output([compiler, "--version"], text=True).splitlines()[0]
    for name in TOPS if args.top == "all" else (args.top,):
        print(f"Preparing {name} native netlist replay...", flush=True)
        result = prepare(name, output / name)
        completed = subprocess.run([str(executable), str(output / name / "replay_netlist.bin"),
                                    str(output / name / "replay_vectors.bin")],
                                   cwd=ROOT, text=True, capture_output=True)
        (output / name / "native_replay.log").write_text(completed.stdout + completed.stderr,
                                                       encoding="utf-8")
        completed.check_returncode()
        # Check that a deliberately corrupted final-code bit is detected.
        corrupted = bytearray((output / name / "replay_vectors.bin").read_bytes())
        input_bits = 21 if name == "online" else 107
        corrupted[4 + input_bits + 1] ^= 1
        corrupt_path = output / name / "replay_corrupt_reference.bin"
        corrupt_path.write_bytes(corrupted)
        negative = subprocess.run([str(executable), str(output / name / "replay_netlist.bin"),
                                   str(corrupt_path)], cwd=ROOT, text=True, capture_output=True)
        if negative.returncode == 0 or "Mismatch" not in negative.stderr:
            raise RuntimeError("Native evaluator did not reject a corrupted expected code")
        (output / name / "native_negative_check.log").write_text(negative.stderr, encoding="utf-8")
        result.update(passed=True, compiler_version=compiler_version,
                      evaluator_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                      corrupt_expected_code_rejected=True,
                      output=completed.stdout.strip(),
                      scope="finite_settled_code_replay_not_formal_equivalence")
        (output / name / "native_replay_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        top_summary_path = output / name / "summary.json"
        top_summary = json.loads(top_summary_path.read_text(encoding="utf-8"))
        top_summary["post_synthesis_simulation"] = "native_zero_delay_code_replay_passed"
        top_summary["native_replay"] = result
        top_summary_path.write_text(json.dumps(top_summary, indent=2), encoding="utf-8")
        summary_path = output / "summary.json"
        if summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            summary["tops"][name] = top_summary
            summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(completed.stdout.strip(), flush=True)


if __name__ == "__main__":
    main()
