import { useMemo } from "react";
import { summarizeEvents, type ReplayEvent } from "@/lib/citadel/replay-stats";

function fmtTime(iso: string | null) {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString();
}

function fmtSpan(ms: number) {
  if (!ms) return "0s";
  const s = ms / 1000;
  return s < 60 ? `${s.toFixed(1)}s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
      {children}
    </p>
  );
}

export function ReplaySummaryPanel({ events }: { events: ReplayEvent[] }) {
  const s = useMemo(() => summarizeEvents(events), [events]);

  return (
    <section aria-label="Filtered event summary" className="border-b border-border px-5 py-3">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <Label>Filtered run</Label>
          <p className="font-mono text-[13px]">
            {s.count} event{s.count === 1 ? "" : "s"}
          </p>
          <p className="font-mono text-[11px] text-muted-foreground">
            {fmtTime(s.firstTimestamp)} → {fmtTime(s.lastTimestamp)} · {fmtSpan(s.spanMs)}
            {s.tokensTotal > 0 ? ` · ${s.tokensTotal.toLocaleString()} tok` : ""}
          </p>
        </div>

        <div>
          <Label>By agent</Label>
          <ul className="space-y-0.5">
            {s.byAgent.slice(0, 4).map((a) => (
              <li key={a.key} className="flex justify-between gap-3 font-mono text-[11px]">
                <span className="truncate uppercase tracking-[0.12em]">{a.key}</span>
                <span className="text-muted-foreground">{a.count}</span>
              </li>
            ))}
            {s.byAgent.length === 0 && <li className="text-[11px] text-muted-foreground">—</li>}
          </ul>
        </div>

        <div>
          <Label>By type</Label>
          <ul className="space-y-0.5">
            {s.byType.slice(0, 4).map((t) => (
              <li key={t.key} className="flex justify-between gap-3 font-mono text-[11px]">
                <span className="truncate">{t.key}</span>
                <span className="text-muted-foreground">{t.count}</span>
              </li>
            ))}
            {s.byType.length === 0 && <li className="text-[11px] text-muted-foreground">—</li>}
          </ul>
        </div>

        <div>
          <Label>Top repeated errors</Label>
          {s.topErrors.length === 0 ? (
            <p className="font-mono text-[11px] text-muted-foreground">No errors in filtered run</p>
          ) : (
            <ul className="space-y-0.5">
              {s.topErrors.map((e) => (
                <li
                  key={e.text}
                  className="flex justify-between gap-3 font-mono text-[11px] text-destructive"
                >
                  <span className="truncate" title={e.text}>
                    {e.text}
                  </span>
                  <span>×{e.count}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
