"""CLI smoke tests for harness/runner.py."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(*args: str, **env_overrides: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("PYTHONUTF8", None)
    env.pop("PYTHONIOENCODING", None)
    # Set rather than delete: harness.config.load_env_file() copies the repo's
    # .env in with setdefault, so an empty string is the only way to express
    # "this key is not configured" from out here.
    env.update(env_overrides)
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


def test_status_names_only_the_active_gatekeeper_provider_key():
    """--status is the CLI twin of /api/system/health and must not contradict it.

    It used to print an unconditional "Gemini Key: NOT SET" on a working Kimi
    config (false alarm) while never mentioning MOONSHOT_API_KEY at all (false
    all-clear -- the run then died mid-Gatekeeper after a green light).
    """
    result = _run_cli(
        "--status",
        GATEKEEPER_PROVIDER="kimi",
        MOONSHOT_API_KEY="sk-m",
        GEMINI_API_KEY="",
        ANTHROPIC_API_KEY="sk-a",
        OPENAI_API_KEY="sk-o",
    )
    assert result.returncode == 0, result.stderr
    assert "MOONSHOT_API_KEY" in result.stdout
    assert "Moonshot Key:  SET" in result.stdout
    assert "Gemini" not in result.stdout

    missing = _run_cli(
        "--status",
        GATEKEEPER_PROVIDER="kimi",
        MOONSHOT_API_KEY="",
        ANTHROPIC_API_KEY="sk-a",
        OPENAI_API_KEY="sk-o",
    )
    assert missing.returncode == 0, missing.stderr
    assert "Moonshot Key:  NOT SET" in missing.stdout


def test_status_defaults_to_gemini_and_flags_an_unrecognised_provider():
    default = _run_cli(
        "--status",
        GATEKEEPER_PROVIDER="",
        GEMINI_API_KEY="sk-g",
        ANTHROPIC_API_KEY="sk-a",
        OPENAI_API_KEY="sk-o",
    )
    assert default.returncode == 0, default.stderr
    assert "Gemini Key:    SET" in default.stdout
    assert "Moonshot" not in default.stdout

    typo = _run_cli("--status", GATEKEEPER_PROVIDER="kim")
    assert typo.returncode == 0, typo.stderr
    assert "UNRECOGNISED GATEKEEPER_PROVIDER" in typo.stdout
