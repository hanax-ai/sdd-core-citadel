"""
Amigo-Gatekeeper Agent (Gemini Review Engine)
External code review formatting helper.
"""

from __future__ import annotations
import os


class AmigoGatekeeper:
    """External Reviewer Helper for formatting review feedback."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

    def format_review_prompt(self, patch_summary: str, diff_text: str) -> str:
        """Format review prompt for external model inspection."""
        return (
            f"Review Request for Task: {patch_summary}\n\n"
            f"Diff Summary:\n{diff_text[:3000]}\n"
        )
