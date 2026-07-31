import { useUIStore } from "@/stores/useUIStore";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { StatusPill } from "./pills";

export function ConnectionControl({ variant = "panel" }: { variant?: "panel" | "compact" }) {
  const { mode, bridgeUrl, setMode, setBridgeUrl } = useUIStore();
  const live = mode === "live";

  if (variant === "compact") {
    return (
      <div className="flex items-center gap-3">
        <Label
          htmlFor="mode-compact"
          className="micro-label cursor-pointer whitespace-nowrap"
          title="Toggle between the local Live Bridge and the scripted demo fixture"
        >
          {live ? "Live bridge" : "Demo mode"}
        </Label>
        <Switch
          id="mode-compact"
          checked={live}
          onCheckedChange={(v) => setMode(v ? "live" : "demo")}
          aria-label="Toggle live bridge mode"
        />
        {live ? (
          <Input
            value={bridgeUrl}
            onChange={(e) => setBridgeUrl(e.target.value)}
            className="h-7 w-52 font-mono text-[11px]"
            aria-label="Bridge base URL"
            spellCheck={false}
          />
        ) : (
          <span className="font-mono text-[11px] text-muted-foreground">scripted fixture</span>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <Label htmlFor="mode" className="text-xs uppercase tracking-widest text-muted-foreground">
          Connection
        </Label>
        <Switch
          id="mode"
          checked={live}
          onCheckedChange={(v) => setMode(v ? "live" : "demo")}
          aria-label="Toggle live bridge mode"
        />
      </div>
      <StatusPill
        label={live ? "LIVE BRIDGE" : "DEMO MODE"}
        tone={live ? "success" : "primary"}
        live={live}
      />
      {live ? (
        <div className="space-y-1.5">
          <Label htmlFor="bridge" className="text-[11px] text-muted-foreground">
            Bridge base URL
          </Label>
          <Input
            id="bridge"
            value={bridgeUrl}
            onChange={(e) => setBridgeUrl(e.target.value)}
            className="h-8 font-mono text-[11px]"
            spellCheck={false}
          />
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            Reachable only from a browser on the same machine as{" "}
            <code className="font-mono">bridge/bridge.py</code>.
          </p>
        </div>
      ) : (
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          Deterministic fixtures — no model calls, no bridge required.
        </p>
      )}
    </div>
  );
}
