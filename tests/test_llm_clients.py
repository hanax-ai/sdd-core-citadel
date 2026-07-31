import json
from types import SimpleNamespace

import pytest

import harness.llm_clients as llm_clients


async def test_call_researcher_raises_without_anthropic_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        await llm_clients.call_researcher("system", "user")


async def test_call_builder_raises_without_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        await llm_clients.call_builder("system", "user")


async def test_call_gatekeeper_raises_without_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        await llm_clients.call_gatekeeper("system", "user")


def _make_fake_gemini_client(raw_text, usage_metadata=None):
    """Stand-in for google.genai.Client: .aio.models.generate_content returns a
    canned response object exposing .text and .usage_metadata, matching the
    real async SDK's response shape. .aio.aclose() records whether it ran."""
    response = SimpleNamespace(text=raw_text, usage_metadata=usage_metadata)

    async def generate_content(**kwargs):
        return response

    class FakeClient:
        instances = []

        def __init__(self, *args, **kwargs):
            self.aclose_called = False
            self.aio = SimpleNamespace(
                models=SimpleNamespace(generate_content=generate_content),
                aclose=self._aclose,
            )
            FakeClient.instances.append(self)

        async def _aclose(self):
            self.aclose_called = True

    return FakeClient


async def test_call_gatekeeper_null_findings_becomes_warning_fallback(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    raw_text = json.dumps({"findings": None})
    monkeypatch.setattr("google.genai.Client", _make_fake_gemini_client(raw_text))

    result = await llm_clients.call_gatekeeper("system", "user")

    assert len(result["findings"]) == 1
    assert result["findings"][0]["severity"] == "WARNING"
    assert "malformed findings" in result["findings"][0]["text"]


async def test_call_gatekeeper_string_findings_becomes_warning_fallback(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    raw_text = json.dumps({"findings": "not a list"})
    monkeypatch.setattr("google.genai.Client", _make_fake_gemini_client(raw_text))

    result = await llm_clients.call_gatekeeper("system", "user")

    assert len(result["findings"]) == 1
    assert result["findings"][0]["severity"] == "WARNING"
    assert "malformed findings" in result["findings"][0]["text"]


async def test_call_gatekeeper_rejects_whole_batch_on_one_malformed_item(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    raw_text = json.dumps(
        {
            "findings": [
                {"line": 1, "severity": "CRITICAL", "text": "well formed"},
                {"line": 2, "severity": "BOGUS", "text": "bad severity"},
            ]
        }
    )
    monkeypatch.setattr("google.genai.Client", _make_fake_gemini_client(raw_text))

    result = await llm_clients.call_gatekeeper("system", "user")

    assert len(result["findings"]) == 1
    assert result["findings"][0]["severity"] == "WARNING"
    assert "malformed findings" in result["findings"][0]["text"]


async def test_call_gatekeeper_valid_findings_pass_through_unchanged(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    valid_findings = [{"line": 5, "severity": "NOTE", "text": "fine"}]
    raw_text = json.dumps({"findings": valid_findings})
    usage_metadata = SimpleNamespace(prompt_token_count=10, candidates_token_count=20)
    fake_client_cls = _make_fake_gemini_client(raw_text, usage_metadata=usage_metadata)
    monkeypatch.setattr("google.genai.Client", fake_client_cls)

    result = await llm_clients.call_gatekeeper("system", "user")

    assert result["findings"] == valid_findings
    # Bonus: confirm the async transport was closed after the call completed.
    assert fake_client_cls.instances[-1].aclose_called is True
