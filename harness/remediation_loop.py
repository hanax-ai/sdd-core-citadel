"""
Amigo Agents External Task Dispatcher
Runs external code generation and review dispatching for target tasks.
"""

from __future__ import annotations
from pathlib import Path
from harness.evidence_collector import collect_task_evidence


def run_collaboration_cycle(target_dir: Path, task_description: str) -> dict:
    """Collect git evidence and dispatch external agent workflow."""
    evidence = collect_task_evidence(target_dir)

    print(f"📊 Target Git Status: Branch '{evidence['git_status'].get('branch')}', {evidence['git_status'].get('modified_count')} modified files")
    print(f"ℹ️ Native SDD-Core verification gates execute directly inside native package tools.")

    return {
        "task": task_description,
        "git_status": evidence["git_status"],
    }
