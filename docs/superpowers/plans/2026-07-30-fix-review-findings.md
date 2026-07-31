# Fix Review Findings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the 14 prioritized findings from `reviews/REPOSITORY_REVIEW_2026-07-30.md` (Windows crash, wrong default path, destructive test script, stale docs, misleading evidence fields, missing license/tests) with an automated pytest regression suite backing each behavioral fix.

**Architecture:** Small, surgical edits to existing files (`harness/`, `agents/`, `tools/`, docs) plus a new `tests/` directory with pytest tests that reproduce each bug before the fix and verify it after. No new modules, no renamed public entry points, no reversal of the repo owner's deliberate "defer gate validation to native SDD-Core tools" decision from commit `7ed3010`.

**Tech Stack:** Python 3.11 stdlib (`ast`, `pathlib`, `subprocess`) + `pytest` (newly added, replacing three unused declared dependencies).

## Global Constraints

- Repo root: `C:\Users\JarvisRichardson\Desktop\SDD\Amigos-Agents`
- Do not reintroduce the deleted gatekeeper audit/remediation loop — only fix the misleading docstrings that overclaim it.
- Do not rename `run_collaboration_cycle` or move `remediation_loop.py` — avoid ripple effects on the sole caller (`harness/runner.py:65`).
- Every behavioral fix gets a pytest test in `tests/` that fails before the fix and passes after.
- `python -m pytest -q` must be green at the end with zero failures.

---

### Task 1: Fix Windows console UnicodeEncodeError + test scaffolding

**Files:**
- Modify: `harness/runner.py:1-15` (add stdout UTF-8 reconfigure at import time)
- Create: `tests/conftest.py`
- Create: `tests/test_runner_cli.py`

**Interfaces:**
- Produces: `tests/conftest.py` inserts repo root onto `sys.path` for every test module (all later test tasks rely on this).

- [ ] **Step 1: Write the failing test**

```python
# tests/conftest.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

```python
# tests/test_runner_cli.py
"""CLI smoke tests for harness/runner.py."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env.pop("PYTHONUTF8", None)
    env.pop("PYTHONIOENCODING", None)
    return subprocess.run(
        [sys.executable, "harness/runner.py", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


def test_status_flag_does_not_crash_on_default_console_encoding():
    result = _run_cli("--status")
    assert "UnicodeEncodeError" not in result.stderr
    assert result.returncode == 0, result.stderr


def test_bare_invocation_does_not_crash_on_default_console_encoding():
    result = _run_cli()
    assert "UnicodeEncodeError" not in result.stderr
    assert result.returncode == 0, result.stderr
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pip install pytest && python -m pytest tests/test_runner_cli.py -v`
Expected: FAIL — `UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f91d'` in stderr.

- [ ] **Step 3: Fix `harness/runner.py`**

Insert immediately after the existing imports (after line 13, before the `from harness.config import ...` line):

```python
# Force UTF-8 stdout so emoji output doesn't crash on default Windows consoles (cp1252).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_runner_cli.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add harness/runner.py tests/conftest.py tests/test_runner_cli.py
git commit -m "fix: reconfigure stdout to UTF-8 so runner.py doesn't crash on Windows"
```

---

### Task 2: Fix wrong `DEFAULT_TARGET_DIR`

**Files:**
- Modify: `harness/config.py:25`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from harness.config import DEFAULT_TARGET_DIR


def test_default_target_dir_is_a_real_existing_directory():
    assert DEFAULT_TARGET_DIR.exists(), f"{DEFAULT_TARGET_DIR} does not exist"
    assert DEFAULT_TARGET_DIR.is_dir()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_config.py -v`
Expected: FAIL — `DEFAULT_TARGET_DIR` resolves to a nonexistent `...\mnt\c\...` path.

- [ ] **Step 3: Fix `harness/config.py:25`**

```python
DEFAULT_TARGET_DIR = Path(r"C:\Users\JarvisRichardson\Desktop\WiP\SDD-Core-Framework-Analysis")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add harness/config.py tests/test_config.py
git commit -m "fix: use native Windows path for DEFAULT_TARGET_DIR"
```

---

### Task 3: Replace destructive `tools/test_adapters.py` with real pytest tests

**Files:**
- Delete: `tools/test_adapters.py`
- Create: `tests/test_adapters.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_adapters.py
"""Tests for tools/git_adapter.py and tools/linter_adapter.py."""
from __future__ import annotations

from pathlib import Path

from tools.git_adapter import get_git_status
from tools.linter_adapter import validate_json_syntax

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_get_git_status_on_this_repo():
    status = get_git_status(REPO_ROOT)
    assert status["is_git"] is True
    assert isinstance(status["modified_files"], list)


def test_validate_json_syntax_accepts_valid_json(tmp_path):
    sample = tmp_path / "sample.json"
    sample.write_text('{"name": "Amigo-Builder"}', encoding="utf-8")
    valid, msg = validate_json_syntax(sample)
    assert valid is True
    assert msg == "OK"


def test_validate_json_syntax_rejects_duplicate_keys(tmp_path):
    sample = tmp_path / "dup.json"
    sample.write_text('{"a": 1, "a": 2}', encoding="utf-8")
    valid, msg = validate_json_syntax(sample)
    assert valid is False
    assert "duplicate" in msg
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_adapters.py -v`
Expected: FAIL — `ModuleNotFoundError` or import path errors (new file, not yet wired), or passes trivially since adapters already work — the real regression this replaces is the destructive write in the old script, not a code bug. Confirm by inspecting `agents/builder.json` content before running: it must be unchanged after the run.

- [ ] **Step 3: Delete the destructive script**

```bash
rm tools/test_adapters.py
```

- [ ] **Step 4: Run test to verify it passes and nothing was mutated**

Run: `python -m pytest tests/test_adapters.py -v`
Expected: PASS (3 passed)

Run: `git status --porcelain agents/builder.json`
Expected: empty output (no changes to the tracked file)

- [ ] **Step 5: Commit**

```bash
git add tests/test_adapters.py
git rm tools/test_adapters.py
git commit -m "fix: replace destructive test_adapters.py script with real pytest tests"
```

---

### Task 4: Update README.md Repository Layout tree

**Files:**
- Modify: `README.md:38-59`

- [ ] **Step 1: Replace the layout tree**

Replace the fenced block between `## 📂 Repository Layout` and the next `---` with:

```text
Amigos-Agents/
├── README.md                           <-- Master Index & Harness Overview
├── AGENTS.md                           <-- Amigo Agents Standing Directives & Conduct Rules
├── requirements.txt                    <-- Python dependencies
├── .env.example                        <-- Environment variable template
├── .gitignore
│
├── docs/                               <-- Design & Planning Docs
│   ├── AMIGO_AGENTS_HARNESS_BLUEPRINT.md   <-- Detailed Multi-Agent Collaboration Blueprint
│   └── implementation_plan.md              <-- Phased build roadmap
│
├── reviews/                            <-- Review & Audit Reports
│
├── harness/                            <-- Multi-Agent Collaboration Orchestrator
│   ├── config.py                       <-- Env/paths loader
│   ├── runner.py                       <-- CLI controller
│   ├── evidence_collector.py           <-- Git/file evidence gathering
│   └── remediation_loop.py             <-- Evidence dispatch (gate validation deferred to native SDD-Core tools)
│
├── agents/                             <-- Agent Roster & Persona Definitions
│   ├── builder.json                    <-- Amigo-Builder profile
│   └── gatekeeper.py                   <-- Amigo-Gatekeeper review-prompt helper
│
├── tools/                              <-- Shared Validation & Diff Inspection Helpers
│   ├── git_adapter.py                  <-- Git status/diff extractor
│   └── linter_adapter.py               <-- JSON syntax & SHA-256 validator
│
├── research/                           <-- Background research artifacts
│
├── tests/                              <-- Pytest regression suite
│
└── logs/                               <-- Execution Transcripts & Gatekeeper Reviews
```

- [ ] **Step 2: Verify by inspection**

Run: `python - <<'PY'
import pathlib
readme = pathlib.Path("README.md").read_text(encoding="utf-8")
assert "reviewer.json" not in readme
assert "sha256_verifier.py" not in readme
assert "docs/AMIGO_AGENTS_HARNESS_BLUEPRINT.md" in readme
print("OK")
PY`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: fix README repository layout to match actual filesystem"
```

---

### Task 5: Fix broken relative links in `reviews/AMIGO_AGENTS_PROJECT_REVIEW_REPORT.md`

**Files:**
- Modify: `reviews/AMIGO_AGENTS_PROJECT_REVIEW_REPORT.md:21,33`

- [ ] **Step 1: Fix the two links**

Line 21: change `[AMIGO_AGENTS_HARNESS_BLUEPRINT.md](../AMIGO_AGENTS_HARNESS_BLUEPRINT.md)` to `[AMIGO_AGENTS_HARNESS_BLUEPRINT.md](../docs/AMIGO_AGENTS_HARNESS_BLUEPRINT.md)`

Line 33: change `[implementation_plan.md](../implementation_plan.md)` to `[implementation_plan.md](../docs/implementation_plan.md)`

- [ ] **Step 2: Verify the targets resolve**

Run: `test -f docs/AMIGO_AGENTS_HARNESS_BLUEPRINT.md && test -f docs/implementation_plan.md && echo OK`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add reviews/AMIGO_AGENTS_PROJECT_REVIEW_REPORT.md
git commit -m "docs: fix broken relative links after docs/ reorg"
```

---

### Task 6: Remove dangling `Directive-1.md` references

**Files:**
- Modify: `AGENTS.md:16`
- Modify: `README.md:68` (post-Task-4 line numbers may shift; match by text, not line number)
- Modify: `docs/implementation_plan.md:88`

- [ ] **Step 1: Edit `AGENTS.md:16`**

From: `- **Amigo-Gatekeeper (Gemini):** Focuses on substantive code reviews (\`Directive-1.md\`), cryptographic SHA-256 hash checks, strict JSON validation (\`allow_nan=False\`), and security threat audits.`
To: `- **Amigo-Gatekeeper (Gemini):** Focuses on substantive code reviews, cryptographic SHA-256 hash checks, strict JSON validation (\`allow_nan=False\`), and security threat audits.`

- [ ] **Step 2: Edit `README.md` Core Features bullet**

From: `- **Amigo-Gatekeeper (Gemini):** Audits code against security guidelines (\`Directive-1.md\`), verifies file table hashes, and checks strict schema constraints.`
To: `- **Amigo-Gatekeeper (Gemini):** Audits code against security guidelines, verifies file table hashes, and checks strict schema constraints.`

- [ ] **Step 3: Edit `docs/implementation_plan.md:88`**

From: `- [ ] Implement \`agents/gatekeeper.py\` (Amigo-Gatekeeper) using Gemini rules (\`Directive-1.md\`) to perform substantive gate reviews.`
To: `- [ ] Implement \`agents/gatekeeper.py\` (Amigo-Gatekeeper) using Gemini review rules to perform substantive gate reviews.`

- [ ] **Step 4: Verify no dangling reference remains**

Run: `grep -rn "Directive-1" --include=*.md .` (excluding `reviews/`, which is a report snapshot, not a live doc)
Expected: no matches in `AGENTS.md`, `README.md`, or `docs/`

- [ ] **Step 5: Commit**

```bash
git add AGENTS.md README.md docs/implementation_plan.md
git commit -m "docs: remove dangling Directive-1.md references"
```

---

### Task 7: Fix misleading "orchestrates gatekeeper loops" docstrings

**Files:**
- Modify: `harness/runner.py:2-4`
- Modify: `harness/remediation_loop.py:1-3,12`

- [ ] **Step 1: Fix `harness/runner.py` module docstring**

From:
```python
"""
Amigo Agents Harness CLI Runner
Orchestrates multi-agent builder & gatekeeper review loops.
"""
```
To:
```python
"""
Amigo Agents Harness CLI Runner
Collects git/task evidence for a target directory. Gate validation is
performed by native SDD-Core tooling, not by this harness.
"""
```

- [ ] **Step 2: Fix `harness/remediation_loop.py` docstrings**

Module docstring, from:
```python
"""
Amigo Agents External Task Dispatcher
Runs external code generation and review dispatching for target tasks.
"""
```
To:
```python
"""
Amigo Agents External Task Dispatcher
Collects evidence for a target task. Gate validation is performed by
native SDD-Core tooling, not by this dispatcher.
"""
```

Function docstring, from:
```python
    """Collect git evidence and dispatch external agent workflow."""
```
To:
```python
    """Collect git evidence for the target task (no gate validation here)."""
```

- [ ] **Step 3: Verify**

Run: `python -m pytest tests/test_runner_cli.py -v`
Expected: PASS (docstring-only change, no behavior change)

- [ ] **Step 4: Commit**

```bash
git add harness/runner.py harness/remediation_loop.py
git commit -m "docs: correct docstrings that overclaimed a gatekeeper review loop"
```

---

### Task 8: Add truncation markers to evidence/prompt output

**Files:**
- Modify: `harness/evidence_collector.py:32-37`
- Modify: `agents/gatekeeper.py:16-21`
- Create: `tests/test_evidence_collector.py`
- Create: `tests/test_gatekeeper.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_evidence_collector.py
from __future__ import annotations

import harness.evidence_collector as ec


def _fake_git_status(target_dir):
    return {"is_git": True, "branch": "main", "modified_count": 0, "modified_files": []}


def test_git_diff_truncation_flag_true_when_diff_exceeds_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "get_git_status", _fake_git_status)
    monkeypatch.setattr(ec, "get_git_diff", lambda target_dir: "x" * 2500)
    evidence = ec.collect_task_evidence(tmp_path)
    assert evidence["git_diff_truncated"] is True
    assert len(evidence["git_diff_summary"]) == 2000


def test_git_diff_truncation_flag_false_when_diff_short(tmp_path, monkeypatch):
    monkeypatch.setattr(ec, "get_git_status", _fake_git_status)
    monkeypatch.setattr(ec, "get_git_diff", lambda target_dir: "short diff")
    evidence = ec.collect_task_evidence(tmp_path)
    assert evidence["git_diff_truncated"] is False
```

```python
# tests/test_gatekeeper.py
from agents.gatekeeper import AmigoGatekeeper


def test_format_review_prompt_marks_truncation():
    gk = AmigoGatekeeper(api_key="unused")
    prompt = gk.format_review_prompt("task", "x" * 4000)
    assert "[...diff truncated...]" in prompt


def test_format_review_prompt_no_marker_when_short():
    gk = AmigoGatekeeper(api_key="unused")
    prompt = gk.format_review_prompt("task", "short diff")
    assert "[...diff truncated...]" not in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_evidence_collector.py tests/test_gatekeeper.py -v`
Expected: FAIL — `KeyError: 'git_diff_truncated'` and `AssertionError` (no marker present).

- [ ] **Step 3: Fix `harness/evidence_collector.py`**

Replace the `return` block (current lines 32-37):
```python
    diff_truncated = bool(git_diff) and len(git_diff) > 2000
    return {
        "target_dir": str(target_dir),
        "git_status": git_info,
        "git_diff_summary": git_diff[:2000] if git_diff else "NO_UNCOMMITTED_CHANGES",
        "git_diff_truncated": diff_truncated,
        "file_evidence": file_evidence,
    }
```

- [ ] **Step 4: Fix `agents/gatekeeper.py`**

```python
    def format_review_prompt(self, patch_summary: str, diff_text: str) -> str:
        """Format review prompt for external model inspection."""
        truncated_diff = diff_text[:3000]
        notice = "\n[...diff truncated...]\n" if len(diff_text) > 3000 else ""
        return (
            f"Review Request for Task: {patch_summary}\n\n"
            f"Diff Summary:\n{truncated_diff}{notice}"
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_evidence_collector.py tests/test_gatekeeper.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add harness/evidence_collector.py agents/gatekeeper.py tests/test_evidence_collector.py tests/test_gatekeeper.py
git commit -m "fix: mark truncated diff evidence instead of silently dropping content"
```

---

### Task 9: Fix misleading `syntax_valid` default for non-JSON focus files

**Files:**
- Modify: `harness/evidence_collector.py:1-30`
- Modify: `tests/test_evidence_collector.py` (append)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_evidence_collector.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_evidence_collector.py -v`
Expected: FAIL — `broken.py` reports `syntax_valid: True` (bug), `.txt` reports `"OK"` instead of `"NOT_CHECKED"`.

- [ ] **Step 3: Fix `harness/evidence_collector.py`**

Add `import ast` to the imports (top of file, alongside `from pathlib import Path`; remove the now-unused `import json` in the same edit — see Task 10).

Replace the per-file evidence block (current lines 22-30):
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_evidence_collector.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add harness/evidence_collector.py tests/test_evidence_collector.py
git commit -m "fix: perform real Python syntax validation instead of assuming valid"
```

---

### Task 10: Dependency cleanup

**Files:**
- Modify: `requirements.txt`
- Modify: `harness/evidence_collector.py` (remove unused `import json`, already folded into Task 9's edit — verify here)

- [ ] **Step 1: Rewrite `requirements.txt`**

```text
pytest>=8.0.0
```

- [ ] **Step 2: Verify no other unused imports remain**

Run: `python - <<'PY'
import ast, pathlib
for path in ["harness/evidence_collector.py", "harness/config.py", "harness/runner.py", "harness/remediation_loop.py", "agents/gatekeeper.py", "tools/git_adapter.py", "tools/linter_adapter.py"]:
    src = pathlib.Path(path).read_text(encoding="utf-8")
    assert "import json" not in src or "json." in src, f"{path}: unused json import"
print("OK")
PY`
Expected: `OK`

- [ ] **Step 3: Run the full test suite**

Run: `python -m pip install -r requirements.txt && python -m pytest -q`
Expected: all tests pass, 0 failures.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore: prune unused dependencies, keep only pytest"
```

---

### Task 11: Add LICENSE

**Files:**
- Create: `LICENSE`

- [ ] **Step 1: Add MIT license**

Standard MIT text, copyright holder `Amigo Agents` (matches this repo's configured git commit identity), year 2026.

- [ ] **Step 2: Verify**

Run: `test -f LICENSE && head -1 LICENSE`
Expected: `MIT License`

- [ ] **Step 3: Commit**

```bash
git add LICENSE
git commit -m "docs: add MIT license"
```

---

### Task 12: Final verification sweep

**Files:** none (verification only)

- [ ] **Step 1: Run full suite**

Run: `python -m pytest -q`
Expected: all green, 0 failures.

- [ ] **Step 2: Re-run the two crash repros manually**

Run: `python harness/runner.py --status`
Expected: prints status block, no traceback, correct native-Windows default target path.

Run: `python harness/runner.py`
Expected: prints version banner, no traceback.

- [ ] **Step 3: Confirm no unintended files changed**

Run: `git status --porcelain`
Expected: only the files touched by Tasks 1-11 (plus the pre-existing untracked `docs/`, `reviews/`, `.agents/` reorg from earlier in the session, unless already committed).
