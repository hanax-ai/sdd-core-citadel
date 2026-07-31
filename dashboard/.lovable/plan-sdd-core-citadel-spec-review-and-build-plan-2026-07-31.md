# SDD-Core CITADEL — spec review and build plan

## Review: gaps between the spec and what this environment can deliver

1. **File locations (`dashboard/`, `harness/bridge.py`, Windows paths).** This project builds one app in its own repo; it cannot write into your local `C:\Users\...\Amigos-Agents` checkout. What I can do: build CITADEL here as the dashboard app, and ship `bridge.py` in this repo as a copy-paste/download artifact you drop into `harness/`.
2. **Stack mismatch.** The spec says React + Vite + `vite.config.ts` proxy to `127.0.0.1:8000`. This project is TanStack Start (file routes in `src/routes`, no React Router, dev server on 8080). The UI, Shadcn, Tailwind, TanStack Query, Zustand, Framer Motion parts all port cleanly; the proxy block is only meaningful once the code lives in your local `dashboard/`.
3. **The bridge is unreachable from the hosted preview.** `127.0.0.1:8000` only exists on your machine. In the Lovable preview every live call fails. Needed: a **connection mode switch** — `Live bridge` (configurable base URL, default `http://127.0.0.1:8000`, persisted) vs `Demo` (the current scripted transcript). Everything must render in Demo so the preview stays reviewable.
4. **Current code is demo-only.** `useAmigoRun` replays a hardcoded script with `setTimeout`; there is no `EventSource`, no `run_id`, no `Last-Event-ID` resume, no REST layer. Spec's event schema (`stage_change`, `agent_message`, `token_metric`, `run_complete`, `error`) differs from the current `StreamEvent` shape, so an adapter layer is required.
5. **Missing views.** Diff visualizer, historical replay with scrubber/speed, RAID register (with CRUD + statuses `OPEN|TRIAGED|ASSIGNED|CLOSED`), system/key status panel, and the resilience states (empty, reconnecting countdown, missing-key warning) don't exist yet. `src/routes/index.tsx` is still the blank placeholder.
6. **Dependencies not installed.** `zustand`, `framer-motion`, and a diff/highlight lib. Recommendation: **Prism.js (lightweight) over Monaco** — Monaco is heavy, SSR-hostile, and side-by-side diff is overkill for unified patches. Suggest unified diff first, side-by-side later.
7. **RAID in SQLite** lives in the bridge; in Demo mode it reads seeded local data. No Lovable Cloud needed unless you want RAID to persist in the hosted app — say the word if so.
8. **Contract details the spec leaves open:** `GET /api/logs` returns a summary list but there's no `GET /api/logs/{run_id}` for the full transcript that replay needs; `run_complete` has no token/duration totals; `findings` line ranges for the diff overlay aren't in any documented payload. I'll assume `GET /api/logs/{run_id}` and a `findings: [{line, severity, text}]` field on the Gatekeeper `agent_message`, and document those assumptions in the bridge.

## What I'll build

**Shell + routing** — replace the placeholder index with the CITADEL command center: left rail nav, dark glassmorphism, WCAG-AA agent accents (Claude `#a855f7`, Codex `#10b981`, Gemini `#06b6d4`) as semantic tokens in `src/styles.css`. Routes: `/` (console), `/patches`, `/replay`, `/raid`, `/system`.

**Data layer**
- `src/lib/citadel/contract.ts` — zod schemas for all five SSE events + REST payloads.
- `src/hooks/useAgentStream.ts` — native `EventSource`, `Last-Event-ID` resume, auto-reconnect with countdown, falls back to the scripted transcript in Demo mode.
- `useUIStore` (Zustand): active view, connection mode + bridge URL, replay speed, drawer state.
- TanStack Query for `run-task`, `logs`, `system/status`.

**Views**
1. Streaming console — stage pill bar (`COLLECTING_EVIDENCE → RESEARCHING → BUILDER_PATCH_R1 → GATEKEEPER_AUDIT_R1 → VERDICT`), Framer Motion entrances on cards/stage changes only, **no motion on diff text**, live token/elapsed metrics.
2. Diff visualizer — Prism-highlighted unified patch with Gemini findings badged on affected lines.
3. Replay — transcript picker, play/pause, scrubber, 1x/2x/5x, no live model calls.
4. RAID register — filterable table by type/status/owner, detail drawer.
5. System status — key presence booleans and model names only, never key values.
6. Resilience — empty state with "Dispatch First Task", reconnect banner countdown, missing-key warning before dispatch.

**Bridge artifact** — `bridge/bridge.py` (FastAPI + sse-starlette, loopback bind, ring buffer `deque(maxlen=1000)`, `asyncio.create_task` run launch, propose-only write guard, SQLite for logs/RAID) plus a short README on dropping it into `harness/` and the Vite proxy snippet for your local `dashboard/`.

## Technical notes
- Add deps: `zustand`, `framer-motion`, `prismjs` (+ types).
- All fetch/EventSource calls run client-side only (no SSR loaders) since the bridge is localhost-only.
- Per-route `head()` metadata with CITADEL-specific titles/descriptions.
- Keep the existing `src/lib/amigo.ts` scripted content as the Demo-mode fixture, reshaped to the spec's event schema.

## Approved decisions
- Build CITADEL in this project + ship `bridge/bridge.py` as a copy-out artifact — approved.
- Prism unified diff with line-badge annotations — approved.
- Connection Mode switch (Live Bridge vs Demo), RAID/transcripts persisted by the local bridge in SQLite with Demo fixtures for hosted preview — approved.
- Contract additions `GET /api/logs/{run_id}` and `findings: [{line, severity, text}]` — accepted into the spec.
