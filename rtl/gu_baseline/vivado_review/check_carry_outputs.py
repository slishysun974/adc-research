"""Independently check the finite CARRY4 connection workaround, without rewriting.

Read the actual old/new instance ports and declared net ranges rather than
trusting the normalizer's sink list. Reverse edits must recover every byte.
This checks wiring, not equivalence of simulation event scheduling.
"""
import hashlib
import re


def require(condition, message):
    if not condition:
        raise ValueError(message)


def cells(text):
    result = {}
    for match in re.finditer(r"\bCARRY4\s+(\\\S+|[A-Za-z_]\w*)\s*\(([^;]+?)\);", text):
        name, body = match.groups()
        require(name not in result, "duplicate CARRY4 instance")
        result[name] = dict(re.findall(r"\.(\w+)\(\s*(.*?)\s*\)(?:,|\s*$)", body, re.S))
    return result


def check_connections(source, output, audit):
    old, new = source.decode("utf-8"), output.decode("utf-8")
    sha = lambda blob: hashlib.sha256(blob).hexdigest()
    require(sha(source) == audit["source_sha256"] == audit["restored_original_sha256"], "raw hash mismatch")
    require(sha(output) == audit["output_sha256"], "normalized hash mismatch")
    declarations = {}
    for match in re.finditer(r"\bwire\s*(?:\[(\d+):(\d+)\])?\s*(\\\S+|[A-Za-z_]\w*)\s*;", old):
        hi, lo, name = match.groups()
        declarations[name] = None if hi is None else (int(hi), int(lo))
    before, after = cells(old), cells(new)
    require(before.keys() == after.keys(), "changed CARRY4 instance set")
    expected, changed = {}, {}
    for name, ports in before.items():
        require(ports.keys() == after[name].keys(), "changed primitive pin set")
        for pin, connection in ports.items():
            if pin not in ("O", "CO") or not connection.startswith("{"):
                require(connection == after[name][pin], "changed untouched primitive port")
                continue
            wire = after[name][pin]
            require(re.fullmatch(r"adc_sim_carry_output_\d+", wire), "missing contiguous output wire")
            require(new.count(f"wire [3:0] {wire};") == 1, "invalid output wire declaration")
            require(wire not in changed, "shared normalized output wire")
            changed[wire] = (name, pin)
            remaining, sinks = connection[1:-1].strip(), []
            while remaining:
                token = re.match(r"(\\\S+|[A-Za-z_]\w*)", remaining)
                require(token is not None, "unparsed old sink")
                net = token.group()
                remaining = remaining[token.end():].lstrip()
                require(net in declarations, f"undeclared sink: {net}")
                indices = re.match(r"\[(\d+)(?::(\d+))?\]", remaining)
                if indices:
                    hi, lo = int(indices[1]), int(indices[2] or indices[1])
                    limits = declarations[net]
                    require(limits is not None and min(limits) <= min(hi, lo) <= max(hi, lo) <= max(limits), "sink outside declaration")
                    step = 1 if lo >= hi else -1
                    sinks.extend(f"{net} [{i}]" for i in range(hi, lo + step, step))
                    remaining = remaining[indices.end():].lstrip()
                else:
                    require(declarations[net] is None, "implicit vector sink unsupported")
                    sinks.append(net)
                if remaining:
                    require(remaining.startswith(","), "unparsed sink separator")
                    remaining = remaining[1:].lstrip()
            require(len(sinks) == 4 and len(set(sinks)) == 4, "not four distinct sink bits")
            expected.update({(wire, bit): sink.strip() for bit, sink in enumerate(reversed(sinks))})
    actual = {}
    for match in re.finditer(r"^\s*assign (.+?)\s*=\s*(adc_sim_carry_output_\d+)\[(\d)\];", new, re.M):
        sink, wire, bit = match.groups()
        key = wire, int(bit)
        require(key not in actual, "duplicate bit alias")
        actual[key] = sink.strip()
    require(actual == expected, "bit aliases differ from original instance ports")
    require(len(changed) == audit["normalized_ports"] and len(actual) == audit["bit_aliases"], "audit count mismatch")
    require(len(before) == audit["carry_cells"], "cell count mismatch")
    require({m["wire"]: (m["cell"], m["port"]) for m in audit["mappings"]} == changed, "audit instance mapping mismatch")
    restored = new
    for edit in reversed(audit["reversible_edits"]):
        a, b = edit["output_start"], edit["output_end"]
        require(restored[a:b] == edit["new"], "invalid reverse edit")
        restored = restored[:a] + edit["old"] + restored[b:]
    require(restored.encode("utf-8") == source, "untouched source bytes changed")
    return {"carry_cells": len(before), "normalized_ports": len(changed), "bit_aliases": len(actual),
            "declaration_ranges_checked": True, "reverse_bytes_match": True}
