"""CLI smoke tests for harness/runner.py."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("PYTHONUTF8", None)
    env.pop("PYTHONIOENCODING", None)
    return subprocess.run(
        [sys.executable, "harness/runner.py", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )


def test_status_flag_does_not_crash_on_default_console_encoding():
    result = _run_cli("--status")
    assert "UnicodeEncodeError" not in result.stderr
    assert result.returncode == 0, result.stderr


def test_bare_invocation_does_not_crash_on_default_console_encoding():
    result = _run_cli()
    assert "UnicodeEncodeError" not in result.stderr
    assert result.returncode == 0, result.stderr
