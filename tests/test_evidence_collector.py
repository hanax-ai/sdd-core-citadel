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


def test_syntax_check_flags_bad_python(tmp_path):
    bad = tmp_path / "broken.py"
    bad.write_text("def broken(:\n    pass\n", encoding="utf-8")
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[bad])
    assert evidence["file_evidence"][0]["syntax_valid"] is False


def test_syntax_check_passes_good_python(tmp_path):
    good = tmp_path / "ok.py"
    good.write_text("def ok():\n    return 1\n", encoding="utf-8")
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[good])
    assert evidence["file_evidence"][0]["syntax_valid"] is True
    assert evidence["file_evidence"][0]["syntax_error"] == "OK"


def test_syntax_check_not_performed_marker_for_unknown_suffix(tmp_path):
    other = tmp_path / "notes.txt"
    other.write_text("hello", encoding="utf-8")
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[other])
    assert evidence["file_evidence"][0]["syntax_valid"] is True
    assert evidence["file_evidence"][0]["syntax_error"] == "NOT_CHECKED"
