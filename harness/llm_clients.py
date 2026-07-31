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


def _fallback_config(role: str) -> tuple[str | None, str | None]:
    """Read <ROLE>_FALLBACK_BASE_URL / <ROLE>_FALLBACK_MODEL from the
    environment. A fallback is only considered configured when both are
    set -- returns (None, None) otherwise, which is this repo's default
    out-of-the-box behavior (no fallback vars in .env.example)."""
    base_url = os.getenv(f"{role}_FALLBACK_BASE_URL")
    model = os.getenv(f"{role}_FALLBACK_MODEL")
    if not base_url or not model:
        return None, None
    return base_url, model


def _is_gemini_quota_error(exc) -> bool:
    """Gemini's google.genai SDK has no dedicated RateLimitError class --
    quota/rate-limit exhaustion surfaces as an APIError (ClientError) with
    code 429 and status "RESOURCE_EXHAUSTED" (confirmed against a real
    exhausted-quota response; see RAID R1/I15)."""
    return getattr(exc, "code", None) == 429 or getattr(exc, "status", None) == "RESOURCE_EXHAUSTED"


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

    async def _request(base_url: str | None, request_model: str):
        client = anthropic.AsyncAnthropic(api_key=api_key, timeout=DEFAULT_TIMEOUT_SECONDS, base_url=base_url)
        try:
            return await client.messages.create(
                model=request_model,
                max_tokens=4096,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        finally:
            await client.close()

    fallback_used = False
    try:
        response = await _request(None, model)
    except anthropic.RateLimitError as exc:
        fallback_base_url, fallback_model = _fallback_config("RESEARCHER")
        if not fallback_base_url:
            raise RuntimeError(
                f"Amigo-Researcher (Anthropic) call failed: quota/rate-limit exceeded ({exc}); "
                "no fallback configured (set RESEARCHER_FALLBACK_BASE_URL/RESEARCHER_FALLBACK_MODEL)."
            ) from exc
        try:
            response = await _request(fallback_base_url, fallback_model)
        except anthropic.AnthropicError as fallback_exc:
            raise RuntimeError(
                f"Amigo-Researcher (Anthropic) call failed: quota/rate-limit exceeded ({exc}); "
                f"fallback endpoint also failed: {fallback_exc}"
            ) from fallback_exc
        fallback_used = True
    except anthropic.AnthropicError as exc:
        raise RuntimeError(f"Amigo-Researcher (Anthropic) call failed: {exc}") from exc

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

    async def _request(base_url: str | None, request_model: str):
        client = AsyncOpenAI(api_key=api_key, timeout=DEFAULT_TIMEOUT_SECONDS, base_url=base_url)
        try:
            return await client.responses.create(
                model=request_model,
                instructions=system,
                input=user,
            )
        finally:
            await client.close()

    fallback_used = False
    try:
        response = await _request(None, model)
    except openai.RateLimitError as exc:
        fallback_base_url, fallback_model = _fallback_config("BUILDER")
        if not fallback_base_url:
            raise RuntimeError(
                f"Amigo-Builder (OpenAI) call failed: quota/rate-limit exceeded ({exc}); "
                "no fallback configured (set BUILDER_FALLBACK_BASE_URL/BUILDER_FALLBACK_MODEL)."
            ) from exc
        try:
            response = await _request(fallback_base_url, fallback_model)
        except openai.OpenAIError as fallback_exc:
            raise RuntimeError(
                f"Amigo-Builder (OpenAI) call failed: quota/rate-limit exceeded ({exc}); "
                f"fallback endpoint also failed: {fallback_exc}"
            ) from fallback_exc
        fallback_used = True
    except openai.OpenAIError as exc:
        raise RuntimeError(f"Amigo-Builder (OpenAI) call failed: {exc}") from exc

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

    async def _request(base_url: str | None, request_model: str):
        client = genai.Client(
            api_key=api_key,
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

    fallback_used = False
    try:
        response = await _request(None, model)
    except genai_errors.APIError as exc:
        if not _is_gemini_quota_error(exc):
            raise RuntimeError(f"Amigo-Gatekeeper (Gemini) call failed: {exc}") from exc
        fallback_base_url, fallback_model = _fallback_config("GATEKEEPER")
        if not fallback_base_url:
            raise RuntimeError(
                f"Amigo-Gatekeeper (Gemini) call failed: quota/rate-limit exceeded ({exc}); "
                "no fallback configured (set GATEKEEPER_FALLBACK_BASE_URL/GATEKEEPER_FALLBACK_MODEL)."
            ) from exc
        try:
            response = await _request(fallback_base_url, fallback_model)
        except genai_errors.APIError as fallback_exc:
            raise RuntimeError(
                f"Amigo-Gatekeeper (Gemini) call failed: quota/rate-limit exceeded ({exc}); "
                f"fallback endpoint also failed: {fallback_exc}"
            ) from fallback_exc
        fallback_used = True

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
