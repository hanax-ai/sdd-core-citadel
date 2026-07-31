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

    client = anthropic.AsyncAnthropic(api_key=api_key)
    model = os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
    started = time.monotonic()
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.AnthropicError as exc:
        raise RuntimeError(f"Amigo-Researcher (Anthropic) call failed: {exc}") from exc
    text = next((block.text for block in response.content if block.type == "text"), "")
    return {
        "text": text,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


async def call_builder(system: str, user: str) -> dict:
    """Call the OpenAI API for Amigo-Builder (Codex)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set; required for Amigo-Builder.")

    import openai
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    started = time.monotonic()
    try:
        response = await client.responses.create(
            model=model,
            instructions=system,
            input=user,
        )
    except openai.OpenAIError as exc:
        raise RuntimeError(f"Amigo-Builder (OpenAI) call failed: {exc}") from exc
    return {
        "text": response.output_text or "",
        "input_tokens": response.usage.input_tokens if response.usage else 0,
        "output_tokens": response.usage.output_tokens if response.usage else 0,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


async def call_gatekeeper(system: str, user: str) -> dict:
    """Call the Gemini API for Amigo-Gatekeeper. Returns structured findings."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set; required for Amigo-Gatekeeper.")

    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types as genai_types

    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    started = time.monotonic()
    try:
        response = await client.aio.models.generate_content(
            model=model,
            contents=f"{system}\n\n{user}",
            config=genai_types.GenerateContentConfig(
                thinking_config=genai_types.ThinkingConfig(thinking_level="HIGH"),
                response_mime_type="application/json",
                response_schema=FINDINGS_JSON_SCHEMA,
            ),
        )
    except genai_errors.APIError as exc:
        raise RuntimeError(f"Amigo-Gatekeeper (Gemini) call failed: {exc}") from exc

    raw_text = response.text or "{}"
    try:
        parsed = json.loads(raw_text)
        findings = parsed.get("findings", [])
    except (json.JSONDecodeError, AttributeError):
        findings = [{"line": 0, "severity": "WARNING", "text": f"Gatekeeper returned unparseable output: {raw_text[:200]}"}]

    usage = getattr(response, "usage_metadata", None)
    return {
        "text": raw_text,
        "findings": findings,
        "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
        "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }
