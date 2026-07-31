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
    "meet -- not to audit the surrounding codebase in general. "
    "Classify every observation by severity: "
    "CRITICAL (the patch is broken or actively harmful), "
    "WARNING (a real defect the patch introduces or fails to address that "
    "should block merging), or "
    "NOTE (a pre-existing condition, worth mentioning but out of scope for "
    "this task and should NOT block merging). "
    "Return your findings as the structured JSON object the schema "
    "requires. An empty findings list means the patch is clean."
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
            f"Diff format note: lines starting with '+' are being ADDED by "
            f"this patch. Lines with no leading '+' or '-' are unchanged "
            f"pre-existing context shown only for orientation -- they are "
            f"NOT part of this patch and were not introduced by it.\n\n"
            f"Diff Summary:\n{truncated_diff}{notice}"
        )

    async def review(self, patch_text: str, evidence: dict) -> list[dict]:
        """Review a proposed patch. Returns a list of structured findings (possibly empty)."""
        user = self.format_review_prompt("Proposed patch under review", patch_text)
        user += f"\n\nEvidence:\n{evidence}"
        result = await call_gatekeeper(SYSTEM_PROMPT, user)
        return result["findings"]


def has_blocking_findings(findings: list[dict]) -> bool:
    """CRITICAL and WARNING findings block; NOTE findings don't."""
    return any(f.get("severity") in ("CRITICAL", "WARNING") for f in findings)
