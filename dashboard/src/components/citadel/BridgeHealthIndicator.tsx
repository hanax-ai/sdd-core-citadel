import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Loader2, PlugZap, AlertTriangle } from "lucide-react";
import { citadelApi } from "@/lib/citadel/client";
import { useUIStore } from "@/stores/useUIStore";
import { cn } from "@/lib/utils";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

export function useBridgeHealth() {
  const mode = useUIStore((s) => s.mode);
  const bridgeUrl = useUIStore((s) => s.bridgeUrl);
  return useQuery({
    queryKey: ["citadel", "health", mode, bridgeUrl],
    queryFn: () => citadelApi.health(bridgeUrl, mode),
    refetchInterval: mode === "live" ? 10_000 : false,
    retry: false,
  });
}

export function BridgeHealthIndicator() {
  const mode = useUIStore((s) => s.mode);
  const bridgeUrl = useUIStore((s) => s.bridgeUrl);
  const { data, error, isFetching } = useBridgeHealth();

  if (mode !== "live") {
    return (
      <span className="inline-flex items-center gap-2 rounded-md border border-border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
        <span className="size-1.5 rounded-full bg-muted-foreground" />
        Bridge idle · demo
      </span>
    );
  }

  const connected = !error && !!data;
  const degraded = connected && data.status !== "ok";

  const tone = !connected
    ? "border-destructive/40 bg-destructive/10 text-destructive"
    : degraded
      ? "border-warning/40 bg-warning/10 text-warning"
      : "border-success/40 bg-success/10 text-success";

  const label = !connected ? "Disconnected" : degraded ? "Degraded" : "Connected";
  const Icon = !connected ? PlugZap : degraded ? AlertTriangle : CheckCircle2;

  const detail: string[] = !connected
    ? [
        (error as Error | null)?.message ??
          `No response from ${bridgeUrl}/api/system/health. Start bridge/bridge.py.`,
      ]
    : data.problems.length > 0
      ? data.problems
      : [`Bridge v${data.version || "?"} · ${data.active_runs} active run(s)`];

  return (
    <TooltipProvider delayDuration={100}>
      <Tooltip>
      <TooltipTrigger asChild>
        <span
          className={cn(
            "inline-flex cursor-help items-center gap-2 rounded-md border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.18em]",
            tone,
          )}
          aria-live="polite"
        >
          {isFetching && !data ? (
            <Loader2 className="size-3 animate-spin" />
          ) : (
            <Icon className="size-3" />
          )}
          {label}
        </span>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs">
        <p className="font-mono text-[11px] leading-relaxed">
          {bridgeUrl}
          /api/system/health
        </p>
        <ul className="mt-1 list-disc space-y-0.5 pl-4 text-[11px] leading-relaxed">
          {detail.map((d) => (
            <li key={d}>{d}</li>
          ))}
        </ul>
        {connected && (
          <p className="mt-1 font-mono text-[10px] opacity-70">
            uptime {Math.round(data.uptime_s)}s · db {data.database_ok ? "ok" : "unavailable"}
          </p>
        )}
      </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}
