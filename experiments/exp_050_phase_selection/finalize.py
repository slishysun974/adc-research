"""Archive checked provenance, observed test log and final document hashes."""

import argparse
import json
from pathlib import Path
import re

from experiments.exp_049_normal_start_closed_loop.run import ROOT,digest,write
from experiments.exp_050_phase_selection.run import paired_summary

DOCUMENTS = (
    "docs/STATUS.md","docs/DECISIONS.md",
    "docs/reports/RESEARCH_STATUS_PLAIN_2026-10-09.md",
    "docs/reports/experiments/EXP_050_PHASE_SELECTION_V1.md",
    "docs/reports/experiments/README.md","docs/theory/FOUR_POINT_PHASE_SELECTION_CONDITIONS_V1.md",
    "docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md","docs/theory/README.md",
    "experiments/README.md","experiments/exp_050_phase_selection/README.md",
    "src/adc_research/calibration/README.md",
)


def run(directory):
    directory.relative_to(ROOT/"artifacts/runs/EXP_050")
    summary_path = directory/"summary.json"
    summary = json.loads(summary_path.read_text())
    verification = json.loads((directory/"verification.json").read_text())
    forks = json.loads((directory/"common_endpoint_forks.json").read_text())
    for evidence in (verification,forks):
        assert evidence["summary_sha256"] == digest(summary_path)
        for path,expected in evidence["source_sha256"].items():
            assert digest(Path(path)) == expected,path
    for path,expected in {**summary["source_evidence_sha256"],**verification["outcome_sha256"]}.items():
        assert digest(Path(path)) == expected,path
    assert digest(directory/"protocol.json") == summary["protocol_sha256"]
    assert paired_summary(summary["cases"]) == summary["paired_comparisons"]
    assert len(summary["cases"]) == 24
    assert all(len(c["methods"]) == 4 and not c["failures"] for c in summary["cases"])
    tests = (directory/"tests_escalated.log").read_text(encoding="utf-8-sig")
    match = re.search(r"Ran (\d+) tests in ([\d.]+)s",tests)
    assert match and re.search(r"\nOK\s*$",tests),"successful full-suite log required"
    sources = [ROOT/path for path in DOCUMENTS]
    sources += list((ROOT/"experiments/exp_050_phase_selection").glob("*.py"))
    sources += [ROOT/"src/adc_research/calibration/window_phase_selection.py",
                ROOT/"tests/test_window_phase_selection.py"]
    links = 0
    for name in DOCUMENTS:
        path = ROOT/name
        for target in re.findall(r"\]\(([^)]+)\)",path.read_text(encoding="utf-8")):
            if "://" in target or target.startswith("#"):
                continue
            assert (path.parent/target.split("#")[0]).resolve().exists(),(name,target)
            links += 1
    image_path = directory/"figures/all_paired_phase_gains.png"
    assert image_path.is_file()
    artifacts = [directory/name for name in ("summary.json","verification.json","protocol.json",
        "common_endpoint_forks.json","tests.log","tests_escalated.log")]+[image_path]
    write(directory/"completion.json",{"source_package_unchanged":True,"paired_statistics_rechecked":True,
        "local_links_checked":links,"tests":int(match[1]),"test_seconds":float(match[2]),
        "test_status":"OK; initial sandbox temp-permission errors retained, approved retry successful",
        "primary_counts":verification["counts"],"post_primary_control_counts":forks["counts"],
        "candidate_screen_outcomes":[{k:v for k,v in p.items() if k != "pairs"} for p in summary["paired_comparisons"]],
        "source_document_sha256":{str(p.relative_to(ROOT)):digest(p) for p in sources},
        "artifact_sha256":{str(p.relative_to(ROOT)):digest(p) for p in artifacts},
        "visual_review_recorded_from_task":"all paired cells PNG viewed",
        "scope":"finite synthetic Gu selector screening; both candidates failed; no hardware or chip victory claim"})
    print(f"Provenance and paired statistics retained; {links} local links checked; {match[1]} tests passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    run(parser.parse_args().directory.resolve())
