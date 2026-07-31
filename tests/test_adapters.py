"""Tests for tools/git_adapter.py and tools/linter_adapter.py."""
from __future__ import annotations

from pathlib import Path

from tools.git_adapter import get_git_status
from tools.linter_adapter import validate_json_syntax

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_get_git_status_on_this_repo():
    status = get_git_status(REPO_ROOT)
    assert status["is_git"] is True
    assert isinstance(status["modified_files"], list)


def test_validate_json_syntax_accepts_valid_json(tmp_path):
    sample = tmp_path / "sample.json"
    sample.write_text('{"name": "Amigo-Builder"}', encoding="utf-8")
    valid, msg = validate_json_syntax(sample)
    assert valid is True
    assert msg == "OK"


def test_validate_json_syntax_rejects_duplicate_keys(tmp_path):
    sample = tmp_path / "dup.json"
    sample.write_text('{"a": 1, "a": 2}', encoding="utf-8")
    valid, msg = validate_json_syntax(sample)
    assert valid is False
    assert "duplicate" in msg
