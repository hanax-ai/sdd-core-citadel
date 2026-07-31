# Async + Structured Findings + Incremental Events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite the Phase 4 collaboration engine to be async-native (so a future FastAPI bridge doesn't block its event loop), give Gatekeeper structured severity-classified findings instead of freeform strings (fixing tonight's "never passes because it treats pre-existing conditions as blocking" behavior with a principled rule: only `CRITICAL`/`WARNING` block, `NOTE` doesn't), add an incremental event-callback hook so a caller can observe progress as it happens, and correct the stale model-name example in the dashboard spec.

**Architecture:** Every `call_*` in `harness/llm_clients.py` becomes `async def` using each SDK's real async client (`AsyncAnthropic`, `AsyncOpenAI`, `client.aio.models.generate_content` — all confirmed to exist), returning a dict (`text`, `input_tokens`, `output_tokens`, `elapsed_ms`) instead of a bare string. Every agent method becomes `async def`. `run_collaboration_cycle` becomes `async def` with an optional `on_event: Callable[[dict], None]` callback invoked at each stage transition, agent output, and token metric point, plus an optional `run_id` threaded into every emitted event. Gatekeeper requests structured JSON output from Gemini (`response_mime_type="application/json"`, `response_schema=...` — both confirmed real fields) instead of parsing freeform lines.

**Tech Stack:** `anthropic`, `openai`, `google-genai` async clients (all already installed) + `pytest-asyncio` (new test dependency).

## Global Constraints

- No behavior change to the propose-only guarantee — Builder still never writes files.
- `MAX_ROUNDS = 3` unchanged.
- Verdict rule: `PASS` when no finding has `severity` in `{"CRITICAL", "WARNING"}` — `NOTE`-severity findings don't block.
- CLI (`runner.py --task`) keeps working with no `on_event` callback supplied (defaults to `None`, CLI behavior unchanged apart from the async wrapper).
- **Gemini live verification is currently blocked** by the free-tier daily quota exhausted earlier tonight — implement and unit-test everything with mocks; a real end-to-end Gemini call is a follow-up once quota resets.
- `python -m pytest -q` must be green at the end.

---

### Task 1: Add `pytest-asyncio`

**Files:**
- Modify: `requirements.txt`
- Create: `pytest.ini`

- [ ] **Step 1:** Add `pytest-asyncio>=0.24.0` to `requirements.txt`.
- [ ] **Step 2:** Create `pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
```
- [ ] **Step 3:** Run: `python -m pip install pytest-asyncio`
- [ ] **Step 4:** Run: `python -m pytest -q` — expected: still 27 passed (no async tests yet, just confirms the plugin doesn't break collection).
- [ ] **Step 5: Commit**
```bash
git add requirements.txt pytest.ini
git commit -m "chore: add pytest-asyncio for upcoming async test suite"
```

---

### Task 2: `harness/llm_clients.py` — async rewrite, dict return, structured Gemini output

**Files:**
- Modify: `harness/llm_clients.py`
- Modify: `tests/test_llm_clients.py`

**Interfaces:**
- Produces: `call_researcher`, `call_builder`, `call_gatekeeper` all become `async def (...) -> dict` with keys `text: str`, `input_tokens: int`, `output_tokens: int`, `elapsed_ms: int`. `call_gatekeeper` additionally returns `findings: list[dict]` (each `{"line": int, "severity": str, "text": str}`) instead of relying on the caller to parse `text`.

- [ ] **Step 1: Update the failing tests**

Replace `tests/test_llm_clients.py` with:
```python
import pytest

import harness.llm_clients as llm_clients


async def test_call_researcher_raises_without_anthropic_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        await llm_clients.call_researcher("system", "user")


async def test_call_builder_raises_without_openai_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        await llm_clients.call_builder("system", "user")


async def test_call_gatekeeper_raises_without_gemini_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
        await llm_clients.call_gatekeeper("system", "user")
```

- [ ] **Step 2:** Run: `python -m pytest tests/test_llm_clients.py -v` — expected FAIL (functions aren't async yet, or `await` on a non-awaitable).

- [ ] **Step 3: Rewrite `harness/llm_clients.py`**
```python
"""
Amigo Agents LLM Provider Clients
Thin per-provider async call wrappers for the Researcher, Builder, and
Gatekeeper agents. SDK imports are lazy so a missing provider package
never breaks the fail-fast key check for the other two providers.
"""

from __future__ import annotations
import json
import os
import time

DEFAULT_ANTHROPIC_MODEL = "claude-opus-5"
DEFAULT_OPENAI_MODEL = "gpt-5.3-codex"
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"

FINDINGS_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line": {
                        "type": "integer",
                        "description": "Line number the finding applies to, or 0 if not line-specific.",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["CRITICAL", "WARNING", "NOTE"],
                    },
                    "text": {"type": "string"},
                },
                "required": ["line", "severity", "text"],
            },
        },
    },
    "required": ["findings"],
}


async def call_researcher(system: str, user: str) -> dict:
    """Call the Anthropic API for Amigo-Researcher (Claude)."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set; required for Amigo-Researcher.")

    import anthropic

    client = anthropic.AsyncAnthropic(api_key=api_key)
    model = os.getenv("ANTHROPIC_MODEL", DEFAULT_ANTHROPIC_MODEL)
    started = time.monotonic()
    try:
        response = await client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.AnthropicError as exc:
        raise RuntimeError(f"Amigo-Researcher (Anthropic) call failed: {exc}") from exc
    text = next((block.text for block in response.content if block.type == "text"), "")
    return {
        "text": text,
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


async def call_builder(system: str, user: str) -> dict:
    """Call the OpenAI API for Amigo-Builder (Codex)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set; required for Amigo-Builder.")

    import openai
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)
    model = os.getenv("OPENAI_MODEL", DEFAULT_OPENAI_MODEL)
    started = time.monotonic()
    try:
        response = await client.responses.create(
            model=model,
            instructions=system,
            input=user,
        )
    except openai.OpenAIError as exc:
        raise RuntimeError(f"Amigo-Builder (OpenAI) call failed: {exc}") from exc
    return {
        "text": response.output_text or "",
        "input_tokens": response.usage.input_tokens if response.usage else 0,
        "output_tokens": response.usage.output_tokens if response.usage else 0,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


async def call_gatekeeper(system: str, user: str) -> dict:
    """Call the Gemini API for Amigo-Gatekeeper. Returns structured findings."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set; required for Amigo-Gatekeeper.")

    from google import genai
    from google.genai import errors as genai_errors
    from google.genai import types as genai_types

    client = genai.Client(api_key=api_key)
    model = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    started = time.monotonic()
    try:
        response = await client.aio.models.generate_content(
            model=model,
            contents=f"{system}\n\n{user}",
            config=genai_types.GenerateContentConfig(
                thinking_config=genai_types.ThinkingConfig(thinking_level="HIGH"),
                response_mime_type="application/json",
                response_schema=FINDINGS_JSON_SCHEMA,
            ),
        )
    except genai_errors.APIError as exc:
        raise RuntimeError(f"Amigo-Gatekeeper (Gemini) call failed: {exc}") from exc

    raw_text = response.text or "{}"
    try:
        parsed = json.loads(raw_text)
        findings = parsed.get("findings", [])
    except (json.JSONDecodeError, AttributeError):
        findings = [{"line": 0, "severity": "WARNING", "text": f"Gatekeeper returned unparseable output: {raw_text[:200]}"}]

    usage = getattr(response, "usage_metadata", None)
    return {
        "text": raw_text,
        "findings": findings,
        "input_tokens": getattr(usage, "prompt_token_count", 0) or 0,
        "output_tokens": getattr(usage, "candidates_token_count", 0) or 0,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }
```

- [ ] **Step 4:** Run: `python -m pytest tests/test_llm_clients.py -v` — expected PASS (3 passed).
- [ ] **Step 5: Commit**
```bash
git add harness/llm_clients.py tests/test_llm_clients.py
git commit -m "feat: async provider clients with structured Gemini findings + token metrics"
```

---

### Task 3: `agents/researcher.py` — async

**Files:**
- Modify: `agents/researcher.py`
- Modify: `tests/test_researcher.py`

- [ ] **Step 1:** Update test to mock an async `call_researcher` and await `analyze`:
```python
import agents.researcher as researcher_module
from agents.researcher import AmigoResearcher


async def test_analyze_calls_researcher_and_returns_notes(monkeypatch):
    captured = {}

    async def fake_call_researcher(system, user):
        captured["system"] = system
        captured["user"] = user
        return {"text": "research notes here", "input_tokens": 10, "output_tokens": 5, "elapsed_ms": 100}

    monkeypatch.setattr(researcher_module, "call_researcher", fake_call_researcher)

    result = await AmigoResearcher().analyze("fix the bug", {"git_status": {"branch": "main"}})

    assert result == "research notes here"
    assert "fix the bug" in captured["user"]
    assert "git_status" in captured["user"]
```
- [ ] **Step 2:** Run: `python -m pytest tests/test_researcher.py -v` — expected FAIL.
- [ ] **Step 3:** Rewrite `agents/researcher.py`'s `analyze`:
```python
    async def analyze(self, task: str, evidence: dict) -> str:
        """Produce research notes for the given task and evidence."""
        user = f"Task: {task}\n\nEvidence:\n{evidence}"
        result = await call_researcher(SYSTEM_PROMPT, user)
        return result["text"]
```
(Change `def analyze` to `async def analyze`.)
- [ ] **Step 4:** Run: `python -m pytest tests/test_researcher.py -v` — expected PASS.
- [ ] **Step 5: Commit**
```bash
git add agents/researcher.py tests/test_researcher.py
git commit -m "feat: make AmigoResearcher.analyze async"
```

---

### Task 4: `agents/builder.py` — async + severity-aware prior findings

**Files:**
- Modify: `agents/builder.py`
- Modify: `tests/test_builder.py`

- [ ] **Step 1:** Update tests for async + structured findings:
```python
import agents.builder as builder_module
from agents.builder import AmigoBuilder


async def test_propose_patch_calls_builder_and_returns_patch(monkeypatch):
    captured = {}

    async def fake_call_builder(system, user):
        captured["user"] = user
        return {"text": "--- a/file.py\n+++ b/file.py\n", "input_tokens": 1, "output_tokens": 1, "elapsed_ms": 1}

    monkeypatch.setattr(builder_module, "call_builder", fake_call_builder)

    result = await AmigoBuilder().propose_patch("fix the bug", "notes text", {"git_status": {}})

    assert result.startswith("--- a/file.py")
    assert "fix the bug" in captured["user"]
    assert "notes text" in captured["user"]
    assert "None" in captured["user"]


async def test_propose_patch_formats_structured_prior_findings(monkeypatch):
    captured = {}

    async def fake_call_builder(system, user):
        captured["user"] = user
        return {"text": "patch", "input_tokens": 1, "output_tokens": 1, "elapsed_ms": 1}

    monkeypatch.setattr(builder_module, "call_builder", fake_call_builder)

    await AmigoBuilder().propose_patch(
        "fix the bug",
        "notes",
        {},
        prior_findings=[{"line": 12, "severity": "CRITICAL", "text": "missing null check"}],
    )

    assert "CRITICAL" in captured["user"]
    assert "line 12" in captured["user"]
    assert "missing null check" in captured["user"]
```
- [ ] **Step 2:** Run: `python -m pytest tests/test_builder.py -v` — expected FAIL.
- [ ] **Step 3:** Rewrite `agents/builder.py`:
```python
    async def propose_patch(
        self,
        task: str,
        notes: str,
        evidence: dict,
        prior_findings: list[dict] | None = None,
    ) -> str:
        """Propose a patch for the given task, informed by prior findings if any."""
        if prior_findings:
            findings_text = "\n".join(
                f"- [{f['severity']}] line {f['line']}: {f['text']}" for f in prior_findings
            )
        else:
            findings_text = "None"
        user = (
            f"Task: {task}\n\n"
            f"Research notes:\n{notes}\n\n"
            f"Evidence:\n{evidence}\n\n"
            f"Prior reviewer findings to address:\n{findings_text}"
        )
        result = await call_builder(SYSTEM_PROMPT, user)
        return result["text"]
```
(Change `def propose_patch` to `async def propose_patch`.)
- [ ] **Step 4:** Run: `python -m pytest tests/test_builder.py -v` — expected PASS (2 passed).
- [ ] **Step 5: Commit**
```bash
git add agents/builder.py tests/test_builder.py
git commit -m "feat: make AmigoBuilder.propose_patch async, format structured findings"
```

---

### Task 5: `agents/gatekeeper.py` — async, structured findings, severity-aware pass rule

**Files:**
- Modify: `agents/gatekeeper.py`
- Modify: `tests/test_gatekeeper_review.py`

**Interfaces:**
- Produces: `AmigoGatekeeper.review(patch_text, evidence) -> list[dict]` (each `{"line": int, "severity": str, "text": str}`, empty list = no findings at all). Also produces module-level `has_blocking_findings(findings: list[dict]) -> bool` for `remediation_loop.py` to use for verdict logic.

- [ ] **Step 1:** Replace `tests/test_gatekeeper_review.py`:
```python
import agents.gatekeeper as gatekeeper_module
from agents.gatekeeper import AmigoGatekeeper, has_blocking_findings


async def test_review_returns_structured_findings(monkeypatch):
    async def fake_call_gatekeeper(system, user):
        return {
            "text": "{}",
            "findings": [{"line": 5, "severity": "NOTE", "text": "pre-existing, out of scope"}],
            "input_tokens": 1,
            "output_tokens": 1,
            "elapsed_ms": 1,
        }

    monkeypatch.setattr(gatekeeper_module, "call_gatekeeper", fake_call_gatekeeper)
    findings = await AmigoGatekeeper(api_key="unused").review("diff text", {"git_status": {}})
    assert findings == [{"line": 5, "severity": "NOTE", "text": "pre-existing, out of scope"}]


async def test_review_returns_empty_list_when_no_findings(monkeypatch):
    async def fake_call_gatekeeper(system, user):
        return {"text": "{}", "findings": [], "input_tokens": 1, "output_tokens": 1, "elapsed_ms": 1}

    monkeypatch.setattr(gatekeeper_module, "call_gatekeeper", fake_call_gatekeeper)
    findings = await AmigoGatekeeper(api_key="unused").review("diff text", {"git_status": {}})
    assert findings == []


def test_has_blocking_findings_true_for_critical():
    assert has_blocking_findings([{"line": 1, "severity": "CRITICAL", "text": "x"}]) is True


def test_has_blocking_findings_true_for_warning():
    assert has_blocking_findings([{"line": 1, "severity": "WARNING", "text": "x"}]) is True


def test_has_blocking_findings_false_for_note_only():
    assert has_blocking_findings([{"line": 1, "severity": "NOTE", "text": "x"}]) is False


def test_has_blocking_findings_false_for_empty():
    assert has_blocking_findings([]) is False
```
- [ ] **Step 2:** Run: `python -m pytest tests/test_gatekeeper_review.py -v` — expected FAIL.
- [ ] **Step 3:** Edit `agents/gatekeeper.py`:

Replace the `SYSTEM_PROMPT` constant:
```python
SYSTEM_PROMPT = (
    "You are Amigo-Gatekeeper. Your job is to catch defects this specific "
    "patch introduces, or requirements from the stated task it fails to "
    "meet -- not to audit the surrounding codebase in general. "
    "Classify every observation by severity: "
    "CRITICAL (the patch is broken or actively harmful), "
    "WARNING (a real defect the patch introduces or fails to address that "
    "should block merging), or "
    "NOTE (a pre-existing condition, worth mentioning but out of scope for "
    "this task and should NOT block merging). "
    "Return your findings as the structured JSON object the schema "
    "requires. An empty findings list means the patch is clean."
)
```

Replace `review()` and add `has_blocking_findings`:
```python
    async def review(self, patch_text: str, evidence: dict) -> list[dict]:
        """Review a proposed patch. Returns a list of structured findings (possibly empty)."""
        user = self.format_review_prompt("Proposed patch under review", patch_text)
        user += f"\n\nEvidence:\n{evidence}"
        result = await call_gatekeeper(SYSTEM_PROMPT, user)
        return result["findings"]


def has_blocking_findings(findings: list[dict]) -> bool:
    """CRITICAL and WARNING findings block; NOTE findings don't."""
    return any(f.get("severity") in ("CRITICAL", "WARNING") for f in findings)
```
(Change `def review` to `async def review`; keep `format_review_prompt` as-is.)
- [ ] **Step 4:** Run: `python -m pytest tests/test_gatekeeper_review.py -v` — expected PASS (6 passed).
- [ ] **Step 5: Commit**
```bash
git add agents/gatekeeper.py tests/test_gatekeeper_review.py
git commit -m "feat: structured severity-classified findings + severity-aware pass rule"
```

---

### Task 6: `harness/remediation_loop.py` — async + incremental events + severity verdict

**Files:**
- Modify: `harness/remediation_loop.py`
- Modify: `tests/test_remediation_loop.py`

**Interfaces:**
- Produces: `async def run_collaboration_cycle(target_dir, task_description, log_dir=LOGS_DIR, run_id=None, on_event=None) -> dict`. `on_event`, if given, is called synchronously with a plain dict for each of: `stage_change`, `agent_message`, `token_metric`, `run_complete`.

- [ ] **Step 1:** Update `tests/test_remediation_loop.py` — replace the whole file:
```python
from __future__ import annotations

import json

import harness.remediation_loop as remediation_loop
from harness.remediation_loop import run_collaboration_cycle


def _patch_agents(monkeypatch, findings_sequence):
    calls = {"analyze": 0, "propose": 0, "review": 0}

    async def fake_analyze(self, task, evidence):
        calls["analyze"] += 1
        return "notes"

    async def fake_propose(self, task, notes, evidence, prior_findings=None):
        calls["propose"] += 1
        return f"patch-{calls['propose']}"

    findings_iter = iter(findings_sequence)

    async def fake_review(self, patch_text, evidence):
        calls["review"] += 1
        return next(findings_iter)

    monkeypatch.setattr(remediation_loop.AmigoResearcher, "analyze", fake_analyze)
    monkeypatch.setattr(remediation_loop.AmigoBuilder, "propose_patch", fake_propose)
    monkeypatch.setattr(remediation_loop.AmigoGatekeeper, "review", fake_review)
    return calls


async def test_loop_passes_when_only_note_findings_remain(tmp_path, monkeypatch):
    calls = _patch_agents(
        monkeypatch,
        [
            [{"line": 1, "severity": "CRITICAL", "text": "a"}],
            [{"line": 1, "severity": "WARNING", "text": "b"}],
            [{"line": 1, "severity": "NOTE", "text": "c"}],
        ],
    )

    result = await run_collaboration_cycle(tmp_path, "fix the bug", log_dir=tmp_path / "logs")

    assert result["verdict"] == "PASS"
    assert calls["analyze"] == 1
    assert calls["propose"] == 3
    assert len(result["rounds"]) == 3

    log_files = list((tmp_path / "logs").glob("*.json"))
    assert len(log_files) == 1
    logged = json.loads(log_files[0].read_text(encoding="utf-8"))
    assert logged["verdict"] == "PASS"


async def test_loop_stops_at_max_rounds_when_blocking_findings_persist(tmp_path, monkeypatch):
    calls = _patch_agents(
        monkeypatch,
        [
            [{"line": 1, "severity": "CRITICAL", "text": "a"}],
            [{"line": 1, "severity": "CRITICAL", "text": "b"}],
            [{"line": 1, "severity": "WARNING", "text": "c"}],
        ],
    )

    result = await run_collaboration_cycle(tmp_path, "fix the bug", log_dir=tmp_path / "logs")

    assert result["verdict"] == "UNRESOLVED"
    assert calls["propose"] == 3


async def test_researcher_called_exactly_once(tmp_path, monkeypatch):
    calls = _patch_agents(monkeypatch, [[]])
    await run_collaboration_cycle(tmp_path, "fix the bug", log_dir=tmp_path / "logs")
    assert calls["analyze"] == 1


async def test_on_event_callback_receives_stage_and_completion_events(tmp_path, monkeypatch):
    _patch_agents(monkeypatch, [[]])
    events = []

    await run_collaboration_cycle(
        tmp_path,
        "fix the bug",
        log_dir=tmp_path / "logs",
        run_id="run_test_1",
        on_event=events.append,
    )

    event_types = [e["type"] for e in events]
    assert "stage_change" in event_types
    assert "agent_message" in event_types
    assert "run_complete" in event_types
    assert all(e.get("run_id") == "run_test_1" for e in events)


async def test_file_named_in_task_is_read_into_evidence(tmp_path, monkeypatch):
    target = tmp_path / "harness"
    target.mkdir()
    (target / "config.py").write_text("DEFAULT_TARGET_DIR = 'real value'\n", encoding="utf-8")

    captured_evidence = {}

    async def fake_analyze(self, task, evidence):
        captured_evidence.update(evidence)
        return "notes"

    monkeypatch.setattr(remediation_loop.AmigoResearcher, "analyze", fake_analyze)
    monkeypatch.setattr(
        remediation_loop.AmigoBuilder,
        "propose_patch",
        lambda self, *a, **k: _async_return("patch"),
    )
    monkeypatch.setattr(
        remediation_loop.AmigoGatekeeper, "review", lambda self, *a, **k: _async_return([])
    )

    await run_collaboration_cycle(
        tmp_path,
        "Add a comment above the assignment in harness/config.py",
        log_dir=tmp_path / "logs",
    )

    paths = [entry["path"] for entry in captured_evidence["file_evidence"]]
    assert any("config.py" in p for p in paths)
    contents = [entry["content"] for entry in captured_evidence["file_evidence"]]
    assert any("real value" in c for c in contents)


async def _async_return(value):
    return value
```
- [ ] **Step 2:** Run: `python -m pytest tests/test_remediation_loop.py -v` — expected FAIL.
- [ ] **Step 3:** Rewrite `harness/remediation_loop.py`:
```python
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
```
- [ ] **Step 4:** Run: `python -m pytest tests/test_remediation_loop.py -v` — expected PASS (6 passed).
- [ ] **Step 5: Commit**
```bash
git add harness/remediation_loop.py tests/test_remediation_loop.py
git commit -m "feat: async remediation loop with incremental events + severity verdict"
```

---

### Task 7: `harness/runner.py` — wrap the now-async call

**Files:**
- Modify: `harness/runner.py`

- [ ] **Step 1:** Add `import asyncio` near the top imports.
- [ ] **Step 2:** Replace:
```python
    result = run_collaboration_cycle(target_path, args.task)
```
with:
```python
    result = asyncio.run(run_collaboration_cycle(target_path, args.task))
```
- [ ] **Step 3:** Run: `python -m pytest tests/test_runner_cli.py -v` — expected PASS (2 passed; `--status` and bare invocation don't touch the async path).
- [ ] **Step 4: Commit**
```bash
git add harness/runner.py
git commit -m "fix: wrap now-async run_collaboration_cycle with asyncio.run in the CLI"
```

---

### Task 8: Fix stale model names in the dashboard spec

**Files:**
- Modify: `docs/GOAL-AMIGO-AGENTS-DASHBOARD-001.md`

- [ ] **Step 1:** Replace the `GET /api/system/status` example response:
```json
{
  "anthropic_key_present": true,
  "openai_key_present": true,
  "gemini_key_present": true,
  "anthropic_model": "claude-opus-5",
  "openai_model": "gpt-5.3-codex",
  "gemini_model": "gemini-3.6-flash"
}
```
(These are the real defaults from `harness/llm_clients.py`, each verified with a live successful call tonight — not guessed.)
- [ ] **Step 2:** Add a short note above the `agent_message` findings example clarifying the real shape now matches what `AmigoGatekeeper.review()` actually returns: `{"line": int, "severity": "CRITICAL"|"WARNING"|"NOTE", "text": str}` (the spec's own example already happens to match this shape — confirm it does, no numeric-severity or extra fields to strip).
- [ ] **Step 3: Commit**
```bash
git add docs/GOAL-AMIGO-AGENTS-DASHBOARD-001.md
git commit -m "docs: correct dashboard spec's stale model-name example"
```

---

### Task 9: Final verification sweep

**Files:** none (verification only)

- [ ] **Step 1:** Run: `python -m pytest -q` — expected all green.
- [ ] **Step 2:** Run: `python harness/runner.py --status` — expected clean, no traceback.
- [ ] **Step 3:** Confirm `git status --porcelain` is clean.
- [ ] **Step 4:** Note in the final report to the user: Gemini's structured-output path (`response_mime_type`/`response_schema`/`thinking_level=HIGH` together) is implemented and unit-tested with mocks, but **not yet confirmed with a real live call** — blocked by tonight's exhausted `gemini-3.6-flash` free-tier quota. Flag this explicitly as the next live-verification step once quota resets or billing is added.
