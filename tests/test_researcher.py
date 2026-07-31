import agents.researcher as researcher_module
from agents.researcher import AmigoResearcher


async def test_analyze_calls_researcher_and_returns_notes(monkeypatch):
    captured = {}

    async def fake_call_researcher(system, user):
        captured["system"] = system
        captured["user"] = user
        return {"text": "research notes here", "input_tokens": 10, "output_tokens": 5, "elapsed_ms": 100}

    monkeypatch.setattr(researcher_module, "call_researcher", fake_call_researcher)

    result = await AmigoResearcher().analyze("fix the bug", {"git_status": {"branch": "main"}})

    assert result == "research notes here"
    assert "fix the bug" in captured["user"]
    assert "git_status" in captured["user"]


async def test_analyze_sets_last_usage_after_call(monkeypatch):
    async def fake_call_researcher(system, user):
        return {"text": "notes", "input_tokens": 10, "output_tokens": 5, "elapsed_ms": 100}

    monkeypatch.setattr(researcher_module, "call_researcher", fake_call_researcher)

    researcher = AmigoResearcher()
    await researcher.analyze("fix the bug", {"git_status": {"branch": "main"}})

    assert researcher.last_usage == {"input_tokens": 10, "output_tokens": 5, "elapsed_ms": 100}
