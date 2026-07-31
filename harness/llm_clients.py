"""
Amigo Agents LLM Provider Clients
Thin per-provider call wrappers for the Researcher, Builder, and
Gatekeeper agents. SDK imports are lazy so a missing provider package
never breaks the fail-fast key check for the other two providers.
"""

from __future__ import annotations
import os

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"
DEFAULT_OPENAI_MODEL = "gpt-5.3-codex"
DEFAULT_GEMINI_MODEL = "gemini-flash-latest"


def call_researcher(system: str, user: str) -> str:
    """Call the Anthropic API for Amigo-Researcher (Claude)."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set; required for Amigo-Researcher.")

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    model = os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
    try:
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.AnthropicError as exc:
        raise RuntimeError(f"Amigo-Researcher (Anthropic) call failed: {exc}") from exc
    return next((block.text for block in response.content if block.type == "text"), "")


def call_builder(system: str, user: str) -> str:
    """Call the OpenAI API for Amigo-Builder (Codex)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set; required for Amigo-Builder.")

    import openai
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    try:
        response = client.responses.create(
            model=model,
            instructions=system,
            input=user,
        )
    except openai.OpenAIError as exc:
        raise RuntimeError(f"Amigo-Builder (OpenAI) call failed: {exc}") from exc
    return response.output_text or ""


def call_gatekeeper(system: str, user: str) -> str:
    """Call the Gemini API for Amigo-Gatekeeper."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set; required for Amigo-Gatekeeper.")

    from google import genai
    from google.genai import errors as genai_errors

    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    try:
        response = client.models.generate_content(model=model, contents=f"{system}\n\n{user}")
    except genai_errors.APIError as exc:
        raise RuntimeError(f"Amigo-Gatekeeper (Gemini) call failed: {exc}") from exc
    return response.text or ""
