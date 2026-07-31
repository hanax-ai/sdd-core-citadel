# Phase 4 Multi-Agent Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the real Researcher → Builder → Gatekeeper collaboration loop per `docs/superpowers/specs/2026-07-30-phase4-multi-agent-engine-design.md` — three LLM-backed agent classes, a remediation loop that runs them for up to 3 rounds, and a JSON transcript per run.

**Architecture:** `harness/llm_clients.py` holds thin per-provider call wrappers (fail-fast key checks + the actual SDK calls). Three new/extended agent classes (`agents/researcher.py`, `agents/builder.py`, `agents/gatekeeper.py`) each call exactly one wrapper. `harness/remediation_loop.py` orchestrates them and writes the transcript. Every agent-layer test mocks its `llm_clients` function — no test calls a real API.

**Tech Stack:** `anthropic`, `openai`, `google-genai` Python SDKs (new dependencies) + stdlib.

## Global Constraints

- Propose-only: `AmigoBuilder.propose_patch` returns text; nothing in this plan writes to `target_dir`.
- Role → provider mapping: Researcher = Anthropic (`claude-opus-5` default), Builder = OpenAI (`gpt-5.3-codex` default), Gatekeeper = Gemini (`gemini-3.1-pro` default) — all three overridable via `ANTHROPIC_MODEL`/`OPENAI_MODEL`/`GEMINI_MODEL` env vars.
- `MAX_ROUNDS = 3`.
- No automated test makes a real network call. `llm_clients`'s SDK imports are lazy (inside each function body) so fail-fast tests pass with zero provider packages installed.
- `python -m pytest -q` must be green at the end.

---

### Task 1: `harness/llm_clients.py` — provider call wrappers

**Files:**
- Create: `harness/llm_clients.py`
- Create: `tests/test_llm_clients.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `call_researcher(system: str, user: str) -> str`, `call_builder(system: str, user: str) -> str`, `call_gatekeeper(system: str, user: str) -> str` — all raise `RuntimeError` naming the missing env var if that provider's API key is unset, before any SDK import or network call.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_llm_clients.py
import pytest

import harness.llm_clients as llm_clients


def test_call_researcher_raises_without_anthropic_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        llm_clients.call_researcher("system", "user")


def test_call_builder_raises_without_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        llm_clients.call_builder("system", "user")


def test_call_gatekeeper_raises_without_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        llm_clients.call_gatekeeper("system", "user")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_llm_clients.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'harness.llm_clients'`

- [ ] **Step 3: Write `harness/llm_clients.py`**

```python
"""
Amigo Agents LLM Provider Clients
Thin per-provider call wrappers for the Researcher, Builder, and
Gatekeeper agents. SDK imports are lazy so a missing provider package
never breaks the fail-fast key check for the other two providers.
"""

from __future__ import annotations
import os

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"
DEFAULT_OPENAI_MODEL = "gpt-5.3-codex"
DEFAULT_GEMINI_MODEL = "gemini-3.1-pro"


def call_researcher(system: str, user: str) -> str:
    """Call the Anthropic API for Amigo-Researcher (Claude)."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set; required for Amigo-Researcher.")

    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    model = os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
    response = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return next((block.text for block in response.content if block.type == "text"), "")


def call_builder(system: str, user: str) -> str:
    """Call the OpenAI API for Amigo-Builder (Codex)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set; required for Amigo-Builder.")

    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return response.choices[0].message.content or ""


def call_gatekeeper(system: str, user: str) -> str:
    """Call the Gemini API for Amigo-Gatekeeper."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set; required for Amigo-Gatekeeper.")

    from google import genai

    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    response = client.models.generate_content(model=model, contents=f"{system}\n\n{user}")
    return response.text or ""
```

- [ ] **Step 4: Update `requirements.txt`**

```text
pytest>=8.0.0
anthropic>=0.40.0
openai>=1.50.0
google-genai>=0.1.0
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_llm_clients.py -v`
Expected: PASS (3 passed) — note these pass without `anthropic`/`openai`/`google-genai` installed, since the key check runs before the lazy import.

- [ ] **Step 6: Commit**

```bash
git add harness/llm_clients.py tests/test_llm_clients.py requirements.txt
git commit -m "feat: add per-provider LLM call wrappers with fail-fast key checks"
```

---

### Task 2: `agents/researcher.py`

**Files:**
- Create: `agents/researcher.py`
- Create: `tests/test_researcher.py`

**Interfaces:**
- Consumes: `harness.llm_clients.call_researcher(system, user) -> str` (Task 1)
- Produces: `AmigoResearcher.analyze(task: str, evidence: dict) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_researcher.py
import agents.researcher as researcher_module
from agents.researcher import AmigoResearcher


def test_analyze_calls_researcher_and_returns_notes(monkeypatch):
    captured = {}

    def fake_call_researcher(system, user):
        captured["system"] = system
        captured["user"] = user
        return "research notes here"

    monkeypatch.setattr(researcher_module, "call_researcher", fake_call_researcher)

    result = AmigoResearcher().analyze("fix the bug", {"git_status": {"branch": "main"}})

    assert result == "research notes here"
    assert "fix the bug" in captured["user"]
    assert "git_status" in captured["user"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_researcher.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.researcher'`

- [ ] **Step 3: Write `agents/researcher.py`**

```python
"""
Amigo-Researcher Agent (Claude)
Deep spec analysis and dependency research before code authoring begins.
"""

from __future__ import annotations
from harness.llm_clients import call_researcher

SYSTEM_PROMPT = (
    "You are Amigo-Researcher. Analyze the task and the provided evidence "
    "(git status, diff, file metadata) and produce concise research notes "
    "covering: relevant files, constraints, and open questions the builder "
    "should account for. Do not write code."
)


class AmigoResearcher:
    """Spec and dependency analyst."""

    def analyze(self, task: str, evidence: dict) -> str:
        """Produce research notes for the given task and evidence."""
        user = f"Task: {task}\n\nEvidence:\n{evidence}"
        return call_researcher(SYSTEM_PROMPT, user)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_researcher.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add agents/researcher.py tests/test_researcher.py
git commit -m "feat: add AmigoResearcher spec/dependency analysis agent"
```

---

### Task 3: `agents/builder.py`

**Files:**
- Create: `agents/builder.py`
- Create: `tests/test_builder.py`

**Interfaces:**
- Consumes: `harness.llm_clients.call_builder(system, user) -> str` (Task 1)
- Produces: `AmigoBuilder.propose_patch(task, notes, evidence, prior_findings=None) -> str`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_builder.py
import agents.builder as builder_module
from agents.builder import AmigoBuilder


def test_propose_patch_calls_builder_and_returns_patch(monkeypatch):
    captured = {}

    def fake_call_builder(system, user):
        captured["user"] = user
        return "--- a/file.py\n+++ b/file.py\n"

    monkeypatch.setattr(builder_module, "call_builder", fake_call_builder)

    result = AmigoBuilder().propose_patch("fix the bug", "notes text", {"git_status": {}})

    assert result.startswith("--- a/file.py")
    assert "fix the bug" in captured["user"]
    assert "notes text" in captured["user"]
    assert "None" in captured["user"]  # no prior findings on round 1


def test_propose_patch_includes_prior_findings(monkeypatch):
    captured = {}

    def fake_call_builder(system, user):
        captured["user"] = user
        return "patch"

    monkeypatch.setattr(builder_module, "call_builder", fake_call_builder)

    AmigoBuilder().propose_patch(
        "fix the bug", "notes", {}, prior_findings=["missing null check"]
    )

    assert "missing null check" in captured["user"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_builder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'agents.builder'`

- [ ] **Step 3: Write `agents/builder.py`**

```python
"""
Amigo-Builder Agent (Codex / OpenAI)
Proposes a text patch for a task. Never writes files -- output is
reviewed by Amigo-Gatekeeper and applied by a human.
"""

from __future__ import annotations
from harness.llm_clients import call_builder

SYSTEM_PROMPT = (
    "You are Amigo-Builder. Given a task, research notes, evidence, and "
    "(on remediation rounds) prior reviewer findings, propose a unified "
    "diff patch that accomplishes the task. Output only the patch, no "
    "prose."
)


class AmigoBuilder:
    """Code patch proposer. Output is a text diff, never applied automatically."""

    def propose_patch(
        self,
        task: str,
        notes: str,
        evidence: dict,
        prior_findings: list[str] | None = None,
    ) -> str:
        """Propose a patch for the given task, informed by prior findings if any."""
        findings_text = (
            "\n".join(f"- {f}" for f in prior_findings) if prior_findings else "None"
        )
        user = (
            f"Task: {task}\n\n"
            f"Research notes:\n{notes}\n\n"
            f"Evidence:\n{evidence}\n\n"
            f"Prior reviewer findings to address:\n{findings_text}"
        )
        return call_builder(SYSTEM_PROMPT, user)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_builder.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add agents/builder.py tests/test_builder.py
git commit -m "feat: add AmigoBuilder patch-proposal agent"
```

---

### Task 4: `agents/gatekeeper.py` — add `review()`

**Files:**
- Modify: `agents/gatekeeper.py`
- Create: `tests/test_gatekeeper_review.py`

**Interfaces:**
- Consumes: `harness.llm_clients.call_gatekeeper(system, user) -> str` (Task 1), existing `AmigoGatekeeper.format_review_prompt` (unchanged)
- Produces: `AmigoGatekeeper.review(patch_text: str, evidence: dict) -> list[str]` (empty list = pass)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_gatekeeper_review.py
import agents.gatekeeper as gatekeeper_module
from agents.gatekeeper import AmigoGatekeeper


def test_review_returns_empty_list_on_pass(monkeypatch):
    monkeypatch.setattr(gatekeeper_module, "call_gatekeeper", lambda system, user: "PASS")
    findings = AmigoGatekeeper(api_key="unused").review("diff text", {"git_status": {}})
    assert findings == []


def test_review_returns_findings_list_when_not_passing(monkeypatch):
    monkeypatch.setattr(
        gatekeeper_module,
        "call_gatekeeper",
        lambda system, user: "Missing test coverage\nUnused import",
    )
    findings = AmigoGatekeeper(api_key="unused").review("diff text", {"git_status": {}})
    assert findings == ["Missing test coverage", "Unused import"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_gatekeeper_review.py -v`
Expected: FAIL — `AttributeError: 'AmigoGatekeeper' object has no attribute 'review'`

- [ ] **Step 3: Add `review()` to `agents/gatekeeper.py`**

Add this import at the top of the file, alongside the existing `import os`:

```python
from harness.llm_clients import call_gatekeeper
```

Add this constant after the imports:

```python
SYSTEM_PROMPT = (
    "You are Amigo-Gatekeeper. Review the proposed patch against the "
    "evidence. If it is correct, complete, and introduces no defects, "
    "respond with exactly the word PASS. Otherwise respond with one "
    "finding per line, each a concrete, actionable problem."
)
```

Add this method to the `AmigoGatekeeper` class, after `format_review_prompt`:

```python
    def review(self, patch_text: str, evidence: dict) -> list[str]:
        """Review a proposed patch. Returns an empty list on pass."""
        user = self.format_review_prompt("Proposed patch under review", patch_text)
        user += f"\n\nEvidence:\n{evidence}"
        response = call_gatekeeper(SYSTEM_PROMPT, user)
        if response.strip().upper().startswith("PASS"):
            return []
        return [line.strip() for line in response.splitlines() if line.strip()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_gatekeeper_review.py tests/test_gatekeeper.py -v`
Expected: PASS (4 passed — 2 new + 2 existing truncation-marker tests)

- [ ] **Step 5: Commit**

```bash
git add agents/gatekeeper.py tests/test_gatekeeper_review.py
git commit -m "feat: add AmigoGatekeeper.review() for real patch review"
```

---

### Task 5: `harness/remediation_loop.py` rewrite + CLI surface

**Files:**
- Modify: `harness/remediation_loop.py`
- Modify: `harness/runner.py`
- Create: `tests/test_remediation_loop.py`

**Interfaces:**
- Consumes: `AmigoResearcher.analyze`, `AmigoBuilder.propose_patch`, `AmigoGatekeeper.review` (Tasks 2-4), `collect_task_evidence` (existing), `LOGS_DIR` (existing, `harness.config`)
- Produces: `run_collaboration_cycle(target_dir: Path, task_description: str, log_dir: Path = LOGS_DIR) -> dict` with keys `task`, `git_status`, `verdict` (`"PASS"` or `"UNRESOLVED"`), `patch_text`, `log_path`, `rounds`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_remediation_loop.py
from __future__ import annotations

import json

import harness.remediation_loop as remediation_loop
from harness.remediation_loop import run_collaboration_cycle


def _patch_agents(monkeypatch, findings_sequence):
    calls = {"analyze": 0, "propose": 0, "review": 0}

    def fake_analyze(self, task, evidence):
        calls["analyze"] += 1
        return "notes"

    def fake_propose(self, task, notes, evidence, prior_findings=None):
        calls["propose"] += 1
        return f"patch-{calls['propose']}"

    findings_iter = iter(findings_sequence)

    def fake_review(self, patch_text, evidence):
        calls["review"] += 1
        return next(findings_iter)

    monkeypatch.setattr(remediation_loop.AmigoResearcher, "analyze", fake_analyze)
    monkeypatch.setattr(remediation_loop.AmigoBuilder, "propose_patch", fake_propose)
    monkeypatch.setattr(remediation_loop.AmigoGatekeeper, "review", fake_review)
    return calls


def test_loop_passes_after_findings_then_empty(tmp_path, monkeypatch):
    calls = _patch_agents(monkeypatch, [["issue A"], ["issue B"], []])

    result = run_collaboration_cycle(tmp_path, "fix the bug", log_dir=tmp_path / "logs")

    assert result["verdict"] == "PASS"
    assert calls["analyze"] == 1
    assert calls["propose"] == 3
    assert calls["review"] == 3
    assert len(result["rounds"]) == 3
    assert result["rounds"][-1]["findings"] == []

    log_files = list((tmp_path / "logs").glob("*.json"))
    assert len(log_files) == 1
    logged = json.loads(log_files[0].read_text(encoding="utf-8"))
    assert logged["verdict"] == "PASS"
    assert len(logged["rounds"]) == 3


def test_loop_stops_at_max_rounds_when_findings_persist(tmp_path, monkeypatch):
    calls = _patch_agents(monkeypatch, [["issue A"], ["issue B"], ["issue C"]])

    result = run_collaboration_cycle(tmp_path, "fix the bug", log_dir=tmp_path / "logs")

    assert result["verdict"] == "UNRESOLVED"
    assert calls["propose"] == 3


def test_researcher_called_exactly_once(tmp_path, monkeypatch):
    calls = _patch_agents(monkeypatch, [[]])
    run_collaboration_cycle(tmp_path, "fix the bug", log_dir=tmp_path / "logs")
    assert calls["analyze"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_remediation_loop.py -v`
Expected: FAIL — `AttributeError: module 'harness.remediation_loop' has no attribute 'AmigoResearcher'` (current module doesn't import the agent classes yet)

- [ ] **Step 3: Rewrite `harness/remediation_loop.py`**

```python
"""
Amigo Agents Collaboration Loop
Runs the Researcher -> Builder -> Gatekeeper remediation cycle for a
target task and writes a full transcript to logs/.
"""

from __future__ import annotations
import json
import re
from datetime import datetime
from pathlib import Path

from agents.builder import AmigoBuilder
from agents.gatekeeper import AmigoGatekeeper
from agents.researcher import AmigoResearcher
from harness.config import LOGS_DIR
from harness.evidence_collector import collect_task_evidence

MAX_ROUNDS = 3


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:50] or "task"


def run_collaboration_cycle(
    target_dir: Path, task_description: str, log_dir: Path = LOGS_DIR
) -> dict:
    """Run the researcher/builder/gatekeeper remediation cycle for the target task."""
    evidence = collect_task_evidence(target_dir)

    researcher = AmigoResearcher()
    notes = researcher.analyze(task_description, evidence)

    builder = AmigoBuilder()
    gatekeeper = AmigoGatekeeper()

    rounds = []
    prior_findings = None
    verdict = "UNRESOLVED"
    patch_text = ""

    for round_num in range(1, MAX_ROUNDS + 1):
        patch_text = builder.propose_patch(task_description, notes, evidence, prior_findings)
        findings = gatekeeper.review(patch_text, evidence)
        rounds.append({"round": round_num, "patch_text": patch_text, "findings": findings})

        if not findings:
            verdict = "PASS"
            break
        prior_findings = findings

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

    return {
        "task": task_description,
        "git_status": evidence["git_status"],
        "verdict": verdict,
        "patch_text": patch_text,
        "log_path": str(log_path),
        "rounds": rounds,
    }
```

- [ ] **Step 4: Update `harness/runner.py`'s `--task` branch**

Replace:
```python
    print(f"🚀 Initializing Amigo Agents for task: {args.task}")
    print(f"📂 Target Directory: {args.target_dir}")
    
    target_path = Path(args.target_dir)
    from harness.remediation_loop import run_collaboration_cycle
    result = run_collaboration_cycle(target_path, args.task)
    
    print("\n✨ Amigo Agents Collaboration Cycle Complete!")
    return 0
```
With:
```python
    print(f"🚀 Initializing Amigo Agents for task: {args.task}")
    print(f"📂 Target Directory: {args.target_dir}")
    
    target_path = Path(args.target_dir)
    from harness.remediation_loop import run_collaboration_cycle
    result = run_collaboration_cycle(target_path, args.task)
    
    print(f"\n✨ Amigo Agents Collaboration Cycle Complete! Verdict: {result['verdict']}")
    print(f"📄 Transcript: {result['log_path']}")
    print(f"\n--- Proposed Patch ---\n{result['patch_text']}")
    return 0
```

Also update the module docstring (currently reads "Collects git/task evidence for a target directory. Gate validation is performed by native SDD-Core tooling, not by this harness.") to:

```python
"""
Amigo Agents Harness CLI Runner
Orchestrates the Researcher/Builder/Gatekeeper collaboration cycle for
a target directory and task.
"""
```

And in `harness/remediation_loop.py`, the module docstring above is already correct as written in Step 3 (no separate edit needed there).

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_remediation_loop.py -v`
Expected: PASS (3 passed)

Run: `python -m pytest tests/test_runner_cli.py -v`
Expected: PASS (2 passed — `--status` and bare invocation still don't touch the collaboration loop, so no real API calls happen in this test)

- [ ] **Step 6: Commit**

```bash
git add harness/remediation_loop.py harness/runner.py tests/test_remediation_loop.py
git commit -m "feat: wire real Researcher/Builder/Gatekeeper remediation loop"
```

---

### Task 6: Final verification sweep

**Files:** none (verification only)

- [ ] **Step 1: Run full suite**

Run: `python -m pytest -q`
Expected: all green, 0 failures.

- [ ] **Step 2: Attempt installing real provider SDKs**

Run: `python -m pip install -r requirements.txt`
Expected: succeeds (or, if `anthropic`/`openai`/`google-genai` are unavailable in this sandbox's network, note which ones failed — this does not block the test suite, which never imports them).

- [ ] **Step 3: Re-confirm the non-agentic CLI paths still work**

Run: `python harness/runner.py --status`
Expected: prints status block, no traceback.

- [ ] **Step 4: Confirm git status clean**

Run: `git status --porcelain`
Expected: empty (all work committed by Tasks 1-5).
