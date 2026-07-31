"""
Amigo Agents LLM Provider Clients
Thin per-provider async call wrappers for the Researcher, Builder, and
Gatekeeper agents. SDK imports are lazy so a missing provider package
never breaks the fail-fast key check for the other two providers.
"""

from __future__ import annotations
import json
import os
import time

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"
DEFAULT_OPENAI_MODEL = "gpt-5.3-codex"
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
DEFAULT_TIMEOUT_SECONDS = 120


def _fallback_config(role: str) -> tuple[str | None, str | None, str | None]:
    """Read <ROLE>_FALLBACK_BASE_URL / <ROLE>_FALLBACK_MODEL / <ROLE>_FALLBACK_API_KEY
    from the environment. A fallback is only considered configured when all
    three are set -- returns (None, None, None) otherwise, which is this
    repo's default out-of-the-box behavior (no fallback vars in .env.example).
    Requiring a distinct fallback API key prevents the primary provider's real
    key from being sent to a fallback endpoint that may not be operated by the
    same trusted party (see RAID I15)."""
    base_url = os.getenv(f"{role}_FALLBACK_BASE_URL")
    model = os.getenv(f"{role}_FALLBACK_MODEL")
    fallback_key = os.getenv(f"{role}_FALLBACK_API_KEY")
    if not base_url or not model or not fallback_key:
        return None, None, None
    return base_url, model, fallback_key


def _is_gemini_quota_error(exc) -> bool:
    """Gemini's google.genai SDK has no dedicated RateLimitError class --
    quota/rate-limit exhaustion surfaces as an APIError (ClientError) with
    code 429 and status "RESOURCE_EXHAUSTED" (confirmed against a real
    exhausted-quota response; see RAID R1/I15)."""
    return getattr(exc, "code", None) == 429 or getattr(exc, "status", None) == "RESOURCE_EXHAUSTED"


async def _call_with_fallback(request, *, model: str, role: str, label: str, error_cls, is_quota):
    """Shared quota/rate-limit fallback flow used by all three provider clients:
    try the primary call; on a quota/rate-limit error, look up a per-role
    fallback base_url/model/key triple from the environment and retry once;
    raise a clear RuntimeError at every failure point. Returns
    (response, fallback_used).

    `request` is the provider's `_request(base_url, request_model, request_key)`
    closure. `error_cls` is the SDK exception type to catch. `is_quota(exc)`
    decides whether a caught exception is a quota/rate-limit condition worth
    falling back on (as opposed to any other provider error, which fails
    fast with no fallback attempt)."""
    try:
        return await request(None, model), False
    except error_cls as exc:
        if not is_quota(exc):
            raise RuntimeError(f"{label} call failed: {exc}") from exc
        fallback_base_url, fallback_model, fallback_key = _fallback_config(role)
        if not fallback_base_url:
            raise RuntimeError(
                f"{label} call failed: quota/rate-limit exceeded ({exc}); "
                f"no fallback configured (set {role}_FALLBACK_BASE_URL/{role}_FALLBACK_MODEL/"
                f"{role}_FALLBACK_API_KEY)."
            ) from exc
        try:
            response = await request(fallback_base_url, fallback_model, fallback_key)
        except error_cls as fallback_exc:
            raise RuntimeError(
                f"{label} call failed: quota/rate-limit exceeded ({exc}); "
                f"fallback endpoint also failed: {fallback_exc}"
            ) from fallback_exc
        return response, True


FINDINGS_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line": {
                        "type": "integer",
                        "description": "Line number the finding applies to, or 0 if not line-specific.",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["CRITICAL", "WARNING", "NOTE"],
                    },
                    "text": {"type": "string"},
                },
                "required": ["line", "severity", "text"],
            },
        },
    },
    "required": ["findings"],
}


async def call_researcher(system: str, user: str) -> dict:
    """Call the Anthropic API for Amigo-Researcher (Claude)."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set; required for Amigo-Researcher.")

    import anthropic

    model = os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
    started = time.monotonic()

    async def _request(base_url: str | None, request_model: str, request_key: str | None = None):
        client = anthropic.AsyncAnthropic(
            api_key=request_key or api_key, timeout=DEFAULT_TIMEOUT_SECONDS, base_url=base_url
        )
        try:
            return await client.messages.create(
                model=request_model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        finally:
            await client.close()

    response, fallback_used = await _call_with_fallback(
        _request,
        model=model,
        role="RESEARCHER",
        label="Amigo-Researcher (Anthropic)",
        error_cls=anthropic.AnthropicError,
        is_quota=lambda exc: isinstance(exc, anthropic.RateLimitError),
    )

    text = next((block.text for block in response.content if block.type == "text"), "")
    result = {
        "text": text,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "fallback_used": fallback_used,
    }
    if fallback_used:
        result["fallback_reason"] = "quota_exceeded"
    return result


async def call_builder(system: str, user: str) -> dict:
    """Call the OpenAI API for Amigo-Builder (Codex)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set; required for Amigo-Builder.")

    import openai
    from openai import AsyncOpenAI

    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    started = time.monotonic()

    async def _request(base_url: str | None, request_model: str, request_key: str | None = None):
        client = AsyncOpenAI(api_key=request_key or api_key, timeout=DEFAULT_TIMEOUT_SECONDS, base_url=base_url)
        try:
            return await client.responses.create(
                model=request_model,
                instructions=system,
                input=user,
            )
        finally:
            await client.close()

    response, fallback_used = await _call_with_fallback(
        _request,
        model=model,
        role="BUILDER",
        label="Amigo-Builder (OpenAI)",
        error_cls=openai.OpenAIError,
        is_quota=lambda exc: isinstance(exc, openai.RateLimitError),
    )

    result = {
        "text": response.output_text or "",
        "input_tokens": response.usage.input_tokens if response.usage else 0,
        "output_tokens": response.usage.output_tokens if response.usage else 0,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "fallback_used": fallback_used,
    }
    if fallback_used:
        result["fallback_reason"] = "quota_exceeded"
    return result


def _validate_findings(findings, raw_text: str) -> list[dict]:
    """Validate Gatekeeper findings shape; degrade to a blocking WARNING finding
    on any mismatch instead of crashing or silently passing bad data through."""
    fallback = [
        {
            "line": 0,
            "severity": "WARNING",
            "text": f"Gatekeeper returned malformed findings (validation failed): {raw_text[:200]}",
        }
    ]
    if not isinstance(findings, list):
        return fallback
    for item in findings:
        if not isinstance(item, dict):
            return fallback
        if not isinstance(item.get("line"), int):
            return fallback
        if item.get("severity") not in {"CRITICAL", "WARNING", "NOTE"}:
            return fallback
        if not isinstance(item.get("text"), str):
            return fallback
    return findings


async def call_gatekeeper(system: str, user: str) -> dict:
    """Call the Gemini API for Amigo-Gatekeeper. Returns structured findings."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set; required for Amigo-Gatekeeper.")

    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types as genai_types

    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    started = time.monotonic()

    async def _request(base_url: str | None, request_model: str, request_key: str | None = None):
        client = genai.Client(
            api_key=request_key or api_key,
            http_options=genai_types.HttpOptions(timeout=DEFAULT_TIMEOUT_SECONDS * 1000, base_url=base_url),
        )
        try:
            return await client.aio.models.generate_content(
                model=request_model,
                contents=f"{system}\n\n{user}",
                config=genai_types.GenerateContentConfig(
                    thinking_config=genai_types.ThinkingConfig(thinking_level="HIGH"),
                    response_mime_type="application/json",
                    response_schema=FINDINGS_JSON_SCHEMA,
                ),
            )
        finally:
            await client.aio.aclose()

    response, fallback_used = await _call_with_fallback(
        _request,
        model=model,
        role="GATEKEEPER",
        label="Amigo-Gatekeeper (Gemini)",
        error_cls=genai_errors.APIError,
        is_quota=_is_gemini_quota_error,
    )

    raw_text = response.text or "{}"
    try:
        parsed = json.loads(raw_text)
        findings = parsed.get("findings", [])
    except (json.JSONDecodeError, AttributeError):
        findings = [{"line": 0, "severity": "WARNING", "text": f"Gatekeeper returned unparseable output: {raw_text[:200]}"}]
    findings = _validate_findings(findings, raw_text)

    usage = getattr(response, "usage_metadata", None)
    result = {
        "text": raw_text,
        "findings": findings,
        "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
        "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        "fallback_used": fallback_used,
    }
    if fallback_used:
        result["fallback_reason"] = "quota_exceeded"
    return result
