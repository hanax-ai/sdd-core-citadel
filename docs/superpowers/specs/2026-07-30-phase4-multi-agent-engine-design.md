# Phase 4: Multi-Agent Collaboration Engine — Design

**Status:** Approved (2026-07-30). Corroborated by independent review: `reviews/Gemini_2026-07-30_20-14-00_AmigoAgentsProposedArchitectureEvaluation.md`.

## Context

`docs/implementation_plan.md` Phase 4 calls for a real Builder → Gatekeeper collaboration engine. Phases 1-3 (harness foundation, tool adapters, evidence collection) are done; `harness/remediation_loop.py` currently only collects git evidence and prints a status line — no LLM is called, no patch is generated, no review happens. This design builds that engine.

## Scope decision

Phase 4 only (not Phase 5 terminal UI, not Phase 6 verification harness) — those depend on this existing first.

## Global constraints

- **Propose-only.** No agent writes to the target repo's files. The Builder's patch is text output; a human applies it. Matches `AGENTS.md` Rule 1 (Zero-Contamination Isolation).
- **All three roles wired to their `.env.example`-documented provider:** Researcher → Anthropic/Claude, Gatekeeper → Gemini, Builder → OpenAI/Codex.
- **Fail fast on missing API keys** — checked before the loop starts, not mid-round.
- **Max 3 remediation rounds** (Builder → Gatekeeper), then stop and report unresolved findings.
- **Unit tests never call real APIs** — `llm_clients` functions are mocked in all automated tests.

## Architecture

```
CLI (--task) → evidence_collector (existing)
             → AmigoResearcher.analyze()        [Claude, once]
             → loop (max 3 rounds):
                   AmigoBuilder.propose_patch()  [OpenAI]
                   AmigoGatekeeper.review()      [Gemini]
                   findings empty? -> break (PASS)
             → write logs/<timestamp>_<slug>.json (full transcript)
             → print final patch_text to stdout
```

## Components

| File | Change | Responsibility |
|---|---|---|
| `harness/llm_clients.py` | New | Per-provider call wrappers: `call_researcher`, `call_builder`, `call_gatekeeper`. Each reads a `<PROVIDER>_MODEL` env var, falls back to a documented default, raises a clear error if its API key is unset. |
| `agents/researcher.py` | New | `AmigoResearcher.analyze(task, evidence) -> notes: str`. One Anthropic call, model `claude-opus-5` (default per current Claude API guidance), adaptive thinking. |
| `agents/builder.py` | New | `AmigoBuilder.propose_patch(task, notes, evidence, prior_findings=None) -> patch_text: str`. One OpenAI call. Returns a text diff; never writes files. |
| `agents/gatekeeper.py` | Extend | Add `review(patch_text, evidence) -> findings: list[str]`, calling Gemini with the existing `format_review_prompt`. Empty list = pass. Existing `format_review_prompt` unchanged. |
| `harness/remediation_loop.py` | Rewrite | Orchestrates the sequence above; writes the JSON transcript; prints the patch. |

## Model defaults (env-overridable)

- `ANTHROPIC_MODEL` default `claude-opus-5` — per the Claude API skill's explicit "always use claude-opus-5 unless told otherwise" rule. High confidence.
- `OPENAI_MODEL` default `gpt-5.3-codex` — best-effort, unverified against an authoritative source.
- `GEMINI_MODEL` default `gemini-3.1-pro` — best-effort, unverified against an authoritative source.

**Caveat carried into the plan:** the OpenAI and Gemini call code is written from general SDK knowledge, not a verified skill reference (no equivalent skill is loaded in this environment for those two providers). It needs a real live test run (with your `.env` keys) before being trusted — that run is not something I'll do myself since it spends your API credits.

## Data flow

1. `collect_task_evidence(target_dir)` — unchanged, existing.
2. `AmigoResearcher.analyze(task, evidence)` → `notes` (once, not per-round).
3. Round loop (`round = 1..3`):
   - `AmigoBuilder.propose_patch(task, notes, evidence, prior_findings)` → `patch_text`
   - `AmigoGatekeeper.review(patch_text, evidence)` → `findings`
   - `findings == []` → break with verdict `PASS`
   - else → `prior_findings = findings`, continue
4. If loop exhausts 3 rounds with findings still present → verdict `UNRESOLVED`.
5. Write `logs/<ISO-timestamp>_<task-slug>.json`: `{task, evidence, research_notes, rounds: [{round, patch_text, findings}], verdict}`.
6. Print final `patch_text` and verdict to stdout.

## Error handling

- Missing `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` → raise before any network call, with a message naming which key is missing.
- Provider API errors (rate limit, auth, server error) → caught per-provider with typed exceptions where the SDK provides them (Anthropic: `RateLimitError`/`APIStatusError`/`APIConnectionError` chain per the Claude API skill), re-raised as a single clear harness-level error that aborts the cycle — no silent retry loop, no hang.

## Testing

- `tests/test_llm_clients.py` — verify missing-key error messages (no network calls; just checks the env-var-not-set path raises before any client is constructed).
- `tests/test_researcher.py`, `tests/test_builder.py`, `tests/test_gatekeeper_review.py` — each mocks its provider call, verifies the function shape (inputs in, expected string/list out).
- `tests/test_remediation_loop.py` — mocks `llm_clients` entirely:
  - findings → findings → empty: loop runs exactly 3 rounds, verdict `PASS`, log file written with 3 round entries.
  - always-findings: loop stops at round 3, verdict `UNRESOLVED`.
  - Researcher called exactly once regardless of round count.
- No automated test calls a real API. A manual live run (`python harness/runner.py --task "..."`) is the verification step for real end-to-end behavior, left to the user.

## Self-review

- Placeholder scan: none found — every component has concrete method signatures and file paths.
- Internal consistency: role→provider mapping matches `.env.example` throughout; propose-only constraint is enforced in Builder (returns text, no file I/O) and remediation_loop (no write calls to `target_dir`).
- Scope check: single cohesive subsystem (Phase 4), not split further.
- Ambiguity check: exact OpenAI/Gemini model strings are flagged as unverified rather than stated as fact — this is intentional, not an oversight.
