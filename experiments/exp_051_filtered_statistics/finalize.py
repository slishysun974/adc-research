"""Validate provenance, recorded tests, paired statistics and document links."""

import argparse
import json
from pathlib import Path
import re

from experiments.exp_049_normal_start_closed_loop.run import ROOT,digest,write
from experiments.exp_051_filtered_statistics.run import compare

DOCUMENTS = (
    "docs/STATUS.md","docs/DECISIONS.md","docs/reports/RESEARCH_STATUS_PLAIN_2026-10-09.md",
    "docs/reports/experiments/EXP_051_FILTERED_STATISTICS_V1.md","docs/reports/experiments/README.md",
    "docs/theory/FILTERED_STATISTICS_STEP_AND_STATE_VARIANCE_V1.md",
    "docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md","docs/theory/README.md",
    "experiments/README.md","experiments/exp_051_filtered_statistics/README.md",
    "src/adc_research/calibration/README.md",
)


def run(directory):
    directory.relative_to(ROOT/"artifacts/runs/EXP_051")
    summary = json.loads((directory/"summary.json").read_text())
    verification = json.loads((directory/"verification.json").read_text())
    audit = json.loads((directory/"filter_sum_audit.json").read_text())
    assert digest(directory/"protocol.json") == summary["protocol_sha256"]
    for evidence in (verification,audit):
        assert evidence["summary_sha256"] == digest(directory/"summary.json")
        for path,expected in evidence["source_sha256"].items():
            assert digest(Path(path)) == expected,path
    for path,expected in {**summary["source_evidence_sha256"],**verification["outcome_sha256"]}.items():
        assert digest(Path(path)) == expected,path
    assert compare(summary["cases"]) == summary["comparisons"]
    assert len(summary["cases"]) == 24 and all(len(c["methods"]) == 3 and not c["failures"] for c in summary["cases"])
    assert audit["identities"] == 384 and all(a["identity_verified"] for a in audit["audits"])
    tests = (directory/"tests.log").read_text(encoding="utf-8-sig")
    match = re.search(r"Ran (\d+) tests in ([\d.]+)s",tests)
    assert match and re.search(r"\nOK\s*$",tests),"full-suite success log required"
    sources = [ROOT/path for path in DOCUMENTS]
    sources += list((ROOT/"experiments/exp_051_filtered_statistics").glob("*.py"))
    sources += [ROOT/path for path in ("src/adc_research/calibration/fixed_filtered_window.py",
        "src/adc_research/theory/filtered_mean_dynamics.py","tests/test_fixed_filtered_window.py","tests/test_filtered_mean_dynamics.py")]
    links = 0
    for name in DOCUMENTS:
        path = ROOT/name
        for target in re.findall(r"\]\(([^)]+)\)",path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            assert (path.parent/target.split("#")[0]).resolve().exists(),(name,target)
            links += 1
    figure = directory/"figures/variance_gain_and_checkpoints.png"
    assert figure.is_file()
    artifacts = [directory/name for name in ("summary.json","verification.json","protocol.json","filter_sum_audit.json","tests.log")]+[figure]
    write(directory/"completion.json",{"provenance_and_pair_statistics_passed":True,"local_links_checked":links,
        "tests":int(match[1]),"test_seconds":float(match[2]),"test_status":"OK; temporary files kept in declared writable project directory",
        "counts":verification["counts"],"filter_sum_identities":audit["identities"],
        "screens":[{k:v for k,v in c.items() if k != "pairs"} for c in summary["comparisons"]],
        "source_document_sha256":{str(p.relative_to(ROOT)):digest(p) for p in sources},
        "artifact_sha256":{str(p.relative_to(ROOT)):digest(p) for p in artifacts},
        "visual_review_recorded_from_task":"variance/gain/checkpoint figure viewed",
        "scope":"finite synthetic candidates and conditional scalar theory; both candidates failed the declared screen"})
    print(f"Source fingerprints retained, {links} links checked, {match[1]} tests passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    run(parser.parse_args().directory.resolve())
