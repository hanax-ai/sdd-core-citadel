import { createFileRoute } from "@tanstack/react-router";
import { AppShell } from "@/components/citadel/AppShell";
import { useSystemStatus } from "@/components/citadel/KeyWarningBanner";
import { StatusPill } from "@/components/citadel/pills";
import { Skeleton } from "@/components/ui/skeleton";
import { AGENT_META } from "@/lib/citadel/contract";
import { useUIStore } from "@/stores/useUIStore";

export const Route = createFileRoute("/system")({
  head: () => ({
    meta: [
      { title: "System status — SDD-Core CITADEL" },
      {
        name: "description",
        content:
          "Bridge health, provider API key detection and configured model IDs for the Amigo Agents harness.",
      },
      { property: "og:title", content: "System status — SDD-Core CITADEL" },
      {
        property: "og:description",
        content: "Bridge health, key detection and model configuration at a glance.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: SystemPage,
});

function SystemPage() {
  const { mode, bridgeUrl } = useUIStore();
  const { data, isLoading, error } = useSystemStatus();

  const rows = data
    ? ([
        ["claude", data.anthropic_key_present, data.anthropic_model, "ANTHROPIC_API_KEY"],
        ["codex", data.openai_key_present, data.openai_model, "OPENAI_API_KEY"],
        ["gemini", data.gemini_key_present, data.gemini_model, "GEMINI_API_KEY"],
      ] as const)
    : [];

  return (
    <AppShell title="System status" subtitle="Bridge connectivity, provider keys and model config.">
      <div className="glass rounded-lg p-5">
        <div className="flex flex-wrap items-center gap-3">
          <StatusPill
            label={mode === "live" ? "LIVE BRIDGE" : "DEMO MODE"}
            tone={mode === "live" ? "success" : "primary"}
          />
          <code className="font-mono text-[11px] text-muted-foreground">
            {mode === "live" ? bridgeUrl : "fixtures://citadel"}
          </code>
        </div>
        {error && <p className="mt-3 text-sm text-destructive">{(error as Error).message}</p>}
      </div>

      {isLoading && <Skeleton className="h-56 w-full rounded-lg" />}

      <div className="grid gap-3 md:grid-cols-3">
        {rows.map(([agent, present, model, envVar]) => (
          <article key={agent} className="glass rounded-lg p-5">
            <p className="text-sm font-medium">{AGENT_META[agent].name}</p>
            <p className="text-xs text-muted-foreground">{AGENT_META[agent].role}</p>
            <div className="mt-3">
              <StatusPill
                label={present ? "KEY DETECTED" : "KEY MISSING"}
                tone={present ? "success" : "danger"}
              />
            </div>
            <dl className="mt-3 space-y-1 text-[11px] text-muted-foreground">
              <div className="flex justify-between gap-2">
                <dt>Model</dt>
                <dd className="font-mono text-foreground">{model}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt>Env var</dt>
                <dd className="font-mono">{envVar}</dd>
              </div>
            </dl>
          </article>
        ))}
      </div>

      <div className="glass rounded-lg p-5 text-sm leading-relaxed text-muted-foreground">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-foreground">
          Zero-contamination guarantees
        </h2>
        <ul className="mt-3 list-disc space-y-1.5 pl-5">
          <li>The harness never writes to the target repository — patches stay in memory.</li>
          <li>Bridge binds to localhost only; CITADEL talks to it from your own browser.</li>
          <li>Transcripts and RAID rows persist in the bridge SQLite database.</li>
        </ul>
      </div>
    </AppShell>
  );
}
