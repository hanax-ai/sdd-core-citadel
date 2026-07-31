import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Play, Pause, RotateCcw, Download, Sheet, Search, X } from "lucide-react";
import { toast } from "sonner";
import { AppShell } from "@/components/citadel/AppShell";
import { AgentBadge, StatusPill } from "@/components/citadel/pills";
import { Highlight } from "@/components/citadel/Highlight";
import { ReplaySummaryPanel } from "@/components/citadel/ReplaySummary";
import { eventsToCsv } from "@/lib/citadel/replay-stats";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { citadelApi } from "@/lib/citadel/client";
import { useUIStore } from "@/stores/useUIStore";
import { AGENT_ROLES, ROLE_TO_AGENT, type AgentRole } from "@/lib/citadel/contract";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/replay")({
  head: () => ({
    meta: [
      { title: "Run replay — SDD-Core CITADEL" },
      {
        name: "description",
        content:
          "Deterministic replay of archived Amigo Agents runs with variable speed scrubbing across every agent message and stage change.",
      },
      { property: "og:title", content: "Run replay — SDD-Core CITADEL" },
      {
        property: "og:description",
        content: "Scrub archived multi-agent runs event by event at 0.5x to 8x speed.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: ReplayPage,
});

const EVENT_TYPES = [
  "stage_change",
  "agent_message",
  "token_metric",
  "run_complete",
  "error",
] as const;
type EventType = (typeof EVENT_TYPES)[number];


const EVENT_TYPE_LABEL: Record<EventType, string> = {
  stage_change: "Stage change",
  agent_message: "Agent message",
  token_metric: "Token metric",
  run_complete: "Run complete",
  error: "Error",
};

function ReplayPage() {
  const { mode, bridgeUrl, replaySpeed, setReplaySpeed } = useUIStore();
  const [runId, setRunId] = useState<string | null>(null);
  const [cursor, setCursor] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [agentFilter, setAgentFilter] = useState<AgentRole[]>([]);
  const [typeFilter, setTypeFilter] = useState<EventType | "all">("all");
  const [keyword, setKeyword] = useState("");
  const [onlyMatches, setOnlyMatches] = useState(true);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const logs = useQuery({
    queryKey: ["citadel", "logs", mode, bridgeUrl],
    queryFn: () => citadelApi.logs(bridgeUrl, mode),
    retry: false,
  });

  const activeId = runId ?? logs.data?.[0]?.run_id ?? null;

  const transcript = useQuery({
    queryKey: ["citadel", "transcript", mode, bridgeUrl, activeId],
    queryFn: () => citadelApi.transcript(bridgeUrl, mode, activeId!),
    enabled: !!activeId,
    retry: false,
  });

  const events = useMemo(() => transcript.data?.events ?? [], [transcript.data]);
  const total = events.length;

  useEffect(() => {
    setCursor(0);
    setPlaying(false);
  }, [activeId]);

  const revealed = useMemo(() => events.slice(0, cursor), [events, cursor]);
  const kw = keyword.trim().toLowerCase();
  const filtersActive = agentFilter.length > 0 || typeFilter !== "all" || kw.length > 0;

  function matchesKeyword(e: (typeof events)[number]) {
    if (!kw) return true;
    const p = e.payload as { agent?: AgentRole; content?: string; stage?: string };
    const hay = [p.content, p.stage, p.agent, e.type].filter(Boolean).join(" ").toLowerCase();
    return hay.includes(kw);
  }

  function passesFacets(e: (typeof events)[number]) {
    const p = e.payload as { agent?: AgentRole };
    if (typeFilter !== "all" && e.type !== typeFilter) return false;
    if (agentFilter.length > 0 && (!p.agent || !agentFilter.includes(p.agent))) return false;
    return true;
  }

  // Facet-filtered set; keyword only narrows it when "Show only matches" is on.
  const faceted = useMemo(
    () => revealed.filter(passesFacets),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [revealed, typeFilter, agentFilter],
  );
  const matchCount = useMemo(
    () => (kw ? faceted.filter(matchesKeyword).length : faceted.length),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [faceted, kw],
  );
  const visible = useMemo(
    () => (onlyMatches && kw ? faceted.filter(matchesKeyword) : faceted),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [faceted, onlyMatches, kw],
  );

  // Same filters applied across the WHOLE run, ignoring the playback cursor —
  // this is what the summary panel and the CSV metadata report on.
  const filteredRun = useMemo(() => {
    const base = events.filter(passesFacets);
    return onlyMatches && kw ? base.filter(matchesKeyword) : base;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [events, typeFilter, agentFilter, onlyMatches, kw]);



  // Full virtualization — only rows in view are mounted, no manual paging.
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const virtualizer = useVirtualizer({
    count: visible.length,
    getScrollElement: () => scrollRef.current,
    estimateSize: () => 132,
    overscan: 8,
    getItemKey: (i) => visible[i]?.id ?? i,
  });

  function toggleAgent(role: AgentRole) {
    setAgentFilter((prev) =>
      prev.includes(role) ? prev.filter((r) => r !== role) : [...prev, role],
    );
  }

  function clearFilters() {
    setAgentFilter([]);
    setTypeFilter("all");
    setKeyword("");
  }

  useEffect(() => {
    if (!playing || cursor >= total) return;
    const cur = events[cursor];
    const prev = cursor > 0 ? events[cursor - 1] : null;
    const gap = Math.max(120, (cur.offset_ms - (prev?.offset_ms ?? 0)) / replaySpeed);
    timer.current = setTimeout(() => setCursor((c) => c + 1), Math.min(gap, 2500));
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [playing, cursor, total, events, replaySpeed]);

  useEffect(() => {
    if (cursor >= total && total > 0) setPlaying(false);
  }, [cursor, total]);

  function exportTranscript() {
    const t = transcript.data;
    if (!t) return;
    // Export honours the active persona / type / keyword filters.
    const exported = filtersActive
      ? t.events.filter((e) => passesFacets(e) && matchesKeyword(e))
      : t.events;
    const payload = {
      exported_at: new Date().toISOString(),
      source: mode === "live" ? bridgeUrl : "demo-fixture",
      filters: {
        agents: agentFilter,
        event_type: typeFilter,
        keyword: keyword.trim(),
        applied: filtersActive,
      },
      run: {
        run_id: t.run_id,
        task: t.task,
        target_dir: t.target_dir ?? null,
        verdict: t.verdict,
        created_at: t.created_at,
        patch_text: t.patch_text,
      },
      total_event_count: t.events.length,
      event_count: exported.length,
      events: exported,
    };
    const url = URL.createObjectURL(
      new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `citadel-run-${t.run_id}.json`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast.success("Transcript exported", {
      description: `${exported.length}${
        filtersActive ? ` of ${t.events.length} (filtered)` : ""
      } events · citadel-run-${t.run_id}.json`,
    });
  }

  function exportCsv() {
    const t = transcript.data;
    if (!t) return;
    // Flat CSV of exactly what the virtualized list is currently showing.
    const rows = visible;
    const url = URL.createObjectURL(
      new Blob(
        [
          eventsToCsv(rows, {
            run_id: t.run_id,
            task: t.task,
            source: mode === "live" ? bridgeUrl : "demo-fixture",
            filters: {
              agents: agentFilter,
              event_type: typeFilter,
              keyword: keyword.trim(),
              only_matches: onlyMatches,
              applied: filtersActive,
            },
          }),
        ],
        { type: "text/csv;charset=utf-8" },
      ),
    );

    const a = document.createElement("a");
    a.href = url;
    a.download = `citadel-run-${t.run_id}-events.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
    toast.success("CSV exported", {
      description: `${rows.length} event${rows.length === 1 ? "" : "s"} · citadel-run-${t.run_id}-events.csv`,
    });
  }




  return (
    <AppShell
      title="Run replay"
      subtitle="Deterministic playback of archived transcripts — same events, your pace."
    >
      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <div className="glass h-fit rounded-lg p-3">
          <p className="px-2 py-1 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Archive
          </p>
          {logs.isLoading && <Skeleton className="mt-2 h-20 w-full" />}
          {logs.error && (
            <p className="px-2 py-3 text-xs text-destructive">{(logs.error as Error).message}</p>
          )}
          <ul className="mt-2 space-y-1">
            {logs.data?.map((l) => (
              <li key={l.run_id}>
                <button
                  onClick={() => setRunId(l.run_id)}
                  className={cn(
                    "w-full rounded-xl px-3 py-2 text-left transition-colors",
                    l.run_id === activeId ? "bg-primary/15" : "hover:bg-muted/50",
                  )}
                >
                  <span className="line-clamp-2 text-[13px]">{l.task}</span>
                  <span className="mt-1 block font-mono text-[10px] text-muted-foreground">
                    {new Date(l.created_at).toLocaleString()}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="glass min-w-0 rounded-lg">
          <header className="flex flex-wrap items-center gap-3 border-b border-border px-5 py-3">
            <Button size="sm" onClick={() => setPlaying((p) => !p)} disabled={total === 0}>
              {playing ? <Pause /> : <Play />}
              {playing ? "Pause" : "Play"}
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setCursor(0);
                setPlaying(false);
              }}
            >
              <RotateCcw /> Restart
            </Button>
            <div className="flex min-w-[180px] flex-1 items-center gap-3">
              <Slider
                min={0}
                max={Math.max(total, 1)}
                step={1}
                value={[cursor]}
                onValueChange={([v]) => {
                  setPlaying(false);
                  setCursor(v);
                }}
              />
              <span className="font-mono text-[11px] text-muted-foreground">
                {cursor}/{total}
              </span>
            </div>
            <div className="flex items-center gap-1">
              {([1, 2, 5] as const).map((s) => (
                <button
                  key={s}
                  onClick={() => setReplaySpeed(s)}
                  className={cn(
                    "rounded-md px-2 py-1 font-mono text-[11px] transition-colors",
                    replaySpeed === s
                      ? "bg-primary/20 text-primary"
                      : "text-muted-foreground hover:bg-muted/50",
                  )}
                >
                  {s}x
                </button>
              ))}
            </div>
            <Button
              size="sm"
              variant="outline"
              onClick={exportTranscript}
              disabled={!transcript.data}
              title="Download this run transcript and events as JSON"
            >
              <Download /> Export JSON
            </Button>
            <Button
              size="sm"
              variant="outline"
              onClick={exportCsv}
              disabled={!transcript.data || visible.length === 0}
              title="Download the currently filtered events as CSV"
            >
              <Sheet /> Export CSV
            </Button>
          </header>


          <div className="flex flex-wrap items-center gap-2 border-b border-border px-5 py-2.5">
            <div className="relative min-w-[180px] flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="Search event text, stage, agent…"
                aria-label="Search events by keyword"
                className="h-8 pl-8 text-[13px]"
                spellCheck={false}
              />
            </div>
            <div className="flex items-center gap-1">
              {AGENT_ROLES.map((role) => {
                const on = agentFilter.includes(role);
                return (
                  <button
                    key={role}
                    onClick={() => toggleAgent(role)}
                    aria-pressed={on}
                    className={cn(
                      "rounded-md border px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors",
                      on
                        ? "border-primary/40 bg-primary/15 text-primary"
                        : "border-border text-muted-foreground hover:bg-muted/50",
                    )}
                  >
                    {role}
                  </button>
                );
              })}
            </div>
            <Select
              value={typeFilter}
              onValueChange={(v) => setTypeFilter(v as EventType | "all")}
            >
              <SelectTrigger className="h-8 w-[168px] text-[13px]" aria-label="Filter by event type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All event types</SelectItem>
                {EVENT_TYPES.map((t) => (
                  <SelectItem key={t} value={t}>
                    {EVENT_TYPE_LABEL[t]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <button
              onClick={() => setOnlyMatches((v) => !v)}
              aria-pressed={onlyMatches}
              disabled={!kw}
              title="Show only events containing the keyword"
              className={cn(
                "rounded-md border px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors disabled:opacity-40",
                onlyMatches
                  ? "border-primary/40 bg-primary/15 text-primary"
                  : "border-border text-muted-foreground hover:bg-muted/50",
              )}
            >
              Only matches
            </button>
            <span className="font-mono text-[11px] text-muted-foreground">
              {visible.length}/{revealed.length} shown
              {kw ? ` · ${matchCount} match${matchCount === 1 ? "" : "es"}` : ""}
            </span>
            {filtersActive && (
              <Button size="sm" variant="ghost" onClick={clearFilters}>
                <X /> Clear
              </Button>
            )}
          </div>

          <ReplaySummaryPanel events={filteredRun} />



          <div ref={scrollRef} className="h-[540px] overflow-y-auto p-5">
            {transcript.isLoading && <Skeleton className="h-full w-full" />}
            <div
              className="relative w-full"
              style={{ height: `${virtualizer.getTotalSize()}px` }}
            >
              {virtualizer.getVirtualItems().map((row) => {
                const e = visible[row.index];
                const p = e.payload as {
                  agent?: AgentRole;
                  content?: string;
                  stage?: string;
                  message_type?: string;
                  verdict?: string;
                };
                const hit = kw ? matchesKeyword(e) : false;
                let body: ReactNode = null;
                if (e.type === "stage_change") {
                  body = (
                    <div className="flex items-center gap-3">
                      <span className="h-px flex-1 bg-border" />
                      <span className="font-mono text-[11px] uppercase tracking-widest text-muted-foreground">
                        <Highlight text={p.stage} query={kw} />
                      </span>
                      <span className="h-px flex-1 bg-border" />
                    </div>
                  );
                } else if (e.type === "run_complete") {
                  body = (
                    <StatusPill
                      label={`RUN ${p.verdict ?? ""}`}
                      tone={p.verdict === "PASS" ? "success" : "danger"}
                    />
                  );
                } else if (e.type === "agent_message" && p.agent) {
                  body = (
                    <article
                      className={cn(
                        "glass-2 rounded-xl border p-4",
                        hit && !onlyMatches ? "border-primary/40" : "border-border",
                      )}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <AgentBadge agent={ROLE_TO_AGENT[p.agent]} />
                        <span className="font-mono text-[11px] text-muted-foreground">
                          +{(e.offset_ms / 1000).toFixed(1)}s ·{" "}
                          <Highlight text={p.message_type} query={kw} />
                        </span>
                      </div>
                      <pre className="mt-3 whitespace-pre-wrap font-mono text-[13px] leading-relaxed text-foreground/85">
                        <Highlight text={p.content} query={kw} />
                      </pre>
                    </article>
                  );
                }
                if (!body) return null;
                return (
                  <div
                    key={row.key}
                    data-index={row.index}
                    ref={virtualizer.measureElement}
                    className="absolute left-0 top-0 w-full pb-3"
                    style={{ transform: `translateY(${row.start}px)` }}
                  >
                    {body}
                  </div>
                );
              })}
            </div>

            {cursor === 0 && !transcript.isLoading && (
              <p className="text-sm text-muted-foreground">
                Press play to replay this run event by event.
              </p>
            )}
            {cursor > 0 && visible.length === 0 && (
              <p className="text-sm text-muted-foreground">
                No revealed events match these filters — clear them or keep playing.
              </p>
            )}
          </div>

        </div>
      </div>
    </AppShell>
  );
}
