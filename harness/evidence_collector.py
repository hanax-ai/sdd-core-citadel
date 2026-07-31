"""
Amigo Agents Evidence Collector
Gathers file lines, git status, schema rules, and error tracebacks
BEFORE invoking LLMs to ensure zero-hallucination evidence-driven workflows.
"""

from __future__ import annotations
import ast
from pathlib import Path
from tools.git_adapter import get_git_status, get_git_diff
from tools.linter_adapter import validate_json_syntax, compute_file_sha256


def collect_task_evidence(target_dir: Path, focus_files: list[Path] | None = None) -> dict:
    """Collect comprehensive empirical evidence across target directory and focus files."""
    git_info = get_git_status(target_dir)
    git_diff = get_git_diff(target_dir)

    file_evidence = []
    if focus_files:
        for f in focus_files:
            if f.is_file():
                if f.suffix == ".json":
                    syntax_valid, syntax_err = validate_json_syntax(f)
                elif f.suffix == ".py":
                    try:
                        ast.parse(f.read_text(encoding="utf-8"))
                        syntax_valid, syntax_err = True, "OK"
                    except SyntaxError as exc:
                        syntax_valid, syntax_err = False, str(exc)
                else:
                    syntax_valid, syntax_err = True, "NOT_CHECKED"
                file_evidence.append({
                    "path": str(f.relative_to(target_dir) if f.is_relative_to(target_dir) else f),
                    "size_bytes": f.stat().st_size,
                    "sha256": compute_file_sha256(f),
                    "syntax_valid": syntax_valid,
                    "syntax_error": syntax_err,
                })

    diff_truncated = bool(git_diff) and len(git_diff) > 2000
    return {
        "target_dir": str(target_dir),
        "git_status": git_info,
        "git_diff_summary": git_diff[:2000] if git_diff else "NO_UNCOMMITTED_CHANGES",
        "git_diff_truncated": diff_truncated,
        "file_evidence": file_evidence,
    }
