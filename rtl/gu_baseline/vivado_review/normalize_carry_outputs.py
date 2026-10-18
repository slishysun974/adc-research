"""Create a separately audited CARRY4 simulation-netlist connection workaround.

Concatenated O/CO ports are replaced with contiguous four-bit wires, followed
by explicit zero-delay bit aliases to the same sinks. Never synthesize this
file or overwrite the original Vivado export. SDF bytes/instances/pins stay
unchanged. This is a controlled XSim workaround, not raw-export acceptance.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re


def digest(data):
    return hashlib.sha256(data).hexdigest()


def normalize(source):
    text = source.decode("utf-8")
    assert text.count("module gu_multicycle_cost_top") == 1 or text.count("module tb_event_carry;") == 1
    module = re.search(r"\bmodule\s+\w+\b[^;]*;", text)
    end = re.search(r"\bendmodule\b", text)
    assert module and end
    blocks = list(re.finditer(r"\bCARRY4\s+(?P<cell>\\\S+|[A-Za-z_]\w*)\s*\((?P<body>[^;]+?)\);", text))
    declarations, aliases, mappings, edits = [], [], [], []
    for block in blocks:
        assert module.end() < block.start() < end.start()
        for port in re.finditer(r"\.(?P<port>O|CO)\(\s*(?P<conn>\{[^{}]+\})\s*\)", block.group("body")):
            conn = port.group("conn")
            sinks = []
            for term in conn[1:-1].split(","):
                parsed = re.fullmatch(r"(?P<name>\\\S+|[A-Za-z_]\w*)(?:\s*\[(?P<hi>\d+)(?::(?P<lo>\d+))?\])?", term.strip())
                assert parsed, (block.group("cell"), term)
                name, hi, lo = parsed.group("name", "hi", "lo")
                if hi is None:
                    sinks.append(name + (" " if name.startswith("\\") else ""))
                else:
                    hi, lo = int(hi), int(lo if lo is not None else hi)
                    step = -1 if hi >= lo else 1
                    sinks.extend(f"{name} [{i}]" for i in range(hi, lo + step, step))
            assert len(sinks) == 4 and len(set(sinks)) == 4, (conn, sinks)
            wire = f"adc_sim_carry_output_{len(mappings)}"
            assert wire not in text
            declarations.append(f"  wire [3:0] {wire};\n")
            aliases.extend(f"  assign {sink} = {wire}[{3-i}];\n" for i, sink in enumerate(sinks))
            a = block.start("body") + port.start("conn")
            b = block.start("body") + port.end("conn")
            assert text[a:b] == conn
            edits.append((a, b, conn, wire))
            mappings.append({"cell": block.group("cell"), "port": port.group("port"),
                             "original_connection": conn, "wire": wire,
                             "sinks_msb_to_lsb": sinks})
    assert mappings
    edits.extend([(module.end(), module.end(), "", "\n" + "".join(declarations)),
                  (end.start(), end.start(), "", "".join(aliases))])
    edits.sort()
    pieces, audit_edits, pos, offset = [], [], 0, 0
    for a, b, old, new in edits:
        assert a >= pos and text[a:b] == old
        pieces.extend((text[pos:a], new))
        audit_edits.append({"input_start": a, "input_end": b, "output_start": a + offset,
                            "output_end": a + offset + len(new), "old": old, "new": new})
        offset += len(new) - (b-a)
        pos = b
    result = "".join(pieces) + text[pos:]
    # Independent reverse replacement must recover every original byte.
    restored = result
    for edit in reversed(audit_edits):
        a, b = edit["output_start"], edit["output_end"]
        assert restored[a:b] == edit["new"]
        restored = restored[:a] + edit["old"] + restored[b:]
    assert restored.encode("utf-8") == source
    return result.encode("utf-8"), {"carry_cells": len(blocks), "normalized_ports": len(mappings),
                                  "bit_aliases": len(aliases), "mappings": mappings,
                                  "reversible_edits": audit_edits,
                                  "source_sha256": digest(source),
                                  "output_sha256": digest(result.encode("utf-8")),
                                  "restored_original_sha256": digest(restored.encode("utf-8")),
                                  "scope": "CARRY4 O/CO concatenation only; no cell/pin/parameter/SDF/RTL/DCP changes. Zero-delay aliases add simulation event boundaries; raw export failure remains separate."}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source", type=Path)
    p.add_argument("output", type=Path)
    p.add_argument("--audit", required=True, type=Path)
    a = p.parse_args()
    assert not a.output.exists() and not a.audit.exists(), "refuse to overwrite evidence"
    output, audit = normalize(a.source.read_bytes())
    a.output.write_bytes(output)
    a.audit.write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: audit[k] for k in ["carry_cells", "normalized_ports", "bit_aliases", "output_sha256"]}))


if __name__ == "__main__":
    main()
