import agents.researcher as researcher_module
from agents.researcher import AmigoResearcher


def test_analyze_calls_researcher_and_returns_notes(monkeypatch):
    captured = {}

    def fake_call_researcher(system, user):
        captured["system"] = system
        captured["user"] = user
        return "research notes here"

    monkeypatch.setattr(researcher_module, "call_researcher", fake_call_researcher)

    result = AmigoResearcher().analyze("fix the bug", {"git_status": {"branch": "main"}})

    assert result == "research notes here"
    assert "fix the bug" in captured["user"]
    assert "git_status" in captured["user"]
