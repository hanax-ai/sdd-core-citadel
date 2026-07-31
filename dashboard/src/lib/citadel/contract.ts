import { z } from "zod";

/**
 * SDD-Core CITADEL — bridge contract (harness/bridge.py)
 * All schemas mirror GOAL-AMIGO-AGENTS-DASHBOARD-001 §3.2.
 */

export const AGENT_ROLES = ["Researcher", "Builder", "Gatekeeper", "Harness"] as const;
export type AgentRole = (typeof AGENT_ROLES)[number];

export type AgentId = "claude" | "codex" | "gemini" | "system";

export const ROLE_TO_AGENT: Record<AgentRole, AgentId> = {
  Researcher: "claude",
  Builder: "codex",
  Gatekeeper: "gemini",
  Harness: "system",
};

export const STAGES = [
  "COLLECTING_EVIDENCE",
  "RESEARCHING",
  "BUILDER_PATCH_R1",
  "GATEKEEPER_AUDIT_R1",
  "BUILDER_PATCH_R2",
  "GATEKEEPER_AUDIT_R2",
  "VERDICT",
] as const;
export type Stage = (typeof STAGES)[number];

/** Pill bar shows the canonical five; round-2 stages fold into their round-1 pill. */
export const STAGE_TRACK: Stage[] = [
  "COLLECTING_EVIDENCE",
  "RESEARCHING",
  "BUILDER_PATCH_R1",
  "GATEKEEPER_AUDIT_R1",
  "VERDICT",
];

export const STAGE_LABEL: Record<Stage, string> = {
  COLLECTING_EVIDENCE: "Collecting evidence",
  RESEARCHING: "Researching",
  BUILDER_PATCH_R1: "Builder patch",
  GATEKEEPER_AUDIT_R1: "Gatekeeper audit",
  BUILDER_PATCH_R2: "Builder patch (R2)",
  GATEKEEPER_AUDIT_R2: "Gatekeeper audit (R2)",
  VERDICT: "Verdict",
};

export const findingSchema = z.object({
  line: z.number(),
  severity: z.enum(["CRITICAL", "WARNING", "NOTE"]),
  text: z.string(),
});
export type Finding = z.infer<typeof findingSchema>;

const base = z.object({
  run_id: z.string(),
  timestamp: z.string(),
});

export const stageChangeSchema = base.extend({
  stage: z.enum(STAGES),
  agent: z.enum(AGENT_ROLES).optional(),
  round: z.number().optional(),
  verdict: z.enum(["PASS", "UNRESOLVED"]).optional(),
});

export const agentMessageSchema = base
  .extend({
    agent: z.enum(AGENT_ROLES),
    round: z.number().default(0),
    message_type: z.string(),
    content: z.string().optional(),
    findings: z.array(findingSchema).optional(),
  })
  .refine(
    (v) =>
      v.message_type === "AUDIT_FINDINGS" ? v.findings !== undefined : v.content !== undefined,
    {
      message:
        "agent_message payload is missing content (or findings, for AUDIT_FINDINGS) for its message_type",
    },
  );

export const tokenMetricSchema = base.extend({
  agent: z.enum(AGENT_ROLES),
  round: z.number().optional(),
  input_tokens: z.number(),
  output_tokens: z.number(),
  elapsed_ms: z.number(),
});

export const runCompleteSchema = base.extend({
  verdict: z.enum(["PASS", "FAIL", "UNRESOLVED"]),
  rounds_total: z.number(),
  patch_text: z.string().default(""),
  tokens_total: z.number().optional(),
  duration_ms: z.number().optional(),
});

export const runErrorSchema = base.extend({
  error_code: z.string(),
  message: z.string(),
});

export type SseEnvelope =
  | ({ type: "stage_change" } & z.infer<typeof stageChangeSchema>)
  | ({ type: "agent_message" } & z.infer<typeof agentMessageSchema>)
  | ({ type: "token_metric" } & z.infer<typeof tokenMetricSchema>)
  | ({ type: "run_complete" } & z.infer<typeof runCompleteSchema>)
  | ({ type: "error" } & z.infer<typeof runErrorSchema>);

/** Adds a client-side stable id used for keys and Last-Event-ID resume. */
export type CitadelEvent = SseEnvelope & { id: string };

export function parseSseEvent(type: string, raw: unknown): SseEnvelope | null {
  try {
    switch (type) {
      case "stage_change":
        return { type, ...stageChangeSchema.parse(raw) };
      case "agent_message":
        return { type, ...agentMessageSchema.parse(raw) };
      case "token_metric":
        return { type, ...tokenMetricSchema.parse(raw) };
      case "run_complete":
        return { type, ...runCompleteSchema.parse(raw) };
      case "error":
        return { type, ...runErrorSchema.parse(raw) };
      default:
        return null;
    }
  } catch {
    return null;
  }
}

/* ---------------- REST ---------------- */

export const runTaskRequestSchema = z.object({
  task: z.string().min(1),
  target_dir: z.string().min(1),
  max_rounds: z.number().int().min(1).max(6),
});
export type RunTaskRequest = z.infer<typeof runTaskRequestSchema>;

export const runTaskResponseSchema = z.object({
  run_id: z.string(),
  status: z.string(),
  timestamp: z.string(),
});
export type RunTaskResponse = z.infer<typeof runTaskResponseSchema>;

export const logEntrySchema = z.object({
  run_id: z.string(),
  task: z.string(),
  verdict: z.enum(["PASS", "FAIL", "UNRESOLVED"]),
  created_at: z.string(),
  rounds_total: z.number().optional(),
  tokens_total: z.number().optional(),
  duration_ms: z.number().optional(),
});
export type LogEntry = z.infer<typeof logEntrySchema>;

/** GET /api/logs/{run_id} — full deterministic transcript for replay. */
export const transcriptSchema = z.object({
  run_id: z.string(),
  task: z.string(),
  target_dir: z.string().optional(),
  verdict: z.enum(["PASS", "FAIL", "UNRESOLVED"]),
  created_at: z.string(),
  patch_text: z.string().default(""),
  events: z.array(
    z.object({
      id: z.string(),
      type: z.enum(["stage_change", "agent_message", "token_metric", "run_complete", "error"]),
      offset_ms: z.number(),
      payload: z.record(z.string(), z.unknown()),
    }),
  ),
});
export type Transcript = z.infer<typeof transcriptSchema>;

export const systemStatusSchema = z.object({
  anthropic_key_present: z.boolean(),
  openai_key_present: z.boolean(),
  gemini_key_present: z.boolean(),
  anthropic_model: z.string(),
  openai_model: z.string(),
  gemini_model: z.string(),
});
export type SystemStatus = z.infer<typeof systemStatusSchema>;

/** GET /api/system/health — liveness + dependency probe for the header indicator. */
export const systemHealthSchema = z.object({
  status: z.enum(["ok", "degraded", "down"]),
  version: z.string().default(""),
  uptime_s: z.number().default(0),
  database_ok: z.boolean().default(true),
  active_runs: z.number().default(0),
  problems: z.array(z.string()).default([]),
  timestamp: z.string().default(""),
});
export type SystemHealth = z.infer<typeof systemHealthSchema>;

export const RAID_TYPES = ["RISK", "ASSUMPTION", "ISSUE", "DEPENDENCY"] as const;
export const RAID_STATUSES = ["OPEN", "TRIAGED", "ASSIGNED", "CLOSED"] as const;

export const raidItemSchema = z.object({
  id: z.string(),
  type: z.enum(RAID_TYPES),
  title: z.string(),
  description: z.string().default(""),
  status: z.enum(RAID_STATUSES),
  owner: z.string(),
  phase: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
});
export type RaidItem = z.infer<typeof raidItemSchema>;
export type RaidType = (typeof RAID_TYPES)[number];
export type RaidStatus = (typeof RAID_STATUSES)[number];

export const AGENT_META: Record<
  AgentId,
  { name: string; role: string; provider: string; icon: string }
> = {
  claude: { name: "Claude", role: "Researcher / Synthesizer", provider: "Anthropic", icon: "🧠" },
  codex: { name: "Codex", role: "Builder / QA Red-Team", provider: "OpenAI", icon: "⚡" },
  gemini: { name: "Gemini", role: "Gatekeeper / Quality Auditor", provider: "Google", icon: "🛡️" },
  system: { name: "Harness", role: "bridge.py", provider: "Local", icon: "◈" },
};

export const accentClasses: Record<
  AgentId,
  { text: string; border: string; bg: string; dot: string }
> = {
  claude: { text: "text-claude", border: "border-claude/40", bg: "bg-claude/10", dot: "bg-claude" },
  codex: { text: "text-codex", border: "border-codex/40", bg: "bg-codex/10", dot: "bg-codex" },
  gemini: { text: "text-gemini", border: "border-gemini/40", bg: "bg-gemini/10", dot: "bg-gemini" },
  system: {
    text: "text-muted-foreground",
    border: "border-border",
    bg: "bg-muted/40",
    dot: "bg-muted-foreground",
  },
};
