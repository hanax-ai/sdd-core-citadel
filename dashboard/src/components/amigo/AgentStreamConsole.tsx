import { useEffect, useRef } from "react";
import { AGENTS, STAGES, accentClasses } from "@/lib/amigo";
import { cn } from "@/lib/utils";
import { AgentBadge, StatusPill } from "./pills";
import { Button } from "@/components/ui/button";
import { Play, Square, Eraser } from "lucide-react";
import type { useAmigoRun } from "@/hooks/useAmigoRun";

type Run = ReturnType<typeof useAmigoRun>;

export function AgentStreamConsole({ run }: { run: Run }) {
  const endRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [run.events.length]);

  const activeIndex = STAGES.findIndex((s) => s === run.stage);

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_280px]">
      <section className="glass rounded-2xl overflow-hidden">
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3">
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs text-muted-foreground">amigo://stream</span>
            <StatusPill
              label={
                run.status === "running"
                  ? "STREAMING"
                  : run.status === "complete"
                    ? "RUN COMPLETE"
                    : run.status === "cancelled"
                      ? "CANCELLED"
                      : "IDLE"
              }
              tone={
                run.status === "running"
                  ? "primary"
                  : run.status === "complete"
                    ? "success"
                    : run.status === "cancelled"
                      ? "danger"
                      : "muted"
              }
              live={run.status === "running"}
            />
          </div>
          <div className="flex gap-2">
            <Button size="sm" onClick={run.start} disabled={run.status === "running"}>
              <Play /> Start run
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={run.cancel}
              disabled={run.status !== "running"}
            >
              <Square /> Cancel
            </Button>
            <Button size="sm" variant="ghost" onClick={run.clear}>
              <Eraser /> Clear
            </Button>
          </div>
        </header>

        <div className="h-[520px] overflow-y-auto p-5 font-mono text-sm">
          {run.events.length === 0 && (
            <p className="text-muted-foreground">
              {run.status === "running"
                ? "› connecting to GET /api/stream …"
                : "› no active stream. Dispatch a task to begin multi-agent collaboration."}
            </p>
          )}
          <div className="space-y-3">
            {run.events.map((e) => {
              const c = accentClasses[e.agent];
              return (
                <article
                  key={e.id}
                  className={cn(
                    "animate-in fade-in slide-in-from-bottom-2 rounded-xl border p-4 glass-2",
                    c.border,
                  )}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <AgentBadge agent={e.agent} />
                      <span className="text-xs text-muted-foreground">{AGENTS[e.agent].role}</span>
                    </div>
                    <span className="text-[11px] text-muted-foreground">
                      {e.stage} · {(e.latencyMs / 1000).toFixed(2)}s
                      {e.tokens > 0 && ` · ${e.tokens.toLocaleString()} tok`}
                    </span>
                  </div>
                  <h4 className={cn("mt-3 text-sm font-semibold", c.text)}>{e.title}</h4>
                  <pre className="mt-2 whitespace-pre-wrap text-[13px] leading-relaxed text-foreground/85">
                    {e.body}
                  </pre>
                </article>
              );
            })}
            {run.status === "running" && (
              <p className="text-muted-foreground">
                <span className="live-dot inline-block">▍</span> awaiting next agent event…
              </p>
            )}
          </div>
          <div ref={endRef} />
        </div>
      </section>

      <aside className="space-y-4">
        <div className="glass rounded-2xl p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            State matrix
          </h3>
          <ol className="mt-4 space-y-3">
            {STAGES.map((s, i) => {
              const done = activeIndex > i;
              const active = activeIndex === i;
              return (
                <li key={s} className="flex items-center gap-3 text-sm">
                  <span
                    className={cn(
                      "size-2 rounded-full",
                      done ? "bg-codex" : active ? "bg-primary live-dot" : "bg-muted-foreground/30",
                    )}
                  />
                  <span
                    className={cn(
                      active
                        ? "font-medium text-foreground"
                        : done
                          ? "text-foreground/70"
                          : "text-muted-foreground",
                    )}
                  >
                    {s}
                  </span>
                </li>
              );
            })}
          </ol>
        </div>

        <div className="glass rounded-2xl p-5">
          <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Live metrics
          </h3>
          <dl className="mt-4 space-y-3 text-sm">
            <Metric label="Model invocations" value={String(run.invocations)} />
            <Metric label="Tokens used" value={run.tokens.toLocaleString()} />
            <Metric label="Elapsed" value={`${(run.elapsed / 1000).toFixed(1)}s`} />
            <Metric label="Mode" value="propose-only" />
          </dl>
        </div>
      </aside>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-mono text-foreground">{value}</dd>
    </div>
  );
}
