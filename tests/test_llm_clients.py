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


# --- Quota/rate-limit fallback mechanism (RAID I15) ---
#
# Fake SDK client factories below record every constructor call's kwargs
# (so tests can confirm a fallback retry used a distinct base_url/model) and
# fail on the *first* underlying call only, when `fail_with` is given -- the
# second call (the fallback retry) always succeeds. This lets a single fake
# stand in for "primary fails, fallback succeeds" without caring whether the
# harness reuses one client instance or builds a second one for the retry.


def _make_fake_anthropic_client(*, fail_with=None, succeed_text="ok"):
    """Stand-in for anthropic.AsyncAnthropic."""
    construct_calls = []
    invocations = {"n": 0}

    class FakeAsyncAnthropic:
        instances = []

        def __init__(self, *args, **kwargs):
            construct_calls.append(kwargs)
            self.closed = False
            self.messages = SimpleNamespace(create=self._create)
            FakeAsyncAnthropic.instances.append(self)

        async def _create(self, **kwargs):
            self.create_kwargs = kwargs
            invocations["n"] += 1
            if invocations["n"] == 1 and fail_with is not None:
                raise fail_with
            block = SimpleNamespace(type="text", text=succeed_text)
            usage = SimpleNamespace(input_tokens=1, output_tokens=2)
            return SimpleNamespace(content=[block], usage=usage)

        async def close(self):
            self.closed = True

    FakeAsyncAnthropic.construct_calls = construct_calls
    return FakeAsyncAnthropic


def _anthropic_rate_limit_error(message="rate limited"):
    import anthropic
    import httpx

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(429, request=request, json={"error": {"type": "rate_limit_error", "message": message}})
    return anthropic.RateLimitError(
        message, response=response, body={"error": {"type": "rate_limit_error", "message": message}}
    )


def _anthropic_auth_error(message="invalid api key"):
    import anthropic
    import httpx

    request = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    response = httpx.Response(401, request=request, json={"error": {"type": "authentication_error", "message": message}})
    return anthropic.AuthenticationError(
        message, response=response, body={"error": {"type": "authentication_error", "message": message}}
    )


async def test_call_researcher_quota_error_no_fallback_raises_quota_specific_error(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.delenv("RESEARCHER_FALLBACK_BASE_URL", raising=False)
    monkeypatch.delenv("RESEARCHER_FALLBACK_MODEL", raising=False)
    fake_cls = _make_fake_anthropic_client(fail_with=_anthropic_rate_limit_error())
    monkeypatch.setattr("anthropic.AsyncAnthropic", fake_cls)

    with pytest.raises(RuntimeError, match=r"(?i)quota|rate[ -]limit"):
        await llm_clients.call_researcher("system", "user")

    assert len(fake_cls.construct_calls) == 1


async def test_call_researcher_quota_error_with_fallback_retries_and_marks_result(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("RESEARCHER_FALLBACK_BASE_URL", "http://localhost:8081/v1")
    monkeypatch.setenv("RESEARCHER_FALLBACK_MODEL", "local-fallback-model")
    monkeypatch.setenv("RESEARCHER_FALLBACK_API_KEY", "fallback-key")
    fake_cls = _make_fake_anthropic_client(fail_with=_anthropic_rate_limit_error(), succeed_text="fallback answer")
    monkeypatch.setattr("anthropic.AsyncAnthropic", fake_cls)

    result = await llm_clients.call_researcher("system", "user")

    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "quota_exceeded"
    assert result["text"] == "fallback answer"
    assert len(fake_cls.construct_calls) == 2
    assert fake_cls.construct_calls[1]["base_url"] == "http://localhost:8081/v1"
    assert fake_cls.instances[-1].create_kwargs["model"] == "local-fallback-model"


async def test_call_researcher_non_quota_error_does_not_trigger_fallback(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("RESEARCHER_FALLBACK_BASE_URL", "http://localhost:8081/v1")
    monkeypatch.setenv("RESEARCHER_FALLBACK_MODEL", "local-fallback-model")
    fake_cls = _make_fake_anthropic_client(fail_with=_anthropic_auth_error())
    monkeypatch.setattr("anthropic.AsyncAnthropic", fake_cls)

    with pytest.raises(RuntimeError) as excinfo:
        await llm_clients.call_researcher("system", "user")

    assert "quota" not in str(excinfo.value).lower()
    assert len(fake_cls.construct_calls) == 1


async def test_call_researcher_fallback_uses_fallback_api_key_not_primary(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "primary-key")
    monkeypatch.setenv("RESEARCHER_FALLBACK_BASE_URL", "http://localhost:8081/v1")
    monkeypatch.setenv("RESEARCHER_FALLBACK_MODEL", "local-fallback-model")
    monkeypatch.setenv("RESEARCHER_FALLBACK_API_KEY", "fallback-key")
    fake_cls = _make_fake_anthropic_client(fail_with=_anthropic_rate_limit_error(), succeed_text="fallback answer")
    monkeypatch.setattr("anthropic.AsyncAnthropic", fake_cls)

    result = await llm_clients.call_researcher("system", "user")

    assert result["fallback_used"] is True
    assert len(fake_cls.construct_calls) == 2
    assert fake_cls.construct_calls[0]["api_key"] == "primary-key"
    assert fake_cls.construct_calls[1]["api_key"] == "fallback-key"
    assert fake_cls.construct_calls[1]["api_key"] != "primary-key"


async def test_call_researcher_fallback_base_url_without_fallback_key_does_not_activate(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "primary-key")
    monkeypatch.setenv("RESEARCHER_FALLBACK_BASE_URL", "http://localhost:8081/v1")
    monkeypatch.setenv("RESEARCHER_FALLBACK_MODEL", "local-fallback-model")
    monkeypatch.delenv("RESEARCHER_FALLBACK_API_KEY", raising=False)
    fake_cls = _make_fake_anthropic_client(fail_with=_anthropic_rate_limit_error())
    monkeypatch.setattr("anthropic.AsyncAnthropic", fake_cls)

    with pytest.raises(RuntimeError, match=r"(?i)quota|rate[ -]limit"):
        await llm_clients.call_researcher("system", "user")

    assert len(fake_cls.construct_calls) == 1


def _make_fake_openai_client(*, fail_with=None, succeed_text="ok"):
    """Stand-in for openai.AsyncOpenAI."""
    construct_calls = []
    invocations = {"n": 0}

    class FakeAsyncOpenAI:
        instances = []

        def __init__(self, *args, **kwargs):
            construct_calls.append(kwargs)
            self.closed = False
            self.responses = SimpleNamespace(create=self._create)
            FakeAsyncOpenAI.instances.append(self)

        async def _create(self, **kwargs):
            self.create_kwargs = kwargs
            invocations["n"] += 1
            if invocations["n"] == 1 and fail_with is not None:
                raise fail_with
            usage = SimpleNamespace(input_tokens=3, output_tokens=4)
            return SimpleNamespace(output_text=succeed_text, usage=usage)

        async def close(self):
            self.closed = True

    FakeAsyncOpenAI.construct_calls = construct_calls
    return FakeAsyncOpenAI


def _openai_rate_limit_error(message="rate limited"):
    import httpx
    import openai

    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(429, request=request, json={"error": {"type": "insufficient_quota", "message": message}})
    return openai.RateLimitError(
        message, response=response, body={"error": {"type": "insufficient_quota", "message": message}}
    )


def _openai_auth_error(message="invalid api key"):
    import httpx
    import openai

    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(401, request=request, json={"error": {"type": "authentication_error", "message": message}})
    return openai.AuthenticationError(
        message, response=response, body={"error": {"type": "authentication_error", "message": message}}
    )


async def test_call_builder_quota_error_no_fallback_raises_quota_specific_error(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("BUILDER_FALLBACK_BASE_URL", raising=False)
    monkeypatch.delenv("BUILDER_FALLBACK_MODEL", raising=False)
    fake_cls = _make_fake_openai_client(fail_with=_openai_rate_limit_error())
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    with pytest.raises(RuntimeError, match=r"(?i)quota|rate[ -]limit"):
        await llm_clients.call_builder("system", "user")

    assert len(fake_cls.construct_calls) == 1


async def test_call_builder_quota_error_with_fallback_retries_and_marks_result(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("BUILDER_FALLBACK_BASE_URL", "http://localhost:8082/v1")
    monkeypatch.setenv("BUILDER_FALLBACK_MODEL", "local-fallback-model")
    monkeypatch.setenv("BUILDER_FALLBACK_API_KEY", "fallback-key")
    fake_cls = _make_fake_openai_client(fail_with=_openai_rate_limit_error(), succeed_text="fallback answer")
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    result = await llm_clients.call_builder("system", "user")

    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "quota_exceeded"
    assert result["text"] == "fallback answer"
    assert len(fake_cls.construct_calls) == 2
    assert fake_cls.construct_calls[1]["base_url"] == "http://localhost:8082/v1"
    assert fake_cls.instances[-1].create_kwargs["model"] == "local-fallback-model"


async def test_call_builder_non_quota_error_does_not_trigger_fallback(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("BUILDER_FALLBACK_BASE_URL", "http://localhost:8082/v1")
    monkeypatch.setenv("BUILDER_FALLBACK_MODEL", "local-fallback-model")
    fake_cls = _make_fake_openai_client(fail_with=_openai_auth_error())
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    with pytest.raises(RuntimeError) as excinfo:
        await llm_clients.call_builder("system", "user")

    assert "quota" not in str(excinfo.value).lower()
    assert len(fake_cls.construct_calls) == 1


async def test_call_builder_fallback_uses_fallback_api_key_not_primary(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "primary-key")
    monkeypatch.setenv("BUILDER_FALLBACK_BASE_URL", "http://localhost:8082/v1")
    monkeypatch.setenv("BUILDER_FALLBACK_MODEL", "local-fallback-model")
    monkeypatch.setenv("BUILDER_FALLBACK_API_KEY", "fallback-key")
    fake_cls = _make_fake_openai_client(fail_with=_openai_rate_limit_error(), succeed_text="fallback answer")
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    result = await llm_clients.call_builder("system", "user")

    assert result["fallback_used"] is True
    assert len(fake_cls.construct_calls) == 2
    assert fake_cls.construct_calls[0]["api_key"] == "primary-key"
    assert fake_cls.construct_calls[1]["api_key"] == "fallback-key"
    assert fake_cls.construct_calls[1]["api_key"] != "primary-key"


async def test_call_builder_fallback_base_url_without_fallback_key_does_not_activate(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "primary-key")
    monkeypatch.setenv("BUILDER_FALLBACK_BASE_URL", "http://localhost:8082/v1")
    monkeypatch.setenv("BUILDER_FALLBACK_MODEL", "local-fallback-model")
    monkeypatch.delenv("BUILDER_FALLBACK_API_KEY", raising=False)
    fake_cls = _make_fake_openai_client(fail_with=_openai_rate_limit_error())
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    with pytest.raises(RuntimeError, match=r"(?i)quota|rate[ -]limit"):
        await llm_clients.call_builder("system", "user")

    assert len(fake_cls.construct_calls) == 1


def _make_fake_gemini_fallback_client(*, fail_with=None, raw_text='{"findings": []}'):
    """Stand-in for google.genai.Client, geared toward the fallback tests:
    records constructor kwargs (to inspect http_options.base_url) and each
    generate_content call's kwargs (to inspect the model requested)."""
    construct_calls = []
    call_kwargs = []
    invocations = {"n": 0}
    response = SimpleNamespace(text=raw_text, usage_metadata=None)

    async def generate_content(**kwargs):
        call_kwargs.append(kwargs)
        invocations["n"] += 1
        if invocations["n"] == 1 and fail_with is not None:
            raise fail_with
        return response

    class FakeClient:
        instances = []

        def __init__(self, *args, **kwargs):
            construct_calls.append(kwargs)
            self.aclose_called = False
            self.aio = SimpleNamespace(
                models=SimpleNamespace(generate_content=generate_content),
                aclose=self._aclose,
            )
            FakeClient.instances.append(self)

        async def _aclose(self):
            self.aclose_called = True

    FakeClient.construct_calls = construct_calls
    FakeClient.call_kwargs = call_kwargs
    return FakeClient


def _gemini_quota_error(message="Quota exceeded for quota metric 'free_tier_requests'."):
    from google.genai import errors as genai_errors

    return genai_errors.ClientError(429, {"error": {"status": "RESOURCE_EXHAUSTED", "message": message}})


def _gemini_other_error(message="invalid request"):
    from google.genai import errors as genai_errors

    return genai_errors.ClientError(400, {"error": {"status": "INVALID_ARGUMENT", "message": message}})


async def test_call_gatekeeper_quota_error_no_fallback_raises_quota_specific_error(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GATEKEEPER_FALLBACK_BASE_URL", raising=False)
    monkeypatch.delenv("GATEKEEPER_FALLBACK_MODEL", raising=False)
    fake_cls = _make_fake_gemini_fallback_client(fail_with=_gemini_quota_error())
    monkeypatch.setattr("google.genai.Client", fake_cls)

    with pytest.raises(RuntimeError, match=r"(?i)quota|rate[ -]limit"):
        await llm_clients.call_gatekeeper("system", "user")

    assert len(fake_cls.construct_calls) == 1


async def test_call_gatekeeper_quota_error_with_fallback_retries_and_marks_result(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_BASE_URL", "http://localhost:8083/v1")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_MODEL", "local-fallback-model")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_API_KEY", "fallback-key")
    valid_findings = [{"line": 1, "severity": "NOTE", "text": "from fallback"}]
    raw_text = json.dumps({"findings": valid_findings})
    fake_cls = _make_fake_gemini_fallback_client(fail_with=_gemini_quota_error(), raw_text=raw_text)
    monkeypatch.setattr("google.genai.Client", fake_cls)

    result = await llm_clients.call_gatekeeper("system", "user")

    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "quota_exceeded"
    assert result["findings"] == valid_findings
    assert len(fake_cls.construct_calls) == 2
    assert fake_cls.construct_calls[1]["http_options"].base_url == "http://localhost:8083/v1"
    assert fake_cls.call_kwargs[-1]["model"] == "local-fallback-model"


async def test_call_gatekeeper_non_quota_error_does_not_trigger_fallback(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_BASE_URL", "http://localhost:8083/v1")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_MODEL", "local-fallback-model")
    fake_cls = _make_fake_gemini_fallback_client(fail_with=_gemini_other_error())
    monkeypatch.setattr("google.genai.Client", fake_cls)

    with pytest.raises(RuntimeError) as excinfo:
        await llm_clients.call_gatekeeper("system", "user")

    assert "quota" not in str(excinfo.value).lower()
    assert len(fake_cls.construct_calls) == 1


async def test_call_gatekeeper_fallback_uses_fallback_api_key_not_primary(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "primary-key")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_BASE_URL", "http://localhost:8083/v1")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_MODEL", "local-fallback-model")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_API_KEY", "fallback-key")
    valid_findings = [{"line": 1, "severity": "NOTE", "text": "from fallback"}]
    raw_text = json.dumps({"findings": valid_findings})
    fake_cls = _make_fake_gemini_fallback_client(fail_with=_gemini_quota_error(), raw_text=raw_text)
    monkeypatch.setattr("google.genai.Client", fake_cls)

    result = await llm_clients.call_gatekeeper("system", "user")

    assert result["fallback_used"] is True
    assert len(fake_cls.construct_calls) == 2
    assert fake_cls.construct_calls[0]["api_key"] == "primary-key"
    assert fake_cls.construct_calls[1]["api_key"] == "fallback-key"
    assert fake_cls.construct_calls[1]["api_key"] != "primary-key"


async def test_call_gatekeeper_fallback_base_url_without_fallback_key_does_not_activate(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "primary-key")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_BASE_URL", "http://localhost:8083/v1")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_MODEL", "local-fallback-model")
    monkeypatch.delenv("GATEKEEPER_FALLBACK_API_KEY", raising=False)
    fake_cls = _make_fake_gemini_fallback_client(fail_with=_gemini_quota_error())
    monkeypatch.setattr("google.genai.Client", fake_cls)

    with pytest.raises(RuntimeError, match=r"(?i)quota|rate[ -]limit"):
        await llm_clients.call_gatekeeper("system", "user")

    assert len(fake_cls.construct_calls) == 1
