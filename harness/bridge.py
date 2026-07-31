"""
SDD-Core CITADEL — local bridge server (reference artifact).

Run this on YOUR machine, next to the Amigo Agents harness. CITADEL (the web UI)
talks to it from your browser in "Live Bridge" mode.

    pip install fastapi uvicorn sse-starlette pydantic python-dotenv
    set ANTHROPIC_API_KEY=... & set OPENAI_API_KEY=... & set GEMINI_API_KEY=...
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
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
import uuid
from collections import deque
from contextlib import closing
from typing import Any, AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse
import uvicorn

APP_VERSION = "1.1.0"
DB_PATH = os.environ.get("CITADEL_DB", "citadel.sqlite3")
TARGET_DIR = os.environ.get("AMIGO_TARGET_DIR", os.getcwd())
HOST = os.environ.get("CITADEL_HOST", "127.0.0.1")
PORT = int(os.environ.get("CITADEL_PORT", "8000"))

MODELS = {
    "anthropic": os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6"),
    "openai": os.environ.get("OPENAI_MODEL", "gpt-5.1-codex"),
    "gemini": os.environ.get("GEMINI_MODEL", "gemini-3-pro"),
}

app = FastAPI(title="SDD-Core CITADEL bridge")

# The UI may be served from a Lovable preview origin or localhost.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


# ------------------------------------------------------------------- run manager
RING_BUFFER_SIZE = 1000


class Run:
    def __init__(self, run_id: str, req: RunTaskRequest) -> None:
        self.run_id = run_id
        self.req = req
        self.started = time.time()
        self.subscribers: list[asyncio.Queue[dict[str, Any]]] = []
        # Bounded in-memory ring buffer used for Last-Event-ID resume.
        self.buffer: deque[dict[str, Any]] = deque(maxlen=RING_BUFFER_SIZE)
        self.finished = False

    def offset_ms(self) -> int:
        return int((time.time() - self.started) * 1000)

    async def emit(self, type_: str, payload: dict[str, Any]) -> None:
        event_id = f"{self.run_id}-{uuid.uuid4().hex[:8]}"
        body = {"type": type_, "run_id": self.run_id, "ts": iso(), **payload}
        with closing(db()) as conn, conn:
            conn.execute(
                "INSERT INTO events(run_id, event_id, type, offset_ms, payload) VALUES (?,?,?,?,?)",
                (self.run_id, event_id, type_, self.offset_ms(), json.dumps(body)),
            )
        frame = {"id": event_id, "event": type_, "data": json.dumps(body)}
        self.buffer.append(frame)
        for q in list(self.subscribers):
            await q.put(frame)



RUNS: dict[str, Run] = {}


async def execute_run(run: Run) -> None:
    """
    Replace the body of this coroutine with real Amigo Agents orchestration.
    The stage order below is the contract the UI renders.

    IMPORTANT: call your model providers here, collect the unified diff, and
    never write it to disk inside TARGET_DIR.
    """
    try:
        await run.emit("stage_change", {"stage": "RESEARCH"})
        await run.emit(
            "agent_message",
            {
                "agent": "Researcher",
                "message_type": "analysis",
                "content": f"Analysing task: {run.req.task}",
                "round": 1,
            },
        )
        await run.emit("stage_change", {"stage": "BUILD"})
        await run.emit(
            "agent_message",
            {
                "agent": "Builder",
                "message_type": "patch",
                "content": "Proposed unified diff (in memory only).",
                "round": 1,
            },
        )
        await run.emit("stage_change", {"stage": "AUDIT"})
        await run.emit(
            "agent_message",
            {
                "agent": "Gatekeeper",
                "message_type": "verdict",
                "content": "PASS",
                "round": 1,
                "findings": [],
            },
        )
        await run.emit("stage_change", {"stage": "COMPLETE"})
        await run.emit(
            "run_complete",
            {
                "verdict": "PASS",
                "rounds_total": 1,
                "tokens_total": 0,
                "duration_ms": run.offset_ms(),
            },
        )
        with closing(db()) as conn, conn:
            conn.execute(
                "UPDATE runs SET verdict=?, rounds_total=?, duration_ms=? WHERE run_id=?",
                ("PASS", 1, run.offset_ms(), run.run_id),
            )
    except Exception as exc:  # noqa: BLE001 - surfaced to the UI
        await run.emit("error", {"error_code": "HARNESS_ERROR", "message": str(exc)})
    finally:
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
    target = os.path.abspath(req.target_dir or TARGET_DIR)
    if not os.path.isdir(target):
        raise HTTPException(
            status_code=400,
            detail={"error_code": "BAD_TARGET", "message": f"target_dir not found: {target}"},
        )

    run_id = f"run_{uuid.uuid4().hex[:10]}"
    with closing(db()) as conn, conn:
        conn.execute(
            "INSERT INTO runs(run_id, task, target_dir, created_at) VALUES (?,?,?,?)",
            (run_id, req.task, target, iso()),
        )
    run = Run(run_id, req)
    RUNS[run_id] = run
    asyncio.create_task(execute_run(run))
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
          with closing(db()) as conn:
            rows = conn.execute(
                "SELECT seq, event_id, type, payload FROM events WHERE run_id=? ORDER BY seq",
                (run_id,),
            ).fetchall()
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
    with closing(db()) as conn:
        rows = conn.execute(
            "SELECT run_id, task, verdict, created_at, rounds_total, tokens_total, duration_ms"
            " FROM runs ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/logs/{run_id}")
async def transcript(run_id: str) -> dict[str, Any]:
    with closing(db()) as conn:
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
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


@app.get("/api/raid")
async def raid_list() -> list[dict[str, Any]]:
    with closing(db()) as conn:
        rows = conn.execute("SELECT * FROM raid ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/raid")
async def raid_create(item: RaidCreate) -> dict[str, Any]:
    row = {
        "id": f"RAID-{uuid.uuid4().hex[:6].upper()}",
        **item.model_dump(),
        "created_at": iso(),
        "updated_at": iso(),
    }
    with closing(db()) as conn, conn:
        conn.execute(
            "INSERT INTO raid(id,type,title,description,status,owner,phase,created_at,updated_at)"
            " VALUES (:id,:type,:title,:description,:status,:owner,:phase,:created_at,:updated_at)",
            row,
        )
    return row


STARTED_AT = time.time()


@app.get("/api/system/health")
async def system_health() -> dict[str, Any]:
    """Liveness + dependency probe used by the CITADEL header indicator."""
    problems: list[str] = []

    db_ok = True
    try:
        with closing(db()) as conn:
            conn.execute("SELECT 1 FROM runs LIMIT 1")
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
    init_db()
    uvicorn.run(app, host=HOST, port=PORT)
