"""
Amigo Agents Evidence Collector
Gathers file lines, git status, schema rules, and error tracebacks
BEFORE invoking LLMs to ensure zero-hallucination evidence-driven workflows.
"""

from __future__ import annotations
import ast
import re
from pathlib import Path
from typing import Any
from tools.git_adapter import get_git_status, get_git_diff
from tools.linter_adapter import validate_json_syntax, compute_file_sha256

# Populated on first use by _get_encoding(); tests override _ENCODING directly.
_ENCODING_UNSET = object()
_ENCODING: Any = _ENCODING_UNSET

# Rough universal token budgets (not per-provider-exact -- cl100k_base is a
# reasonable generic approximation across Anthropic/OpenAI/Gemini). Kept in
# the same ballpark as the old flat character limits (4000/2000 chars).
FILE_CONTENT_TOKEN_BUDGET = 1800
GIT_DIFF_TOKEN_BUDGET = 1000

REDACTED = "[REDACTED-SECRET]"

def _redact_credential_value(match: re.Match) -> str:
    """Redact only the secret value, preserving the key name and any quoting."""
    quote = match.group(3) or ""
    return f"{match.group(1)}{match.group(2)}{quote}{REDACTED}{quote}"


# High-confidence secret/credential shapes, applied in sequence. Each entry
# carries its own replacement (a literal or a callable), so redaction behaviour
# travels with the pattern instead of being dispatched on the label.
_SECRET_PATTERNS = [
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}"), REDACTED),
    # Matches quoted values and bare ones (.env / YAML / shell exports); the
    # unquoted branch needs 16+ non-space characters, which keeps ordinary
    # short call expressions like `api_key = os.getenv(...)` from tripping it.
    ("generic_credential", re.compile(
        r"(?i)([A-Za-z0-9_]*(?:api[_-]?key|secret|token|password)[A-Za-z0-9_]*)"
        r"(\s*[:=]\s*)"
        r"(?:(['\"])[^'\"]{16,}\3|[^\s'\"]{16,})"
    ), _redact_credential_value),
    # Redact from a private-key header through its matching footer, or to the
    # end of the text if no footer is present, so key material never leaks
    # even when only the header pattern (not the full PEM block) is present.
    ("private_key_block", re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"
        r"[\s\S]*?(?:-----END (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----|\Z)"
    ), REDACTED),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"), REDACTED),
]


def _redact_secrets(text: str) -> tuple[str, bool]:
    """Scan text for high-confidence secret/credential patterns and redact them in place.

    Returns (possibly-redacted text, whether anything was redacted).

    Scan failures fail closed: `re.error` and `RecursionError` are caught and
    the entire text is replaced with the placeholder, flag set True, rather
    than letting unscanned content through. Anything else (`MemoryError`, or a
    `TypeError` from a non-str argument) propagates and aborts evidence
    collection before any of it reaches a provider -- also safe, and it keeps
    real bugs visible instead of silently returning a redaction placeholder.
    """
    try:
        redacted = False
        for _name, pattern, replacement in _SECRET_PATTERNS:
            new_text, count = pattern.subn(replacement, text)
            if count:
                redacted = True
            text = new_text
        return text, redacted
    except (re.error, RecursionError):
        # Both are defensive: patterns are precompiled, and RecursionError would
        # mean deep recursion inside the matching engine -- not catastrophic
        # backtracking, which burns CPU without ever raising.
        return REDACTED, True


def _get_encoding() -> Any:
    """Return the cl100k_base encoder, or None if it can't be loaded.

    Deferred to first use because tiktoken fetches BPE data on load (a network
    call on a cold cache); callers that never truncate shouldn't pay for it.
    A failed load is cached as None so the attempt isn't retried per call.
    """
    global _ENCODING
    if _ENCODING is _ENCODING_UNSET:
        try:
            import tiktoken
            _ENCODING = tiktoken.get_encoding("cl100k_base")
        except Exception:
            _ENCODING = None
    return _ENCODING


def _truncate_to_tokens(text: str, max_tokens: int) -> tuple[str, bool]:
    """Truncate text on a token boundary. Falls back to a rough char-based
    approximation (~4 chars/token) if tiktoken is unavailable."""
    encoding = _get_encoding()
    if encoding is not None:
        try:
            tokens = encoding.encode(text)
            if len(tokens) <= max_tokens:
                return text, False
            return encoding.decode(tokens[:max_tokens]), True
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
