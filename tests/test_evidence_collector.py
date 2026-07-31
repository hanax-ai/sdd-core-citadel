from __future__ import annotations

import re

import harness.evidence_collector as ec


def _fake_git_status(target_dir):
    return {"is_git": True, "branch": "main", "modified_count": 0, "modified_files": []}


# High token-per-char density text (short, "noisy" tokens that don't merge
# well under BPE) vs. low-density plain-English prose. Used to prove
# truncation is now driven by real token count, not raw character count.
_DENSE_UNIT = "Zx9#kq7! "
_PROSE_UNIT = "The quick brown fox jumps over the lazy dog. "

_WORD_OR_CHAR_RE = re.compile(r"[A-Za-z]+|[\s\S]")


class _FakeEncoding:
    """Deterministic stand-in for the real tiktoken encoder.

    The token-budget tests below need dense/sparse fixtures that reliably
    cross (or stay under) a token budget. Asserting that against the real
    `cl100k_base` encoder makes the tests depend on tiktoken's BPE data
    having downloaded successfully in this environment -- which fails
    offline, on a cold CI cache, etc. (see CodeRabbit finding on commit
    659db2b). This fake reproduces just the qualitative property the
    fixtures rely on -- common all-letter runs of 3+ chars ("words") count
    as a single token, like a real trained BPE vocab would collapse them;
    everything else (digits, symbols, whitespace, 1-2 letter runs) costs one
    token per character, like rare fragments that don't merge -- with fixed,
    hand-verified token counts, independent of any real encoder.
    """

    def encode(self, text: str) -> list[str]:
        tokens: list[str] = []
        for run in _WORD_OR_CHAR_RE.findall(text):
            if run.isalpha() and len(run) >= 3:
                tokens.append(run)
            else:
                tokens.extend(run)
        return tokens

    def decode(self, tokens: list[str]) -> str:
        return "".join(tokens)


_FAKE_ENCODING = _FakeEncoding()


def _sized_over(unit: str, budget: int) -> str:
    """Repeat `unit` to land clear of `budget` tokens under the fake encoder."""
    return unit * (budget // len(_FAKE_ENCODING.encode(unit)) + 10)


def _sized_under(unit: str, budget: int) -> str:
    """Repeat `unit` to the most whole units that still fit inside `budget`."""
    return unit * (budget // len(_FAKE_ENCODING.encode(unit)))


def _use_fake_encoding(monkeypatch):
    """Force a deterministic encoder so token-boundary assertions hold
    regardless of whether the real tiktoken encoder loaded in this
    environment."""
    monkeypatch.setattr(ec, "_ENCODING", _FAKE_ENCODING)


def test_git_diff_truncation_flag_true_when_diff_exceeds_limit(tmp_path, monkeypatch):
    # Dense, high-token-per-char text: few chars, many tokens. Paired with the
    # sparse test below, this proves truncation keys off tokens, not chars.
    dense_diff = _sized_over(_DENSE_UNIT, ec.GIT_DIFF_TOKEN_BUDGET)
    assert len(_FAKE_ENCODING.encode(dense_diff)) > ec.GIT_DIFF_TOKEN_BUDGET
    _use_fake_encoding(monkeypatch)
    monkeypatch.setattr(ec, "get_git_status", _fake_git_status)
    monkeypatch.setattr(ec, "get_git_diff", lambda target_dir: dense_diff)
    evidence = ec.collect_task_evidence(tmp_path)
    assert evidence["git_diff_truncated"] is True
    assert len(evidence["git_diff_summary"]) < len(dense_diff)


def test_git_diff_not_truncated_when_chars_high_but_tokens_low(tmp_path, monkeypatch):
    # Sparse prose: many more chars than the dense fixture above, yet within the
    # token budget -- a char-based cutoff would truncate, a token-based one must not.
    sparse_diff = _sized_under(_PROSE_UNIT, ec.GIT_DIFF_TOKEN_BUDGET)
    assert len(_FAKE_ENCODING.encode(sparse_diff)) <= ec.GIT_DIFF_TOKEN_BUDGET
    assert len(sparse_diff) > len(_sized_over(_DENSE_UNIT, ec.GIT_DIFF_TOKEN_BUDGET))
    _use_fake_encoding(monkeypatch)
    monkeypatch.setattr(ec, "get_git_status", _fake_git_status)
    monkeypatch.setattr(ec, "get_git_diff", lambda target_dir: sparse_diff)
    evidence = ec.collect_task_evidence(tmp_path)
    assert evidence["git_diff_truncated"] is False
    assert evidence["git_diff_summary"] == sparse_diff


def test_git_diff_truncation_flag_false_when_diff_short(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "get_git_status", _fake_git_status)
    monkeypatch.setattr(ec, "get_git_diff", lambda target_dir: "short diff")
    evidence = ec.collect_task_evidence(tmp_path)
    assert evidence["git_diff_truncated"] is False


def test_syntax_check_flags_bad_python(tmp_path):
    bad = tmp_path / "broken.py"
    bad.write_text("def broken(:\n    pass\n", encoding="utf-8")
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[bad])
    assert evidence["file_evidence"][0]["syntax_valid"] is False


def test_syntax_check_passes_good_python(tmp_path):
    good = tmp_path / "ok.py"
    good.write_text("def ok():\n    return 1\n", encoding="utf-8")
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[good])
    assert evidence["file_evidence"][0]["syntax_valid"] is True
    assert evidence["file_evidence"][0]["syntax_error"] == "OK"


def test_syntax_check_not_performed_marker_for_unknown_suffix(tmp_path):
    other = tmp_path / "notes.txt"
    other.write_text("hello", encoding="utf-8")
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[other])
    assert evidence["file_evidence"][0]["syntax_valid"] is True
    assert evidence["file_evidence"][0]["syntax_error"] == "NOT_CHECKED"


def test_focus_file_evidence_includes_real_content(tmp_path):
    target = tmp_path / "small.py"
    target.write_text("DEFAULT_TARGET_DIR = 'placeholder'\n", encoding="utf-8")
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[target])
    entry = evidence["file_evidence"][0]
    assert entry["content"] == "DEFAULT_TARGET_DIR = 'placeholder'\n"
    assert entry["content_truncated"] is False


def test_focus_file_content_truncated_when_tokens_exceed_budget(tmp_path, monkeypatch):
    # Dense text: few chars, many tokens -- clears the file-content token budget.
    _use_fake_encoding(monkeypatch)
    dense_content = _sized_over(_DENSE_UNIT, ec.FILE_CONTENT_TOKEN_BUDGET)
    assert len(_FAKE_ENCODING.encode(dense_content)) > ec.FILE_CONTENT_TOKEN_BUDGET
    target = tmp_path / "big.py"
    target.write_text(dense_content, encoding="utf-8")
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[target])
    entry = evidence["file_evidence"][0]
    assert entry["content_truncated"] is True
    assert len(entry["content"]) < len(dense_content)


def test_focus_file_content_not_truncated_when_chars_high_but_tokens_low(tmp_path, monkeypatch):
    # Sparse prose: many more chars than the dense fixture above, yet within the
    # token budget -- token-aware truncation must leave it alone.
    _use_fake_encoding(monkeypatch)
    sparse_content = _sized_under(_PROSE_UNIT, ec.FILE_CONTENT_TOKEN_BUDGET)
    assert len(_FAKE_ENCODING.encode(sparse_content)) <= ec.FILE_CONTENT_TOKEN_BUDGET
    assert len(sparse_content) > len(_sized_over(_DENSE_UNIT, ec.FILE_CONTENT_TOKEN_BUDGET))
    target = tmp_path / "prose.py"
    target.write_text(sparse_content, encoding="utf-8")
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[target])
    entry = evidence["file_evidence"][0]
    assert entry["content_truncated"] is False
    assert entry["content"] == sparse_content


def test_encoder_load_failure_falls_back_to_chars_and_is_not_retried(monkeypatch):
    # An encoder that can't load (offline, cold cache, missing package) must
    # degrade to the char approximation instead of aborting evidence
    # collection, and the failure must be cached so later calls don't retry it.
    import builtins

    monkeypatch.setattr(ec, "_ENCODING", ec._ENCODING_UNSET)
    real_import = builtins.__import__
    attempts = []

    def _failing_import(name, *args, **kwargs):
        if name == "tiktoken":
            attempts.append(name)
            raise ImportError("simulated offline / cold-cache load failure")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _failing_import)

    truncated, was_truncated = ec._truncate_to_tokens("x" * 100, 10)
    assert was_truncated is True
    assert truncated == "x" * 40  # 10 tokens * ~4 chars per token

    untouched, flag = ec._truncate_to_tokens("short", 10)
    assert flag is False
    assert untouched == "short"

    assert len(attempts) == 1


# --- R6: secret-scanning / redaction -----------------------------------------

def test_secret_redaction_aws_access_key(tmp_path):
    target = tmp_path / "creds.py"
    target.write_text('aws_access_key_id = "AKIAIOSFODNN7EXAMPLE"\n', encoding="utf-8")
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[target])
    entry = evidence["file_evidence"][0]
    assert "AKIAIOSFODNN7EXAMPLE" not in entry["content"]
    assert "[REDACTED-SECRET]" in entry["content"]
    assert entry["secrets_redacted"] is True


def test_secret_redaction_generic_api_key_assignment(tmp_path):
    target = tmp_path / "config.py"
    target.write_text('api_key = "test-placeholder-abcdefghijklmnop"\n', encoding="utf-8")
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[target])
    entry = evidence["file_evidence"][0]
    assert "test-placeholder-abcdefghijklmnop" not in entry["content"]
    assert "[REDACTED-SECRET]" in entry["content"]
    assert entry["secrets_redacted"] is True


def test_secret_redaction_prefixed_suffixed_credential_name(tmp_path):
    # Real-world credential variable names rarely have the keyword sitting
    # directly next to the separator -- AWS_SECRET_ACCESS_KEY and
    # STRIPE_SECRET_KEY both have identifier characters before/after the
    # "secret" keyword. The key names themselves must survive (only the
    # quoted value is redacted).
    target = tmp_path / "creds.py"
    target.write_text(
        'AWS_SECRET_ACCESS_KEY = "just-a-placeholder-value-1234567"\n'
        'STRIPE_SECRET_KEY = "another-placeholder-value-7654321"\n',
        encoding="utf-8",
    )
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[target])
    entry = evidence["file_evidence"][0]
    assert "just-a-placeholder-value-1234567" not in entry["content"]
    assert "another-placeholder-value-7654321" not in entry["content"]
    assert "AWS_SECRET_ACCESS_KEY" in entry["content"]
    assert "STRIPE_SECRET_KEY" in entry["content"]
    assert entry["content"].count("[REDACTED-SECRET]") == 2
    assert entry["secrets_redacted"] is True


def test_secret_redaction_unquoted_credential_value(tmp_path):
    # .env / YAML / shell-export style assignments carry no quotes, so the
    # quoted-only pattern let these through verbatim.
    target = tmp_path / "settings.env"
    target.write_text(
        "OPENAI_API_KEY=sk-proj-placeholder-abcdefghijklmnop\n"
        "db_password: another-placeholder-value-7654321\n",
        encoding="utf-8",
    )
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[target])
    entry = evidence["file_evidence"][0]
    assert "sk-proj-placeholder-abcdefghijklmnop" not in entry["content"]
    assert "another-placeholder-value-7654321" not in entry["content"]
    assert "OPENAI_API_KEY" in entry["content"]
    assert "db_password" in entry["content"]
    assert entry["content"].count("[REDACTED-SECRET]") == 2
    assert entry["secrets_redacted"] is True


def _pem_banner(boundary: str, kind: str) -> str:
    # Assembled at runtime so no complete PEM banner literal sits in tracked source.
    return f"{'-' * 5}{boundary} {kind} PRIVATE KEY{'-' * 5}"


_FAKE_KEY_BODY = "MIIEpAIBAAKCAQEAtestFakeKeyMaterialNotReal1234567890"


def test_secret_redaction_private_key_full_block(tmp_path):
    begin, end = _pem_banner("BEGIN", "RSA"), _pem_banner("END", "RSA")
    target = tmp_path / "key.pem"
    target.write_text(f"{begin}\n{_FAKE_KEY_BODY}\n{end}\n", encoding="utf-8")
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[target])
    entry = evidence["file_evidence"][0]
    assert begin not in entry["content"]
    assert _FAKE_KEY_BODY not in entry["content"]
    assert "[REDACTED-SECRET]" in entry["content"]
    assert entry["secrets_redacted"] is True


def test_secret_redaction_private_key_header_without_footer(tmp_path):
    # Truncated/partial key material still has to be caught -- this exercises the
    # pattern's run-to-end-of-text branch rather than the footer branch.
    begin = _pem_banner("BEGIN", "OPENSSH")
    target = tmp_path / "partial_key.pem"
    target.write_text(f"{begin}\n{_FAKE_KEY_BODY}\n", encoding="utf-8")
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[target])
    entry = evidence["file_evidence"][0]
    assert begin not in entry["content"]
    assert _FAKE_KEY_BODY not in entry["content"]
    assert "[REDACTED-SECRET]" in entry["content"]
    assert entry["secrets_redacted"] is True


def test_secret_redaction_jwt(tmp_path):
    target = tmp_path / "token.txt"
    fake_jwt = (
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIxMjM0NTY3ODkwIn0."
        "SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    )
    target.write_text(f"token = {fake_jwt}\n", encoding="utf-8")
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[target])
    entry = evidence["file_evidence"][0]
    assert fake_jwt not in entry["content"]
    assert "[REDACTED-SECRET]" in entry["content"]
    assert entry["secrets_redacted"] is True


def test_no_false_positive_redaction_on_clean_code(tmp_path):
    clean_source = (
        "from pathlib import Path\n"
        "import os\n\n"
        "def get_env_summary() -> dict:\n"
        "    return {\n"
        '        "anthropic_key_set": bool(os.getenv("ANTHROPIC_API_KEY")),\n'
        '        "gemini_key_set": bool(os.getenv("GEMINI_API_KEY")),\n'
        '        "openai_key_set": bool(os.getenv("OPENAI_API_KEY")),\n'
        "    }\n"
    )
    target = tmp_path / "config.py"
    target.write_text(clean_source, encoding="utf-8")
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[target])
    entry = evidence["file_evidence"][0]
    assert entry["content"] == clean_source
    assert entry["secrets_redacted"] is False
    assert "[REDACTED-SECRET]" not in entry["content"]


def test_redact_secrets_fails_closed_on_scan_error(monkeypatch):
    # A scanning failure must not fall back to returning the original,
    # unredacted text -- that would defeat the control exactly when it's
    # needed. Force a scan error and assert the content is replaced with the
    # redaction placeholder and the flag is True (not the original text /
    # False).
    class _RaisingPattern:
        def subn(self, *args, **kwargs):
            raise re.error("boom")

    monkeypatch.setattr(ec, "_SECRET_PATTERNS", [("aws_access_key", _RaisingPattern(), ec.REDACTED)])
    text, flagged = ec._redact_secrets("some content with AKIA1234567890123456")
    assert text == ec.REDACTED
    assert flagged is True


def test_git_diff_secrets_redacted(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "get_git_status", _fake_git_status)
    monkeypatch.setattr(
        ec,
        "get_git_diff",
        lambda target_dir: '+aws_access_key_id = "AKIAIOSFODNN7EXAMPLE"\n',
    )
    evidence = ec.collect_task_evidence(tmp_path)
    assert "AKIAIOSFODNN7EXAMPLE" not in evidence["git_diff_summary"]
    assert evidence["git_diff_secrets_redacted"] is True
