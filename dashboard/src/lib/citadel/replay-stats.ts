import type { Transcript } from "@/lib/citadel/contract";

export type ReplayEvent = Transcript["events"][number];

type Payload = {
  agent?: string;
  content?: string;
  stage?: string;
  message_type?: string;
  verdict?: string;
  timestamp?: string;
  round?: number;
  input_tokens?: number;
  output_tokens?: number;
  elapsed_ms?: number;
  error_code?: string;
  message?: string;
};

const CSV_COLUMNS = [
  "index",
  "id",
  "type",
  "offset_ms",
  "timestamp",
  "agent",
  "round",
  "stage",
  "message_type",
  "input_tokens",
  "output_tokens",
  "elapsed_ms",
  "verdict",
  "error_code",
  "text",
] as const;

function cell(value: unknown): string {
  if (value === undefined || value === null) return "";
  const s = String(value).replace(/\r?\n/g, " ").trim();
  return /[",;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export type CsvMeta = {
  run_id?: string;
  task?: string;
  source?: string;
  filters?: Record<string, unknown>;
};

export function eventsToCsv(events: ReplayEvent[], meta: CsvMeta = {}): string {
  const rows = events.map((e, i) => {
    const p = e.payload as Payload;
    return [
      i + 1,
      e.id,
      e.type,
      e.offset_ms,
      p.timestamp,
      p.agent,
      p.round,
      p.stage,
      p.message_type,
      p.input_tokens,
      p.output_tokens,
      p.elapsed_ms,
      p.verdict,
      p.error_code,
      p.content ?? p.message ?? "",
    ]
      .map(cell)
      .join(",");
  });

  // Key summary figures land above the column header so the spreadsheet
  // opens with the same stats as the on-screen summary panel.
  const s = summarizeEvents(events);
  const kv = (k: string, v: unknown) => [cell(`# ${k}`), cell(v)].join(",");
  const header: string[] = [
    kv("exported_at", new Date().toISOString()),
    kv("run_id", meta.run_id ?? ""),
    kv("task", meta.task ?? ""),
    kv("source", meta.source ?? ""),
    kv("filters", JSON.stringify(meta.filters ?? {})),
    kv("event_count", s.count),
    kv("first_timestamp", s.firstTimestamp ?? ""),
    kv("last_timestamp", s.lastTimestamp ?? ""),
    kv("span_ms", s.spanMs),
    kv("tokens_total", s.tokensTotal),
    kv("counts_by_agent", s.byAgent.map((a) => `${a.key}=${a.count}`).join(" ")),
    kv("counts_by_type", s.byType.map((t) => `${t.key}=${t.count}`).join(" ")),
    kv(
      "top_errors",
      s.topErrors.length ? s.topErrors.map((e) => `${e.text} x${e.count}`).join(" | ") : "none",
    ),
    "",
  ];

  return [...header, CSV_COLUMNS.join(","), ...rows].join("\n");
}


export type ReplaySummary = {
  count: number;
  byAgent: { key: string; count: number }[];
  byType: { key: string; count: number }[];
  firstTimestamp: string | null;
  lastTimestamp: string | null;
  firstOffsetMs: number | null;
  lastOffsetMs: number | null;
  spanMs: number;
  tokensTotal: number;
  topErrors: { text: string; count: number }[];
};

function tally(values: string[]): { key: string; count: number }[] {
  const m = new Map<string, number>();
  for (const v of values) m.set(v, (m.get(v) ?? 0) + 1);
  return [...m.entries()]
    .map(([key, count]) => ({ key, count }))
    .sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
}

export function summarizeEvents(events: ReplayEvent[]): ReplaySummary {
  const payloads = events.map((e) => e.payload as Payload);
  const timestamps = payloads.map((p) => p.timestamp).filter(Boolean) as string[];
  const offsets = events.map((e) => e.offset_ms);
  const errorText = events
    .filter((e) => e.type === "error")
    .map((e) => {
      const p = e.payload as Payload;
      return [p.error_code, p.message].filter(Boolean).join(": ") || "Unknown error";
    });

  return {
    count: events.length,
    byAgent: tally(payloads.map((p) => p.agent ?? "—")),
    byType: tally(events.map((e) => e.type)),
    firstTimestamp: timestamps[0] ?? null,
    lastTimestamp: timestamps[timestamps.length - 1] ?? null,
    firstOffsetMs: offsets.length ? offsets[0] : null,
    lastOffsetMs: offsets.length ? offsets[offsets.length - 1] : null,
    spanMs: offsets.length ? offsets[offsets.length - 1] - offsets[0] : 0,
    tokensTotal: payloads.reduce(
      (sum, p) => sum + (p.input_tokens ?? 0) + (p.output_tokens ?? 0),
      0,
    ),
    topErrors: tally(errorText)
      .map(({ key, count }) => ({ text: key, count }))
      .slice(0, 5),
  };
}
