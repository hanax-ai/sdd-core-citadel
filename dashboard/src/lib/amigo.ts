export type AgentId = "claude" | "codex" | "gemini" | "system";

export type StreamEvent = {
  id: string;
  agent: AgentId;
  stage: string;
  title: string;
  body: string;
  tokens: number;
  latencyMs: number;
  ts: number;
};

export const AGENTS: Record<
  AgentId,
  { name: string; role: string; provider: string; icon: string; accent: string }
> = {
  claude: {
    name: "Claude",
    role: "Researcher / Synthesizer",
    provider: "Anthropic",
    icon: "🧠",
    accent: "claude",
  },
  codex: {
    name: "Codex",
    role: "Builder",
    provider: "OpenAI",
    icon: "⚡",
    accent: "codex",
  },
  gemini: {
    name: "Gemini",
    role: "Gatekeeper / QA Auditor",
    provider: "Google",
    icon: "🛡️",
    accent: "gemini",
  },
  system: {
    name: "Harness",
    role: "runner.py",
    provider: "Local",
    icon: "◈",
    accent: "muted",
  },
};

export const STAGES = [
  "Collecting Evidence",
  "Researching",
  "Round 1 Builder Patch",
  "Round 1 Gatekeeper Audit",
  "Round 2 Builder Patch",
  "Round 2 Gatekeeper Audit",
  "PASS",
] as const;

export const SCRIPTED_RUN: Omit<StreamEvent, "id" | "ts">[] = [
  {
    agent: "system",
    stage: "Collecting Evidence",
    title: "evidence_collector.py — scanning target",
    body: "Indexed 148 files · 22 modules · git HEAD 8f2c1ad (clean)\nCollected linter baseline: ruff 4 warnings, mypy 0 errors.",
    tokens: 0,
    latencyMs: 812,
  },
  {
    agent: "claude",
    stage: "Researching",
    title: "Spec analysis & research notes",
    body: "Task decomposed into 3 units:\n1. Extract token refresh into `auth/session.py`\n2. Guard concurrent refresh with an asyncio.Lock\n3. Backfill regression test for double-refresh race.\nRisk: shared module imported by 6 call sites.",
    tokens: 1842,
    latencyMs: 3410,
  },
  {
    agent: "codex",
    stage: "Round 1 Builder Patch",
    title: "Proposed in-memory diff — auth/session.py",
    body: "Generated unified patch (2 hunks, +23 / -7). Propose-only: no files written to target repo.",
    tokens: 2610,
    latencyMs: 5120,
  },
  {
    agent: "gemini",
    stage: "Round 1 Gatekeeper Audit",
    title: "Quality gate — 2 findings",
    body: "FAIL\n• Lock is instantiated per-call; must be module-level singleton.\n• Missing timeout on refresh await — potential deadlock.",
    tokens: 1204,
    latencyMs: 2870,
  },
  {
    agent: "codex",
    stage: "Round 2 Builder Patch",
    title: "Revised diff — addresses both findings",
    body: "Hoisted `_refresh_lock` to module scope, added `asyncio.wait_for(..., timeout=10)`. (+27 / -9).",
    tokens: 2288,
    latencyMs: 4630,
  },
  {
    agent: "gemini",
    stage: "Round 2 Gatekeeper Audit",
    title: "Quality gate — PASS",
    body: "PASS\n• Lint clean · types clean · no secret leakage · no target mutation detected.\nPatch approved for manual hand-application.",
    tokens: 1096,
    latencyMs: 2410,
  },
  {
    agent: "system",
    stage: "PASS",
    title: "Run complete — logs/20260731T0212_auth-race.json",
    body: "Total 3 rounds skipped to 2 · 9,040 tokens · 19.2s wall clock. Patch retained in memory only.",
    tokens: 0,
    latencyMs: 120,
  },
];

export const DIFF_PATCH = `--- a/auth/session.py
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

export const GATEKEEPER_FINDINGS = [
  { line: 15, severity: "resolved", text: "Lock must be module-level singleton — fixed in round 2." },
  { line: 44, severity: "resolved", text: "Missing timeout on refresh await — wait_for added." },
  { line: 40, severity: "note", text: "Double-checked locking is intentional; documented in test." },
];

export const RUN_LOGS = [
  { file: "20260731T0212_auth-race.json", task: "Fix token refresh race condition", rounds: 2, result: "PASS", tokens: 9040, duration: "19.2s" },
  { file: "20260730T1841_rls-policies.json", task: "Audit RLS policies on billing tables", rounds: 3, result: "PASS", tokens: 12480, duration: "31.4s" },
  { file: "20260730T1102_cli-flags.json", task: "Add --dry-run flag to runner CLI", rounds: 1, result: "PASS", tokens: 4120, duration: "8.7s" },
  { file: "20260729T2033_evidence-cache.json", task: "Cache evidence collector output", rounds: 3, result: "UNRESOLVED", tokens: 15220, duration: "42.9s" },
];

export const PHASES = [
  { n: 1, name: "Harness Foundation", status: "COMPLETE", detail: "runner.py, config.py, llm_clients.py" },
  { n: 2, name: "Tool Adapters & Safety Isolation", status: "COMPLETE", detail: "git_adapter.py, linter_adapter.py" },
  { n: 3, name: "Evidence Collection Engine", status: "COMPLETE", detail: "evidence_collector.py" },
  { n: 4, name: "Multi-Agent Collaboration Engine", status: "COMPLETE", detail: "Mocked & live verified" },
  { n: 5, name: "Terminal UI & Streaming Command Center", status: "IN PROGRESS", detail: "dashboard/ — this goal" },
  { n: 6, name: "Verification Harness & CI Suite", status: "UPCOMING", detail: "Regression + CI gates" },
];

export type RaidType = "Risk" | "Assumption" | "Issue" | "Dependency";

export const RAID: {
  id: string;
  type: RaidType;
  title: string;
  owner: string;
  severity: "High" | "Medium" | "Low";
  status: string;
}[] = [
  { id: "R-01", type: "Risk", title: "Provider rate limits stall remediation loops mid-run", owner: "Harness", severity: "High", status: "Mitigating" },
  { id: "R-02", type: "Risk", title: "Large evidence payloads exceed context window", owner: "Claude", severity: "Medium", status: "Open" },
  { id: "A-01", type: "Assumption", title: "Target repos remain read-only under propose-only model", owner: "Program", severity: "High", status: "Validated" },
  { id: "A-02", type: "Assumption", title: "Operators hand-apply patches within the same session", owner: "Program", severity: "Low", status: "Validated" },
  { id: "I-01", type: "Issue", title: "SSE reconnect drops the last partial stream chunk", owner: "Dashboard", severity: "Medium", status: "In Progress" },
  { id: "I-02", type: "Issue", title: "Unresolved runs lack a structured failure summary", owner: "Gemini", severity: "Low", status: "Open" },
  { id: "D-01", type: "Dependency", title: "ANTHROPIC / OPENAI / GEMINI keys present in environment", owner: "Ops", severity: "High", status: "Satisfied" },
  { id: "D-02", type: "Dependency", title: "Bridge API exposing /api/stream and /api/run-task", owner: "Harness", severity: "High", status: "In Progress" },
];

export const PROVIDERS = [
  {
    id: "claude" as const,
    keyEnv: "ANTHROPIC_API_KEY",
    modelEnv: "ANTHROPIC_MODEL",
    present: true,
    models: ["claude-sonnet-4-6", "claude-opus-4-1", "claude-haiku-4-5"],
  },
  {
    id: "codex" as const,
    keyEnv: "OPENAI_API_KEY",
    modelEnv: "OPENAI_MODEL",
    present: true,
    models: ["gpt-5.2-codex", "gpt-5.2", "gpt-5-mini"],
  },
  {
    id: "gemini" as const,
    keyEnv: "GEMINI_API_KEY",
    modelEnv: "GEMINI_MODEL",
    present: false,
    models: ["gemini-3-pro", "gemini-3-flash", "gemini-2.5-pro"],
  },
];

export const accentClasses: Record<
  AgentId,
  { text: string; border: string; bg: string; dot: string }
> = {
  claude: { text: "text-claude", border: "border-claude/40", bg: "bg-claude/10", dot: "bg-claude" },
  codex: { text: "text-codex", border: "border-codex/40", bg: "bg-codex/10", dot: "bg-codex" },
  gemini: { text: "text-gemini", border: "border-gemini/40", bg: "bg-gemini/10", dot: "bg-gemini" },
  system: { text: "text-muted-foreground", border: "border-border", bg: "bg-muted/40", dot: "bg-muted-foreground" },
};
