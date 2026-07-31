"""
Amigo Agents External Task Dispatcher
Collects evidence for a target task. Gate validation is performed by
native SDD-Core tooling, not by this dispatcher.
"""

from __future__ import annotations
from pathlib import Path
from harness.evidence_collector import collect_task_evidence


def run_collaboration_cycle(target_dir: Path, task_description: str) -> dict:
    """Collect git evidence for the target task (no gate validation here)."""
    evidence = collect_task_evidence(target_dir)

    print(f"📊 Target Git Status: Branch '{evidence['git_status'].get('branch')}', {evidence['git_status'].get('modified_count')} modified files")
    print(f"ℹ️ Native SDD-Core verification gates execute directly inside native package tools.")

    return {
        "task": task_description,
        "git_status": evidence["git_status"],
    }
