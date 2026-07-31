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


def _use_fake_encoding(monkeypatch):
    """Force a deterministic encoder so token-boundary assertions hold
    regardless of whether the real tiktoken encoder loaded in this
    environment."""
    monkeypatch.setattr(ec, "_ENCODING", _FakeEncoding())


def test_git_diff_truncation_flag_true_when_diff_exceeds_limit(tmp_path, monkeypatch):
    # 1170 chars (well under the old 2000-char limit); under the real
    # cl100k_base encoder this is ~1041 tokens (exceeds budget), and under
    # the deterministic fake encoder it's exactly 1170 tokens (also exceeds
    # budget) -- either way proves truncation is token-based, and does so
    # deterministically here via the fake.
    dense_diff = _DENSE_UNIT * 130
    _use_fake_encoding(monkeypatch)
    monkeypatch.setattr(ec, "get_git_status", _fake_git_status)
    monkeypatch.setattr(ec, "get_git_diff", lambda target_dir: dense_diff)
    evidence = ec.collect_task_evidence(tmp_path)
    assert evidence["git_diff_truncated"] is True
    assert len(evidence["git_diff_summary"]) < len(dense_diff)


def test_git_diff_not_truncated_when_chars_high_but_tokens_low(tmp_path, monkeypatch):
    # 2250 chars (over the old 2000-char limit); under the real cl100k_base
    # encoder this is ~501 tokens, and under the deterministic fake encoder
    # it's exactly 950 tokens -- both under the new token budget, proving
    # this isn't just char truncation in disguise (a real char-based cutoff
    # would have truncated this), deterministically here via the fake.
    sparse_diff = _PROSE_UNIT * 50
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
    # 2250 chars (well under the old 4000-char limit); under the real
    # cl100k_base encoder this is ~2001 tokens, and under the deterministic
    # fake encoder it's exactly 2250 tokens -- both exceed the new token
    # budget, proving truncation is token-based (not the old flat 4000-char
    # cutoff), deterministically here via the fake.
    _use_fake_encoding(monkeypatch)
    dense_content = _DENSE_UNIT * 250
    target = tmp_path / "big.py"
    target.write_text(dense_content, encoding="utf-8")
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[target])
    entry = evidence["file_evidence"][0]
    assert entry["content_truncated"] is True
    assert len(entry["content"]) < len(dense_content)


def test_focus_file_content_not_truncated_when_chars_high_but_tokens_low(tmp_path, monkeypatch):
    # 4050 chars (over the old 4000-char limit); under the real cl100k_base
    # encoder this is ~901 tokens, and under the deterministic fake encoder
    # it's exactly 1710 tokens -- both under the new token budget. A real
    # char-based cutoff would have truncated this at 4000 chars;
    # token-aware truncation must not, deterministically here via the fake.
    _use_fake_encoding(monkeypatch)
    sparse_content = _PROSE_UNIT * 90
    target = tmp_path / "prose.py"
    target.write_text(sparse_content, encoding="utf-8")
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[target])
    entry = evidence["file_evidence"][0]
    assert entry["content_truncated"] is False
    assert entry["content"] == sparse_content


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


def test_secret_redaction_private_key_header(tmp_path):
    target = tmp_path / "key.pem"
    target.write_text(
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEAtestFakeKeyMaterialNotReal1234567890\n"
        "-----END RSA PRIVATE KEY-----\n",
        encoding="utf-8",
    )
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[target])
    entry = evidence["file_evidence"][0]
    assert "-----BEGIN RSA PRIVATE KEY-----" not in entry["content"]
    assert "MIIEpAIBAAKCAQEAtestFakeKeyMaterialNotReal1234567890" not in entry["content"]
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

    monkeypatch.setattr(ec, "_SECRET_PATTERNS", [("aws_access_key", _RaisingPattern())])
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
