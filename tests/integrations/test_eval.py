"""
Keeps the deterministic evaluator (`evals/capture_fetch.py`) from bit-rotting: runs it
as a subprocess and asserts a clean exit. The script makes its own throwaway store, so
this needs no fixtures.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_capture_fetch_evaluator_passes():
    result = subprocess.run(
        [sys.executable, "-m", "evals.capture_fetch"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "checks passed" in result.stdout
