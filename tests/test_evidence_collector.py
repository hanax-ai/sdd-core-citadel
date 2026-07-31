from __future__ import annotations

import harness.evidence_collector as ec


def _fake_git_status(target_dir):
    return {"is_git": True, "branch": "main", "modified_count": 0, "modified_files": []}


# High token-per-char density text (short, "noisy" tokens that don't merge
# well under BPE) vs. low-density plain-English prose. Used to prove
# truncation is now driven by real token count, not raw character count.
_DENSE_UNIT = "Zx9#kq7! "
_PROSE_UNIT = "The quick brown fox jumps over the lazy dog. "


def test_git_diff_truncation_flag_true_when_diff_exceeds_limit(tmp_path, monkeypatch):
    # 1170 chars (well under the old 2000-char limit) but ~1041 tokens,
    # which exceeds the new token budget -- proves truncation is token-based.
    dense_diff = _DENSE_UNIT * 130
    monkeypatch.setattr(ec, "get_git_status", _fake_git_status)
    monkeypatch.setattr(ec, "get_git_diff", lambda target_dir: dense_diff)
    evidence = ec.collect_task_evidence(tmp_path)
    assert evidence["git_diff_truncated"] is True
    assert len(evidence["git_diff_summary"]) < len(dense_diff)


def test_git_diff_not_truncated_when_chars_high_but_tokens_low(tmp_path, monkeypatch):
    # 2250 chars (over the old 2000-char limit) but only ~501 tokens, under
    # the new token budget -- proves this isn't just char truncation in
    # disguise; a real char-based cutoff would have truncated this.
    sparse_diff = _PROSE_UNIT * 50
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


def test_focus_file_content_truncated_when_tokens_exceed_budget(tmp_path):
    # 2250 chars (well under the old 4000-char limit) but ~2001 tokens,
    # which exceeds the new token budget -- proves truncation is token-based,
    # not the old flat 4000-char cutoff.
    dense_content = _DENSE_UNIT * 250
    target = tmp_path / "big.py"
    target.write_text(dense_content, encoding="utf-8")
    evidence = ec.collect_task_evidence(tmp_path, focus_files=[target])
    entry = evidence["file_evidence"][0]
    assert entry["content_truncated"] is True
    assert len(entry["content"]) < len(dense_content)


def test_focus_file_content_not_truncated_when_chars_high_but_tokens_low(tmp_path):
    # 4050 chars (over the old 4000-char limit) but only ~901 tokens, under
    # the new token budget -- a real char-based cutoff would have truncated
    # this at 4000 chars; token-aware truncation must not.
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
