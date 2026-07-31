"""
Amigo-Builder Agent (Codex / OpenAI)
Proposes a text patch for a task. Never writes files -- output is
reviewed by Amigo-Gatekeeper and applied by a human.
"""

from __future__ import annotations
from harness.llm_clients import call_builder

SYSTEM_PROMPT = (
    "You are Amigo-Builder. Given a task, research notes, evidence, and "
    "(on remediation rounds) prior reviewer findings, propose a unified "
    "diff patch that accomplishes the task. Output only the patch, no "
    "prose."
)


class AmigoBuilder:
    """Code patch proposer. Output is a text diff, never applied automatically."""

    def propose_patch(
        self,
        task: str,
        notes: str,
        evidence: dict,
        prior_findings: list[str] | None = None,
    ) -> str:
        """Propose a patch for the given task, informed by prior findings if any."""
        findings_text = (
            "\n".join(f"- {f}" for f in prior_findings) if prior_findings else "None"
        )
        user = (
            f"Task: {task}\n\n"
            f"Research notes:\n{notes}\n\n"
            f"Evidence:\n{evidence}\n\n"
            f"Prior reviewer findings to address:\n{findings_text}"
        )
        return call_builder(SYSTEM_PROMPT, user)
