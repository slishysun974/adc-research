"""Exact cumulative-statistic identity on each EMA trajectory and partition."""

import argparse
from fractions import Fraction as F
import json
from pathlib import Path

from experiments.exp_049_normal_start_closed_loop.run import digest,write


def run(directory):
    summary = json.loads((directory/"summary.json").read_text())
    audits = []
    for case in summary["cases"]:
        method = next(m for m in case["methods"] if m["method"] == "ema_quarter")
        path = directory/case["name"]/"ema_quarter.json"
        assert digest(path) == method["artifact_sha256"]
        windows = json.loads(path.read_text())["windows"]
        for phase,a,b in (("training",0,128),("online_sine",128,160)):
            for bank,bank_name in enumerate(("stage1","stage2")):
                for i in range(4):
                    start = 0 if a == 0 else windows[a-1]["filters_after"][bank][i]
                    previous = start
                    filtered,raw,rounding = F(0),0,F(0)
                    for w in windows[a:b]:
                        h = w["filters_after"][bank][i]
                        p = w[bank_name+"_products"][i]
                        filtered += F(h,4)
                        raw += p
                        rounding += F(h)-F(3*previous+4*p,4)
                        previous = h
                    boundary = 3*F(previous-start,4)
                    assert filtered == raw-boundary+rounding
                    audits.append({"case":case["name"],"phase":phase,"bank":bank_name,"gate_index":i,
                        "filtered_sum":filtered,"raw_sum":raw,"boundary_term":boundary,
                        "filter_rounding_sum":rounding,"identity_verified":True})
    write(directory/"filter_sum_audit.json",{"identities":len(audits),"audits":audits,
        "summary_sha256":digest(directory/"summary.json"),"source_sha256":{str(Path(__file__)):digest(Path(__file__))}})
    print(f"Exact filter cumulative-sum identities: {len(audits)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory",type=Path)
    run(parser.parse_args().directory.resolve())
