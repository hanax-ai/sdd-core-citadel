"""
Amigo Agents Collaboration Loop
Runs the Researcher -> Builder -> Gatekeeper remediation cycle for a
target task, emitting incremental progress events, and writes a full
JSON transcript to logs/.
"""

from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Callable

from agents.builder import AmigoBuilder
from agents.gatekeeper import AmigoGatekeeper, has_blocking_findings
from agents.researcher import AmigoResearcher
from harness.config import LOGS_DIR
from harness.evidence_collector import collect_task_evidence

MAX_ROUNDS = 3
_PATH_TOKEN = re.compile(r"[\w./\\-]+\.\w+")


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:50] or "task"


def _extract_focus_files(task_description: str, target_dir: Path) -> list[Path]:
    """Find file paths named in the task that actually exist under target_dir."""
    found = []
    for token in _PATH_TOKEN.findall(task_description):
        candidate = (target_dir / token.replace("\\", "/")).resolve()
        if candidate.is_file() and candidate not in found:
            found.append(candidate)
    return found


async def run_collaboration_cycle(
    target_dir: Path,
    task_description: str,
    log_dir: Path = LOGS_DIR,
    run_id: str | None = None,
    on_event: Callable[[dict], None] | None = None,
) -> dict:
    """Run the researcher/builder/gatekeeper remediation cycle for the target task."""

    def emit(event_type: str, **fields) -> None:
        if on_event is None:
            return
        on_event({"type": event_type, "run_id": run_id, "timestamp": datetime.now().isoformat(), **fields})

    focus_files = _extract_focus_files(task_description, target_dir)
    emit("stage_change", stage="COLLECTING_EVIDENCE")
    evidence = collect_task_evidence(target_dir, focus_files=focus_files)

    researcher = AmigoResearcher()
    emit("stage_change", stage="RESEARCHING", agent="Researcher")
    notes = await researcher.analyze(task_description, evidence)
    emit("agent_message", agent="Researcher", message_type="RESEARCH_NOTES", content=notes)

    builder = AmigoBuilder()
    gatekeeper = AmigoGatekeeper()

    rounds = []
    prior_findings = None
    verdict = "UNRESOLVED"
    patch_text = ""

    for round_num in range(1, MAX_ROUNDS + 1):
        emit("stage_change", stage=f"BUILDER_PATCH_R{round_num}", agent="Builder", round=round_num)
        patch_text = await builder.propose_patch(task_description, notes, evidence, prior_findings)
        emit("agent_message", agent="Builder", round=round_num, message_type="PATCH", content=patch_text)

        emit("stage_change", stage=f"GATEKEEPER_AUDIT_R{round_num}", agent="Gatekeeper", round=round_num)
        findings = await gatekeeper.review(patch_text, evidence)
        emit(
            "agent_message",
            agent="Gatekeeper",
            round=round_num,
            message_type="AUDIT_FINDINGS",
            findings=findings,
        )
        rounds.append({"round": round_num, "patch_text": patch_text, "findings": findings})

        if not has_blocking_findings(findings):
            verdict = "PASS"
            break
        prior_findings = findings

    emit("stage_change", stage="VERDICT", verdict=verdict)

    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
    log_path = log_dir / f"{timestamp}_{_slugify(task_description)}.json"
    log_path.write_text(
        json.dumps(
            {
                "task": task_description,
                "evidence": evidence,
                "research_notes": notes,
                "rounds": rounds,
                "verdict": verdict,
            },
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    result = {
        "task": task_description,
        "git_status": evidence["git_status"],
        "verdict": verdict,
        "patch_text": patch_text,
        "log_path": str(log_path),
        "rounds": rounds,
    }
    emit("run_complete", verdict=verdict, rounds_total=len(rounds), patch_text=patch_text)
    return result
