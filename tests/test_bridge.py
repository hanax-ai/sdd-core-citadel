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
import harness.llm_clients as llm_clients
from harness.config import GATEKEEPER_KEY_ENV, get_env_summary, resolve_gatekeeper_provider

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


def test_correct_api_key_via_query_param_is_accepted_on_the_stream_route(client):
    # EventSource (used by the SSE stream route) can't set headers, so that
    # route -- and only that route -- must also accept the key as a `?key=`
    # query param. Consume a bit of the stream to prove the connection was
    # actually accepted (an unauthorized request never even opens the
    # stream/gets a 401 instead).
    with client.stream("GET", "/api/stream/does-not-exist", params={"key": "test-secret-key"}) as resp:
        assert resp.status_code == 200


def test_wrong_api_key_via_query_param_is_rejected_on_the_stream_route(client):
    resp = client.get("/api/stream/does-not-exist", params={"key": "nope"})
    assert resp.status_code == 401


def test_query_param_key_is_not_accepted_on_other_routes(client):
    # Regression test: the query-param fallback exists ONLY for the SSE
    # stream route. Every other route must stay header-only, even with no
    # header at all and a valid `?key=`.
    resp = client.get("/api/logs", params={"key": "test-secret-key"})
    assert resp.status_code == 401


def test_empty_header_does_not_fall_through_to_query_param_on_stream_route(client):
    # Regression test: an empty-but-present X-Bridge-Key header must not be
    # treated as "no header" -- the header takes precedence over the query
    # param even when it's the empty string, so this must still be rejected.
    resp = client.get(
        "/api/stream/does-not-exist",
        params={"key": "test-secret-key"},
        headers={"X-Bridge-Key": ""},
    )
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


# ------------------------------------------------------- provider-aware system probes
PROVIDER_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "MOONSHOT_API_KEY",
    "GATEKEEPER_PROVIDER",
)


def _pin_provider_env(monkeypatch, **values: str) -> None:
    """Set exactly the named provider env vars and delete every other one.

    Mandatory for these tests: harness.config.load_env_file() copies the repo's
    .env into os.environ at import time (and it does set GATEKEEPER_PROVIDER),
    so without this the assertions would silently describe the developer's
    machine instead of the case under test.
    """
    for name in PROVIDER_ENV_VARS:
        if name in values:
            monkeypatch.setenv(name, values[name])
        else:
            monkeypatch.delenv(name, raising=False)


def _health(client) -> dict:
    resp = client.get("/api/system/health", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    return resp.json()


def _status(client) -> dict:
    resp = client.get("/api/system/status", headers=AUTH_HEADERS)
    assert resp.status_code == 200
    return resp.json()


def test_health_is_ok_on_a_kimi_config_with_no_gemini_key(client, monkeypatch):
    # The false-alarm case: Kimi is serving the Gatekeeper and every key that
    # matters is present, so GEMINI_API_KEY must not be named at all.
    _pin_provider_env(
        monkeypatch,
        GATEKEEPER_PROVIDER="kimi",
        ANTHROPIC_API_KEY="sk-a",
        OPENAI_API_KEY="sk-o",
        MOONSHOT_API_KEY="sk-m",
    )
    body = _health(client)
    assert body["problems"] == []
    assert body["status"] == "ok"


def test_health_reports_the_moonshot_key_missing_on_a_kimi_config(client, monkeypatch):
    # The false-all-clear case, and the whole point of the probe: catching this
    # before a run starts instead of dying mid-Gatekeeper.
    _pin_provider_env(
        monkeypatch,
        GATEKEEPER_PROVIDER="kimi",
        ANTHROPIC_API_KEY="sk-a",
        OPENAI_API_KEY="sk-o",
    )
    body = _health(client)
    assert body["problems"] == ["missing provider keys: MOONSHOT_API_KEY"]
    assert body["status"] == "degraded"


def test_health_still_reports_the_gemini_key_missing_when_no_provider_is_set(client, monkeypatch):
    # Regression guard: an unset GATEKEEPER_PROVIDER is still Gemini, so a
    # missing GEMINI_API_KEY must still be a problem -- and a MOONSHOT_API_KEY
    # that no active provider needs must not be.
    _pin_provider_env(monkeypatch, ANTHROPIC_API_KEY="sk-a", OPENAI_API_KEY="sk-o")
    body = _health(client)
    assert body["problems"] == ["missing provider keys: GEMINI_API_KEY"]
    assert body["status"] == "degraded"


def test_health_is_ok_on_a_gemini_config_with_no_moonshot_key(client, monkeypatch):
    _pin_provider_env(
        monkeypatch,
        ANTHROPIC_API_KEY="sk-a",
        OPENAI_API_KEY="sk-o",
        GEMINI_API_KEY="sk-g",
    )
    body = _health(client)
    assert body["problems"] == []
    assert body["status"] == "ok"


def test_health_lists_every_missing_key_sorted(client, monkeypatch):
    _pin_provider_env(monkeypatch, GATEKEEPER_PROVIDER="kimi")
    body = _health(client)
    assert body["problems"] == [
        "missing provider keys: ANTHROPIC_API_KEY, MOONSHOT_API_KEY, OPENAI_API_KEY"
    ]


def test_health_reports_an_unknown_gatekeeper_provider_as_a_problem(client, monkeypatch):
    # Neither gatekeeper key is set here: an unrecognised provider means we
    # cannot know which key a run would need, so no key claim may be made --
    # only the misconfiguration itself, verbatim from the same error text a run
    # would raise.
    _pin_provider_env(
        monkeypatch,
        GATEKEEPER_PROVIDER="claude",
        ANTHROPIC_API_KEY="sk-a",
        OPENAI_API_KEY="sk-o",
    )
    body = _health(client)
    assert body["problems"] == [
        "GATEKEEPER_PROVIDER is set to 'claude'; valid values are 'gemini' (default) and 'kimi'."
    ]
    assert body["status"] == "degraded"


def test_health_appends_every_problem_kind_in_the_contract_order(client, monkeypatch, tmp_path):
    # The contract fixes the append order sqlite -> invalid provider -> missing
    # keys, but every other test here produces at most one entry, so a reorder
    # would ship undetected. This is the only case that builds all three at once.
    monkeypatch.setattr(bridge, "DB_PATH", str(tmp_path / "no-such-dir" / "citadel.sqlite3"))
    _pin_provider_env(monkeypatch, GATEKEEPER_PROVIDER="gpt")
    body = _health(client)
    assert body["problems"] == [
        f"sqlite unavailable at {bridge.DB_PATH}: unable to open database file",
        "GATEKEEPER_PROVIDER is set to 'gpt'; valid values are 'gemini' (default) and 'kimi'.",
        "missing provider keys: ANTHROPIC_API_KEY, OPENAI_API_KEY",
    ]
    # db_ok is what separates "down" from "degraded".
    assert body["database_ok"] is False
    assert body["status"] == "down"


def test_status_reports_kimi_as_the_gatekeeper_provider(client, monkeypatch):
    _pin_provider_env(
        monkeypatch,
        GATEKEEPER_PROVIDER="kimi",
        ANTHROPIC_API_KEY="sk-a",
        OPENAI_API_KEY="sk-o",
        MOONSHOT_API_KEY="sk-m",
    )
    body = _status(client)
    assert body["gatekeeper_provider"] == "kimi"
    assert body["moonshot_key_present"] is True
    # Compared against bridge.MODELS, not the DEFAULT_* constants: MODELS is an
    # import-time snapshot of MOONSHOT_MODEL/GEMINI_MODEL, which monkeypatch
    # cannot reach, so asserting the defaults would turn the suite red on the
    # override that is the whole reason moonshot_model is on the wire.
    assert body["moonshot_model"] == bridge.MODELS["moonshot"]
    # Raw facts, always reported: the inactive provider's pair is not hidden or
    # repurposed, it just is not what gatekeeper_provider points at.
    assert body["gemini_key_present"] is False
    assert body["gemini_model"] == bridge.MODELS["gemini"]


def test_status_reports_gemini_as_the_gatekeeper_provider_when_unset(client, monkeypatch):
    _pin_provider_env(
        monkeypatch,
        ANTHROPIC_API_KEY="sk-a",
        OPENAI_API_KEY="sk-o",
        GEMINI_API_KEY="sk-g",
    )
    body = _status(client)
    assert body["gatekeeper_provider"] == "gemini"
    assert body["gemini_key_present"] is True
    assert body["moonshot_key_present"] is False


def test_status_reads_the_gatekeeper_provider_live_not_at_import_time(client, monkeypatch):
    # bridge.MODELS is an import-time snapshot; gatekeeper_provider deliberately
    # is not. Flipping it twice within one process proves the endpoint re-reads
    # the env rather than reporting whatever was set when the module loaded --
    # something a single-direction assertion could pass by coincidence.
    _pin_provider_env(monkeypatch, GATEKEEPER_PROVIDER="kimi")
    assert _status(client)["gatekeeper_provider"] == "kimi"
    _pin_provider_env(monkeypatch, GATEKEEPER_PROVIDER="gemini")
    assert _status(client)["gatekeeper_provider"] == "gemini"


def test_status_reports_a_null_gatekeeper_provider_for_an_unknown_value(client, monkeypatch):
    # The endpoint that explains misconfiguration must not itself 500 on one.
    _pin_provider_env(monkeypatch, GATEKEEPER_PROVIDER="kim")
    body = _status(client)
    assert body["gatekeeper_provider"] is None


def test_status_keeps_every_pre_existing_field(client, monkeypatch):
    # The frontend reads these by name; adding fields is safe, renaming is not.
    _pin_provider_env(monkeypatch, ANTHROPIC_API_KEY="sk-a", OPENAI_API_KEY="sk-o")
    body = _status(client)
    assert set(body) == {
        "anthropic_key_present",
        "openai_key_present",
        "gemini_key_present",
        "anthropic_model",
        "openai_model",
        "gemini_model",
        "moonshot_key_present",
        "moonshot_model",
        "gatekeeper_provider",
    }
    assert body["anthropic_key_present"] is True
    assert body["openai_key_present"] is True
    assert body["anthropic_model"] == bridge.MODELS["anthropic"]
    assert body["openai_model"] == bridge.MODELS["openai"]


def test_health_keeps_every_pre_existing_field(client, monkeypatch):
    _pin_provider_env(
        monkeypatch,
        ANTHROPIC_API_KEY="sk-a",
        OPENAI_API_KEY="sk-o",
        GEMINI_API_KEY="sk-g",
    )
    body = _health(client)
    assert set(body) == {
        "status",
        "version",
        "uptime_s",
        "database_ok",
        "active_runs",
        "problems",
        "timestamp",
    }
    assert body["database_ok"] is True


async def test_the_health_probe_and_the_real_gatekeeper_router_cannot_drift(monkeypatch):
    """harness.config.resolve_gatekeeper_provider (what the probes report) and
    harness.llm_clients.call_gatekeeper (what a run actually calls) parse
    GATEKEEPER_PROVIDER independently. Nothing else would catch them disagreeing
    -- and a probe that disagrees with the router is worse than no probe -- so
    this pins them together across every parsing edge case, error text included.
    Lives here rather than in test_llm_clients.py because it exists to protect
    the bridge's health/status endpoints.
    """

    async def fake_gemini(system, user):
        return {"provider": "gemini"}

    async def fake_kimi(system, user):
        return {"provider": "kimi"}

    monkeypatch.setattr(llm_clients, "_call_gatekeeper_gemini", fake_gemini)
    monkeypatch.setattr(llm_clients, "_call_gatekeeper_kimi", fake_kimi)

    # The accepted provider names are DERIVED from GATEKEEPER_KEY_ENV rather
    # than hardcoded. That dict doubles as the validity set
    # resolve_gatekeeper_provider() enforces, while call_gatekeeper's validity
    # set is its own pair of hand-written branches; a third entry added to the
    # dict with no matching branch would otherwise make the health probe bless a
    # provider every run rejects -- the exact false all-clear this change kills.
    # (The reverse drift, a branch with no dict entry, cannot be enumerated from
    # here; it degrades to a false alarm rather than a false all-clear, and the
    # unrecognised-value cases below cover part of it.)
    raw_values: list[str | None] = [None, "", "   ", "gpt", "kim", "moonshot"]
    for provider in GATEKEEPER_KEY_ENV:
        raw_values += [provider, provider.upper(), f" {provider.capitalize()}\t"]

    for raw in raw_values:
        if raw is None:
            monkeypatch.delenv("GATEKEEPER_PROVIDER", raising=False)
        else:
            monkeypatch.setenv("GATEKEEPER_PROVIDER", raw)

        try:
            expected = resolve_gatekeeper_provider()
        except RuntimeError as exc:
            with pytest.raises(RuntimeError) as router_exc:
                await llm_clients.call_gatekeeper("system", "user")
            assert str(router_exc.value) == str(exc), f"error text diverged for {raw!r}"
        else:
            routed = await llm_clients.call_gatekeeper("system", "user")
            assert routed["provider"] == expected, f"routing diverged for {raw!r}"


def test_env_summary_is_provider_aware(monkeypatch):
    # harness.config.get_env_summary has the same mislabelling problem as the
    # bridge endpoints. Tested here rather than in test_config.py only because
    # that file is outside this change's scope.
    _pin_provider_env(monkeypatch, GATEKEEPER_PROVIDER="kimi", MOONSHOT_API_KEY="sk-m")
    summary = get_env_summary()
    assert summary["gatekeeper_provider"] == "kimi"
    assert summary["moonshot_key_set"] is True
    assert summary["gemini_key_set"] is False
    # runner.py --status reads these by name; they must keep existing.
    assert summary["anthropic_key_set"] is False
    assert summary["openai_key_set"] is False

    _pin_provider_env(monkeypatch, GATEKEEPER_PROVIDER="nope")
    assert get_env_summary()["gatekeeper_provider"] is None
