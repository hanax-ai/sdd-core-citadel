"""
Amigo-Researcher Agent (Claude)
Deep spec analysis and dependency research before code authoring begins.
"""

from __future__ import annotations
from harness.llm_clients import call_researcher

SYSTEM_PROMPT = (
    "You are Amigo-Researcher. Analyze the task and the provided evidence "
    "(git status, diff, file metadata) and produce concise research notes "
    "covering: relevant files, constraints, and open questions the builder "
    "should account for. Do not write code."
)


class AmigoResearcher:
    """Spec and dependency analyst."""

    async def analyze(self, task: str, evidence: dict) -> str:
        """Produce research notes for the given task and evidence."""
        user = f"Task: {task}\n\nEvidence:\n{evidence}"
        result = await call_researcher(SYSTEM_PROMPT, user)
        return result["text"]
