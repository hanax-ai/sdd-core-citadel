import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { AppShell } from "@/components/citadel/AppShell";
import { DiffViewer } from "@/components/citadel/DiffViewer";
import { StatusPill } from "@/components/citadel/pills";
import { citadelApi } from "@/lib/citadel/client";
import { useUIStore } from "@/stores/useUIStore";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import type { Finding } from "@/lib/citadel/contract";

export const Route = createFileRoute("/patches")({
  head: () => ({
    meta: [
      { title: "Patch review — SDD-Core CITADEL" },
      {
        name: "description",
        content:
          "Review propose-only unified diffs produced by the Amigo Agents harness, with Gatekeeper findings pinned to the exact changed lines.",
      },
      { property: "og:title", content: "Patch review — SDD-Core CITADEL" },
      {
        property: "og:description",
        content: "Unified diffs with inline Gatekeeper findings, never auto-applied.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: PatchesPage,
});

function PatchesPage() {
  const { mode, bridgeUrl } = useUIStore();
  const [selected, setSelected] = useState<string | null>(null);

  const logs = useQuery({
    queryKey: ["citadel", "logs", mode, bridgeUrl],
    queryFn: () => citadelApi.logs(bridgeUrl, mode),
    retry: false,
  });

  const runId = selected ?? logs.data?.[0]?.run_id ?? null;

  const transcript = useQuery({
    queryKey: ["citadel", "transcript", mode, bridgeUrl, runId],
    queryFn: () => citadelApi.transcript(bridgeUrl, mode, runId!),
    enabled: !!runId,
    retry: false,
  });

  const findings: Finding[] =
    transcript.data?.events.flatMap((e) => {
      const f = (e.payload as { findings?: Finding[] }).findings;
      return Array.isArray(f) ? f : [];
    }) ?? [];

  return (
    <AppShell
      title="Patch review"
      subtitle="Propose-only diffs. Nothing is written to the target repository — copy and apply by hand."
    >
      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <div className="glass h-fit rounded-lg p-3">
          <p className="px-2 py-1 text-xs font-semibold uppercase tracking-widest text-muted-foreground">
            Runs
          </p>
          {logs.isLoading && <Skeleton className="mt-2 h-20 w-full" />}
          {logs.error && (
            <p className="px-2 py-3 text-xs text-destructive">{(logs.error as Error).message}</p>
          )}
          <ul className="mt-2 space-y-1">
            {logs.data?.map((l) => (
              <li key={l.run_id}>
                <button
                  onClick={() => setSelected(l.run_id)}
                  className={cn(
                    "w-full rounded-xl px-3 py-2 text-left transition-colors",
                    l.run_id === runId ? "bg-primary/15" : "hover:bg-muted/50",
                  )}
                >
                  <span className="line-clamp-2 text-[13px] text-foreground">{l.task}</span>
                  <span className="mt-1 flex items-center gap-2">
                    <StatusPill
                      label={l.verdict}
                      tone={l.verdict === "PASS" ? "success" : "danger"}
                    />
                    <span className="font-mono text-[10px] text-muted-foreground">{l.run_id}</span>
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="min-w-0">
          {transcript.isLoading && <Skeleton className="h-[520px] w-full rounded-lg" />}
          {transcript.data && (
            <DiffViewer patch={transcript.data.patch_text} findings={findings} />
          )}
          {!runId && !logs.isLoading && (
            <div className="glass grid h-64 place-items-center rounded-lg text-sm text-muted-foreground">
              No completed runs yet.
            </div>
          )}
        </div>
      </div>
    </AppShell>
  );
}
