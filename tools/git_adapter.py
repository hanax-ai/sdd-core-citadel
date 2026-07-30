"""
Amigo Agents Git Tool Adapter
Extracts working tree status, modified files, and git diffs
from target codebases without altering git state or history.
"""

from __future__ import annotations
import subprocess
from pathlib import Path


def run_git_command(args: list[str], cwd: Path) -> tuple[int, str]:
    """Execute a git command in the target directory and return returncode, output."""
    try:
        res = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
        return res.returncode, res.stdout.strip()
    except Exception as exc:
        return 1, str(exc)


def get_git_status(target_dir: Path) -> dict:
    """Return structured git status summary for target directory."""
    code, output = run_git_command(["status", "--porcelain"], cwd=target_dir)
    if code != 0:
        return {"is_git": False, "error": output, "modified_files": []}

    modified_files = []
    for line in output.splitlines():
        if line.strip():
            modified_files.append(line.strip())

    code_branch, branch_name = run_git_command(["branch", "--show-current"], cwd=target_dir)

    return {
        "is_git": True,
        "branch": branch_name if code_branch == 0 else "unknown",
        "modified_count": len(modified_files),
        "modified_files": modified_files,
    }


def get_git_diff(target_dir: Path) -> str:
    """Return unified diff of uncommitted changes in target directory."""
    code, diff = run_git_command(["diff"], cwd=target_dir)
    return diff if code == 0 else ""
