from __future__ import annotations

import os
import time

# BRIDGE_API_KEY is read at module import time (same pattern as bridge.py's
# other env-configured constants), so it must be set before `harness.bridge`
# is first imported.
os.environ["BRIDGE_API_KEY"] = "test-secret-key"

import pytest
from fastapi.testclient import TestClient

import harness.bridge as bridge

AUTH_HEADERS = {"X-Bridge-Key": "test-secret-key"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(bridge, "DB_PATH", str(tmp_path / "test_citadel.sqlite3"))
    monkeypatch.setattr(bridge, "TARGET_DIR", str(tmp_path.resolve()))
    monkeypatch.setenv("BRIDGE_ALLOWED_TARGET_DIRS", str(tmp_path.resolve()))
    bridge.RUNS.clear()
    with TestClient(bridge.app) as c:
        yield c


def _wait_for_run_to_finish(run_id: str, timeout: float = 5.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        run = bridge.RUNS.get(run_id)
        if run is not None and run.finished:
            return run
        time.sleep(0.02)
    raise AssertionError(f"run {run_id} did not finish within {timeout}s")


# --------------------------------------------------------------------------- auth
def test_missing_api_key_is_rejected(client):
    resp = client.post("/api/run-task", json={"task": "do something"})
    assert resp.status_code == 401


def test_wrong_api_key_is_rejected(client):
    resp = client.post(
        "/api/run-task",
        json={"task": "do something"},
        headers={"X-Bridge-Key": "nope"},
    )
    assert resp.status_code == 401


def test_correct_api_key_is_accepted_on_a_read_route(client):
    resp = client.get("/api/logs", headers=AUTH_HEADERS)
    assert resp.status_code == 200


def test_correct_api_key_via_query_param_is_accepted(client):
    # EventSource (used by the SSE stream route) can't set headers, so the
    # bridge must also accept the key as a `?key=` query param.
    resp = client.get("/api/logs", params={"key": "test-secret-key"})
    assert resp.status_code == 200


def test_wrong_api_key_via_query_param_is_rejected(client):
    resp = client.get("/api/logs", params={"key": "nope"})
    assert resp.status_code == 401


# --------------------------------------------------------------- target_dir allowlist
def test_target_dir_outside_allowlist_is_rejected(client, tmp_path):
    outside = tmp_path.parent / "definitely-outside-allowlist"
    outside.mkdir(exist_ok=True)
    resp = client.post(
        "/api/run-task",
        json={"task": "do something", "target_dir": str(outside)},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "TARGET_NOT_ALLOWED"


def test_target_dir_that_does_not_exist_but_is_inside_allowlist_is_rejected(client, tmp_path):
    missing = tmp_path / "does-not-exist"
    resp = client.post(
        "/api/run-task",
        json={"task": "do something", "target_dir": str(missing)},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "BAD_TARGET"


def test_propose_only_guard_rejects_write_requests(client, tmp_path):
    resp = client.post(
        "/api/run-task",
        json={"task": "do something", "target_dir": str(tmp_path), "write": True},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "WRITE_REJECTED"


# ------------------------------------------------------------- real wiring + events
def _fake_run_collaboration_cycle_factory(captured_kwargs):
    async def fake_run_collaboration_cycle(**kwargs):
        captured_kwargs.update(kwargs)
        on_event = kwargs["on_event"]
        run_id = kwargs["run_id"]
        on_event(
            {
                "type": "stage_change",
                "run_id": run_id,
                "timestamp": "2026-01-01T00:00:00",
                "stage": "COLLECTING_EVIDENCE",
            }
        )
        on_event(
            {
                "type": "agent_message",
                "run_id": run_id,
                "timestamp": "2026-01-01T00:00:00",
                "agent": "Researcher",
                "message_type": "RESEARCH_NOTES",
                "content": "notes",
            }
        )
        on_event(
            {
                "type": "token_metric",
                "run_id": run_id,
                "timestamp": "2026-01-01T00:00:00",
                "agent": "Researcher",
                "input_tokens": 10,
                "output_tokens": 5,
                "elapsed_ms": 100,
            }
        )
        on_event(
            {
                "type": "agent_message",
                "run_id": run_id,
                "timestamp": "2026-01-01T00:00:00",
                "agent": "Gatekeeper",
                "round": 1,
                "message_type": "AUDIT_FINDINGS",
                "findings": [],
            }
        )
        on_event(
            {
                "type": "token_metric",
                "run_id": run_id,
                "timestamp": "2026-01-01T00:00:00",
                "agent": "Gatekeeper",
                "round": 1,
                "input_tokens": 20,
                "output_tokens": 8,
                "elapsed_ms": 200,
            }
        )
        on_event(
            {
                "type": "run_complete",
                "run_id": run_id,
                "timestamp": "2026-01-01T00:00:00",
                "verdict": "PASS",
                "rounds_total": 1,
                "patch_text": "diff --git a/x b/x\n+hello\n",
            }
        )
        return {
            "run_id": run_id,
            "task": kwargs["task_description"],
            "git_status": "clean",
            "verdict": "PASS",
            "patch_text": "diff --git a/x b/x\n+hello\n",
            "log_path": "logs/fake.json",
            "rounds": [{"round": 1, "patch_text": "diff --git a/x b/x\n+hello\n", "findings": []}],
        }

    return fake_run_collaboration_cycle


def test_run_task_calls_real_harness_with_correct_args(client, tmp_path, monkeypatch):
    captured_kwargs = {}
    monkeypatch.setattr(bridge, "run_collaboration_cycle", _fake_run_collaboration_cycle_factory(captured_kwargs))

    resp = client.post(
        "/api/run-task",
        json={"task": "fix the bug", "target_dir": str(tmp_path)},
        headers=AUTH_HEADERS,
    )
    assert resp.status_code == 200
    run_id = resp.json()["run_id"]
    assert resp.json()["status"] == "started"

    _wait_for_run_to_finish(run_id)

    assert captured_kwargs["task_description"] == "fix the bug"
    assert captured_kwargs["run_id"] == run_id
    assert captured_kwargs["target_dir"] == tmp_path.resolve()
    assert callable(captured_kwargs["on_event"])


def test_events_land_in_transcript_in_their_real_shape(client, tmp_path, monkeypatch):
    captured_kwargs = {}
    monkeypatch.setattr(bridge, "run_collaboration_cycle", _fake_run_collaboration_cycle_factory(captured_kwargs))

    resp = client.post(
        "/api/run-task",
        json={"task": "fix the bug", "target_dir": str(tmp_path)},
        headers=AUTH_HEADERS,
    )
    run_id = resp.json()["run_id"]
    _wait_for_run_to_finish(run_id)

    transcript_resp = client.get(f"/api/logs/{run_id}", headers=AUTH_HEADERS)
    assert transcript_resp.status_code == 200
    body = transcript_resp.json()

    assert body["verdict"] == "PASS"
    assert body["patch_text"] == "diff --git a/x b/x\n+hello\n"

    event_types = [e["type"] for e in body["events"]]
    assert event_types == [
        "stage_change",
        "agent_message",
        "token_metric",
        "agent_message",
        "token_metric",
        "run_complete",
    ]

    # Field names/values must be the real harness contract, verbatim --
    # not renamed (no `ts`, real message_type values, real severity field
    # names on token_metric).
    token_events = [e["payload"] for e in body["events"] if e["type"] == "token_metric"]
    assert token_events[0]["input_tokens"] == 10
    assert token_events[0]["output_tokens"] == 5
    assert token_events[0]["elapsed_ms"] == 100
    assert "timestamp" in token_events[0]
    assert "ts" not in token_events[0]

    findings_event = next(e["payload"] for e in body["events"] if e["type"] == "agent_message" and e["payload"].get("message_type") == "AUDIT_FINDINGS")
    assert findings_event["findings"] == []
    assert findings_event["agent"] == "Gatekeeper"

    # runs table UPDATE must set patch_text + tokens_total (sum of every
    # token_metric event for this run: 10+5 + 20+8 = 43).
    logs_resp = client.get("/api/logs", headers=AUTH_HEADERS)
    row = next(r for r in logs_resp.json() if r["run_id"] == run_id)
    assert row["tokens_total"] == 43
    assert row["verdict"] == "PASS"


def test_harness_exception_produces_error_event_not_a_silent_crash(client, tmp_path, monkeypatch):
    async def fake_raises(**kwargs):
        on_event = kwargs["on_event"]
        on_event(
            {
                "type": "stage_change",
                "run_id": kwargs["run_id"],
                "timestamp": "2026-01-01T00:00:00",
                "stage": "COLLECTING_EVIDENCE",
            }
        )
        raise RuntimeError("GEMINI_API_KEY is not set; required for Amigo-Gatekeeper.")

    monkeypatch.setattr(bridge, "run_collaboration_cycle", fake_raises)

    resp = client.post(
        "/api/run-task",
        json={"task": "fix the bug", "target_dir": str(tmp_path)},
        headers=AUTH_HEADERS,
    )
    run_id = resp.json()["run_id"]
    _wait_for_run_to_finish(run_id)

    transcript_resp = client.get(f"/api/logs/{run_id}", headers=AUTH_HEADERS)
    body = transcript_resp.json()

    error_events = [e["payload"] for e in body["events"] if e["type"] == "error"]
    assert len(error_events) == 1
    assert "GEMINI_API_KEY" in error_events[0]["message"]
    assert body["verdict"] == "ERROR"

    logs_resp = client.get("/api/logs", headers=AUTH_HEADERS)
    row = next(r for r in logs_resp.json() if r["run_id"] == run_id)
    assert row["verdict"] == "ERROR"
