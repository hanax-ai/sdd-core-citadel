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
DEFAULT_MOONSHOT_MODEL = "kimi-k3"
DEFAULT_TIMEOUT_SECONDS = 120

# Moonshot serves Kimi through an OpenAI-compatible endpoint, so the Gatekeeper's
# Kimi path reuses the openai SDK against this base URL instead of pulling in a
# fourth provider package.
MOONSHOT_BASE_URL = "https://api.moonshot.ai/v1"


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
    (response, fallback_fields), where fallback_fields splices straight into a
    caller's result dict and carries `fallback_reason` only on fallback.

    `request` is the provider's `_request(base_url, request_model, request_key)`
    closure. `error_cls` is the SDK exception type -- or tuple of types -- to
    catch. `is_quota(exc)`
    decides whether a caught exception is a quota/rate-limit condition worth
    falling back on (as opposed to any other provider error, which fails
    fast with no fallback attempt)."""
    try:
        return await request(None, model), {"fallback_used": False}
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
        return response, {"fallback_used": True, "fallback_reason": "quota_exceeded"}


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

    response, fallback_fields = await _call_with_fallback(
        _request,
        model=model,
        role="RESEARCHER",
        label="Amigo-Researcher (Anthropic)",
        error_cls=anthropic.AnthropicError,
        is_quota=lambda exc: isinstance(exc, anthropic.RateLimitError),
    )

    text = next((block.text for block in response.content if block.type == "text"), "")
    return {
        "text": text,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        **fallback_fields,
    }


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

    response, fallback_fields = await _call_with_fallback(
        _request,
        model=model,
        role="BUILDER",
        label="Amigo-Builder (OpenAI)",
        error_cls=openai.OpenAIError,
        is_quota=lambda exc: isinstance(exc, openai.RateLimitError),
    )

    return {
        "text": response.output_text or "",
        "input_tokens": response.usage.input_tokens if response.usage else 0,
        "output_tokens": response.usage.output_tokens if response.usage else 0,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        **fallback_fields,
    }


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


def _empty_review_findings() -> list[dict]:
    """Blocking finding for a completion that came back with no content.
    Degrading empty content to "{}" parses as zero findings, and zero findings
    means "the patch is clean" -- so a review that produced no output at all
    would approve an unreviewed patch. A merge gate must not fail open, which is
    why the empty-choices branch raises and the abnormal-finish branches block;
    this keeps the empty-content case in the same family. Shared by every
    Gatekeeper provider so the gate cannot fail open on one and closed on
    another."""
    return [
        {
            "line": 0,
            "severity": "WARNING",
            "text": (
                "Gatekeeper returned empty content, so the review produced no output "
                "and the patch has not been reviewed."
            ),
        }
    ]


def _parse_gatekeeper_findings(raw_text: str) -> list[dict]:
    """Turn a Gatekeeper model's raw JSON text into a validated findings list.
    Shared by every Gatekeeper provider so that swapping providers cannot change
    how malformed or unparseable review output is degraded."""
    try:
        parsed = json.loads(raw_text)
        findings = parsed.get("findings", [])
    except (json.JSONDecodeError, AttributeError):
        findings = [{"line": 0, "severity": "WARNING", "text": f"Gatekeeper returned unparseable output: {raw_text[:200]}"}]
    return _validate_findings(findings, raw_text)


async def _call_gatekeeper_gemini(system: str, user: str) -> dict:
    """Call the Gemini API for Amigo-Gatekeeper. Returns structured findings."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set; required for Amigo-Gatekeeper.")

    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types as genai_types
    import httpx

    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    resolved_model = model
    started = time.monotonic()

    async def _request(base_url: str | None, request_model: str, request_key: str | None = None):
        # Record the model the request actually went out with: on the fallback
        # path that is the fallback model, and the result has to attribute the
        # findings to the model that really produced them.
        nonlocal resolved_model
        resolved_model = request_model
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

    response, fallback_fields = await _call_with_fallback(
        _request,
        model=model,
        role="GATEKEEPER",
        label="Amigo-Gatekeeper (Gemini)",
        # genai's APIError subclasses Exception directly, so unlike the Anthropic
        # and OpenAI base classes it does not cover httpx transport failures.
        error_cls=(genai_errors.APIError, httpx.HTTPError),
        is_quota=_is_gemini_quota_error,
    )

    raw_text = response.text or ""
    if not raw_text.strip():
        findings = _empty_review_findings()
    else:
        findings = _parse_gatekeeper_findings(raw_text)

    usage = getattr(response, "usage_metadata", None)
    return {
        "text": raw_text,
        "findings": findings,
        # Which provider and model actually served this review, so a transcript
        # replayed under a different GATEKEEPER_PROVIDER still attributes its
        # findings correctly.
        "provider": "gemini",
        "model": resolved_model,
        "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
        "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        **fallback_fields,
    }


async def _call_gatekeeper_kimi(system: str, user: str) -> dict:
    """Call Moonshot's Kimi K3 for Amigo-Gatekeeper. Returns structured findings.
    Moonshot exposes an OpenAI-compatible surface but has no Responses API, so
    unlike call_builder this goes through chat.completions."""
    api_key = os.getenv("MOONSHOT_API_KEY")
    if not api_key:
        raise RuntimeError("MOONSHOT_API_KEY is not set; required for Amigo-Gatekeeper (Kimi).")

    import openai
    from openai import AsyncOpenAI

    model = os.getenv("MOONSHOT_MODEL", DEFAULT_MOONSHOT_MODEL)
    resolved_model = model
    started = time.monotonic()

    async def _request(base_url: str | None, request_model: str, request_key: str | None = None):
        # Record the model the request actually went out with: on the fallback
        # path that is the fallback model, and the result has to attribute the
        # findings to the model that really produced them.
        nonlocal resolved_model
        resolved_model = request_model
        # _call_with_fallback invokes the primary attempt as request(None, model),
        # so an unset base_url has to resolve to Moonshot here -- passing None
        # straight to AsyncOpenAI would send the primary call to OpenAI instead.
        client = AsyncOpenAI(
            api_key=request_key or api_key,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            base_url=base_url or MOONSHOT_BASE_URL,
        )
        try:
            # K3 rejects temperature/top_p/n/presence_penalty/frequency_penalty
            # outright -- sending them at all is an error, so they are omitted
            # rather than passed at their usual defaults.
            return await client.chat.completions.create(
                model=request_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                # K3 always reasons and bills reasoning as output tokens; the
                # effort default is "max", so "low" is set explicitly as a cost
                # control on a review call that only has to emit findings JSON.
                reasoning_effort="low",
                # Moonshot's rate-limit accounting reserves max_completion_tokens
                # rather than counting real output, and it defaults to 131072 --
                # pinning it to the Researcher's 4096 keeps the reservation sane.
                max_completion_tokens=4096,
                response_format={
                    "type": "json_schema",
                    "json_schema": {"name": "findings", "strict": True, "schema": FINDINGS_JSON_SCHEMA},
                },
            )
        finally:
            await client.close()

    response, fallback_fields = await _call_with_fallback(
        _request,
        model=model,
        role="GATEKEEPER",
        label="Amigo-Gatekeeper (Kimi)",
        error_cls=openai.OpenAIError,
        # Quota exhaustion, rate limiting and overload all surface as HTTP 429
        # on this API, which the openai SDK raises as RateLimitError.
        is_quota=lambda exc: isinstance(exc, openai.RateLimitError),
    )

    if not response.choices:
        # Degrading an empty choices list to "{}" the way a null message.content
        # degrades would report zero findings for a review that never ran, and a
        # merge gate must not fail open -- so this takes the module's other
        # option and raises a clear RuntimeError instead. Realistic on the
        # fallback path, which points at an arbitrary third-party server.
        raise RuntimeError("Amigo-Gatekeeper (Kimi) call failed: response contained no choices.")

    choice = response.choices[0]
    # The message also carries reasoning_content; only content holds the
    # schema-conforming findings JSON, so the reasoning trace is never read.
    raw_text = choice.message.content or ""
    finish_reason = getattr(choice, "finish_reason", None)
    if finish_reason == "length":
        # max_completion_tokens is shared by reasoning and content on K3, so a
        # cutoff usually yields invalid JSON that would otherwise degrade to a
        # blocking "unparseable output" finding naming the wrong cause. Still
        # blocking -- the review did not finish -- but now diagnosable.
        findings = [
            {
                "line": 0,
                "severity": "WARNING",
                "text": (
                    "Gatekeeper response was truncated by the max_completion_tokens limit "
                    f"(finish_reason=length), so the review is incomplete: {raw_text[:200]}"
                ),
            }
        ]
    elif finish_reason not in (None, "stop"):
        # Any other abnormal terminator means the review did not run to
        # completion. content_filter is the realistic one here: Moonshot can
        # filter on model *output*, not just input, so a Gatekeeper reviewing
        # security-sensitive code can be cut off mid-review. Left deliberately
        # broad so an unrecognised terminator blocks rather than being parsed
        # as if it were a finished review.
        findings = [
            {
                "line": 0,
                "severity": "WARNING",
                "text": (
                    f"Gatekeeper response ended abnormally (finish_reason={finish_reason}), "
                    f"so the review is incomplete: {raw_text[:200]}"
                ),
            }
        ]
    elif not raw_text.strip():
        # A normal-looking completion whose content is null or blank: the review
        # ran to "stop" but said nothing, which must block rather than parse as
        # an empty (== clean) findings list.
        findings = _empty_review_findings()
    else:
        findings = _parse_gatekeeper_findings(raw_text)

    return {
        "text": raw_text,
        "findings": findings,
        # Which provider and model actually served this review, so a transcript
        # replayed under a different GATEKEEPER_PROVIDER still attributes its
        # findings correctly.
        "provider": "kimi",
        "model": resolved_model,
        # Moonshot reports usage with the chat-completions field names.
        "input_tokens": response.usage.prompt_tokens if response.usage else 0,
        "output_tokens": response.usage.completion_tokens if response.usage else 0,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
        **fallback_fields,
    }


async def call_gatekeeper(system: str, user: str) -> dict:
    """Route Amigo-Gatekeeper to its configured provider. Gemini is the default
    and stays the default: Kimi is opt-in and only runs when GATEKEEPER_PROVIDER
    is explicitly set to "kimi", so an environment that never sets the variable
    keeps the exact behavior it had before Kimi existed. An empty or
    whitespace-only value counts as unset (a bare `GATEKEEPER_PROVIDER=` line or
    a docker-compose passthrough of an undefined variable) and keeps Gemini."""
    provider = os.getenv("GATEKEEPER_PROVIDER", "").strip().lower() or "gemini"
    if provider == "gemini":
        return await _call_gatekeeper_gemini(system, user)
    if provider == "kimi":
        return await _call_gatekeeper_kimi(system, user)
    raise RuntimeError(
        f"GATEKEEPER_PROVIDER is set to {provider!r}; valid values are 'gemini' (default) and 'kimi'."
    )
