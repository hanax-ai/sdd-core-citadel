import {
  logEntrySchema,
  runTaskResponseSchema,
  systemStatusSchema,
  systemHealthSchema,
  transcriptSchema,
  raidItemSchema,
  type LogEntry,
  type RaidItem,
  type RunTaskRequest,
  type SystemHealth,
  type SystemStatus,
  type Transcript,
} from "./contract";
import { DEMO_LOGS, DEMO_RAID, DEMO_STATUS, DEMO_TRANSCRIPT } from "./fixtures";
import { z } from "zod";

export class BridgeError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "BridgeError";
  }
}

async function bridgeFetch<S extends z.ZodTypeAny>(
  baseUrl: string,
  path: string,
  schema: S,
  init?: RequestInit,
): Promise<z.infer<S>> {
  let res: Response;
  try {
    res = await fetch(`${baseUrl.replace(/\/$/, "")}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new BridgeError(
      `Cannot reach the bridge at ${baseUrl}. Start harness/bridge.py, or switch to Demo mode.`,
    );
  }
  const body = await res.text();
  if (!res.ok) {
    throw new BridgeError(`Bridge responded ${res.status}: ${body.slice(0, 300)}`, res.status);
  }
  return schema.parse(JSON.parse(body));
}

export const citadelApi = {
  streamUrl: (baseUrl: string, runId: string) =>
    `${baseUrl.replace(/\/$/, "")}/api/stream/${encodeURIComponent(runId)}`,

  async runTask(baseUrl: string, req: RunTaskRequest) {
    return bridgeFetch(baseUrl, "/api/run-task", runTaskResponseSchema, {
      method: "POST",
      body: JSON.stringify(req),
    });
  },

  async logs(baseUrl: string, mode: "demo" | "live"): Promise<LogEntry[]> {
    if (mode === "demo") return DEMO_LOGS;
    return bridgeFetch(baseUrl, "/api/logs", z.array(logEntrySchema));
  },

  async transcript(baseUrl: string, mode: "demo" | "live", runId: string): Promise<Transcript> {
    if (mode === "demo") return DEMO_TRANSCRIPT;
    return bridgeFetch(baseUrl, `/api/logs/${encodeURIComponent(runId)}`, transcriptSchema);
  },

  async status(baseUrl: string, mode: "demo" | "live"): Promise<SystemStatus> {
    if (mode === "demo") return DEMO_STATUS;
    return bridgeFetch(baseUrl, "/api/system/status", systemStatusSchema);
  },

  async health(baseUrl: string, mode: "demo" | "live"): Promise<SystemHealth> {
    if (mode === "demo")
      return {
        status: "ok",
        version: "demo-fixture",
        uptime_s: 0,
        database_ok: true,
        active_runs: 0,
        problems: [],
        timestamp: new Date().toISOString(),
      };
    return bridgeFetch(baseUrl, "/api/system/health", systemHealthSchema);
  },

  async raid(baseUrl: string, mode: "demo" | "live"): Promise<RaidItem[]> {
    if (mode === "demo") return DEMO_RAID;
    return bridgeFetch(baseUrl, "/api/raid", z.array(raidItemSchema));
  },
};
