"""Check mapped Verilog connectivity/parameters after an XDC cleanup."""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import re

def normalize(path):
    text=path.read_text()
    text=re.sub(r'/\*.*?\*/|//[^\n]*','',text,flags=re.S)
    text=re.sub(r'\(\*.*?\*\)','',text,flags=re.S)
    return re.sub(r'\s+','',text)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('run',type=Path)
    args=parser.parse_args()
    paths=[args.run/'netlists/gu_review_funcsim.v',args.run/'netlists/gu_review_rechecked_funcsim.v']
    values=[normalize(p) for p in paths]
    result={'identical_mapped_verilog':values[0]==values[1], 'normalization':'comments, whitespace, and non-functional Verilog attributes removed; primitive types, ports and parameters retained', 'sha256':[hashlib.sha256(v.encode()).hexdigest() for v in values]}
    (args.run/'netlists/recheck_comparison.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    if not result['identical_mapped_verilog']:
        first=next((i for i,(a,b) in enumerate(zip(*values)) if a!=b),min(map(len,values)))
        print('First differing position:',first)
        print('Original:',values[0][max(0,first-120):first+250])
        print('Rechecked:',values[1][max(0,first-120):first+250])
        raise SystemExit(1)

if __name__=='__main__':main()
