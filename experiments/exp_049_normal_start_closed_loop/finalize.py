"""Check result provenance, local document links and archive final hashes."""

import argparse
import json
from pathlib import Path
import re

from experiments.exp_049_normal_start_closed_loop.run import ROOT,digest,write

DOCUMENTS = (
    "docs/STATUS.md","docs/DECISIONS.md",
    "docs/reports/RESEARCH_STATUS_PLAIN_2026-10-09.md",
    "docs/reports/experiments/EXP_049_NORMAL_START_CLOSED_LOOP_V1.md",
    "docs/reports/experiments/README.md",
    "docs/theory/NORMAL_START_WINDOW_ATTRIBUTION_AND_CODE_EFFECTS_V1.md",
    "docs/theory/UNKNOWN_GAIN_END_TO_END_FRAMEWORK_V0_1.md","docs/theory/README.md",
    "experiments/README.md","experiments/exp_049_normal_start_closed_loop/README.md",
    "src/adc_research/evaluation/README.md",
)


def run(directory):
    directory.relative_to(ROOT/"artifacts/runs/EXP_049")
    summary = json.loads((directory/"summary.json").read_text())
    verified = json.loads((directory/"verification_and_propagation.json").read_text())
    assert verified["summary_sha256"] == digest(directory/"summary.json")
    assert summary["protocol_sha256"] == digest(directory/"protocol.json")
    for path,expected in {**summary["source_evidence_sha256"],**summary["source_sha256"],
                          **verified["source_sha256"],**verified["detail_sha256"]}.items():
        assert digest(Path(path)) == expected,path
    links = 0
    for name in DOCUMENTS:
        path = ROOT/name
        text = path.read_text(encoding="utf-8")
        for target in re.findall(r"\]\(([^)]+)\)",text):
            if "://" in target or target.startswith("#"):
                continue
            target = target.split("#")[0]
            assert (path.parent/target).resolve().exists(),(name,target)
            links += 1
    files = [ROOT/name for name in DOCUMENTS]
    files += list((ROOT/"experiments/exp_049_normal_start_closed_loop").glob("*.py"))
    files += [ROOT/"tests/test_window_trajectory_diagnostics.py",
              ROOT/"src/adc_research/evaluation/window_trajectory_diagnostics.py"]
    figures = sorted((directory/"figures").glob("*.png"))
    assert len(figures) == 2
    artifacts = [directory/name for name in ("summary.json","verification_and_propagation.json","protocol.json")]+figures
    write(directory/"completion.json",{
        "provenance_and_local_links_passed":True,"checked_local_links":links,
        "experiment_source_and_document_sha256":{str(p.relative_to(ROOT)):digest(p) for p in files},
        "artifact_sha256":{str(p.relative_to(ROOT)):digest(p) for p in artifacts},
        "verified_counts":verified["counts"],
        "full_suite_result_recorded_from_task_output":{"command":"python -m unittest discover -s tests",
            "tests":328,"exit_code":0,"result":"OK","elapsed_seconds":18.063},
        "visual_review_recorded_from_task":"both PNGs viewed; checkpoint annotation overlap corrected and viewed again",
        "scope":"synthetic finite-record Gu baseline diagnosis; no chip or new-algorithm performance guarantee"})
    print(f"Provenance retained; {links} local document links checked; final hashes saved.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    run(parser.parse_args().directory.resolve())
