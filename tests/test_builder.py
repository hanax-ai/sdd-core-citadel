import agents.builder as builder_module
from agents.builder import AmigoBuilder


def test_propose_patch_calls_builder_and_returns_patch(monkeypatch):
    captured = {}

    def fake_call_builder(system, user):
        captured["user"] = user
        return "--- a/file.py\n+++ b/file.py\n"

    monkeypatch.setattr(builder_module, "call_builder", fake_call_builder)

    result = AmigoBuilder().propose_patch("fix the bug", "notes text", {"git_status": {}})

    assert result.startswith("--- a/file.py")
    assert "fix the bug" in captured["user"]
    assert "notes text" in captured["user"]
    assert "None" in captured["user"]  # no prior findings on round 1


def test_propose_patch_includes_prior_findings(monkeypatch):
    captured = {}

    def fake_call_builder(system, user):
        captured["user"] = user
        return "patch"

    monkeypatch.setattr(builder_module, "call_builder", fake_call_builder)

    AmigoBuilder().propose_patch(
        "fix the bug", "notes", {}, prior_findings=["missing null check"]
    )

    assert "missing null check" in captured["user"]
