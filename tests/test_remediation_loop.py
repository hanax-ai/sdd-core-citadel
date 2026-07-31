from __future__ import annotations

import json

import harness.remediation_loop as remediation_loop
from harness.remediation_loop import run_collaboration_cycle


def _patch_agents(monkeypatch, findings_sequence):
    calls = {"analyze": 0, "propose": 0, "review": 0}

    async def fake_analyze(self, task, evidence):
        calls["analyze"] += 1
        return "notes"

    async def fake_propose(self, task, notes, evidence, prior_findings=None):
        calls["propose"] += 1
        return f"patch-{calls['propose']}"

    findings_iter = iter(findings_sequence)

    async def fake_review(self, patch_text, evidence):
        calls["review"] += 1
        return next(findings_iter)

    monkeypatch.setattr(remediation_loop.AmigoResearcher, "analyze", fake_analyze)
    monkeypatch.setattr(remediation_loop.AmigoBuilder, "propose_patch", fake_propose)
    monkeypatch.setattr(remediation_loop.AmigoGatekeeper, "review", fake_review)
    return calls


async def test_loop_passes_when_only_note_findings_remain(tmp_path, monkeypatch):
    calls = _patch_agents(
        monkeypatch,
        [
            [{"line": 1, "severity": "CRITICAL", "text": "a"}],
            [{"line": 1, "severity": "WARNING", "text": "b"}],
            [{"line": 1, "severity": "NOTE", "text": "c"}],
        ],
    )

    result = await run_collaboration_cycle(tmp_path, "fix the bug", log_dir=tmp_path / "logs")

    assert result["verdict"] == "PASS"
    assert calls["analyze"] == 1
    assert calls["propose"] == 3
    assert len(result["rounds"]) == 3

    log_files = list((tmp_path / "logs").glob("*.json"))
    assert len(log_files) == 1
    logged = json.loads(log_files[0].read_text(encoding="utf-8"))
    assert logged["verdict"] == "PASS"


async def test_loop_stops_at_max_rounds_when_blocking_findings_persist(tmp_path, monkeypatch):
    calls = _patch_agents(
        monkeypatch,
        [
            [{"line": 1, "severity": "CRITICAL", "text": "a"}],
            [{"line": 1, "severity": "CRITICAL", "text": "b"}],
            [{"line": 1, "severity": "WARNING", "text": "c"}],
        ],
    )

    result = await run_collaboration_cycle(tmp_path, "fix the bug", log_dir=tmp_path / "logs")

    assert result["verdict"] == "UNRESOLVED"
    assert calls["propose"] == 3


async def test_researcher_called_exactly_once(tmp_path, monkeypatch):
    calls = _patch_agents(monkeypatch, [[]])
    await run_collaboration_cycle(tmp_path, "fix the bug", log_dir=tmp_path / "logs")
    assert calls["analyze"] == 1


async def test_on_event_callback_receives_stage_and_completion_events(tmp_path, monkeypatch):
    _patch_agents(monkeypatch, [[]])
    events = []

    await run_collaboration_cycle(
        tmp_path,
        "fix the bug",
        log_dir=tmp_path / "logs",
        run_id="run_test_1",
        on_event=events.append,
    )

    event_types = [e["type"] for e in events]
    assert "stage_change" in event_types
    assert "agent_message" in event_types
    assert "run_complete" in event_types
    assert all(e.get("run_id") == "run_test_1" for e in events)


async def test_file_named_in_task_is_read_into_evidence(tmp_path, monkeypatch):
    target = tmp_path / "harness"
    target.mkdir()
    (target / "config.py").write_text("DEFAULT_TARGET_DIR = 'real value'\n", encoding="utf-8")

    captured_evidence = {}

    async def fake_analyze(self, task, evidence):
        captured_evidence.update(evidence)
        return "notes"

    async def fake_propose(self, *a, **k):
        return "patch"

    async def fake_review(self, *a, **k):
        return []

    monkeypatch.setattr(remediation_loop.AmigoResearcher, "analyze", fake_analyze)
    monkeypatch.setattr(remediation_loop.AmigoBuilder, "propose_patch", fake_propose)
    monkeypatch.setattr(remediation_loop.AmigoGatekeeper, "review", fake_review)

    await run_collaboration_cycle(
        tmp_path,
        "Add a comment above the assignment in harness/config.py",
        log_dir=tmp_path / "logs",
    )

    paths = [entry["path"] for entry in captured_evidence["file_evidence"]]
    assert any("config.py" in p for p in paths)
    contents = [entry["content"] for entry in captured_evidence["file_evidence"]]
    assert any("real value" in c for c in contents)
