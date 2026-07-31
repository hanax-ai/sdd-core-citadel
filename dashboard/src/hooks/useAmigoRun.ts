import { useCallback, useEffect, useRef, useState } from "react";
import { SCRIPTED_RUN, type StreamEvent } from "@/lib/amigo";

export type RunStatus = "idle" | "running" | "complete" | "cancelled";

export function useAmigoRun() {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [status, setStatus] = useState<RunStatus>("idle");
  const [elapsed, setElapsed] = useState(0);
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const ticker = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearTimers = useCallback(() => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    if (ticker.current) clearInterval(ticker.current);
    ticker.current = null;
  }, []);

  useEffect(() => clearTimers, [clearTimers]);

  const start = useCallback(() => {
    clearTimers();
    setEvents([]);
    setElapsed(0);
    setStatus("running");
    const startedAt = Date.now();
    ticker.current = setInterval(
      () => setElapsed(Date.now() - startedAt),
      100,
    );

    let offset = 400;
    SCRIPTED_RUN.forEach((e, i) => {
      offset += 900 + Math.min(e.latencyMs, 2600) * 0.5;
      timers.current.push(
        setTimeout(() => {
          setEvents((prev) => [
            ...prev,
            { ...e, id: `${startedAt}-${i}`, ts: Date.now() },
          ]);
          if (i === SCRIPTED_RUN.length - 1) {
            setStatus("complete");
            if (ticker.current) clearInterval(ticker.current);
          }
        }, offset),
      );
    });
  }, [clearTimers]);

  const cancel = useCallback(() => {
    clearTimers();
    setStatus("cancelled");
  }, [clearTimers]);

  const clear = useCallback(() => {
    clearTimers();
    setEvents([]);
    setElapsed(0);
    setStatus("idle");
  }, [clearTimers]);

  const tokens = events.reduce((s, e) => s + e.tokens, 0);
  const invocations = events.filter((e) => e.agent !== "system").length;
  const stage = events.at(-1)?.stage ?? "Idle";

  return { events, status, elapsed, tokens, invocations, stage, start, cancel, clear };
}
