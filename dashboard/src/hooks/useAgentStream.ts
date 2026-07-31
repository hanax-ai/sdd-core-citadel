import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ROLE_TO_AGENT,
  parseSseEvent,
  type CitadelEvent,
  type Finding,
  type RunTaskRequest,
  type Stage,
} from "@/lib/citadel/contract";
import { citadelApi } from "@/lib/citadel/client";
import { DEMO_TRANSCRIPT } from "@/lib/citadel/fixtures";
import { useUIStore } from "@/stores/useUIStore";

export type RunStatus = "idle" | "dispatching" | "running" | "complete" | "error" | "cancelled";
export type ConnectionState = "closed" | "connecting" | "open" | "reconnecting" | "lost";

const RECONNECT_BASE_SECONDS = 3;
const RECONNECT_MAX_SECONDS = 30;
const RECONNECT_MAX_ATTEMPTS = 8;

export function useAgentStream() {
  const mode = useUIStore((s) => s.mode);
  const bridgeUrl = useUIStore((s) => s.bridgeUrl);
  const bridgeKey = useUIStore((s) => s.bridgeKey);

  const [events, setEvents] = useState<CitadelEvent[]>([]);
  const [status, setStatus] = useState<RunStatus>("idle");
  const [connection, setConnection] = useState<ConnectionState>("closed");
  const [retryIn, setRetryIn] = useState(0);
  const [runId, setRunId] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [errorText, setErrorText] = useState<string | null>(null);

  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const ticker = useRef<ReturnType<typeof setInterval> | null>(null);
  const source = useRef<EventSource | null>(null);
  const lastEventId = useRef<string | null>(null);
  const cancelled = useRef(false);
  const reconnectAttempts = useRef(0);

  const teardown = useCallback(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    if (ticker.current) clearInterval(ticker.current);
    ticker.current = null;
    source.current?.close();
    source.current = null;
  }, []);

  useEffect(() => teardown, [teardown]);

  const push = useCallback((e: CitadelEvent) => {
    lastEventId.current = e.id;
    setEvents((prev) => [...prev, e]);
    if (e.type === "run_complete") setStatus("complete");
    if (e.type === "error") {
      setStatus("error");
      setErrorText(`${e.error_code}: ${e.message}`);
    }
  }, []);

  const startClock = useCallback(() => {
    const t0 = Date.now();
    setElapsed(0);
    ticker.current = setInterval(() => setElapsed(Date.now() - t0), 100);
  }, []);

  /* -------- demo driver: deterministic replay of the bundled transcript -------- */
  const startDemo = useCallback(() => {
    setRunId(DEMO_TRANSCRIPT.run_id);
    setStatus("running");
    setConnection("open");
    startClock();
    DEMO_TRANSCRIPT.events.forEach((ev) => {
      timers.current.push(
        setTimeout(() => {
          const parsed = parseSseEvent(ev.type, ev.payload);
          if (parsed) push({ ...parsed, id: ev.id });
          if (ev.id === DEMO_TRANSCRIPT.events.at(-1)?.id) {
            if (ticker.current) clearInterval(ticker.current);
            setConnection("closed");
          }
        }, ev.offset_ms),
      );
    });
  }, [push, startClock]);

  /* -------- live driver: EventSource against harness/bridge.py -------- */
  const connect = useCallback(
    (id: string) => {
      setConnection((c) => (c === "closed" ? "connecting" : c));
      const url = new URL(citadelApi.streamUrl(bridgeUrl, id, bridgeKey));
      if (lastEventId.current) url.searchParams.set("last_event_id", lastEventId.current);
      const es = new EventSource(url.toString());
      source.current = es;

      const bind = (type: string) =>
        es.addEventListener(type, (raw) => {
          const msg = raw as MessageEvent<string>;
          try {
            const parsed = parseSseEvent(type, JSON.parse(msg.data));
            if (parsed) push({ ...parsed, id: msg.lastEventId || crypto.randomUUID() });
          } catch {
            /* ignore malformed frame */
          }
        });

      ["stage_change", "agent_message", "token_metric", "run_complete", "error"].forEach(bind);

      es.onopen = () => {
        setConnection("open");
        reconnectAttempts.current = 0;
      };
      es.onerror = () => {
        es.close();
        source.current = null;
        if (cancelled.current) return;

        reconnectAttempts.current += 1;
        if (reconnectAttempts.current > RECONNECT_MAX_ATTEMPTS) {
          setConnection("lost");
          setRetryIn(0);
          setErrorText(
            "Connection lost after repeated retries. Reconnect manually or start a new run.",
          );
          return;
        }

        setConnection("reconnecting");
        let left = Math.min(
          RECONNECT_BASE_SECONDS * 2 ** (reconnectAttempts.current - 1),
          RECONNECT_MAX_SECONDS,
        );
        setRetryIn(left);
        const iv = setInterval(() => {
          left -= 1;
          setRetryIn(left);
          if (left <= 0) {
            clearInterval(iv);
            if (!cancelled.current) connect(id);
          }
        }, 1000);
        timers.current.push(iv as unknown as ReturnType<typeof setTimeout>);
      };
    },
    [bridgeUrl, bridgeKey, push],
  );

  const reconnect = useCallback(() => {
    if (!runId) return;
    cancelled.current = false;
    reconnectAttempts.current = 0;
    setConnection("connecting");
    connect(runId);
  }, [connect, runId]);

  const start = useCallback(
    async (req: RunTaskRequest) => {
      teardown();
      cancelled.current = false;
      lastEventId.current = null;
      reconnectAttempts.current = 0;
      setEvents([]);
      setErrorText(null);
      setElapsed(0);

      if (mode === "demo") {
        startDemo();
        return { run_id: DEMO_TRANSCRIPT.run_id };
      }

      setStatus("dispatching");
      try {
        const res = await citadelApi.runTask(bridgeUrl, req);
        setRunId(res.run_id);
        setStatus("running");
        startClock();
        connect(res.run_id);
        return res;
      } catch (err) {
        setStatus("error");
        setErrorText(err instanceof Error ? err.message : "Dispatch failed");
        throw err;
      }
    },
    [bridgeUrl, connect, mode, startClock, startDemo, teardown],
  );

  const cancel = useCallback(() => {
    cancelled.current = true;
    teardown();
    setConnection("closed");
    setStatus("cancelled");
  }, [teardown]);

  const clear = useCallback(() => {
    cancelled.current = true;
    teardown();
    setEvents([]);
    setElapsed(0);
    setStatus("idle");
    setConnection("closed");
    setRunId(null);
    setErrorText(null);
  }, [teardown]);

  const derived = useMemo(() => deriveRunState(events), [events]);

  return {
    ...derived,
    events,
    status,
    connection,
    retryIn,
    runId,
    elapsed,
    errorText,
    start,
    cancel,
    clear,
    reconnect,
    isRunning: status === "running" || status === "dispatching",
  };
}

export function deriveRunState(events: CitadelEvent[]) {
  let stage: Stage | null = null;
  let tokens = 0;
  let verdict: "PASS" | "FAIL" | "UNRESOLVED" | null = null;
  let patchText = "";
  let rounds = 0;
  let findings: Finding[] = [];

  for (const e of events) {
    if (e.type === "stage_change") stage = e.stage;
    if (e.type === "token_metric") tokens += e.input_tokens + e.output_tokens;
    if (e.type === "agent_message") {
      rounds = Math.max(rounds, e.round ?? 0);
      if (e.findings?.length) findings = e.findings;
    }
    if (e.type === "run_complete") {
      verdict = e.verdict;
      patchText = e.patch_text || patchText;
      rounds = e.rounds_total;
    }
  }

  const messages = events.filter((e) => e.type === "agent_message");
  const invocations = messages.filter(
    (e) => e.type === "agent_message" && ROLE_TO_AGENT[e.agent] !== "system",
  ).length;

  return { stage, tokens, verdict, patchText, rounds, findings, invocations };
}
