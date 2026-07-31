from __future__ import annotations

import json

import harness.remediation_loop as remediation_loop
from harness.remediation_loop import run_collaboration_cycle


def _patch_agents(monkeypatch, findings_sequence):
    calls = {"analyze": 0, "propose": 0, "review": 0}

    def fake_analyze(self, task, evidence):
        calls["analyze"] += 1
        return "notes"

    def fake_propose(self, task, notes, evidence, prior_findings=None):
        calls["propose"] += 1
        return f"patch-{calls['propose']}"

    findings_iter = iter(findings_sequence)

    def fake_review(self, patch_text, evidence):
        calls["review"] += 1
        return next(findings_iter)

    monkeypatch.setattr(remediation_loop.AmigoResearcher, "analyze", fake_analyze)
    monkeypatch.setattr(remediation_loop.AmigoBuilder, "propose_patch", fake_propose)
    monkeypatch.setattr(remediation_loop.AmigoGatekeeper, "review", fake_review)
    return calls


def test_loop_passes_after_findings_then_empty(tmp_path, monkeypatch):
    calls = _patch_agents(monkeypatch, [["issue A"], ["issue B"], []])

    result = run_collaboration_cycle(tmp_path, "fix the bug", log_dir=tmp_path / "logs")

    assert result["verdict"] == "PASS"
    assert calls["analyze"] == 1
    assert calls["propose"] == 3
    assert calls["review"] == 3
    assert len(result["rounds"]) == 3
    assert result["rounds"][-1]["findings"] == []

    log_files = list((tmp_path / "logs").glob("*.json"))
    assert len(log_files) == 1
    logged = json.loads(log_files[0].read_text(encoding="utf-8"))
    assert logged["verdict"] == "PASS"
    assert len(logged["rounds"]) == 3


def test_loop_stops_at_max_rounds_when_findings_persist(tmp_path, monkeypatch):
    calls = _patch_agents(monkeypatch, [["issue A"], ["issue B"], ["issue C"]])

    result = run_collaboration_cycle(tmp_path, "fix the bug", log_dir=tmp_path / "logs")

    assert result["verdict"] == "UNRESOLVED"
    assert calls["propose"] == 3


def test_researcher_called_exactly_once(tmp_path, monkeypatch):
    calls = _patch_agents(monkeypatch, [[]])
    run_collaboration_cycle(tmp_path, "fix the bug", log_dir=tmp_path / "logs")
    assert calls["analyze"] == 1
