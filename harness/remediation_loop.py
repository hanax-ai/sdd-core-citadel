"""
Amigo Agents Remediation Loop
Orchestrates automated fix rounds between Amigo-Builder and Amigo-Gatekeeper.
"""

from __future__ import annotations
from pathlib import Path
from harness.evidence_collector import collect_task_evidence
from agents.gatekeeper import AmigoGatekeeper


def run_collaboration_cycle(target_dir: Path, task_description: str, max_rounds: int = 3) -> dict:
    """Run automated evidence collection -> review audit -> fix round loop."""
    print(f"🔄 Starting Three Amigos Collaboration Cycle for task: '{task_description}'")

    # Step 1: Collect empirical evidence
    evidence = collect_task_evidence(target_dir)
    print(f"📊 Evidence Collected: Git Branch '{evidence['git_status'].get('branch')}', {evidence['git_status'].get('modified_count')} modified files")

    # Step 2: Initialize Amigo-Gatekeeper
    gatekeeper = AmigoGatekeeper()
    audit_res = gatekeeper.audit_evidence_and_patch(evidence, patch_summary=task_description)

    print(f"🛡️ Amigo-Gatekeeper Audit Verdict: {audit_res['verdict']} ({audit_res['findings_count']} findings)")
    for finding in audit_res.get("findings", []):
        print(f"   - [{finding['severity']}] {finding['code']}: {finding['message']}")

    return {
        "task": task_description,
        "evidence_summary": {
            "git_branch": evidence["git_status"].get("branch"),
            "modified_files": evidence["git_status"].get("modified_count"),
        },
        "gatekeeper_verdict": audit_res,
        "rounds_executed": 1,
    }
