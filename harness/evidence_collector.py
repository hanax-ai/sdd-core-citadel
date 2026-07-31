"""
Amigo Agents Evidence Collector
Gathers file lines, git status, schema rules, and error tracebacks
BEFORE invoking LLMs to ensure zero-hallucination evidence-driven workflows.
"""

from __future__ import annotations
import ast
import re
from pathlib import Path
from tools.git_adapter import get_git_status, get_git_diff
from tools.linter_adapter import validate_json_syntax, compute_file_sha256

try:
    import tiktoken
    _ENCODING = tiktoken.get_encoding("cl100k_base")
except Exception:
    _ENCODING = None

# Rough universal token budgets (not per-provider-exact -- cl100k_base is a
# reasonable generic approximation across Anthropic/OpenAI/Gemini). Kept in
# the same ballpark as the old flat character limits (4000/2000 chars).
FILE_CONTENT_TOKEN_BUDGET = 1800
GIT_DIFF_TOKEN_BUDGET = 1000

REDACTED = "[REDACTED-SECRET]"

# High-confidence secret/credential shapes. Each is applied in sequence; the
# "generic_credential" pattern is handled specially so only the secret value
# (not the surrounding key name) is redacted.
_SECRET_PATTERNS = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("generic_credential", re.compile(
        r"(?i)(api[_-]?key|secret|token|password)(\s*[:=]\s*)(['\"])[^'\"]{16,}\3"
    )),
    # Redact from a private-key header through its matching footer, or to the
    # end of the text if no footer is present, so key material never leaks
    # even when only the header pattern (not the full PEM block) is present.
    ("private_key_block", re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"
        r"[\s\S]*?(?:-----END (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----|\Z)"
    )),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
]


def _redact_secrets(text: str) -> tuple[str, bool]:
    """Scan text for high-confidence secret/credential patterns and redact them in place.

    Returns (possibly-redacted text, whether anything was redacted). Never
    raises: a failure in scanning falls back to returning the original text
    unredacted rather than crashing evidence collection.
    """
    try:
        redacted = False
        for name, pattern in _SECRET_PATTERNS:
            if name == "generic_credential":
                new_text, count = pattern.subn(
                    lambda m: f"{m.group(1)}{m.group(2)}{m.group(3)}{REDACTED}{m.group(3)}",
                    text,
                )
            else:
                new_text, count = pattern.subn(REDACTED, text)
            if count:
                redacted = True
            text = new_text
        return text, redacted
    except Exception:
        return text, False


def _truncate_to_tokens(text: str, max_tokens: int) -> tuple[str, bool]:
    """Truncate text on a token boundary. Falls back to a rough char-based
    approximation (~4 chars/token) if tiktoken is unavailable."""
    if _ENCODING is not None:
        try:
            tokens = _ENCODING.encode(text)
            if len(tokens) <= max_tokens:
                return text, False
            return _ENCODING.decode(tokens[:max_tokens]), True
        except Exception:
            pass
    approx_chars = max_tokens * 4
    if len(text) <= approx_chars:
        return text, False
    return text[:approx_chars], True


def collect_task_evidence(target_dir: Path, focus_files: list[Path] | None = None) -> dict:
    """Collect comprehensive empirical evidence across target directory and focus files."""
    git_info = get_git_status(target_dir)
    git_diff = get_git_diff(target_dir)
    git_diff, diff_secrets_redacted = _redact_secrets(git_diff) if git_diff else (git_diff, False)

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
                raw_content = f.read_text(encoding="utf-8", errors="replace")
                scanned_content, file_secrets_redacted = _redact_secrets(raw_content)
                truncated_content, content_truncated = _truncate_to_tokens(
                    scanned_content, FILE_CONTENT_TOKEN_BUDGET
                )
                file_evidence.append({
                    "path": str(f.relative_to(target_dir) if f.is_relative_to(target_dir) else f),
                    "size_bytes": f.stat().st_size,
                    "sha256": compute_file_sha256(f),
                    "syntax_valid": syntax_valid,
                    "syntax_error": syntax_err,
                    "content": truncated_content,
                    "content_truncated": content_truncated,
                    "secrets_redacted": file_secrets_redacted,
                })

    if git_diff:
        git_diff_summary, diff_truncated = _truncate_to_tokens(git_diff, GIT_DIFF_TOKEN_BUDGET)
    else:
        git_diff_summary, diff_truncated = "NO_UNCOMMITTED_CHANGES", False

    return {
        "target_dir": str(target_dir),
        "git_status": git_info,
        "git_diff_summary": git_diff_summary,
        "git_diff_truncated": diff_truncated,
        "git_diff_secrets_redacted": diff_secrets_redacted,
        "file_evidence": file_evidence,
    }
