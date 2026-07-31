import { z } from "zod";

/**
 * SDD-Core CITADEL — bridge contract (harness/bridge.py)
 * All schemas mirror GOAL-AMIGO-AGENTS-DASHBOARD-001 §3.2.
 */

export const AGENT_ROLES = ["Researcher", "Builder", "Gatekeeper", "Harness"] as const;
export type AgentRole = (typeof AGENT_ROLES)[number];

export type AgentId = "claude" | "codex" | "gemini" | "kimi" | "system";

/** AgentIds the Gatekeeper role can resolve to at runtime; mirrors GATEKEEPER_PROVIDER. */
export type GatekeeperAgentId = Extract<AgentId, "gemini" | "kimi">;

/** GATEKEEPER_PROVIDER unset/empty means Gemini -- see harness/llm_clients.call_gatekeeper. */
export const DEFAULT_GATEKEEPER_AGENT: GatekeeperAgentId = "gemini";

const STATIC_ROLE_TO_AGENT: Record<Exclude<AgentRole, "Gatekeeper">, AgentId> = {
  Researcher: "claude",
  Builder: "codex",
  Harness: "system",
};

/** The Gatekeeper's provider is runtime config (GATEKEEPER_PROVIDER), so this
 *  cannot be a const map -- that hardcoded map is what mis-attributed Kimi's
 *  findings to Gemini. `null` (an unrecognised GATEKEEPER_PROVIDER) falls back
 *  to the default only for cosmetic identity; factual claims about keys and
 *  models are suppressed by the caller instead.
 *
 *  `gatekeeper` is CURRENT config. Historical surfaces must never pass it --
 *  a run recorded under Gemini would then be badged Kimi the moment
 *  GATEKEEPER_PROVIDER flips. They pass the event's own `provider` instead,
 *  and render provider-neutrally when the event carries none. */
export function roleToAgent(
  role: AgentRole,
  gatekeeper: GatekeeperAgentId | null | undefined = DEFAULT_GATEKEEPER_AGENT,
): AgentId {
  return role === "Gatekeeper"
    ? (gatekeeper ?? DEFAULT_GATEKEEPER_AGENT)
    : STATIC_ROLE_TO_AGENT[role];
}

/** Narrow an untyped payload value (transcript payloads are `unknown`-valued)
 *  to a known Gatekeeper provider. Absent, unrecognised or wrong-typed all
 *  yield `null`, which callers MUST render as a provider-neutral badge rather
 *  than substituting whatever provider happens to be configured now. */
export function asGatekeeperAgent(value: unknown): GatekeeperAgentId | null {
  return value === "gemini" || value === "kimi" ? value : null;
}

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

/** Providers that can serve the Gatekeeper role; mirrors GATEKEEPER_PROVIDER. */
const gatekeeperProviderSchema = z.enum(["gemini", "kimi"]);

export const agentMessageSchema = base
  .extend({
    agent: z.enum(AGENT_ROLES),
    round: z.number().default(0),
    message_type: z.string(),
    content: z.string().optional(),
    findings: z.array(findingSchema).optional(),
    // Which provider actually served the Gatekeeper for THIS message, and the
    // model id it resolved to, stamped by the harness at emit time. Only
    // Gatekeeper messages carry them -- Researcher and Builder are not
    // provider-switchable -- so both are optional, and every event recorded
    // before the harness stamped them omits them entirely.
    //
    // `.catch(undefined)` rather than a bare `.optional()`: parseSseEvent turns
    // ANY parse failure into a silently dropped frame, so a provider string
    // this enum has not heard of yet must degrade to "unattributed" instead of
    // vanishing the whole audit message.
    provider: gatekeeperProviderSchema.optional().catch(undefined),
    model: z.string().optional().catch(undefined),
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

/**
 * One persisted remediation round from the harness run record.
 *
 * `gatekeeper_provider` / `gatekeeper_model` are the round-level twin of the
 * per-event attribution above: which provider actually audited this round.
 * Both are OPTIONAL -- every round persisted before the fields existed omits
 * them, and those transcripts must still parse.
 */
export const transcriptRoundSchema = z.object({
  round: z.number(),
  patch_text: z.string().optional(),
  // Two shapes exist in the wild. Transcripts written before the Gatekeeper
  // gained severity classification persisted each finding as a bare string;
  // current runs persist the {line, severity, text} object. Accept both, or a
  // freshly written transcript would fail this schema and be silently dropped
  // by the `.catch(undefined)` on `rounds` -- losing exactly the data we just
  // added provider attribution to record.
  findings: z.array(z.union([z.string(), findingSchema])).optional(),
  gatekeeper_provider: gatekeeperProviderSchema.optional().catch(undefined),
  gatekeeper_model: z.string().optional().catch(undefined),
});
export type TranscriptRound = z.infer<typeof transcriptRoundSchema>;

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
  // Present only if the bridge surfaces the harness round record on this
  // endpoint; today it returns `events` alone. Optional AND `.catch` so that
  // neither its absence nor a later shape change can fail the transcript parse
  // the whole replay page depends on.
  rounds: z.array(transcriptRoundSchema).optional().catch(undefined),
});
export type Transcript = z.infer<typeof transcriptSchema>;

/**
 * GET /api/system/status.
 *
 * `gemini_*` and `moonshot_*` are RAW facts -- "this env var is non-empty",
 * "this model id is configured" -- reported for both providers regardless of
 * which one is active. They do NOT mean "the Gatekeeper is ready"; that is
 * `gatekeeper_provider`, the runtime truth, which is `null` only when
 * GATEKEEPER_PROVIDER holds an unrecognised value.
 *
 * The three defaults let a new dashboard talk to a pre-switch bridge that does
 * not send these fields -- such a bridge is always Gemini, so the defaults are
 * semantically exact rather than merely safe.
 */
export const systemStatusSchema = z.object({
  anthropic_key_present: z.boolean(),
  openai_key_present: z.boolean(),
  gemini_key_present: z.boolean(),
  anthropic_model: z.string(),
  openai_model: z.string(),
  gemini_model: z.string(),
  moonshot_key_present: z.boolean().default(false),
  moonshot_model: z.string().default(""),
  gatekeeper_provider: z.enum(["gemini", "kimi"]).nullable().default("gemini"),
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
  // Name is the provider family, not the model id (MOONSHOT_MODEL can override
  // kimi-k3) -- consistent with "Gemini" rather than "gemini-3.6-flash". The
  // icon deliberately matches gemini's: it denotes the ROLE, not the vendor.
  kimi: { name: "Kimi", role: "Gatekeeper / Quality Auditor", provider: "Moonshot", icon: "🛡️" },
  system: { name: "Harness", role: "bridge.py", provider: "Local", icon: "◈" },
};

/** Identity for a Gatekeeper message that carries no provider attribution.
 *  Deliberately names no vendor: the icon is the one both gatekeeper entries in
 *  AGENT_META share (it denotes the ROLE), and the name is the role itself. */
export const UNATTRIBUTED_GATEKEEPER = {
  name: "Gatekeeper",
  role: "Gatekeeper / Quality Auditor",
  icon: "🛡️",
} as const;

export const accentClasses: Record<
  AgentId,
  { text: string; border: string; bg: string; dot: string }
> = {
  claude: { text: "text-claude", border: "border-claude/40", bg: "bg-claude/10", dot: "bg-claude" },
  codex: { text: "text-codex", border: "border-codex/40", bg: "bg-codex/10", dot: "bg-codex" },
  gemini: { text: "text-gemini", border: "border-gemini/40", bg: "bg-gemini/10", dot: "bg-gemini" },
  // Resolves only while --color-kimi is registered in the styles.css @theme block.
  kimi: { text: "text-kimi", border: "border-kimi/40", bg: "bg-kimi/10", dot: "bg-kimi" },
  system: {
    text: "text-muted-foreground",
    border: "border-border",
    bg: "bg-muted/40",
    dot: "bg-muted-foreground",
  },
};
