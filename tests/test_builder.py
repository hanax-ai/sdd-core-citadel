import agents.builder as builder_module
from agents.builder import AmigoBuilder


async def test_propose_patch_calls_builder_and_returns_patch(monkeypatch):
    captured = {}

    async def fake_call_builder(system, user):
        captured["user"] = user
        return {"text": "--- a/file.py\n+++ b/file.py\n", "input_tokens": 1, "output_tokens": 1, "elapsed_ms": 1}

    monkeypatch.setattr(builder_module, "call_builder", fake_call_builder)

    result = await AmigoBuilder().propose_patch("fix the bug", "notes text", {"git_status": {}})

    assert result.startswith("--- a/file.py")
    assert "fix the bug" in captured["user"]
    assert "notes text" in captured["user"]
    assert "None" in captured["user"]


async def test_propose_patch_formats_structured_prior_findings(monkeypatch):
    captured = {}

    async def fake_call_builder(system, user):
        captured["user"] = user
        return {"text": "patch", "input_tokens": 1, "output_tokens": 1, "elapsed_ms": 1}

    monkeypatch.setattr(builder_module, "call_builder", fake_call_builder)

    await AmigoBuilder().propose_patch(
        "fix the bug",
        "notes",
        {},
        prior_findings=[{"line": 12, "severity": "CRITICAL", "text": "missing null check"}],
    )

    assert "CRITICAL" in captured["user"]
    assert "line 12" in captured["user"]
    assert "missing null check" in captured["user"]


async def test_propose_patch_sets_last_usage_after_call(monkeypatch):
    async def fake_call_builder(system, user):
        return {"text": "patch", "input_tokens": 10, "output_tokens": 5, "elapsed_ms": 100}

    monkeypatch.setattr(builder_module, "call_builder", fake_call_builder)

    builder = AmigoBuilder()
    await builder.propose_patch("fix the bug", "notes text", {"git_status": {}})

    assert builder.last_usage == {"input_tokens": 10, "output_tokens": 5, "elapsed_ms": 100}
