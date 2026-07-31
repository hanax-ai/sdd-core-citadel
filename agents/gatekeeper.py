"""
Amigo-Gatekeeper Agent (Gemini Review Engine)
External code review formatting helper.
"""

from __future__ import annotations
import os

from harness.llm_clients import call_gatekeeper

SYSTEM_PROMPT = (
    "You are Amigo-Gatekeeper. Your job is to catch defects this specific "
    "patch introduces, or requirements from the stated task it fails to "
    "meet -- not to audit the surrounding codebase in general. Do not flag "
    "pre-existing conditions the patch doesn't touch or make worse, even "
    "if they're real issues, unless the task explicitly asked to fix them. "
    "If the patch correctly and completely accomplishes the stated task "
    "with no new defects, respond with exactly the word PASS. Otherwise "
    "respond with one finding per line, each a concrete, actionable "
    "problem introduced or left unresolved by this specific patch "
    "relative to the task."
)


class AmigoGatekeeper:
    """External Reviewer Helper for formatting review feedback."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

    def format_review_prompt(self, patch_summary: str, diff_text: str) -> str:
        """Format review prompt for external model inspection."""
        truncated_diff = diff_text[:3000]
        notice = "\n[...diff truncated...]\n" if len(diff_text) > 3000 else ""
        return (
            f"Review Request for Task: {patch_summary}\n\n"
            f"Diff Summary:\n{truncated_diff}{notice}"
        )

    def review(self, patch_text: str, evidence: dict) -> list[str]:
        """Review a proposed patch. Returns an empty list on pass."""
        user = self.format_review_prompt("Proposed patch under review", patch_text)
        user += f"\n\nEvidence:\n{evidence}"
        response = call_gatekeeper(SYSTEM_PROMPT, user)
        if response.strip().upper().startswith("PASS"):
            return []
        return [line.strip() for line in response.splitlines() if line.strip()]
