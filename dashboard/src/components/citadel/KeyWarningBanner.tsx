import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, PlugZap } from "lucide-react";
import { citadelApi } from "@/lib/citadel/client";
import { useUIStore } from "@/stores/useUIStore";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { DEFAULT_GATEKEEPER_AGENT, type GatekeeperAgentId } from "@/lib/citadel/contract";

export function useSystemStatus() {
  const mode = useUIStore((s) => s.mode);
  const bridgeUrl = useUIStore((s) => s.bridgeUrl);
  return useQuery({
    queryKey: ["citadel", "status", mode, bridgeUrl],
    queryFn: () => citadelApi.status(bridgeUrl, mode),
    retry: false,
  });
}

/**
 * Which provider is actually serving the Gatekeeper right now.
 *
 * `null` means GATEKEEPER_PROVIDER holds an unrecognised value -- no provider
 * will serve the role at all. Callers must fall back to
 * DEFAULT_GATEKEEPER_AGENT for cosmetic identity only, and suppress any factual
 * claim about keys or models; /api/system/health carries the real diagnosis.
 *
 * While the query is in flight this reports the default, so nothing flickers.
 * react-query dedupes the shared key, so extra call sites are free.
 */
export function useGatekeeperAgent(): GatekeeperAgentId | null {
  const { data } = useSystemStatus();
  return data ? data.gatekeeper_provider : DEFAULT_GATEKEEPER_AGENT;
}

// NB: these are provider keys (bridge -> AI providers: ANTHROPIC_API_KEY,
// OPENAI_API_KEY, and whichever key the ACTIVE gatekeeper provider needs),
// configured server-side in the bridge's own .env -- never entered through this
// UI. Not to be confused with the bridge access key (this UI <-> bridge)
// entered in ConnectionControl.
export function KeyWarningBanner() {
  const mode = useUIStore((s) => s.mode);
  const { data, error } = useSystemStatus();
  const gatekeeper = useGatekeeperAgent();

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

  // Only the ACTIVE gatekeeper provider's key is ever named. Naming
  // GEMINI_API_KEY under GATEKEEPER_PROVIDER=kimi was a false alarm about runs
  // that work fine; never naming MOONSHOT_API_KEY was a false all-clear that
  // let runs die mid-audit. On an unrecognised GATEKEEPER_PROVIDER no key is
  // named at all -- we cannot know which one is needed, and /api/system/health
  // reports the misconfiguration itself.
  const gatekeeperKey =
    gatekeeper === "kimi"
      ? !data.moonshot_key_present && "MOONSHOT_API_KEY (Kimi)"
      : gatekeeper === "gemini"
        ? !data.gemini_key_present && "GEMINI_API_KEY (Gemini)"
        : false;

  const missing = [
    !data.anthropic_key_present && "ANTHROPIC_API_KEY (Claude)",
    !data.openai_key_present && "OPENAI_API_KEY (Codex)",
    gatekeeperKey,
  ].filter(Boolean) as string[];

  // An unrecognised GATEKEEPER_PROVIDER is not a missing key -- no provider
  // serves the role at all, so no key CAN be named. It gets its own banner
  // rather than only a tooltip on the header health pill: it is the same class
  // of failure (a misconfiguration that used to get a green light and then
  // killed the run mid-audit) that this whole surface exists to catch.
  const providerMisconfigured = gatekeeper === null;

  if (!providerMisconfigured && missing.length === 0) return null;

  return (
    <>
      {providerMisconfigured && (
        <Alert className="border-destructive/40 bg-destructive/10">
          <AlertTriangle className="size-4 text-destructive" />
          <AlertTitle className="text-destructive">Gatekeeper provider misconfigured</AlertTitle>
          <AlertDescription>
            <code className="font-mono">GATEKEEPER_PROVIDER</code> holds an unrecognised value —
            valid values are <code className="font-mono">gemini</code> (default) and{" "}
            <code className="font-mono">kimi</code>. No provider will serve the Gatekeeper, so runs
            will fail at the audit stage.
          </AlertDescription>
        </Alert>
      )}
      {missing.length > 0 && (
        <Alert className="border-warning/40 bg-warning/10">
          <AlertTriangle className="size-4 text-warning" />
          <AlertTitle className="text-warning">Provider keys missing</AlertTitle>
          <AlertDescription>
            {missing.join(" · ")} not detected by the bridge. Runs will fail when they reach that
            agent.
          </AlertDescription>
        </Alert>
      )}
    </>
  );
}
