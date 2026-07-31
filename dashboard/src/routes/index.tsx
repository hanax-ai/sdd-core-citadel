import { createFileRoute } from "@tanstack/react-router";
import { useRef } from "react";
import { AppShell } from "@/components/citadel/AppShell";
import { StreamConsole } from "@/components/citadel/StreamConsole";
import { TaskDispatcher } from "@/components/citadel/TaskDispatcher";
import { useAgentStream } from "@/hooks/useAgentStream";
import type { RunTaskRequest } from "@/lib/citadel/contract";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "SDD-Core CITADEL — Amigo Agents Command Center" },
      {
        name: "description",
        content:
          "Real-time multi-agent command center for the Amigo Agents harness: live Researcher, Builder and Gatekeeper stream, propose-only patches, deterministic replay.",
      },
      { property: "og:title", content: "SDD-Core CITADEL — Agent Command Center" },
      {
        property: "og:description",
        content:
          "Stream Researcher, Builder and Gatekeeper collaboration live, review propose-only diffs and replay past runs.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: ConsolePage,
});

function ConsolePage() {
  const run = useAgentStream();
  const latest = useRef<RunTaskRequest>({
    task: "Refactor auth module and fix token refresh race condition",
    target_dir: "C:\\Users\\JarvisRichardson\\Desktop\\WiP\\SDD-Core-Framework-Analysis",
    max_rounds: 3,
  });

  return (
    <AppShell
      title="SDD-Core CITADEL"
      subtitle="Live multi-agent collaboration over SSE — Researcher, Builder, Gatekeeper."
    >
      <StreamConsole
        run={run}
        onDispatch={() => void run.start(latest.current)}
        sidebar={
          <TaskDispatcher
            disabled={run.isRunning}
            registerDefaults={(req) => {
              latest.current = req;
            }}
            onDispatch={(req) => run.start(req)}
          />
        }
      />
    </AppShell>
  );
}
