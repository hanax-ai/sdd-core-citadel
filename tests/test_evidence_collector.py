from __future__ import annotations

import harness.evidence_collector as ec


def _fake_git_status(target_dir):
    return {"is_git": True, "branch": "main", "modified_count": 0, "modified_files": []}


def test_git_diff_truncation_flag_true_when_diff_exceeds_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "get_git_status", _fake_git_status)
    monkeypatch.setattr(ec, "get_git_diff", lambda target_dir: "x" * 2500)
    evidence = ec.collect_task_evidence(tmp_path)
    assert evidence["git_diff_truncated"] is True
    assert len(evidence["git_diff_summary"]) == 2000


def test_git_diff_truncation_flag_false_when_diff_short(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "get_git_status", _fake_git_status)
    monkeypatch.setattr(ec, "get_git_diff", lambda target_dir: "short diff")
    evidence = ec.collect_task_evidence(tmp_path)
    assert evidence["git_diff_truncated"] is False
