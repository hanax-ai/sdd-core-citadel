import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, PlugZap } from "lucide-react";
import { citadelApi } from "@/lib/citadel/client";
import { useUIStore } from "@/stores/useUIStore";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";

export function useSystemStatus() {
  const mode = useUIStore((s) => s.mode);
  const bridgeUrl = useUIStore((s) => s.bridgeUrl);
  return useQuery({
    queryKey: ["citadel", "status", mode, bridgeUrl],
    queryFn: () => citadelApi.status(bridgeUrl, mode),
    retry: false,
  });
}

// NB: these are provider keys (bridge -> AI providers: ANTHROPIC_API_KEY,
// OPENAI_API_KEY, GEMINI_API_KEY), configured server-side in the bridge's own
// .env -- never entered through this UI. Not to be confused with the bridge
// access key (this UI <-> bridge) entered in ConnectionControl.
export function KeyWarningBanner() {
  const mode = useUIStore((s) => s.mode);
  const { data, error } = useSystemStatus();

  if (mode === "live" && error) {
    return (
      <Alert className="border-destructive/40 bg-destructive/10">
        <PlugZap className="size-4 text-destructive" />
        <AlertTitle className="text-destructive">Bridge unreachable</AlertTitle>
        <AlertDescription>{(error as Error).message}</AlertDescription>
      </Alert>
    );
  }

  if (!data) return null;

  const missing = [
    !data.anthropic_key_present && "ANTHROPIC_API_KEY (Claude)",
    !data.openai_key_present && "OPENAI_API_KEY (Codex)",
    !data.gemini_key_present && "GEMINI_API_KEY (Gemini)",
  ].filter(Boolean) as string[];

  if (missing.length === 0) return null;

  return (
    <Alert className="border-warning/40 bg-warning/10">
      <AlertTriangle className="size-4 text-warning" />
      <AlertTitle className="text-warning">Provider keys missing</AlertTitle>
      <AlertDescription>
        {missing.join(" · ")} not detected by the bridge. Runs that need those agents will fail.
      </AlertDescription>
    </Alert>
  );
}
