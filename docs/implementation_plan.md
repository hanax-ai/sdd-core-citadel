# 🚀 Amigo Agents Harness — Implementation Plan

> **Goal:** Build and deploy the **Amigo Agents Multi-Agent Collaboration Harness** based on the AI harness design principles demonstrated by Claire Vo (*"What is an AI harness? I build one live in less than 30 minutes"*), tailored for automated code authoring, substantive gatekeeper reviews, and zero-contamination target codebase auditing.

---

## 📋 Prerequisites & Environment Setup

Before starting implementation, ensure the following prerequisites are installed and configured:

### 1. Host Infrastructure & Runtimes
- [ ] **Python 3.12+** (for harness controller `harness/runner.py` and validator tools).
- [ ] **Node.js v20+** & `npm` / `pnpm` (optional, for Ink terminal UI rendering).
- [ ] **Git 2.40+** (installed and available on system PATH).

### 2. Environment Variables & API Keys
- [ ] **`ANTHROPIC_API_KEY`** (for Claude Code / Amigo-Researcher).
- [ ] **`GEMINI_API_KEY`** or Google Antigravity environment (for Amigo-Gatekeeper reviewer).
- [ ] **`OPENAI_API_KEY`** (optional, for Codex / Amigo-Builder).

### 3. Target Workspace Bindings
- [ ] Read/Write access to target project directory: `C:\Users\JarvisRichardson\Desktop\WiP\SDD-Core-Framework-Analysis\`.
- [ ] Isolated working directory: `C:\Users\JarvisRichardson\Desktop\SDD\Amigos-Agents\`.

---

## 🏗️ Architecture & Component Roadmap

```mermaid
flowchart TD
    subgraph Phase1 ["Phase 1: Harness Foundation & CLI"]
        Runner["harness/runner.py Controller"]
        Config["harness/config.py Config Loader"]
    end

    subgraph Phase2 ["Phase 2: Opinionated Tool Adapters"]
        GitAdapter["tools/git_adapter.py (Diffs & Commits)"]
        SentryAdapter["tools/sentry_adapter.py (Stack Trace & Error Ingest)"]
        LinearAdapter["tools/ticket_adapter.py (Task & Issue Ingest)"]
        LinterAdapter["tools/linter_adapter.py (JSON Schema & Hashes)"]
    end

    subgraph Phase3 ["Phase 3: Evidence-Gathering Loop"]
        Collector["harness/evidence_collector.py"]
        EvidenceStore["logs/evidence_store.json"]
    end

    subgraph Phase4 ["Phase 4: Multi-Agent Collaboration Engine"]
        BuilderAgent["agents/builder.py (Amigo-Builder)"]
        GatekeeperAgent["agents/gatekeeper.py (Amigo-Gatekeeper / Gemini)"]
        RemediationLoop["harness/remediation_loop.py"]
    end

    subgraph Phase5 ["Phase 5: Terminal UI & Telemetry"]
        TerminalUI["harness/ui.py (Rich / Ink Terminal UI)"]
        LogManager["logs/session_logger.py"]
    end

    subgraph Phase6 ["Phase 6: Verification & Acceptance"]
        TestRunner["tools/test_harness.py"]
    end

    Phase1 --> Phase2 --> Phase3 --> Phase4 --> Phase5 --> Phase6
```

---

## 📑 Proposed Implementation Tasks

### Task 1: Bootstrap Harness Foundation & Configuration (`Phase 1`)
- [ ] Create `harness/config.py` to parse project settings, API keys, target workspace paths, and log destinations.
- [ ] Create `harness/runner.py` CLI controller supporting `--task`, `--target-dir`, and `--agent-mode` flags.
- [ ] Verify clean CLI startup and help output (`python harness/runner.py --help`).

### Task 2: Build Opinionated Tool Adapters (`Phase 2`)
- [ ] Implement `tools/git_adapter.py` to extract git diffs, modified file lists, and working tree status without altering git history.
- [ ] Implement `tools/sentry_adapter.py` / error log parser to ingest raw tracebacks, error codes, and exception details.
- [ ] Implement `tools/linter_adapter.py` to run Draft 2020-12 JSON Schema validation and SHA-256 file table recomputations.
- [ ] Verify adapter outputs return clean structured JSON payloads.

### Task 3: Implement Evidence-Gathering Loop (`Phase 3`)
- [ ] Create `harness/evidence_collector.py` to force the harness to gather file lines, git diffs, error tracebacks, and schema rules BEFORE invoking LLMs.
- [ ] Store structured evidence payloads in `logs/evidence_store.json`.
- [ ] Verify that no code fix is attempted without complete evidence collection.

### Task 4: Construct Multi-Agent Implementer-Reviewer Engine (`Phase 4`)
- [ ] Implement `agents/builder.py` (Amigo-Builder) to generate diff patches and implementation plans.
- [ ] Implement `agents/gatekeeper.py` (Amigo-Gatekeeper) using Gemini review rules to perform substantive gate reviews.
- [ ] Implement `harness/remediation_loop.py` to automatically pass gatekeeper findings back to the builder for remediation fix rounds.
- [ ] Verify automated fix loop cycles until 0 findings remain or max iterations are reached.

### Task 5: Build Terminal UI & Telemetry Logger (`Phase 5`)
- [ ] Implement `harness/ui.py` using Python `Rich` (or Node.js `Ink`) to display live progress bars, step-by-step agent turns, and color-coded review verdicts.
- [ ] Implement `logs/session_logger.py` to record full, un-truncated execution logs in `Amigos-Agents/logs/`.

### Task 6: End-to-End Verification & Integration Test (`Phase 6`)
- [ ] Create `tools/test_harness.py` to run a simulated bug-fix and code-review task against a mock target file.
- [ ] Verify end-to-end execution completes, passes all gate checks, and writes zero transient files into the target project.

---

## 🔍 Verification Plan

### Automated Tests
- [ ] `python tools/test_harness.py` — Verify end-to-end harness execution loop.
- [ ] `python tools/linter_adapter.py --check-all` — Verify schema linting and hash checking adapters.

### Manual Verification
- [ ] Run sample task: `python harness/runner.py --task "Audit P2-C7 integrity gate" --target-dir "C:\Users\JarvisRichardson\Desktop\WiP\SDD-Core-Framework-Analysis"`.
- [ ] Confirm execution logs are written to `Amigos-Agents/logs/` and target codebase manifests remain 100% untouched.
