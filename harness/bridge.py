"""
SDD-Core CITADEL — local bridge server (reference artifact).

Run this on YOUR machine, next to the Amigo Agents harness. CITADEL (the web UI)
talks to it from your browser in "Live Bridge" mode.

    pip install fastapi uvicorn sse-starlette pydantic python-dotenv
    set ANTHROPIC_API_KEY=... & set OPENAI_API_KEY=... & set GEMINI_API_KEY=...
    set BRIDGE_API_KEY=...
    python bridge.py

Contract implemented:
    POST /api/run-task        -> {run_id, status}
    GET  /api/stream/{run_id} -> SSE: stage_change | agent_message | token_metric
                                     | run_complete | error   (supports Last-Event-ID)
    GET  /api/logs            -> [LogEntry]
    GET  /api/logs/{run_id}   -> Transcript (deterministic replay)
    GET  /api/raid            -> [RaidItem]
    POST /api/raid            -> RaidItem
    GET  /api/system/health   -> liveness + dependency probe
    GET  /api/system/status   -> key presence + model IDs

ZERO CONTAMINATION: this process never writes to AMIGO_TARGET_DIR. Patches are
returned as unified diff text only and must be applied by hand.

AUTH: every route requires a shared secret, checked against the BRIDGE_API_KEY
env var (see harness/BRIDGE_README.md). Sent as the `X-Bridge-Key` header
normally; the SSE stream route also accepts it as a `?key=` query param,
since the browser's native EventSource API cannot set custom headers. This
is a bridge-level addition on top of the harness's own event contract; the
harness itself has no concept of auth.

`error` SSE events are also a bridge-level addition: `run_collaboration_cycle`
has no `error` event type of its own -- a provider failure raises a plain
Python exception. The bridge catches that at the boundary and synthesizes an
`error` event so the frontend has something to render instead of the stream
just going silent.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
import sqlite3
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
import uvicorn

from harness.config import DEFAULT_TARGET_DIR
from harness.remediation_loop import run_collaboration_cycle

APP_VERSION = "1.1.0"
DB_PATH = os.environ.get("CITADEL_DB", "citadel.sqlite3")
TARGET_DIR = os.environ.get("AMIGO_TARGET_DIR", str(DEFAULT_TARGET_DIR))
HOST = os.environ.get("CITADEL_HOST", "127.0.0.1")
PORT = int(os.environ.get("CITADEL_PORT", "8000"))

# Shared-secret auth (see harness/BRIDGE_README.md). Fail-fast happens in the
# lifespan startup hook below, not here at import time, so this module can
# still be imported (e.g. by tests) before the env var is set.
BRIDGE_API_KEY = os.environ.get("BRIDGE_API_KEY", "")

MODELS = {
    "anthropic": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
    "openai": os.environ.get("OPENAI_MODEL", "gpt-5.1-codex"),
    "gemini": os.environ.get("GEMINI_MODEL", "gemini-3-pro"),
}

# The dashboard's dev server (dashboard/vite.config.ts has no explicit port
# override -- @lovable.dev/vite-tanstack-config leaves it at Vite's default).
DASHBOARD_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


async def require_bridge_key(
    x_bridge_key: str | None = Header(default=None, alias="X-Bridge-Key"),
    key: str | None = Query(default=None),
) -> None:
    """Localhost-dev-tool auth: a single static shared secret, constant-time
    compared. Not a login system -- see harness/BRIDGE_README.md.

    Checks the `X-Bridge-Key` header first; if absent, falls back to a `?key=`
    query param. The fallback exists for the SSE stream route -- the browser's
    native EventSource API cannot set custom request headers, so that's the
    only way it can authenticate."""
    supplied = x_bridge_key or key
    if not supplied or not hmac.compare_digest(supplied, BRIDGE_API_KEY):
        raise HTTPException(
            status_code=401,
            detail={"error_code": "UNAUTHORIZED", "message": "Missing or invalid X-Bridge-Key header."},
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    if not BRIDGE_API_KEY:
        raise RuntimeError(
            "BRIDGE_API_KEY is not set. Refusing to start the bridge without a shared "
            "secret -- set BRIDGE_API_KEY in your environment or .env file. See "
            "harness/BRIDGE_README.md."
        )
    await asyncio.to_thread(init_db)
    yield


app = FastAPI(title="SDD-Core CITADEL bridge", lifespan=lifespan, dependencies=[Depends(require_bridge_key)])

# The UI is served from the dashboard's own dev server (localhost only).
app.add_middleware(
    CORSMiddleware,
    allow_origins=DASHBOARD_DEV_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# --------------------------------------------------------------------------- db
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with closing(db()) as conn, conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id TEXT PRIMARY KEY,
                task TEXT NOT NULL,
                target_dir TEXT,
                verdict TEXT DEFAULT 'UNRESOLVED',
                created_at TEXT NOT NULL,
                patch_text TEXT DEFAULT '',
                rounds_total INTEGER DEFAULT 0,
                tokens_total INTEGER DEFAULT 0,
                duration_ms INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS events (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                type TEXT NOT NULL,
                offset_ms INTEGER NOT NULL,
                payload TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS raid (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT NOT NULL,
                owner TEXT NOT NULL,
                phase TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )


def iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --------------------------------------------------------------- sync db helpers
# Every blocking sqlite3 call lives in one of these plain sync functions, each
# invoked via `await asyncio.to_thread(...)` from async code -- same pattern as
# harness/remediation_loop.py's _write_transcript.
def _insert_run_sync(run_id: str, task: str, target_dir: str, created_at: str) -> None:
    with closing(db()) as conn, conn:
        conn.execute(
            "INSERT INTO runs(run_id, task, target_dir, created_at) VALUES (?,?,?,?)",
            (run_id, task, target_dir, created_at),
        )


def _finalize_run_sync(
    run_id: str, verdict: str, rounds_total: int, tokens_total: int, duration_ms: int, patch_text: str
) -> None:
    with closing(db()) as conn, conn:
        conn.execute(
            "UPDATE runs SET verdict=?, rounds_total=?, tokens_total=?, duration_ms=?, patch_text=? WHERE run_id=?",
            (verdict, rounds_total, tokens_total, duration_ms, patch_text, run_id),
        )


def _mark_run_error_sync(run_id: str, duration_ms: int, tokens_total: int) -> None:
    with closing(db()) as conn, conn:
        conn.execute(
            "UPDATE runs SET verdict=?, tokens_total=?, duration_ms=? WHERE run_id=?",
            ("ERROR", tokens_total, duration_ms, run_id),
        )


def _insert_event_sync(run_id: str, event_id: str, type_: str, offset_ms: int, payload_json: str) -> None:
    with closing(db()) as conn, conn:
        conn.execute(
            "INSERT INTO events(run_id, event_id, type, offset_ms, payload) VALUES (?,?,?,?,?)",
            (run_id, event_id, type_, offset_ms, payload_json),
        )


def _select_logs_sync() -> list[dict[str, Any]]:
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT run_id, task, verdict, created_at, rounds_total, tokens_total, duration_ms"
            " FROM runs ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
    return [dict(r) for r in rows]


def _select_transcript_sync(run_id: str) -> dict[str, Any] | None:
    with closing(db()) as conn:
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if run is None:
            return None
        events = conn.execute(
            "SELECT event_id, type, offset_ms, payload FROM events WHERE run_id=? ORDER BY seq",
            (run_id,),
        ).fetchall()
    return {
        "run_id": run["run_id"],
        "task": run["task"],
        "target_dir": run["target_dir"],
        "verdict": run["verdict"],
        "created_at": run["created_at"],
        "patch_text": run["patch_text"] or "",
        "events": [
            {
                "id": e["event_id"],
                "type": e["type"],
                "offset_ms": e["offset_ms"],
                "payload": json.loads(e["payload"]),
            }
            for e in events
        ],
    }


def _select_events_sync(run_id: str) -> list[dict[str, Any]]:
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT seq, event_id, type, payload FROM events WHERE run_id=? ORDER BY seq",
            (run_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _select_raid_sync() -> list[dict[str, Any]]:
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM raid ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def _insert_raid_sync(row: dict[str, Any]) -> None:
    with closing(db()) as conn, conn:
        conn.execute(
            "INSERT INTO raid(id,type,title,description,status,owner,phase,created_at,updated_at)"
            " VALUES (:id,:type,:title,:description,:status,:owner,:phase,:created_at,:updated_at)",
            row,
        )


def _db_health_check_sync() -> None:
    with closing(db()) as conn:
        conn.execute("SELECT 1 FROM runs LIMIT 1")


# ------------------------------------------------------------------------ models
class RunTaskRequest(BaseModel):
    task: str
    target_dir: str | None = None
    max_rounds: int = Field(default=3, ge=1, le=6)
    # Propose-only contract: the UI may only ever ask for a diff.
    mode: str = "propose"
    apply_patch: bool = False
    write: bool = False


class RaidCreate(BaseModel):
    type: str
    title: str
    description: str = ""
    status: str = "OPEN"
    owner: str = "unassigned"
    phase: str = "Phase 0"


# --------------------------------------------------------------- target_dir allowlist
def _allowed_target_roots() -> list[Path]:
    raw = os.environ.get("BRIDGE_ALLOWED_TARGET_DIRS", "")
    if raw.strip():
        return [Path(p.strip()).resolve() for p in raw.split(",") if p.strip()]
    return [DEFAULT_TARGET_DIR.resolve()]


def _is_within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _resolve_target_dir(requested: str | None) -> Path:
    """Resolve + allowlist-check a request's target_dir. Same .resolve() +
    .relative_to() traversal guard already used in
    harness/remediation_loop.py's _extract_focus_files."""
    candidate = Path(requested or TARGET_DIR).resolve()
    if not any(_is_within(candidate, root) for root in _allowed_target_roots()):
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "TARGET_NOT_ALLOWED",
                "message": f"target_dir {candidate} is not inside an allowed root "
                "(set BRIDGE_ALLOWED_TARGET_DIRS to permit it).",
            },
        )
    if not candidate.is_dir():
        raise HTTPException(
            status_code=400,
            detail={"error_code": "BAD_TARGET", "message": f"target_dir not found: {candidate}"},
        )
    return candidate


# ------------------------------------------------------------------- run manager
RING_BUFFER_SIZE = 1000

# Live-task retention: asyncio only holds a weak reference to scheduled tasks,
# so a task with no other strong reference can be garbage-collected mid-run.
# Every task we fire-and-forget gets added here and self-removes on completion.
_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


def _track(task: "asyncio.Task[Any]") -> "asyncio.Task[Any]":
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_BACKGROUND_TASKS.discard)
    return task


class Run:
    def __init__(self, run_id: str, req: RunTaskRequest, target_dir: Path) -> None:
        self.run_id = run_id
        self.req = req
        self.target_dir = target_dir
        self.started = time.time()
        self.subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        # Bounded in-memory ring buffer used for Last-Event-ID resume.
        self.buffer: deque[dict[str, Any]] = deque(maxlen=RING_BUFFER_SIZE)
        self.finished = False
        self.tokens_total = 0
        self.patch_text = ""
        # Events to persist, in emission order. A single dedicated drain
        # task (see _drain_persist_queue) consumes this serially so SQLite
        # writes land in the same order the harness emitted them -- firing
        # one asyncio.to_thread() task per event independently would let
        # concurrent thread-pool writes race and land out of order.
        self._persist_queue: asyncio.Queue[tuple[str, str, int, str] | None] = asyncio.Queue()

    def offset_ms(self) -> int:
        return int((time.time() - self.started) * 1000)

    def emit(self, event: dict[str, Any]) -> None:
        """The sync adapter passed to run_collaboration_cycle as `on_event`.

        The harness calls this SYNCHRONOUSLY -- it's a plain function, not a
        coroutine -- from inside execute_run(), which is itself a coroutine
        already scheduled on the bridge's running event loop (via
        asyncio.create_task in run_task()). Because a loop is already
        running, this can safely enqueue async work; calling asyncio.run()
        here would crash (a loop is already running).

        Ring-buffer append + SSE fan-out happen immediately, synchronously,
        and in order (cheap, non-blocking). The blocking SQLite insert is
        handed off to this run's drain task via a queue, so a slow disk
        write never stalls the harness. Stores the event dict verbatim --
        no renaming/reshaping of the harness's real field names.
        """
        event_type = event.get("type", "message")
        event_id = f"{self.run_id}-{uuid.uuid4().hex[:8]}"
        payload_json = json.dumps(event)

        if event_type == "token_metric":
            self.tokens_total += int(event.get("input_tokens") or 0) + int(event.get("output_tokens") or 0)
        elif event_type == "run_complete":
            self.patch_text = event.get("patch_text", "")

        frame = {"id": event_id, "event": event_type, "data": payload_json}
        self.buffer.append(frame)
        for q in list(self.subscribers):
            q.put_nowait(frame)

        self._persist_queue.put_nowait((event_id, event_type, self.offset_ms(), payload_json))


async def _drain_persist_queue(run: "Run") -> None:
    """Consume run._persist_queue serially, one blocking SQLite insert at a
    time, so events land in SQLite in the exact order they were emitted."""
    while True:
        item = await run._persist_queue.get()
        if item is None:
            break
        event_id, event_type, offset_ms, payload_json = item
        try:
            await asyncio.to_thread(_insert_event_sync, run.run_id, event_id, event_type, offset_ms, payload_json)
        except Exception as exc:  # noqa: BLE001 - a dropped event write must not crash the run
            print(f"[bridge] failed to persist event {event_id} for run {run.run_id}: {exc}")


RUNS: dict[str, Run] = {}


async def execute_run(run: Run) -> None:
    """Run the real Researcher -> Builder -> Gatekeeper collaboration cycle
    and relay every event it emits, verbatim, to SSE subscribers + SQLite."""
    drain_task = asyncio.create_task(_drain_persist_queue(run))
    try:
        result = await run_collaboration_cycle(
            target_dir=run.target_dir,
            task_description=run.req.task,
            run_id=run.run_id,
            on_event=run.emit,
        )
        await asyncio.to_thread(
            _finalize_run_sync,
            run.run_id,
            result["verdict"],
            len(result["rounds"]),
            run.tokens_total,
            run.offset_ms(),
            result["patch_text"],
        )
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI, never silent
        # `error` is a bridge-level addition: run_collaboration_cycle has no
        # error event of its own, it just raises. Turn that into something
        # the frontend can render, and persist an ERROR verdict so this run
        # doesn't just vanish from /api/logs.
        run.emit(
            {
                "type": "error",
                "run_id": run.run_id,
                "timestamp": iso(),
                "error_code": "HARNESS_ERROR",
                "message": str(exc),
            }
        )
        await asyncio.to_thread(_mark_run_error_sync, run.run_id, run.offset_ms(), run.tokens_total)
    finally:
        # Signal the drain task to stop and wait for it, so a consumer that
        # sees `finished` (or reads the "close" SSE frame) is guaranteed the
        # full transcript is already durable in SQLite, in order.
        run._persist_queue.put_nowait(None)
        await drain_task
        run.finished = True
        for q in list(run.subscribers):
            await q.put({"event": "close", "data": "{}"})


# -------------------------------------------------------------------- endpoints
@app.post("/api/run-task")
async def run_task(req: RunTaskRequest) -> dict[str, str]:
    # ---- propose-only write rejection guard (zero contamination) --------------
    if req.apply_patch or req.write or req.mode.lower() != "propose":
        raise HTTPException(
            status_code=400,
            detail={
                "error_code": "WRITE_REJECTED",
                "message": "This bridge is propose-only: patches are returned as unified diff "
                "text and are never written to the target directory.",
            },
        )
    target = _resolve_target_dir(req.target_dir)

    run_id = f"run_{uuid.uuid4().hex[:10]}"
    await asyncio.to_thread(_insert_run_sync, run_id, req.task, str(target), iso())

    run = Run(run_id, req, target)
    RUNS[run_id] = run
    _track(asyncio.create_task(execute_run(run)))
    return {"run_id": run_id, "status": "started"}


@app.get("/api/stream/{run_id}")
async def stream(run_id: str, request: Request) -> EventSourceResponse:
    last_id = request.headers.get("last-event-id") or request.query_params.get("last_event_id")

    async def gen() -> AsyncIterator[dict[str, Any]]:
        # 1. Replay everything the client missed, in order.
        #    Prefer the in-memory ring buffer (maxlen=1000); fall back to SQLite.
        live_run = RUNS.get(run_id)
        if live_run is not None and last_id is not None and any(
            f["id"] == last_id for f in live_run.buffer
        ):
            seen = False
            for frame in list(live_run.buffer):
                if not seen:
                    if frame["id"] == last_id:
                        seen = True
                    continue
                yield frame
        else:
            rows = await asyncio.to_thread(_select_events_sync, run_id)
            replaying = last_id is not None
            for row in rows:
                if replaying:
                    if row["event_id"] == last_id:
                        replaying = False
                    continue
                yield {"id": row["event_id"], "event": row["type"], "data": row["payload"]}

        # 2. Then follow live output, if the run is still active.
        run = RUNS.get(run_id)
        if run is None or run.finished:
            return
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        run.subscribers.append(queue)
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    frame = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
                    continue
                if frame.get("event") == "close":
                    break
                yield frame
        finally:
            if queue in run.subscribers:
                run.subscribers.remove(queue)

    return EventSourceResponse(gen(), ping=15)


@app.get("/api/logs")
async def logs() -> list[dict[str, Any]]:
    return await asyncio.to_thread(_select_logs_sync)


@app.get("/api/logs/{run_id}")
async def transcript(run_id: str) -> dict[str, Any]:
    result = await asyncio.to_thread(_select_transcript_sync, run_id)
    if result is None:
        raise HTTPException(status_code=404, detail="run not found")
    return result


@app.get("/api/raid")
async def raid_list() -> list[dict[str, Any]]:
    return await asyncio.to_thread(_select_raid_sync)


@app.post("/api/raid")
async def raid_create(item: RaidCreate) -> dict[str, Any]:
    row = {
        "id": f"RAID-{uuid.uuid4().hex[:6].upper()}",
        **item.model_dump(),
        "created_at": iso(),
        "updated_at": iso(),
    }
    await asyncio.to_thread(_insert_raid_sync, row)
    return row


STARTED_AT = time.time()


@app.get("/api/system/health")
async def system_health() -> dict[str, Any]:
    """Liveness + dependency probe used by the CITADEL header indicator."""
    problems: list[str] = []

    db_ok = True
    try:
        await asyncio.to_thread(_db_health_check_sync)
    except Exception as exc:  # noqa: BLE001
        db_ok = False
        problems.append(f"sqlite unavailable at {DB_PATH}: {exc}")

    keys = {
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "gemini": bool(os.environ.get("GEMINI_API_KEY")),
    }
    missing = [name for name, present in keys.items() if not present]
    if missing:
        problems.append("missing provider keys: " + ", ".join(sorted(missing)))

    status = "ok" if not problems else ("degraded" if db_ok else "down")
    return {
        "status": status,
        "version": APP_VERSION,
        "uptime_s": round(time.time() - STARTED_AT, 3),
        "database_ok": db_ok,
        "active_runs": sum(1 for r in RUNS.values() if not r.finished),
        "problems": problems,
        "timestamp": iso(),
    }


@app.get("/api/system/status")
async def system_status() -> dict[str, Any]:
    return {
        "anthropic_key_present": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "openai_key_present": bool(os.environ.get("OPENAI_API_KEY")),
        "gemini_key_present": bool(os.environ.get("GEMINI_API_KEY")),
        "anthropic_model": MODELS["anthropic"],
        "openai_model": MODELS["openai"],
        "gemini_model": MODELS["gemini"],
    }


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
