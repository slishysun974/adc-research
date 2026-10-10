"""Emit the mapped bit graph with scalar nets for legacy HDL simulators.

This is a representation change: keep every cell, pin, port and state bit.
No arithmetic optimization, gate pruning or source RTL modification is made.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from .run import ROOT, TOPS, _relative


def export(source: Path, output: Path) -> dict:
    _relative(output)
    output.mkdir(parents=True, exist_ok=True)
    module = json.loads(source.read_text(encoding="utf-8"))["modules"][TOPS["online"]]
    cells, ports = module["cells"], module["ports"]
    bit_ids = {b for p in ports.values() for b in p["bits"] if isinstance(b, int)}
    state_ids = set()
    counts = Counter()
    for cell in cells.values():
        kind = cell["type"]
        if kind not in ("$_AND_", "$_OR_", "$_XOR_", "$_NOT_", "$_MUX_",
                        "$_SDFFE_PP0P_", "$_SDFFE_PP1P_"):
            raise ValueError(f"Unsupported primitive: {kind}")
        counts[kind] += 1
        for bits in cell["connections"].values():
            if len(bits) != 1:
                raise ValueError("Expected scalar cell pins")
            bit_ids.update(b for b in bits if isinstance(b, int))
        if "DFF" in kind:
            state_ids.add(cell["connections"]["Q"][0])

    def bit(value):
        return f"n{value}" if isinstance(value, int) else {"0": "1'b0", "1": "1'b1", "x": "1'bx", "z": "1'bz"}[value]

    netlist = output / "gates.v"
    with netlist.open("w", encoding="utf-8", newline="\n") as stream:
        def emit(line):
            stream.write(line + "\n")
        emit("// Scalar serialization of the original Yosys JSON bit graph.")
        emit(f"module {TOPS['online']}({', '.join(ports)});")
        for name, port in ports.items():
            width = len(port["bits"])
            emit(f"  {port['direction']} wire [{width-1}:0] {name};")
        for identity in sorted(bit_ids):
            emit(f"  {'reg' if identity in state_ids else 'wire'} n{identity};")
        for name, port in ports.items():
            for index, value in enumerate(port["bits"]):
                if port["direction"] == "input":
                    emit(f"  assign {bit(value)} = {name}[{index}];")
                else:
                    emit(f"  assign {name}[{index}] = {bit(value)};")
        for cell in cells.values():
            kind = cell["type"]
            pins = {p: bit(bits[0]) for p, bits in cell["connections"].items()}
            if "DFF" in kind:
                reset_value = "1'b1" if kind == "$_SDFFE_PP1P_" else "1'b0"
                emit(f"  always @(posedge {pins['C']})")
                emit(f"    if ({pins['R']}) {pins['Q']} <= {reset_value};")
                emit(f"    else if ({pins['E']}) {pins['Q']} <= {pins['D']};")
            else:
                if kind == "$_NOT_":
                    expression = f"~{pins['A']}"
                elif kind == "$_MUX_":
                    expression = f"{pins['S']} ? {pins['B']} : {pins['A']}"
                else:
                    operator = {"$_AND_": "&", "$_OR_": "|", "$_XOR_": "^"}[kind]
                    expression = f"{pins['A']} {operator} {pins['B']}"
                emit(f"  assign {pins['Y']} = {expression};")
        emit("endmodule")
    result = {"source_json": _relative(source),
              "source_json_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "verilog_sha256": hashlib.sha256(netlist.read_bytes()).hexdigest(),
              "cells_by_type": dict(counts), "total_cells": sum(counts.values()),
              "state_bits": len(state_ids),
              "scope": "scalar_serialization_without_graph_or_arithmetic_changes"}
    (output / "export_summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    print(json.dumps(export(ROOT/args.source, ROOT/args.output), indent=2))
