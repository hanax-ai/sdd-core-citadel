import { useEffect, useRef, type ReactNode } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  Play,
  Square,
  Eraser,
  Rocket,
  WifiOff,
  Loader2,
  AlertTriangle,
  RotateCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { AgentBadge, StatusPill } from "./pills";
import { StageTracker } from "./StageTracker";
import {
  AGENT_META,
  DEFAULT_GATEKEEPER_AGENT,
  accentClasses,
  roleToAgent,
  type CitadelEvent,
  type GatekeeperAgentId,
} from "@/lib/citadel/contract";
import { useGatekeeperAgent } from "./KeyWarningBanner";
import { cn } from "@/lib/utils";
import type { useAgentStream } from "@/hooks/useAgentStream";

type Run = ReturnType<typeof useAgentStream>;

export function StreamConsole({
  run,
  onDispatch,
  sidebar,
}: {
  run: Run;
  onDispatch: () => void;
  sidebar?: ReactNode;
}) {
  const endRef = useRef<HTMLDivElement>(null);
  const gatekeeper = useGatekeeperAgent();
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [run.events.length]);

  const cards = run.events.filter((e) => e.type !== "token_metric");

  const openFindings = run.events.reduce(
    (n, e) =>
      e.type === "agent_message"
        ? n + (e.findings?.filter((f) => f.severity !== "NOTE").length ?? 0)
        : n,
    0,
  );

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Kpi
          label="Run status"
          value={statusLabel(run)}
          hint={run.runId ? run.runId : "no run dispatched"}
          tone={run.status === "error" ? "danger" : run.status === "running" ? "primary" : "muted"}
        />
        <Kpi
          label="Verdict"
          value={run.verdict ?? "—"}
          hint={`${run.rounds} remediation round${run.rounds === 1 ? "" : "s"}`}
          tone={run.verdict === "PASS" ? "success" : run.verdict ? "danger" : "muted"}
        />
        <Kpi
          label="Open findings"
          value={String(openFindings)}
          hint="gatekeeper · unresolved"
          tone={openFindings ? "warning" : "success"}
        />
        <Kpi
          label="Tokens"
          value={run.tokens.toLocaleString()}
          hint={`${(run.elapsed / 1000).toFixed(1)}s elapsed · ${run.invocations} messages`}
        />
      </div>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_330px]">
        <section className="glass overflow-hidden rounded-lg">
          <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3">
            <div className="flex items-center gap-3">
              <span className="font-mono text-xs text-muted-foreground">
                {run.runId ? `stream/${run.runId}` : "amigo://stream"}
              </span>
              <StatusPill
                label={statusLabel(run)}
                tone={statusTone(run)}
                live={run.status === "running"}
              />
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={onDispatch} disabled={run.isRunning}>
                <Play /> Start run
              </Button>
              <Button size="sm" variant="outline" onClick={run.cancel} disabled={!run.isRunning}>
                <Square /> Cancel
              </Button>
              <Button size="sm" variant="ghost" onClick={run.clear}>
                <Eraser /> Clear
              </Button>
            </div>
          </header>

          <div className="border-b border-border px-5 py-3">
            <StageTracker stage={run.stage} round={run.rounds} />
          </div>

          {run.status === "dispatching" && (
            <div className="flex items-center gap-2 border-b border-primary/30 bg-primary/10 px-5 py-2 text-xs text-primary">
              <Loader2 className="size-3.5 animate-spin" />
              Dispatching task to the bridge — waiting for a run id…
            </div>
          )}

          {run.status !== "error" && run.connection === "connecting" && (
            <div className="flex items-center gap-2 border-b border-primary/30 bg-primary/10 px-5 py-2 text-xs text-primary">
              <Loader2 className="size-3.5 animate-spin" />
              Opening event stream…
            </div>
          )}

          {run.connection === "reconnecting" && (
            <div className="flex items-center gap-2 border-b border-warning/30 bg-warning/10 px-5 py-2 text-xs text-warning">
              <WifiOff className="size-3.5" />
              Stream disconnected. Reconnecting in {run.retryIn}s… (resuming from last event ID)
            </div>
          )}

          {run.connection === "lost" && (
            <div className="flex flex-wrap items-center gap-2 border-b border-destructive/30 bg-destructive/10 px-5 py-2 text-xs text-destructive">
              <WifiOff className="size-3.5" />
              Connection lost after repeated retries. Auto-reconnect stopped.
              <Button
                size="sm"
                variant="outline"
                className="ml-auto h-6 px-2 text-[11px]"
                onClick={run.reconnect}
              >
                <RotateCw className="size-3" /> Reconnect
              </Button>
            </div>
          )}

          {run.status === "error" && (
            <div className="flex flex-wrap items-center gap-2 border-b border-destructive/30 bg-destructive/10 px-5 py-2 text-xs text-destructive">
              <AlertTriangle className="size-3.5" />
              <span className="font-mono">{run.errorText ?? "Bridge unreachable"}</span>
              <Button
                size="sm"
                variant="outline"
                className="ml-auto h-6 px-2 text-[11px]"
                onClick={onDispatch}
              >
                <RotateCw className="size-3" /> Retry
              </Button>
            </div>
          )}

          <div className="h-[560px] overflow-y-auto p-5">
            {cards.length === 0 ? (
              <EmptyState onDispatch={onDispatch} disabled={run.isRunning} />
            ) : (
              <div className="space-y-3">
                <AnimatePresence initial={false}>
                  {cards.map((e) => (
                    <EventCard key={e.id} event={e} gatekeeper={gatekeeper} />
                  ))}
                </AnimatePresence>
                {run.status === "running" && (
                  <p className="font-mono text-sm text-muted-foreground">
                    <span className="live-dot inline-block">▍</span> awaiting next agent event…
                  </p>
                )}
                {run.errorText && (
                  <p className="font-mono text-sm text-destructive">{run.errorText}</p>
                )}
              </div>
            )}
            <div ref={endRef} />
          </div>
        </section>

        <aside className="space-y-4">
          {sidebar}
          <div className="glass rounded-lg p-5">
            <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Live metrics
            </h3>
            <dl className="mt-4 space-y-3 text-sm">
              <Metric label="Agent messages" value={String(run.invocations)} />
              <Metric label="Tokens used" value={run.tokens.toLocaleString()} />
              <Metric label="Rounds" value={String(run.rounds)} />
              <Metric label="Elapsed" value={`${(run.elapsed / 1000).toFixed(1)}s`} />
              <Metric label="Verdict" value={run.verdict ?? "—"} />
              <Metric label="Mode" value="propose-only" />
            </dl>
          </div>

          <div className="glass rounded-lg p-5">
            <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
              Agent roster
            </h3>
            <ul className="mt-4 space-y-3">
              {(["claude", "codex", gatekeeper ?? DEFAULT_GATEKEEPER_AGENT] as const).map((id) => (
                <li key={id} className="flex items-center justify-between gap-2">
                  <AgentBadge agent={id} />
                  <span className="text-[11px] text-muted-foreground">
                    {AGENT_META[id].provider}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </div>
    </div>
  );
}

function Kpi({
  label,
  value,
  hint,
  tone = "muted",
}: {
  label: string;
  value: string;
  hint?: string;
  tone?: "muted" | "primary" | "success" | "warning" | "danger";
}) {
  const toneClass = {
    muted: "text-foreground",
    primary: "text-primary",
    success: "text-success",
    warning: "text-warning",
    danger: "text-destructive",
  }[tone];

  return (
    <div className="glass rounded-lg px-4 py-3">
      <p className="micro-label">{label}</p>
      <p className={cn("mt-1.5 truncate text-2xl font-semibold tracking-tight", toneClass)}>
        {value}
      </p>
      {hint && <p className="mt-1 truncate font-mono text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

function EventCard({
  event,
  gatekeeper,
}: {
  event: CitadelEvent;
  gatekeeper: GatekeeperAgentId | null;
}) {
  if (event.type === "stage_change") {
    return (
      <motion.div
        layout
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0 }}
        className="flex items-center gap-3 py-1"
      >
        <span className="h-px flex-1 bg-border" />
        <span className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
          {event.stage}
        </span>
        <span className="h-px flex-1 bg-border" />
      </motion.div>
    );
  }

  if (event.type === "run_complete") {
    return (
      <motion.article
        layout
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-2 rounded-xl border border-codex/40 p-4"
      >
        <div className="flex flex-wrap items-center justify-between gap-2">
          <StatusPill
            label={`RUN ${event.verdict}`}
            tone={event.verdict === "PASS" ? "success" : "danger"}
          />
          <span className="font-mono text-[11px] text-muted-foreground">
            {event.rounds_total} rounds
            {event.tokens_total ? ` · ${event.tokens_total.toLocaleString()} tok` : ""}
            {event.duration_ms ? ` · ${(event.duration_ms / 1000).toFixed(1)}s` : ""}
          </span>
        </div>
        <p className="mt-2 text-sm text-foreground/85">
          Patch retained in memory only — hand-apply it from the Patches view.
        </p>
      </motion.article>
    );
  }

  if (event.type === "error") {
    return (
      <motion.article
        layout
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass-2 rounded-xl border border-destructive/40 p-4"
      >
        <StatusPill label={event.error_code} tone="danger" />
        <p className="mt-2 font-mono text-[13px] text-destructive">{event.message}</p>
      </motion.article>
    );
  }

  if (event.type !== "agent_message") return null;

  // The event's OWN attribution wins where it exists: the harness stamps the
  // provider that actually served this message, and a live stream can outlive a
  // GATEKEEPER_PROVIDER change mid-session. Current config is the fallback only
  // for events from a harness that predates the field -- unlike replay, that
  // fallback is defensible here because these events are being produced by the
  // very configuration the status endpoint is reporting.
  const agent = roleToAgent(event.agent, event.provider ?? gatekeeper);
  const c = accentClasses[agent];

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ type: "spring", stiffness: 260, damping: 28 }}
      className={cn("glass-2 rounded-xl border p-4", c.border)}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <AgentBadge agent={agent} />
          <span className="text-xs text-muted-foreground">{AGENT_META[agent].role}</span>
        </div>
        <span className="font-mono text-[11px] text-muted-foreground">
          {event.message_type}
          {event.round ? ` · round ${event.round}` : ""}
        </span>
      </div>
      {/* No motion on the message body — spec §5.1 forbids animating code text. */}
      {event.content ? (
        <pre className="mt-3 whitespace-pre-wrap font-mono text-[13px] leading-relaxed text-foreground/85">
          {event.content}
        </pre>
      ) : null}
      {event.findings?.length ? (
        <ul className="mt-3 space-y-1.5">
          {event.findings.map((f, i) => (
            <li key={i} className="flex items-start gap-2 text-xs">
              <span
                className={cn(
                  "mt-0.5 rounded border px-1.5 py-0.5 font-mono text-[10px] uppercase",
                  f.severity === "CRITICAL"
                    ? "border-destructive/40 text-destructive"
                    : f.severity === "WARNING"
                      ? "border-warning/40 text-warning"
                      : "border-border text-muted-foreground",
                )}
              >
                L{f.line} {f.severity}
              </span>
              <span className="text-foreground/80">{f.text}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </motion.article>
  );
}

function EmptyState({ onDispatch, disabled }: { onDispatch: () => void; disabled: boolean }) {
  // Reads the hook directly rather than taking a prop: react-query dedupes the
  // shared status query, so this costs nothing and keeps the call site simple.
  const gatekeeper = useGatekeeperAgent();
  const gatekeeperName = AGENT_META[gatekeeper ?? DEFAULT_GATEKEEPER_AGENT].name;
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4 text-center">
      <div className="grid size-16 place-items-center rounded-lg border border-border bg-muted/30 text-2xl">
        ◈
      </div>
      <div>
        <p className="text-sm font-medium">No runs yet</p>
        <p className="mt-1 max-w-sm text-sm text-muted-foreground">
          Dispatch a task to watch Claude, Codex and {gatekeeperName} collaborate in real time. The
          harness never writes to your target repository.
        </p>
      </div>
      <Button onClick={onDispatch} disabled={disabled}>
        <Rocket /> Dispatch first task
      </Button>
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

function statusLabel(run: Run) {
  switch (run.status) {
    case "running":
      return "STREAMING";
    case "dispatching":
      return "DISPATCHING";
    case "complete":
      return "RUN COMPLETE";
    case "cancelled":
      return "CANCELLED";
    case "error":
      return "ERROR";
    default:
      return "IDLE";
  }
}

function statusTone(run: Run) {
  switch (run.status) {
    case "running":
    case "dispatching":
      return "primary" as const;
    case "complete":
      return "success" as const;
    case "cancelled":
      return "warning" as const;
    case "error":
      return "danger" as const;
    default:
      return "muted" as const;
  }
}
