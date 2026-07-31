# RAID Log — Amigo Agents

Schema matches `docs/GOAL-AMIGO-AGENTS-DASHBOARD-001.md` section 5.4 (RAID Register). This file is the source of record until `harness/bridge.py` lands and persists it to SQLite.

Fields: `id | type | title | status | owner | phase`

## Risks

| id | title | status | owner | phase |
|----|-------|--------|-------|-------|
| R1 | `gemini-3.6-flash` + `thinking_level=HIGH` + structured schema has never completed a real live call — mocked-only, blocked by free-tier daily quota (20 req/day) | CLOSED — quota reset, live call succeeded 2026-07-30 with correct severity classification and real token counts (43 in / 58 out) | — | Phase4 |
| R2 | `bridge/bridge.py` wildcard CORS (`allow_origins=["*"]`) + zero auth/API-key check on any route, no Origin/Host validation | OPEN — real vuln, must fix before any live use even on localhost (DNS-rebinding-style: any page open in the user's browser can reach the port) | — | Phase4-Dashboard |
| R4 | `bridge/bridge.py` `target_dir` comes straight from the request body (`os.path.abspath` + `os.path.isdir` only, no allowlist) | OPEN — combined with R2, any reachable caller can point a future-wired harness at an arbitrary filesystem path; evidence collection would read and transmit those files to external LLM APIs | — | Phase4-Dashboard |
| R5 | `bridge/bridge.py` `HOST` silently overridable via `CITADEL_HOST` env var, defaults to `127.0.0.1` with no warning if changed | OPEN — combined with R2, setting this to `0.0.0.0` for convenience exposes the whole harness to the LAN unauthenticated | — | Phase4-Dashboard |
| R3 | Live-dev-machine TLS interception (Norton AV) required a local `pip-system-certs` workaround, undocumented for other environments/devs | OPEN | — | Phase4 |

## Assumptions

| id | title | status | owner | phase |
|----|-------|--------|-------|-------|
| A1 | Provider SDK close/timeout methods (`AsyncAnthropic.close()`, `AsyncOpenAI.close()`, `client.aio.aclose()`) are real and safe to call | CLOSED — verified via live SDK introspection, not guessed | — | Phase4 |
| A2 | Propose-only guarantee (Builder never writes files) is a sufficient safety boundary | TRIAGED — holds today only because `bridge.py`'s `execute_run()` never actually calls `run_collaboration_cycle` (it's a hardcoded mock, see I4); the guarantee has not actually been exercised through the bridge's HTTP surface yet. Re-open this check once real wiring happens | — | Phase4-Dashboard |
| A3 | Task-description text is trusted input | CLOSED — was false; path-traversal fix (`_extract_focus_files`) proved arbitrary task text could read files outside `target_dir`. Treat as a standing reminder: any user-supplied text reaching filesystem logic needs the same scrutiny going forward | — | Phase4 |

## Issues

| id | title | status | owner | phase |
|----|-------|--------|-------|-------|
| I1 | No clean live `PASS` verdict on record yet for the current Gatekeeper config (blocked by R1) | CLOSED — R1 cleared; live call against production `call_gatekeeper` path returned correctly-classified CRITICAL/NOTE findings, confirming the config works end-to-end. Still worth running a real full `run_collaboration_cycle` end-to-end for a genuine PASS on record, but the model/schema path itself is no longer unverified | — | Phase4 |
| I2 | Dashboard's Vite proxy SSE snippet (from the earlier bridge handoff note) strips `content-encoding` without decompressing the body first | OPEN — moot for now: the delivered `vite.config.ts` doesn't actually contain a proxy block at all (the `.lovable` plan notes the proxy is "only meaningful once the code lives in your local `dashboard/`"). Re-check this the moment a proxy config is actually added | — | Phase4-Dashboard |
| I3 | Spec's planned SQLite persistence needs async-safe I/O | CONFIRMED, now concrete — every DB write in `bridge.py` (`Run.emit()` and 3 other sites) uses blocking stdlib `sqlite3` directly inside `async def` functions with no `asyncio.to_thread`; fires once per harness event, stalls every concurrent SSE stream during a run. Same bug class already fixed in `remediation_loop.py` tonight | — | Phase4-Dashboard |
| I4 | `bridge.py`'s `execute_run()` never imports or calls `harness.remediation_loop.run_collaboration_cycle` at all — it's a hardcoded mock (fixed stage names, canned PASS verdict, fake patch text) | OPEN — the single biggest gap. The bridge doesn't bridge anything yet; needs `execute_run` rewritten from scratch | — | Phase4-Dashboard |
| I5 | `bridge.py`'s `Run.emit()` is `async def`, but the real `on_event` contract is a plain sync `Callable[[dict], None]` — no adapter converts one to the other | OPEN — wiring `on_event=run.emit` as-is will not work; can't await from the sync context `run_collaboration_cycle` calls it from | — | Phase4-Dashboard |
| I6 | `bridge.py`'s `asyncio.create_task(execute_run(run))` return value is discarded, no reference retained anywhere | OPEN — the Task can be garbage-collected mid-run per asyncio semantics; a run could silently die with no error surfaced | — | Phase4-Dashboard |
| I7 | `bridge.py`'s emitted event shape doesn't match the real contract at all — stage names (`RESEARCH`/`BUILD`/`AUDIT`/`COMPLETE` vs real `COLLECTING_EVIDENCE`/`RESEARCHING`/`BUILDER_PATCH_R{n}`/`GATEKEEPER_AUDIT_R{n}`/`VERDICT`), `message_type` values, and a `ts` field instead of `timestamp` | OPEN — currently moot since it's mock data (I4), but must be corrected as part of the `execute_run` rewrite | — | Phase4-Dashboard |
| I8 | `bridge.py`'s `runs` table UPDATE never sets `patch_text` or `tokens_total`, though both are schema columns returned by `/api/logs` endpoints | OPEN — nothing sums `token_metric` events or persists the final patch even once wired; fields silently stay empty/zero | — | Phase4-Dashboard |
| I9 | Frontend `contract.ts`'s zod schemas don't match the real event contract in 4 places: `token_metric` requires `tokens_used` (real: `input_tokens`+`output_tokens`) so every real token event is silently dropped; `severity` enum is `blocker/warning/note/resolved` (real: `CRITICAL/WARNING/NOTE`) so every real Gatekeeper finding fails parsing; `agent_message.content` is mandatory but AUDIT_FINDINGS events carry only `findings`, so Gatekeeper output never reaches the UI live; `stage_change.agent` is required but is only sometimes present on real events | OPEN — three of these independently drop entire real event categories; this is the most severe frontend finding since PASS/FAIL gating is the product's core value | — | Phase4-Dashboard |
| I10 | Frontend `fixtures.ts` (Demo mode) was built to match the frontend's own wrong contract (`tokens_used`, `severity: "blocker"/"resolved"`, invented `message_type` values), not the real one | OPEN — Demo mode will look flawless and validate cleanly, then break the moment a real bridge is wired in; testing against Demo mode would not have caught I9 | — | Phase4-Dashboard |
| I11 | Frontend assumes an `error` SSE event the real harness never emits (it crashes via uncaught Python exception instead); on a real crash, `useAgentStream`'s reconnect loop retries every 3s indefinitely with no max-attempt cap or backoff | OPEN — documented contract gap, not a code defect per se, but the unbounded-retry consequence should be fixed regardless | — | Phase4-Dashboard |

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
- **A Demo/mock mode built against the wrong contract validates itself and hides the bug.** CITADEL's `fixtures.ts` was shaped to match `contract.ts`'s own (wrong) zod schemas, so Demo mode looks flawless while the real event schema is different in 4 places. Never trust a mock's self-consistency as evidence the mock matches reality — check the mock against the actual producer's contract, not against the mock's own consumer.
- **"Contract implemented" in a docstring/README is a claim, not a verification.** `bridge.py`'s execute_run is entirely mocked (never calls the real harness) despite reading as feature-complete; only reading past the interface layer into the actual call sites caught it.
