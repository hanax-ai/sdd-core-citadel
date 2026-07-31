import json
from types import SimpleNamespace
from typing import ClassVar

import pytest

import agents.gatekeeper as gatekeeper_module
import harness.llm_clients as llm_clients
from agents.gatekeeper import AmigoGatekeeper, has_blocking_findings


@pytest.fixture(autouse=True)
def pin_gatekeeper_provider(monkeypatch):
    """Pin the Gatekeeper to its default provider for every test in this module.
    harness.config.load_env_file() seeds .env into os.environ at import time, so
    a developer who uncomments GATEKEEPER_PROVIDER=kimi would otherwise route
    the Gemini-path tests below -- none of which set the variable -- to Moonshot.
    Tests that care about another value override this with monkeypatch.setenv,
    and the unset-default test deletes it with monkeypatch.delenv."""
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "gemini")


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
        instances: ClassVar[list] = []

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


async def test_call_gatekeeper_null_text_blocks_instead_of_reading_as_clean(monkeypatch):
    # google-genai returns response.text as None when the candidate carries no
    # text part. Degrading that to "{}" parses as zero findings, and zero
    # findings means "the patch is clean" -- so a review that produced no output
    # would clear an unreviewed patch through the merge gate.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr("google.genai.Client", _make_fake_gemini_client(None))

    result = await llm_clients.call_gatekeeper("system", "user")

    assert len(result["findings"]) == 1
    assert result["findings"][0]["severity"] == "WARNING"
    assert "no output" in result["findings"][0]["text"]
    assert has_blocking_findings(result["findings"]) is True


async def test_call_gatekeeper_reports_provider_and_model_gemini(monkeypatch):
    # Transcripts record only agent="Gatekeeper", so without this the provider
    # that actually reviewed a patch is unrecoverable after the fact.
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.setattr("google.genai.Client", _make_fake_gemini_client('{"findings": []}'))

    result = await llm_clients.call_gatekeeper("system", "user")
    assert result["provider"] == "gemini"
    assert result["model"] == "gemini-3.6-flash"

    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.6-pro")
    result = await llm_clients.call_gatekeeper("system", "user")
    assert result["provider"] == "gemini"
    assert result["model"] == "gemini-3.6-pro"


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
        instances: ClassVar[list] = []

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
        instances: ClassVar[list] = []

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


def _make_fake_gemini_fallback_client(*, fail_with=None, fallback_fail_with=None, raw_text='{"findings": []}'):
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
        if invocations["n"] == 2 and fallback_fail_with is not None:
            raise fallback_fail_with
        return response

    class FakeClient:
        instances: ClassVar[list] = []

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
    # The fallback served the review, so the attribution has to name the
    # fallback model rather than the primary one it never reached.
    assert result["provider"] == "gemini"
    assert result["model"] == "local-fallback-model"


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


async def test_call_gatekeeper_transport_error_becomes_contextual_runtime_error(monkeypatch):
    # genai's APIError does not cover httpx failures, so a connection error used
    # to escape as a raw httpx exception instead of the harness error format.
    import httpx

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_BASE_URL", "http://localhost:8083/v1")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_MODEL", "local-fallback-model")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_API_KEY", "fallback-key")
    fake_cls = _make_fake_gemini_fallback_client(fail_with=httpx.ConnectError("connection refused"))
    monkeypatch.setattr("google.genai.Client", fake_cls)

    with pytest.raises(RuntimeError) as excinfo:
        await llm_clients.call_gatekeeper("system", "user")

    assert "Amigo-Gatekeeper (Gemini) call failed" in str(excinfo.value)
    assert "connection refused" in str(excinfo.value)
    # A transport failure is not a quota condition, so no fallback is attempted.
    assert "quota" not in str(excinfo.value).lower()
    assert len(fake_cls.construct_calls) == 1


async def test_call_gatekeeper_fallback_transport_error_becomes_contextual_runtime_error(monkeypatch):
    import httpx

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_BASE_URL", "http://localhost:8083/v1")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_MODEL", "local-fallback-model")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_API_KEY", "fallback-key")
    fake_cls = _make_fake_gemini_fallback_client(
        fail_with=_gemini_quota_error(),
        fallback_fail_with=httpx.ConnectError("fallback unreachable"),
    )
    monkeypatch.setattr("google.genai.Client", fake_cls)

    with pytest.raises(RuntimeError) as excinfo:
        await llm_clients.call_gatekeeper("system", "user")

    assert "fallback endpoint also failed" in str(excinfo.value)
    assert "fallback unreachable" in str(excinfo.value)
    assert len(fake_cls.construct_calls) == 2


# --- Gatekeeper on Kimi K3 (Moonshot), opt-in via GATEKEEPER_PROVIDER=kimi ---
#
# Moonshot exposes an OpenAI-compatible endpoint, so the client is the same
# openai.AsyncOpenAI class the Builder uses -- but it speaks chat.completions
# (Moonshot has no Responses API) and its usage counters are named
# prompt_tokens/completion_tokens, hence a separate fake below.


def _make_fake_moonshot_client(
    *,
    fail_with=None,
    raw_text='{"findings": []}',
    reasoning_content=None,
    usage=None,
    finish_reason="stop",
    choices=None,
):
    """Stand-in for openai.AsyncOpenAI pointed at Moonshot: exposes
    .chat.completions.create and returns a response whose message carries both
    .content and .reasoning_content, mirroring real K3 output. Records
    constructor kwargs and fails on the *first* call only when `fail_with` is
    given, so one fake covers primary-fails-then-fallback-succeeds. `choices`
    overrides the whole choices list, for the empty-choices case."""
    construct_calls = []
    invocations = {"n": 0}
    message = SimpleNamespace(content=raw_text, reasoning_content=reasoning_content)
    if choices is None:
        choices = [SimpleNamespace(message=message, finish_reason=finish_reason)]
    response = SimpleNamespace(choices=choices, usage=usage)

    class FakeAsyncOpenAI:
        instances: ClassVar[list] = []

        def __init__(self, *args, **kwargs):
            construct_calls.append(kwargs)
            self.closed = False
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
            FakeAsyncOpenAI.instances.append(self)

        async def _create(self, **kwargs):
            self.create_kwargs = kwargs
            invocations["n"] += 1
            if invocations["n"] == 1 and fail_with is not None:
                raise fail_with
            return response

        async def close(self):
            self.closed = True

    FakeAsyncOpenAI.construct_calls = construct_calls
    return FakeAsyncOpenAI


def _moonshot_rate_limit_error(message="rate limit reached"):
    """Moonshot surfaces quota exhaustion, rate limiting and overload all as
    HTTP 429 (there is no 402 in this API), which the openai SDK raises as
    RateLimitError."""
    import httpx
    import openai

    request = httpx.Request("POST", "https://api.moonshot.ai/v1/chat/completions")
    body = {"error": {"type": "rate_limit_reached_error", "message": message}}
    response = httpx.Response(429, request=request, json=body)
    return openai.RateLimitError(message, response=response, body=body)


def _moonshot_auth_error(message="invalid api key"):
    import httpx
    import openai

    request = httpx.Request("POST", "https://api.moonshot.ai/v1/chat/completions")
    body = {"error": {"type": "invalid_authentication_error", "message": message}}
    response = httpx.Response(401, request=request, json=body)
    return openai.AuthenticationError(message, response=response, body=body)


async def test_call_gatekeeper_kimi_raises_without_moonshot_key(monkeypatch):
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.delenv("MOONSHOT_API_KEY", raising=False)

    with pytest.raises(RuntimeError) as excinfo:
        await llm_clients.call_gatekeeper("system", "user")

    assert str(excinfo.value) == "MOONSHOT_API_KEY is not set; required for Amigo-Gatekeeper (Kimi)."


async def test_call_gatekeeper_kimi_primary_call_targets_moonshot_base_url(monkeypatch):
    # _call_with_fallback invokes the primary attempt with base_url=None, so an
    # unresolved None would silently send the Gatekeeper to OpenAI's servers.
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    fake_cls = _make_fake_moonshot_client()
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    await llm_clients.call_gatekeeper("system", "user")

    assert fake_cls.construct_calls[0]["base_url"] == "https://api.moonshot.ai/v1"


async def test_call_gatekeeper_kimi_sends_a_request_timeout(monkeypatch):
    # Without an explicit timeout the openai SDK would still default to 600s,
    # far past the harness's own budget, so a stalled socket stalls the run.
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    fake_cls = _make_fake_moonshot_client()
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    await llm_clients.call_gatekeeper("system", "user")

    assert fake_cls.construct_calls[0]["timeout"] == llm_clients.DEFAULT_TIMEOUT_SECONDS


async def test_call_gatekeeper_kimi_sends_system_and_user_prompts_to_the_model(monkeypatch):
    # The whole review depends on the diff and the review instructions actually
    # reaching K3; nothing else in this file would notice if they did not.
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    fake_cls = _make_fake_moonshot_client()
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    await llm_clients.call_gatekeeper("review instructions", "the diff under review")

    messages = fake_cls.instances[-1].create_kwargs["messages"]
    assert {"role": "system", "content": "review instructions"} in messages
    assert {"role": "user", "content": "the diff under review"} in messages


async def test_call_gatekeeper_kimi_uses_default_model_and_env_override(monkeypatch):
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    monkeypatch.delenv("MOONSHOT_MODEL", raising=False)
    fake_cls = _make_fake_moonshot_client()
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    await llm_clients.call_gatekeeper("system", "user")
    assert fake_cls.instances[-1].create_kwargs["model"] == "kimi-k3"

    monkeypatch.setenv("MOONSHOT_MODEL", "kimi-k3-internal")
    await llm_clients.call_gatekeeper("system", "user")
    assert fake_cls.instances[-1].create_kwargs["model"] == "kimi-k3-internal"


async def test_call_gatekeeper_reports_provider_and_model_kimi(monkeypatch):
    # Transcripts record only agent="Gatekeeper", so without this the provider
    # that actually reviewed a patch is unrecoverable after the fact.
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    monkeypatch.delenv("MOONSHOT_MODEL", raising=False)
    fake_cls = _make_fake_moonshot_client()
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    result = await llm_clients.call_gatekeeper("system", "user")
    assert result["provider"] == "kimi"
    assert result["model"] == "kimi-k3"

    monkeypatch.setenv("MOONSHOT_MODEL", "kimi-k3-internal")
    result = await llm_clients.call_gatekeeper("system", "user")
    assert result["provider"] == "kimi"
    assert result["model"] == "kimi-k3-internal"


async def test_call_gatekeeper_kimi_omits_parameters_k3_rejects(monkeypatch):
    # K3 errors out if temperature/top_p/n/presence_penalty/frequency_penalty
    # are sent at all -- not just at non-default values.
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    fake_cls = _make_fake_moonshot_client()
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    await llm_clients.call_gatekeeper("system", "user")

    create_kwargs = fake_cls.instances[-1].create_kwargs
    for rejected in ("temperature", "top_p", "n", "presence_penalty", "frequency_penalty"):
        assert rejected not in create_kwargs


async def test_call_gatekeeper_kimi_sends_cost_and_limit_controls(monkeypatch):
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    fake_cls = _make_fake_moonshot_client()
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    await llm_clients.call_gatekeeper("system", "user")

    create_kwargs = fake_cls.instances[-1].create_kwargs
    # reasoning_effort defaults to "max" and reasoning tokens bill as output;
    # max_completion_tokens defaults to 131072 and is *reserved* against the
    # rate limit rather than billed on actual output.
    assert create_kwargs["reasoning_effort"] == "low"
    assert create_kwargs["max_completion_tokens"] == 4096


async def test_call_gatekeeper_kimi_requests_strict_findings_schema(monkeypatch):
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    fake_cls = _make_fake_moonshot_client()
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    await llm_clients.call_gatekeeper("system", "user")

    response_format = fake_cls.instances[-1].create_kwargs["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["strict"] is True
    assert response_format["json_schema"]["schema"] is llm_clients.FINDINGS_JSON_SCHEMA


async def test_call_gatekeeper_kimi_ignores_reasoning_content(monkeypatch):
    # K3 always emits reasoning tokens; message.reasoning_content sits next to
    # message.content and must never be parsed or concatenated.
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    content_findings = [{"line": 7, "severity": "NOTE", "text": "from content"}]
    decoy_findings = [{"line": 99, "severity": "CRITICAL", "text": "from reasoning"}]
    fake_cls = _make_fake_moonshot_client(
        raw_text=json.dumps({"findings": content_findings}),
        reasoning_content=json.dumps({"findings": decoy_findings}),
    )
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    result = await llm_clients.call_gatekeeper("system", "user")

    assert result["findings"] == content_findings
    assert "from reasoning" not in result["text"]


async def test_call_gatekeeper_kimi_valid_findings_pass_through_unchanged(monkeypatch):
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    valid_findings = [{"line": 5, "severity": "NOTE", "text": "fine"}]
    fake_cls = _make_fake_moonshot_client(raw_text=json.dumps({"findings": valid_findings}))
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    result = await llm_clients.call_gatekeeper("system", "user")

    assert result["findings"] == valid_findings


async def test_call_gatekeeper_kimi_malformed_findings_become_warning_fallback(monkeypatch):
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    raw_text = json.dumps({"findings": [{"line": 2, "severity": "BOGUS", "text": "bad severity"}]})
    fake_cls = _make_fake_moonshot_client(raw_text=raw_text)
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    result = await llm_clients.call_gatekeeper("system", "user")

    assert len(result["findings"]) == 1
    assert result["findings"][0]["severity"] == "WARNING"
    assert "malformed findings" in result["findings"][0]["text"]


async def test_call_gatekeeper_kimi_unparseable_text_becomes_warning_finding(monkeypatch):
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    fake_cls = _make_fake_moonshot_client(raw_text="not json at all")
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    result = await llm_clients.call_gatekeeper("system", "user")

    assert len(result["findings"]) == 1
    assert result["findings"][0]["severity"] == "WARNING"
    assert "unparseable output" in result["findings"][0]["text"]


async def test_call_gatekeeper_kimi_truncated_response_says_so(monkeypatch):
    # max_completion_tokens is shared by reasoning and content on K3, so a cutoff
    # is plausible and lands as invalid JSON. That would degrade to a blocking
    # WARNING blaming "unparseable output" -- the finding has to name the real
    # cause, or a token limit reads as a genuine review objection.
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    fake_cls = _make_fake_moonshot_client(raw_text='{"findings": [{"line": 1,', finish_reason="length")
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    result = await llm_clients.call_gatekeeper("system", "user")

    assert len(result["findings"]) == 1
    assert result["findings"][0]["severity"] == "WARNING"
    assert "truncated" in result["findings"][0]["text"]
    assert "unparseable" not in result["findings"][0]["text"]


async def test_call_gatekeeper_kimi_content_filtered_response_says_so(monkeypatch):
    # Moonshot can content-filter model *output*, not just input, so a Gatekeeper
    # reviewing security-sensitive code can be cut off mid-review. Without this
    # branch a filtered stop degrades to a WARNING blaming "unparseable output",
    # which reads as a real review objection rather than a failed review.
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    fake_cls = _make_fake_moonshot_client(raw_text="", finish_reason="content_filter")
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    result = await llm_clients.call_gatekeeper("system", "user")

    assert len(result["findings"]) == 1
    assert result["findings"][0]["severity"] == "WARNING"
    assert "content_filter" in result["findings"][0]["text"]
    assert "unparseable" not in result["findings"][0]["text"]


async def test_call_gatekeeper_kimi_unknown_finish_reason_blocks_rather_than_parsing(monkeypatch):
    # An unrecognised terminator must not be parsed as a finished review: a
    # well-formed empty findings list would otherwise read as "patch is clean".
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    fake_cls = _make_fake_moonshot_client(raw_text='{"findings": []}', finish_reason="some_future_reason")
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    result = await llm_clients.call_gatekeeper("system", "user")

    assert result["findings"] != []
    assert result["findings"][0]["severity"] == "WARNING"
    assert "some_future_reason" in result["findings"][0]["text"]


async def test_call_gatekeeper_kimi_empty_choices_raises_instead_of_indexerror(monkeypatch):
    # An HTTP 200 with no choices is realistic on the fallback path, which points
    # at an arbitrary third-party OpenAI-compatible server. Indexing it blindly
    # escapes as a raw IndexError; degrading it to "{}" would be worse still,
    # since a merge gate reporting zero findings for a review that never ran
    # fails open.
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    fake_cls = _make_fake_moonshot_client(choices=[])
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    with pytest.raises(RuntimeError) as excinfo:
        await llm_clients.call_gatekeeper("system", "user")

    assert "Amigo-Gatekeeper (Kimi) call failed" in str(excinfo.value)
    assert "no choices" in str(excinfo.value)


async def test_call_gatekeeper_kimi_null_content_blocks_instead_of_reading_as_clean(monkeypatch):
    # Distinct from the empty-choices case above: content is present but null on
    # an otherwise-normal completion. Degrading that to "{}" parses as zero
    # findings, and zero findings means "the patch is clean" -- so a review that
    # produced no output would clear an unreviewed patch through the merge gate.
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    fake_cls = _make_fake_moonshot_client(raw_text=None)
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    result = await llm_clients.call_gatekeeper("system", "user")

    assert len(result["findings"]) == 1
    assert result["findings"][0]["severity"] == "WARNING"
    assert "no output" in result["findings"][0]["text"]
    assert has_blocking_findings(result["findings"]) is True


async def test_call_gatekeeper_kimi_maps_token_usage_fields(monkeypatch):
    # Moonshot reports prompt_tokens/completion_tokens, not the Responses API's
    # input_tokens/output_tokens -- the decoys below fail the test if the wrong
    # field names are read.
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    usage = SimpleNamespace(prompt_tokens=13, completion_tokens=29, input_tokens=999, output_tokens=888)
    fake_cls = _make_fake_moonshot_client(usage=usage)
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    result = await llm_clients.call_gatekeeper("system", "user")

    assert result["input_tokens"] == 13
    assert result["output_tokens"] == 29


async def test_call_gatekeeper_kimi_missing_usage_yields_zero_tokens(monkeypatch):
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    fake_cls = _make_fake_moonshot_client(usage=None)
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    result = await llm_clients.call_gatekeeper("system", "user")

    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0


async def test_call_gatekeeper_kimi_closes_async_client(monkeypatch):
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    fake_cls = _make_fake_moonshot_client()
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    await llm_clients.call_gatekeeper("system", "user")

    assert fake_cls.instances[-1].closed is True


async def test_call_gatekeeper_kimi_closes_async_client_on_failure(monkeypatch):
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    monkeypatch.delenv("GATEKEEPER_FALLBACK_BASE_URL", raising=False)
    fake_cls = _make_fake_moonshot_client(fail_with=_moonshot_auth_error())
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    with pytest.raises(RuntimeError):
        await llm_clients.call_gatekeeper("system", "user")

    assert fake_cls.instances[-1].closed is True


async def test_call_gatekeeper_kimi_quota_error_no_fallback_raises_quota_specific_error(monkeypatch):
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    monkeypatch.delenv("GATEKEEPER_FALLBACK_BASE_URL", raising=False)
    monkeypatch.delenv("GATEKEEPER_FALLBACK_MODEL", raising=False)
    fake_cls = _make_fake_moonshot_client(fail_with=_moonshot_rate_limit_error())
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    with pytest.raises(RuntimeError, match=r"(?i)quota|rate[ -]limit"):
        await llm_clients.call_gatekeeper("system", "user")

    assert len(fake_cls.construct_calls) == 1


async def test_call_gatekeeper_kimi_quota_error_with_fallback_retries_and_marks_result(monkeypatch):
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_BASE_URL", "http://localhost:8083/v1")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_MODEL", "local-fallback-model")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_API_KEY", "fallback-key")
    valid_findings = [{"line": 1, "severity": "NOTE", "text": "from fallback"}]
    fake_cls = _make_fake_moonshot_client(
        fail_with=_moonshot_rate_limit_error(),
        raw_text=json.dumps({"findings": valid_findings}),
    )
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    result = await llm_clients.call_gatekeeper("system", "user")

    assert result["fallback_used"] is True
    assert result["fallback_reason"] == "quota_exceeded"
    assert result["findings"] == valid_findings
    assert len(fake_cls.construct_calls) == 2
    assert fake_cls.construct_calls[1]["base_url"] == "http://localhost:8083/v1"
    assert fake_cls.instances[-1].create_kwargs["model"] == "local-fallback-model"
    # The fallback served the review, so the attribution has to name the
    # fallback model rather than the primary one it never reached.
    assert result["provider"] == "kimi"
    assert result["model"] == "local-fallback-model"


async def test_call_gatekeeper_kimi_non_quota_error_does_not_trigger_fallback(monkeypatch):
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "test-key")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_BASE_URL", "http://localhost:8083/v1")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_MODEL", "local-fallback-model")
    fake_cls = _make_fake_moonshot_client(fail_with=_moonshot_auth_error())
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    with pytest.raises(RuntimeError) as excinfo:
        await llm_clients.call_gatekeeper("system", "user")

    assert "quota" not in str(excinfo.value).lower()
    assert len(fake_cls.construct_calls) == 1


async def test_call_gatekeeper_kimi_fallback_uses_fallback_api_key_not_primary(monkeypatch):
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "primary-key")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_BASE_URL", "http://localhost:8083/v1")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_MODEL", "local-fallback-model")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_API_KEY", "fallback-key")
    fake_cls = _make_fake_moonshot_client(fail_with=_moonshot_rate_limit_error())
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    result = await llm_clients.call_gatekeeper("system", "user")

    assert result["fallback_used"] is True
    assert len(fake_cls.construct_calls) == 2
    assert fake_cls.construct_calls[0]["api_key"] == "primary-key"
    assert fake_cls.construct_calls[1]["api_key"] == "fallback-key"
    assert fake_cls.construct_calls[1]["api_key"] != "primary-key"


async def test_call_gatekeeper_kimi_fallback_base_url_without_fallback_key_does_not_activate(monkeypatch):
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    monkeypatch.setenv("MOONSHOT_API_KEY", "primary-key")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_BASE_URL", "http://localhost:8083/v1")
    monkeypatch.setenv("GATEKEEPER_FALLBACK_MODEL", "local-fallback-model")
    monkeypatch.delenv("GATEKEEPER_FALLBACK_API_KEY", raising=False)
    fake_cls = _make_fake_moonshot_client(fail_with=_moonshot_rate_limit_error())
    monkeypatch.setattr("openai.AsyncOpenAI", fake_cls)

    with pytest.raises(RuntimeError, match=r"(?i)quota|rate[ -]limit"):
        await llm_clients.call_gatekeeper("system", "user")

    assert len(fake_cls.construct_calls) == 1


# --- GATEKEEPER_PROVIDER dispatch ---


def _patch_both_gatekeeper_providers(monkeypatch):
    """Wire fakes for both Gatekeeper providers with distinguishable findings,
    so a routing test can prove which one ran and that the other never was
    constructed."""
    gemini_cls = _make_fake_gemini_fallback_client(
        raw_text=json.dumps({"findings": [{"line": 1, "severity": "NOTE", "text": "from gemini"}]})
    )
    kimi_cls = _make_fake_moonshot_client(
        raw_text=json.dumps({"findings": [{"line": 1, "severity": "NOTE", "text": "from kimi"}]})
    )
    monkeypatch.setattr("google.genai.Client", gemini_cls)
    monkeypatch.setattr("openai.AsyncOpenAI", kimi_cls)
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-key")
    return gemini_cls, kimi_cls


async def test_call_gatekeeper_defaults_to_gemini_when_provider_unset(monkeypatch):
    # Gemini stays the default Gatekeeper provider: Kimi is strictly opt-in and
    # an environment that never sets GATEKEEPER_PROVIDER must not reach Moonshot.
    monkeypatch.delenv("GATEKEEPER_PROVIDER", raising=False)
    gemini_cls, kimi_cls = _patch_both_gatekeeper_providers(monkeypatch)

    result = await llm_clients.call_gatekeeper("system", "user")

    assert result["findings"][0]["text"] == "from gemini"
    assert len(gemini_cls.construct_calls) == 1
    assert len(kimi_cls.construct_calls) == 0


async def test_call_gatekeeper_provider_kimi_routes_to_kimi(monkeypatch):
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    gemini_cls, kimi_cls = _patch_both_gatekeeper_providers(monkeypatch)

    result = await llm_clients.call_gatekeeper("system", "user")

    assert result["findings"][0]["text"] == "from kimi"
    assert len(kimi_cls.construct_calls) == 1
    assert len(gemini_cls.construct_calls) == 0


async def test_call_gatekeeper_provider_ignores_case_and_surrounding_whitespace(monkeypatch):
    gemini_cls, kimi_cls = _patch_both_gatekeeper_providers(monkeypatch)

    monkeypatch.setenv("GATEKEEPER_PROVIDER", " KIMI ")
    kimi_result = await llm_clients.call_gatekeeper("system", "user")

    monkeypatch.setenv("GATEKEEPER_PROVIDER", " Gemini ")
    gemini_result = await llm_clients.call_gatekeeper("system", "user")

    assert kimi_result["findings"][0]["text"] == "from kimi"
    assert gemini_result["findings"][0]["text"] == "from gemini"
    assert len(kimi_cls.construct_calls) == 1
    assert len(gemini_cls.construct_calls) == 1


async def test_call_gatekeeper_empty_provider_falls_back_to_gemini(monkeypatch):
    # A bare `GATEKEEPER_PROVIDER=` line in .env, a docker-compose `- VAR`
    # passthrough of an undefined variable, or an empty CI env: value all set the
    # variable to "". .env.example promises the default provider in that case.
    gemini_cls, kimi_cls = _patch_both_gatekeeper_providers(monkeypatch)
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "")

    result = await llm_clients.call_gatekeeper("system", "user")

    assert result["findings"][0]["text"] == "from gemini"
    assert len(kimi_cls.construct_calls) == 0
    assert len(gemini_cls.construct_calls) == 1


async def test_call_gatekeeper_whitespace_provider_falls_back_to_gemini(monkeypatch):
    gemini_cls, kimi_cls = _patch_both_gatekeeper_providers(monkeypatch)
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "   ")

    result = await llm_clients.call_gatekeeper("system", "user")

    assert result["findings"][0]["text"] == "from gemini"
    assert len(kimi_cls.construct_calls) == 0
    assert len(gemini_cls.construct_calls) == 1


async def test_call_gatekeeper_unknown_provider_raises_naming_valid_values(monkeypatch):
    monkeypatch.setenv("GATEKEEPER_PROVIDER", "gpt")
    _patch_both_gatekeeper_providers(monkeypatch)

    with pytest.raises(RuntimeError) as excinfo:
        await llm_clients.call_gatekeeper("system", "user")

    message = str(excinfo.value)
    assert "GATEKEEPER_PROVIDER" in message
    assert "gemini" in message
    assert "kimi" in message


# --- Provider-independent Gatekeeper guarantees ---


async def test_call_gatekeeper_blank_content_blocks_identically_on_both_providers(monkeypatch):
    # A merge gate that fails open on one provider and closed on the other is
    # worse than either, because switching GATEKEEPER_PROVIDER silently changes
    # what "reviewed" means. Whitespace-only content is the case a `.strip()`-less
    # emptiness check would let through.
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("MOONSHOT_API_KEY", "moonshot-key")
    monkeypatch.setattr("google.genai.Client", _make_fake_gemini_client("   \n"))
    monkeypatch.setattr("openai.AsyncOpenAI", _make_fake_moonshot_client(raw_text="   \n"))

    monkeypatch.setenv("GATEKEEPER_PROVIDER", "gemini")
    gemini_result = await llm_clients.call_gatekeeper("system", "user")

    monkeypatch.setenv("GATEKEEPER_PROVIDER", "kimi")
    kimi_result = await llm_clients.call_gatekeeper("system", "user")

    assert has_blocking_findings(gemini_result["findings"]) is True
    assert gemini_result["findings"] == kimi_result["findings"]


async def test_gatekeeper_review_records_the_provider_that_served_it(monkeypatch):
    # AmigoGatekeeper.review() keeps returning bare findings, so the attribution
    # has to ride along on the instance the way last_usage already does.
    async def fake_call_gatekeeper(system, user):
        return {
            "text": "{}",
            "findings": [],
            "provider": "kimi",
            "model": "kimi-k3-internal",
            "input_tokens": 1,
            "output_tokens": 1,
            "elapsed_ms": 1,
        }

    monkeypatch.setattr(gatekeeper_module, "call_gatekeeper", fake_call_gatekeeper)
    gatekeeper = AmigoGatekeeper(api_key="unused")
    findings = await gatekeeper.review("diff text", {"git_status": {}})

    assert findings == []
    assert gatekeeper.last_provider == "kimi"
    assert gatekeeper.last_model == "kimi-k3-internal"


async def test_gatekeeper_review_leaves_attribution_unknown_when_result_omits_it(monkeypatch):
    # Nothing may assume the fields are present -- an unattributed result stays
    # unattributed rather than being credited to the configured provider, since
    # guessing the attribution is the defect this records.
    async def fake_call_gatekeeper(system, user):
        return {"text": "{}", "findings": [], "input_tokens": 1, "output_tokens": 1, "elapsed_ms": 1}

    monkeypatch.setattr(gatekeeper_module, "call_gatekeeper", fake_call_gatekeeper)
    gatekeeper = AmigoGatekeeper(api_key="unused")
    await gatekeeper.review("diff text", {"git_status": {}})

    assert gatekeeper.last_provider is None
    assert gatekeeper.last_model is None


# --- Moonshot Flavored JSON Schema (MFJS) compliance ---
#
# Moonshot validates response_format schemas server-side against MFJS, which
# rejects a subset of standard JSON Schema outright. The shared
# FINDINGS_JSON_SCHEMA is also handed to google-genai, so it has to stay inside
# the intersection of both dialects -- this guards against a future edit that
# adds a key one provider accepts and the other rejects.

MFJS_FORBIDDEN_KEYS = frozenset(
    {
        "title",
        "format",
        "$comment",
        "prefixItems",
        "unevaluatedItems",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minContains",
        "maxContains",
    }
)


def _walk_schema_keys(node):
    """Yield every mapping key in a JSON-schema-shaped structure. Property names
    are yielded too -- deliberately conservative, since MFJS-forbidden words are
    not plausible finding field names anyway."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _walk_schema_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_schema_keys(item)


def _walk_schema_refs(node):
    """Yield every $ref value in a JSON-schema-shaped structure."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            yield from _walk_schema_refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_schema_refs(item)


def test_findings_schema_uses_no_mfjs_forbidden_keys():
    used = set(_walk_schema_keys(llm_clients.FINDINGS_JSON_SCHEMA))

    assert not (used & MFJS_FORBIDDEN_KEYS)


def test_findings_schema_uses_no_external_refs():
    # MFJS resolves only local $defs references; external/HTTP $refs are rejected.
    # The current schema is written inline and contains no $ref at all, so the
    # loop below is vacuous today -- this is a forward-looking guard for a future
    # edit that introduces one. The check above it keeps the guard honest by
    # proving the walker really does surface a $ref when one exists.
    assert list(_walk_schema_refs({"properties": {"x": {"$ref": "https://example.com/s.json"}}})) == [
        "https://example.com/s.json"
    ]
    for ref in _walk_schema_refs(llm_clients.FINDINGS_JSON_SCHEMA):
        assert ref.startswith("#")
