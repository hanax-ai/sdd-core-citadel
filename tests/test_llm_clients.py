import pytest

import harness.llm_clients as llm_clients


def test_call_researcher_raises_without_anthropic_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        llm_clients.call_researcher("system", "user")


def test_call_builder_raises_without_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        llm_clients.call_builder("system", "user")


def test_call_gatekeeper_raises_without_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        llm_clients.call_gatekeeper("system", "user")
