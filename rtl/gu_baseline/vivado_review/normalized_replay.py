"""Prepare/verify/accept the diagnosed staged-v4 normalized SDF replay.

Uses only the Python standard library. No synthesis or simulation is started
by this program. A qualified replay certificate never certifies raw exports,
methodology clearance, other candidates, devices or physical hardware.
"""
from pathlib import Path
import argparse
import json
import shutil

from check_carry_outputs import check_connections, require
from normalize_carry_outputs import normalize
from prepare_timing_crosscheck import check_log, sha

HERE = Path(__file__).resolve().parent
IDENTITY = {
    "netlists/routed.v": "48dfda44c1cec29aa5d4a1449f9cfaec90794b944df02341730c94a3dc939238",
    "netlists/routed.sdf": "2a62127912a6952b4dcaf157e3214660b228e1bea2dcbc350184015c6d6aa35a",
    "netlists/tb_staged_cost.sv": "06b4c9ee4f6624b0a6a2f982c013c9f13f9e5da7a8456dd7a9f97603ef503309",
    "checkpoints/routed.dcp": "7ff56658df60b0b203c7d19afa09ee890594ff6c3690816056dac6b713140b98",
    "online.txt": "c64faa81c5346ffe381cfc54e591654d9a8e050c89dab301185a6c37a345f82b",
    "negative.txt": "4df25a4093b1b18c7de816a5da18c093930026ea70bf14b26a9e57279f022ea5",
    "row221_negative.txt": "9d1fa6c2fbd6bd5e37758c49f6a1b510c1c19cdedb011920a90d2ee1b5d24032",
}
CONTROLS = {
    "pilot": ("STAGED_SDF_PILOT_PASS rows=222 reset_phases=38", None),
    "pilot_negative": ("FUNCTIONAL_INTERNAL_MISMATCH row=221", "STAGED_SDF_PILOT_PASS"),
    "full": ("MULTICYCLE_COST_PASS vectors=8263 replay=128 reset_phases=38", None),
    "negative": ("FUNCTIONAL_INTERNAL_MISMATCH row=0", "MULTICYCLE_COST_PASS"),
}
TOOLS = ("normalized_replay.py", "normalize_carry_outputs.py", "check_carry_outputs.py",
         "prepare_timing_crosscheck.py", "run_normalized_replay.sh")


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(data, indent=2) + "\n")


def safe_relative(root, name):
    path = root / name.replace("\\", "/")
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        raise ValueError("manifest path escapes bundle") from None
    return path


def check_vectors(run):
    rows = [[int(x) for x in row.split()] for row in (run / "online.txt").read_text().splitlines()]
    require(len(rows) == 8263 and all(len(row) == 19 for row in rows), "invalid reference vectors")
    for name, index, column in (("negative.txt", 0, 6), ("row221_negative.txt", 221, 16)):
        expected = [row.copy() for row in rows]
        expected[index][column] ^= 1  # final code or second-stage accumulator0; no input change
        actual = [[int(x) for x in row.split()] for row in (run / name).read_text().splitlines()]
        require(actual == expected, f"invalid single-bit negative control: {name}")


def verify(run):
    manifest = read_json(run / "replay_manifest.json")
    require(manifest["schema"] == "adc.normalized_sdf_replay.v1", "wrong bundle schema")
    for name, expected in manifest["bundle_sha256"].items():
        require(sha(safe_relative(run, name)) == expected, f"changed bundle input: {name}")
    require(manifest["source_identity"] == IDENTITY, "wrong staged-v4 identity")
    for name, expected in IDENTITY.items():
        require(sha(run / "physical" / name) == expected, f"changed physical source: {name}")
    require(sha(run / "design/routed.sdf") == IDENTITY["netlists/routed.sdf"], "changed SDF")
    require(sha(run / "design/tb_staged_cost.sv") == IDENTITY["netlists/tb_staged_cost.sv"], "changed scoreboard")
    for name in ("online.txt", "negative.txt", "row221_negative.txt"):
        require(sha(run / name) == IDENTITY[name], "changed replay vectors")
    check_vectors(run)
    connections = check_connections((run / "physical/netlists/routed.v").read_bytes(),
                                    (run / "design/routed.v").read_bytes(),
                                    read_json(run / "connection_audit.json"))
    require(connections["normalized_ports"] == 521 and connections["bit_aliases"] == 2084,
            "wrong normalization coverage")
    return manifest, connections


def prepare(baseline, output):
    require(not output.exists(), "refuse to overwrite evidence")
    for name, expected in IDENTITY.items():
        require(sha(baseline / name) == expected, f"not the diagnosed staged-v4 input: {name}")
    old = read_json(baseline / "manifest.json")
    for name, expected in old["source_sha256"].items():
        require(sha(baseline / "sources" / Path(name.replace("\\", "/")).name) == expected, "changed RTL source")
    check_vectors(baseline)
    blob, audit = normalize((baseline / "netlists/routed.v").read_bytes())
    check_connections((baseline / "netlists/routed.v").read_bytes(), blob, audit)
    output.mkdir(parents=True)
    for directory in ("design", "tools", "logs", "physical"):
        (output / directory).mkdir()
    for name in IDENTITY:
        target = output / "physical" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(baseline / name, target)
    # Preserve actual reports and their qualifications; never convert SYNTH-9
    # advisories to a zero-violation methodology result.
    for name in ("manifest.json", "staged_result.json", "timing_result.json", "netlist_check_protocol.json"):
        shutil.copyfile(baseline / name, output / "physical" / name)
    for directory in ("sources", "reports"):
        shutil.copytree(baseline / directory, output / "physical" / directory)
    (output / "design/routed.v").write_bytes(blob)
    for name in ("routed.sdf", "tb_staged_cost.sv"):
        shutil.copyfile(baseline / "netlists" / name, output / "design" / name)
    for name in ("online.txt", "negative.txt", "row221_negative.txt"):
        shutil.copyfile(baseline / name, output / name)
    (output / "design/run_staged.tcl").write_bytes(b"run all\nquit\n")
    write_json(output / "connection_audit.json", audit)
    for name in TOOLS:
        shutil.copyfile(HERE / name, output / "tools" / name)
    manifest = {"schema": "adc.normalized_sdf_replay.v1", "source_identity": IDENTITY,
                "status": "prepared_only", "baseline_origin": str(baseline),
                "contract": "2022.1 xc7z020clg400-1,100MHz,E39/40; original maxdelay/transport/pulse=0; 184+53 internal bits",
                "budget": "one compile/elaborate<=600s; pilot and row221negative<=600s each; full<=3600s and row0negative<=600s only after pilot gates; no options sweep",
                "bundle_sha256": {p.relative_to(output).as_posix(): sha(p) for p in output.rglob("*") if p.is_file()},
                "boundary": "Normalized simulation connection workaround only. Raw export failed; methodology31 SYNTH-9 retained. No board/ASIC/vendor-bug certification."}
    write_json(output / "replay_manifest.json", manifest)
    verify(output)
    return {"bundle": str(output), "prepared_only": True, "normalized_ports": 521}


def check_stage(logs, stage):
    if stage in ("compile", "elaborate"):
        check_log(logs / f"timing_{stage}.log", None, "routed.sdf" if stage == "elaborate" else None)
    else:
        marker, reject = CONTROLS[stage]
        for suffix in (".log", "_console.log"):
            check_log(logs / f"timing_{stage}{suffix}", marker, None, reject)


def import_saved(run, saved):
    verify(run)
    require(not any((run / "logs").iterdir()), "refuse to overwrite logs")
    inputs = read_json(saved / "inputs.json")
    require({name.replace("\\", "/") for name in inputs["sha256"]} ==
            {"design/" + name for name in ("routed.v", "routed.sdf", "tb_staged_cost.sv", "run_staged.tcl")},
            "incomplete saved design identity")
    require(set(inputs["vector_sha256"]) == {"online.txt", "negative.txt", "row221_negative.txt"},
            "incomplete saved vector identity")
    for section in ("sha256", "vector_sha256"):
        for name, expected in inputs[section].items():
            require(sha(safe_relative(saved, name)) == expected, "changed saved replay input")
            require(sha(safe_relative(run, name)) == expected, "saved replay inputs differ from new bundle")
    # The saved result captures log hashes before this revalidation. Copy it
    # with its input/runner protocol; do not relabel saved runs as new runs.
    result = read_json(saved.parent / "research_result.json")
    require(result["normalized_full_SDF_and_controls_pass"] is True and result["overall_raw_export_acceptance"] is False,
            "wrong saved qualification")
    for name, evidence in result["whole_normalized_netlist"].items():
        require(sha(saved / "logs" / name) == evidence["sha256"], "changed saved result log")
    for stage in ("compile", "elaborate", *CONTROLS):
        check_stage(saved / "logs", stage)
    provenance = {}
    for path in (saved / "inputs.json", saved.parent / "research_result.json",
                 saved.parent / "normalization_protocol.json", saved.parent / "tools/run_normalized_full.sh"):
        target = run / "saved_evidence" / path.name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(path, target)
        provenance[target.relative_to(run).as_posix()] = sha(path)
    for path in (saved / "logs").glob("*.log"):
        shutil.copyfile(path, run / "logs" / path.name)
        provenance[f"logs/{path.name}"] = sha(path)
    write_json(run / "evidence_origin.json", {"mode": "reused_saved_full_replay", "origin": str(saved), "sha256": provenance})
    return {"saved_evidence_imported": True, "new_simulations": 0}


def validate(run, pilot_only=False):
    manifest, connections = verify(run)
    stages = ("compile", "elaborate", "pilot", "pilot_negative") + (() if pilot_only else ("full", "negative"))
    for stage in stages:
        check_stage(run / "logs", stage)
    origin_path = run / "evidence_origin.json"
    origin = read_json(origin_path) if origin_path.exists() else {"mode": "new_replay"}
    for name, expected in origin.get("sha256", {}).items():
        require(sha(safe_relative(run, name)) == expected, "changed imported evidence")
    result = {"schema": "adc.normalized_sdf_certificate.v1", "qualified_normalized_pilot_pass": True,
              "qualified_normalized_full_sdf_pass": not pilot_only,
              "raw_export_acceptance": False, "methodology_clearance": False,
              "evidence_origin": origin, "connection_check": connections,
              "manifest_sha256": sha(run / "replay_manifest.json"),
              "logs_sha256": {p.name: sha(p) for p in (run / "logs").glob("*.log")},
              "reused_physical_timing": read_json(run / "physical/timing_result.json"),
              "boundary": manifest["boundary"]}
    write_json(run / ("normalized_pilot_validation.json" if pilot_only else "normalized_validation.json"), result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("prepare")
    p.add_argument("baseline", type=Path)
    p.add_argument("output", type=Path)
    for command in ("verify", "validate", "import-saved", "check-stage"):
        p = commands.add_parser(command)
        p.add_argument("run", type=Path)
        if command == "validate":
            p.add_argument("--pilot-only", action="store_true")
        if command == "import-saved":
            p.add_argument("saved", type=Path)
        if command == "check-stage":
            p.add_argument("stage", choices=("compile", "elaborate", *CONTROLS))
    args = parser.parse_args()
    if args.command == "prepare":
        result = prepare(args.baseline.resolve(), args.output.resolve())
    elif args.command == "verify":
        _, result = verify(args.run.resolve())
    elif args.command == "import-saved":
        result = import_saved(args.run.resolve(), args.saved.resolve())
    elif args.command == "check-stage":
        check_stage(args.run / "logs", args.stage)
        result = {"stage_pass": args.stage}
    else:
        result = validate(args.run.resolve(), args.pilot_only)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
