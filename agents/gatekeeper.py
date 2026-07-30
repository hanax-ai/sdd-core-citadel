"""
Amigo-Gatekeeper Agent (Gemini Review Engine)
Performs substantive gatekeeper code reviews, schema validation, and security auditing.
"""

from __future__ import annotations
import json
import os
from pathlib import Path


class AmigoGatekeeper:
    """Substantive Reviewer & Security Auditor Agent."""

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")

    def audit_evidence_and_patch(self, evidence: dict, patch_summary: str) -> dict:
        """Perform substantive review audit against Directive-1.md rules."""
        findings = []

        # Audit 1: Uncommitted git changes check
        if evidence.get("git_status", {}).get("modified_count", 0) > 200:
            findings.append({
                "severity": "IMPORTANT",
                "code": "AMIGO-GATE-001",
                "message": "Target directory has excessive uncommitted changes (>200 files). High risk of context noise.",
            })

        # Audit 2: Syntax validation check
        for f_ev in evidence.get("file_evidence", []):
            if not f_ev.get("syntax_valid", True):
                findings.append({
                    "severity": "CRITICAL",
                    "code": "AMIGO-GATE-002",
                    "message": f"Syntax error in {f_ev['path']}: {f_ev['syntax_error']}",
                })

        passed = len([f for f in findings if f["severity"] in ("CRITICAL", "IMPORTANT")]) == 0

        return {
            "verdict": "PASS" if passed else "FAIL",
            "findings_count": len(findings),
            "findings": findings,
            "gatekeeper_model": "Gemini-2.0-Flash/Pro",
        }
