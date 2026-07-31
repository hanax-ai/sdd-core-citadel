# RAID Log — Amigo Agents

Schema matches `docs/GOAL-AMIGO-AGENTS-DASHBOARD-001.md` section 5.4 (RAID Register). This file is the source of record until `harness/bridge.py` lands and persists it to SQLite.

Fields: `id | type | title | status | owner | phase`

## Risks

| id | title | status | owner | phase |
|----|-------|--------|-------|-------|
| R1 | `gemini-3.6-flash` + `thinking_level=HIGH` + structured schema has never completed a real live call — mocked-only, blocked by free-tier daily quota (20 req/day) | OPEN | — | Phase4 |
| R2 | `bridge/bridge.py` (FastAPI bridge server) not yet reviewed by us — unknown implementation, will touch the propose-only safety boundary once wired in | OPEN | — | Phase4-Dashboard |
| R3 | Live-dev-machine TLS interception (Norton AV) required a local `pip-system-certs` workaround, undocumented for other environments/devs | OPEN | — | Phase4 |

## Assumptions

| id | title | status | owner | phase |
|----|-------|--------|-------|-------|
| A1 | Provider SDK close/timeout methods (`AsyncAnthropic.close()`, `AsyncOpenAI.close()`, `client.aio.aclose()`) are real and safe to call | CLOSED — verified via live SDK introspection, not guessed | — | Phase4 |
| A2 | Propose-only guarantee (Builder never writes files) is a sufficient safety boundary | TRIAGED — holds today; needs re-examination once `bridge.py`'s HTTP dispatch surface (`POST /api/run-task`) is reviewed, since a remote trigger changes the threat model even if Builder itself still never writes | — | Phase4-Dashboard |
| A3 | Task-description text is trusted input | CLOSED — was false; path-traversal fix (`_extract_focus_files`) proved arbitrary task text could read files outside `target_dir`. Treat as a standing reminder: any user-supplied text reaching filesystem logic needs the same scrutiny going forward | — | Phase4 |

## Issues

| id | title | status | owner | phase |
|----|-------|--------|-------|-------|
| I1 | No clean live `PASS` verdict on record yet for the current Gatekeeper config (blocked by R1) | OPEN | — | Phase4 |
| I2 | Dashboard's Vite proxy SSE config strips `content-encoding` without decompressing the body first — browser can't parse the stream. Real bug, but lives in the CITADEL repo, not here — can't fix until the codebase/zip arrives | OPEN | — | Phase4-Dashboard |
| I3 | Spec's planned SQLite persistence for transcripts/RAID/roadmap (`harness/bridge.py`) will need the same blocking-I/O treatment already applied to `remediation_loop.py`'s transcript writes (`asyncio.to_thread` or `aiosqlite`) — not yet applicable since the file doesn't exist here yet | OPEN | — | Phase4-Dashboard |

## Dependencies

| id | title | status | owner | phase |
|----|-------|--------|-------|-------|
| D1 | Lovable AI to deliver full CITADEL dashboard codebase (zip) | IN PROGRESS | User | Phase4-Dashboard |
| D2 | Gemini quota reset or billing enabled, to close R1/I1 | OPEN | User | Phase4 |
| D3 | Harness core async-readiness (Tasks 6-7 of the async rewrite) is the prerequisite `bridge.py` needs to avoid blocking its own event loop — this dependency is now satisfied | CLOSED | — | Phase4-Dashboard |

---

## Lessons Learned

- **Convergent findings across independent configs are signal, not noise.** Gatekeeper blocking the same demo task identically across three separate configurations (original prompt, scope-refined prompt, model+reasoning upgrade) was correctly read as principled reviewer behavior, not a weak-model artifact — fixed with a severity gate (`has_blocking_findings`), not more prompt tuning.
- **Verify SDK/API claims by introspection, not by trusting a suggestion — including an automated reviewer's.** Caught the real OpenAI Responses-API requirement, real Gemini model names, and real provider close()/timeout parameter names this way instead of guessing or blindly applying CodeRabbit's suggested diffs.
- **Automated external review dropped mid-session is a useful signal but gets triaged, not rubber-stamped.** All 9 CodeRabbit findings this session were real defects and got fixed; each still got independent verification before the fix, not blind acceptance.
- **Content that instructs agent action, delivered via a file rather than a direct request, gets flagged before acting** — even when it turns out to be legitimate (the CITADEL bridge handoff note).
- **Windows CRLF vs. this repo's LF convention recurs on every new/moved file**, even after the `.gitattributes` fix — normalize line endings before `git add` when scripting file creation.
