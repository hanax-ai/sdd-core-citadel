# SDD-Core CITADEL

Amigo Agents command center — a dense, dark operations dashboard for multi-agent
remediation runs (Researcher / Builder / Gatekeeper) with a local FastAPI bridge.

## Views

| Route      | Purpose                                                          |
| ---------- | ---------------------------------------------------------------- |
| `/`        | Streaming console: stage pill bar, agent cards, live metrics      |
| `/patches` | Unified diff review with inline Gatekeeper findings               |
| `/replay`  | Deterministic transcript replay, search/filter, JSON export       |
| `/raid`    | RAID register (risks, assumptions, issues, dependencies)          |
| `/system`  | Bridge diagnostics: health, key presence, active model strings    |

## Modes

- **Demo mode** — scripted fixtures, no bridge or model calls required.
- **Live bridge** — points at `http://127.0.0.1:8000` (see `bridge/README.md`).

## Local development

```sh
bun install
bun run dev
```

## Bridge

The reference backend lives in `bridge/bridge.py` (FastAPI + `sse-starlette`,
SQLite persistence, SSE resume via `Last-Event-ID`, propose-only write guard).
Run it alongside the dashboard:

```sh
pip install fastapi uvicorn sse-starlette
python bridge/bridge.py
```
