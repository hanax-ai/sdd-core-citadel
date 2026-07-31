import type { LogEntry, RaidItem, SystemStatus, Transcript } from "./contract";

/** Demo-mode fixtures. Used whenever Connection Mode is "demo" (hosted preview). */

export const DEMO_PATCH = `--- a/auth/session.py
+++ b/auth/session.py
@@ -12,9 +12,14 @@ from .tokens import decode, refresh_token
-import asyncio
+import asyncio
+
+_refresh_lock = asyncio.Lock()
 
 class Session:
     def __init__(self, token: str) -> None:
         self.token = token
-        self._lock = asyncio.Lock()
 
@@ -31,10 +36,15 @@ class Session:
     async def ensure_fresh(self) -> str:
-        if decode(self.token).is_expired:
-            self.token = await refresh_token(self.token)
-        return self.token
+        if not decode(self.token).is_expired:
+            return self.token
+        async with _refresh_lock:
+            if decode(self.token).is_expired:
+                self.token = await asyncio.wait_for(
+                    refresh_token(self.token), timeout=10
+                )
+        return self.token
`;

const RUN_ID = "run_2026-07-31_021200_a1b2c3";

function iso(offsetMs: number) {
  return new Date(Date.parse("2026-07-31T02:12:00Z") + offsetMs).toISOString();
}

export const DEMO_TRANSCRIPT: Transcript = {
  run_id: RUN_ID,
  task: "Refactor auth module and fix token refresh race condition",
  target_dir: "C:\\Users\\JarvisRichardson\\Desktop\\WiP\\SDD-Core-Framework-Analysis",
  verdict: "PASS",
  created_at: iso(0),
  patch_text: DEMO_PATCH,
  events: [
    {
      id: "1",
      type: "stage_change",
      offset_ms: 300,
      payload: {
        run_id: RUN_ID,
        stage: "COLLECTING_EVIDENCE",
        agent: "Harness",
        timestamp: iso(300),
      },
    },
    {
      id: "2",
      type: "agent_message",
      offset_ms: 900,
      payload: {
        run_id: RUN_ID,
        agent: "Harness",
        round: 0,
        message_type: "EVIDENCE_COLLECTED",
        content:
          "Indexed 148 files · 22 modules · git HEAD 8f2c1ad (clean)\nLinter baseline: ruff 4 warnings, mypy 0 errors.",
        timestamp: iso(900),
      },
    },
    {
      id: "3",
      type: "stage_change",
      offset_ms: 1400,
      payload: { run_id: RUN_ID, stage: "RESEARCHING", agent: "Researcher", timestamp: iso(1400) },
    },
    {
      id: "4",
      type: "agent_message",
      offset_ms: 3200,
      payload: {
        run_id: RUN_ID,
        agent: "Researcher",
        round: 1,
        message_type: "RESEARCH_SYNTHESIS",
        content:
          "Task decomposed into 3 units:\n1. Extract token refresh into `auth/session.py`\n2. Guard concurrent refresh with an asyncio.Lock\n3. Backfill regression test for the double-refresh race.\nRisk: shared module imported by 6 call sites.",
        timestamp: iso(3200),
      },
    },
    {
      id: "5",
      type: "token_metric",
      offset_ms: 3300,
      payload: {
        run_id: RUN_ID,
        agent: "Researcher",
        tokens_used: 1842,
        elapsed_ms: 3410,
        timestamp: iso(3300),
      },
    },
    {
      id: "6",
      type: "stage_change",
      offset_ms: 3800,
      payload: {
        run_id: RUN_ID,
        stage: "BUILDER_PATCH_R1",
        agent: "Builder",
        timestamp: iso(3800),
      },
    },
    {
      id: "7",
      type: "agent_message",
      offset_ms: 6400,
      payload: {
        run_id: RUN_ID,
        agent: "Builder",
        round: 1,
        message_type: "PATCH_PROPOSED",
        content:
          "Generated unified patch for auth/session.py (2 hunks, +23 / -7). Propose-only: nothing written to the target repository.",
        timestamp: iso(6400),
      },
    },
    {
      id: "8",
      type: "token_metric",
      offset_ms: 6500,
      payload: {
        run_id: RUN_ID,
        agent: "Builder",
        tokens_used: 2610,
        elapsed_ms: 5120,
        timestamp: iso(6500),
      },
    },
    {
      id: "9",
      type: "stage_change",
      offset_ms: 7000,
      payload: {
        run_id: RUN_ID,
        stage: "GATEKEEPER_AUDIT_R1",
        agent: "Gatekeeper",
        timestamp: iso(7000),
      },
    },
    {
      id: "10",
      type: "agent_message",
      offset_ms: 9200,
      payload: {
        run_id: RUN_ID,
        agent: "Gatekeeper",
        round: 1,
        message_type: "AUDIT_FAIL",
        content:
          "FAIL — 2 findings.\n• Lock is instantiated per-call; must be a module-level singleton.\n• Missing timeout on the refresh await — potential deadlock.",
        findings: [
          { line: 8, severity: "blocker", text: "Lock must be a module-level singleton." },
          { line: 20, severity: "blocker", text: "Missing timeout on refresh await." },
        ],
        timestamp: iso(9200),
      },
    },
    {
      id: "11",
      type: "token_metric",
      offset_ms: 9300,
      payload: {
        run_id: RUN_ID,
        agent: "Gatekeeper",
        tokens_used: 1204,
        elapsed_ms: 2870,
        timestamp: iso(9300),
      },
    },
    {
      id: "12",
      type: "stage_change",
      offset_ms: 9800,
      payload: {
        run_id: RUN_ID,
        stage: "BUILDER_PATCH_R2",
        agent: "Builder",
        timestamp: iso(9800),
      },
    },
    {
      id: "13",
      type: "agent_message",
      offset_ms: 12200,
      payload: {
        run_id: RUN_ID,
        agent: "Builder",
        round: 2,
        message_type: "PATCH_PROPOSED",
        content:
          "Hoisted `_refresh_lock` to module scope and wrapped the refresh in `asyncio.wait_for(..., timeout=10)` (+27 / -9).",
        timestamp: iso(12200),
      },
    },
    {
      id: "14",
      type: "token_metric",
      offset_ms: 12300,
      payload: {
        run_id: RUN_ID,
        agent: "Builder",
        tokens_used: 2288,
        elapsed_ms: 4630,
        timestamp: iso(12300),
      },
    },
    {
      id: "15",
      type: "stage_change",
      offset_ms: 12800,
      payload: {
        run_id: RUN_ID,
        stage: "GATEKEEPER_AUDIT_R2",
        agent: "Gatekeeper",
        timestamp: iso(12800),
      },
    },
    {
      id: "16",
      type: "agent_message",
      offset_ms: 15100,
      payload: {
        run_id: RUN_ID,
        agent: "Gatekeeper",
        round: 2,
        message_type: "AUDIT_PASS",
        content:
          "PASS — lint clean · types clean · no secret leakage · no target mutation detected.\nPatch approved for manual hand-application.",
        findings: [
          { line: 8, severity: "resolved", text: "Module-level `_refresh_lock` — resolved in R2." },
          { line: 20, severity: "resolved", text: "`asyncio.wait_for` timeout added — resolved." },
          {
            line: 19,
            severity: "note",
            text: "Double-checked locking is intentional; covered by regression test.",
          },
        ],
        timestamp: iso(15100),
      },
    },
    {
      id: "17",
      type: "token_metric",
      offset_ms: 15200,
      payload: {
        run_id: RUN_ID,
        agent: "Gatekeeper",
        tokens_used: 1096,
        elapsed_ms: 2410,
        timestamp: iso(15200),
      },
    },
    {
      id: "18",
      type: "stage_change",
      offset_ms: 15600,
      payload: { run_id: RUN_ID, stage: "VERDICT", agent: "Harness", timestamp: iso(15600) },
    },
    {
      id: "19",
      type: "run_complete",
      offset_ms: 16000,
      payload: {
        run_id: RUN_ID,
        verdict: "PASS",
        rounds_total: 2,
        patch_text: DEMO_PATCH,
        tokens_total: 9040,
        duration_ms: 19200,
        timestamp: iso(16000),
      },
    },
  ],
};

export const DEMO_LOGS: LogEntry[] = [
  {
    run_id: RUN_ID,
    task: "Refactor auth module and fix token refresh race condition",
    verdict: "PASS",
    created_at: "2026-07-31T02:12:00Z",
    rounds_total: 2,
    tokens_total: 9040,
    duration_ms: 19200,
  },
  {
    run_id: "run_2026-07-30_184100_9fd012",
    task: "Audit RLS policies on billing tables",
    verdict: "PASS",
    created_at: "2026-07-30T18:41:00Z",
    rounds_total: 3,
    tokens_total: 12480,
    duration_ms: 31400,
  },
  {
    run_id: "run_2026-07-30_110200_44ab71",
    task: "Add --dry-run flag to runner CLI",
    verdict: "PASS",
    created_at: "2026-07-30T11:02:00Z",
    rounds_total: 1,
    tokens_total: 4120,
    duration_ms: 8700,
  },
  {
    run_id: "run_2026-07-29_203300_c81de5",
    task: "Cache evidence collector output",
    verdict: "UNRESOLVED",
    created_at: "2026-07-29T20:33:00Z",
    rounds_total: 3,
    tokens_total: 15220,
    duration_ms: 42900,
  },
];

export const DEMO_STATUS: SystemStatus = {
  anthropic_key_present: true,
  openai_key_present: true,
  gemini_key_present: false,
  anthropic_model: "claude-sonnet-4-6",
  openai_model: "gpt-5.2-codex",
  gemini_model: "gemini-3-pro",
};

const now = "2026-07-31T02:12:00Z";

export const DEMO_RAID: RaidItem[] = [
  {
    id: "R-01",
    type: "RISK",
    title: "Provider rate limits stall remediation loops mid-run",
    description:
      "A 429 from any provider mid-round leaves the loop waiting; runs can exceed the wall-clock budget.",
    status: "TRIAGED",
    owner: "Harness",
    phase: "Phase 4",
    created_at: now,
    updated_at: now,
  },
  {
    id: "R-02",
    type: "RISK",
    title: "Large evidence payloads exceed the context window",
    description: "Evidence collector output for large repos overflows the Researcher context.",
    status: "OPEN",
    owner: "Claude",
    phase: "Phase 3",
    created_at: now,
    updated_at: now,
  },
  {
    id: "A-01",
    type: "ASSUMPTION",
    title: "Target repos remain read-only under the propose-only model",
    description: "The bridge terminates any run that attempts a write inside target_dir.",
    status: "CLOSED",
    owner: "Program",
    phase: "Phase 2",
    created_at: now,
    updated_at: now,
  },
  {
    id: "A-02",
    type: "ASSUMPTION",
    title: "Operators hand-apply patches within the same session",
    description: "Patches live in memory only and are not persisted to the target working tree.",
    status: "CLOSED",
    owner: "Program",
    phase: "Phase 2",
    created_at: now,
    updated_at: now,
  },
  {
    id: "I-01",
    type: "ISSUE",
    title: "SSE reconnect drops the last partial stream chunk",
    description: "Last-Event-ID resume replays from the ring buffer but skips a partial frame.",
    status: "ASSIGNED",
    owner: "Dashboard",
    phase: "Phase 5",
    created_at: now,
    updated_at: now,
  },
  {
    id: "I-02",
    type: "ISSUE",
    title: "Unresolved runs lack a structured failure summary",
    description: "UNRESOLVED verdicts return no machine-readable reason payload.",
    status: "OPEN",
    owner: "Gemini",
    phase: "Phase 4",
    created_at: now,
    updated_at: now,
  },
  {
    id: "D-01",
    type: "DEPENDENCY",
    title: "ANTHROPIC / OPENAI / GEMINI keys present in the environment",
    description: "Bridge reports presence booleans only; values never cross the network boundary.",
    status: "CLOSED",
    owner: "Ops",
    phase: "Phase 1",
    created_at: now,
    updated_at: now,
  },
  {
    id: "D-02",
    type: "DEPENDENCY",
    title: "Bridge exposes /api/run-task and /api/stream/{run_id}",
    description: "FastAPI + sse-starlette daemon bound to 127.0.0.1:8000.",
    status: "ASSIGNED",
    owner: "Harness",
    phase: "Phase 5",
    created_at: now,
    updated_at: now,
  },
];

export const PHASES = [
  { n: 1, name: "Harness Foundation", status: "COMPLETE", detail: "runner.py, config.py, llm_clients.py" },
  { n: 2, name: "Tool Adapters & Safety Isolation", status: "COMPLETE", detail: "git_adapter.py, linter_adapter.py" },
  { n: 3, name: "Evidence Collection Engine", status: "COMPLETE", detail: "evidence_collector.py" },
  { n: 4, name: "Multi-Agent Collaboration Engine", status: "COMPLETE", detail: "Mocked & live verified" },
  { n: 5, name: "Terminal UI & Streaming Command Center", status: "IN PROGRESS", detail: "dashboard/ + harness/bridge.py" },
  { n: 6, name: "Verification Harness & CI Suite", status: "UPCOMING", detail: "Regression + CI gates" },
];
