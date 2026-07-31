import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { AppShell } from "@/components/citadel/AppShell";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { citadelApi } from "@/lib/citadel/client";
import { useUIStore } from "@/stores/useUIStore";
import { RAID_STATUSES, RAID_TYPES, type RaidItem, type RaidType } from "@/lib/citadel/contract";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/raid")({
  head: () => ({
    meta: [
      { title: "RAID register — SDD-Core CITADEL" },
      {
        name: "description",
        content:
          "Track risks, assumptions, issues and dependencies across SDD-Core phases with owners, status and phase filtering.",
      },
      { property: "og:title", content: "RAID register — SDD-Core CITADEL" },
      {
        property: "og:description",
        content: "Risks, assumptions, issues and dependencies for the SDD-Core programme.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: RaidPage,
});

const TYPE_STYLE: Record<RaidType, string> = {
  RISK: "border-destructive/40 text-destructive",
  ASSUMPTION: "border-claude/40 text-claude",
  ISSUE: "border-warning/40 text-warning",
  DEPENDENCY: "border-gemini/40 text-gemini",
};

function RaidPage() {
  const { mode, bridgeUrl } = useUIStore();
  const [type, setType] = useState<RaidType | "ALL">("ALL");
  const [q, setQ] = useState("");

  const raid = useQuery({
    queryKey: ["citadel", "raid", mode, bridgeUrl],
    queryFn: () => citadelApi.raid(bridgeUrl, mode),
    retry: false,
  });

  const items = useMemo(() => {
    const all: RaidItem[] = raid.data ?? [];
    return all.filter(
      (i) =>
        (type === "ALL" || i.type === type) &&
        (q.trim() === "" ||
          `${i.title} ${i.description} ${i.owner} ${i.phase}`
            .toLowerCase()
            .includes(q.toLowerCase())),
    );
  }, [raid.data, type, q]);

  return (
    <AppShell
      title="RAID register"
      subtitle="Risks, assumptions, issues and dependencies tracked across SDD-Core phases."
    >
      <div className="flex flex-wrap items-center gap-2">
        {(["ALL", ...RAID_TYPES] as const).map((t) => (
          <button
            key={t}
            onClick={() => setType(t)}
            className={cn(
              "rounded-full border px-3 py-1 font-mono text-[11px] uppercase tracking-wider transition-colors",
              type === t
                ? "border-primary/50 bg-primary/15 text-primary"
                : "border-border text-muted-foreground hover:text-foreground",
            )}
          >
            {t}
          </button>
        ))}
        <Input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search title, owner, phase…"
          className="h-8 max-w-xs"
        />
      </div>

      {raid.isLoading && <Skeleton className="h-72 w-full rounded-lg" />}
      {raid.error && (
        <div className="glass rounded-lg p-5 text-sm text-destructive">
          {(raid.error as Error).message}
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {items.map((i) => (
          <article key={i.id} className="glass rounded-lg p-4">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span
                className={cn(
                  "rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider",
                  TYPE_STYLE[i.type],
                )}
              >
                {i.type}
              </span>
              <span className="font-mono text-[10px] text-muted-foreground">{i.id}</span>
            </div>
            <h2 className="mt-2 text-sm font-medium">{i.title}</h2>
            <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
              {i.description}
            </p>
            <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[11px] text-muted-foreground">
              <div className="flex gap-1.5">
                <dt>Owner</dt>
                <dd className="text-foreground">{i.owner}</dd>
              </div>
              <div className="flex gap-1.5">
                <dt>Phase</dt>
                <dd className="text-foreground">{i.phase}</dd>
              </div>
              <div className="flex gap-1.5">
                <dt>Status</dt>
                <dd
                  className={cn("font-mono", i.status === "CLOSED" ? "text-codex" : "text-warning")}
                >
                  {i.status}
                </dd>
              </div>
            </dl>
          </article>
        ))}
      </div>

      {!raid.isLoading && items.length === 0 && (
        <div className="glass grid h-40 place-items-center rounded-lg text-sm text-muted-foreground">
          No RAID items match this filter. Statuses: {RAID_STATUSES.join(" · ")}
        </div>
      )}
    </AppShell>
  );
}
