"""Saved-history audit entry; preserves the exact executed analysis and failures."""
from pathlib import Path
import runpy

root = Path(__file__).resolve().parents[2]
runpy.run_path(str(root/'artifacts/research/mean_shadow_history_audit_20261015_v1/analyze_shadow_history_v3.py'), run_name='__main__')
