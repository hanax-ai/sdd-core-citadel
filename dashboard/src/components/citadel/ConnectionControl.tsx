import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { useUIStore } from "@/stores/useUIStore";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { StatusPill } from "./pills";

export function ConnectionControl({ variant = "panel" }: { variant?: "panel" | "compact" }) {
  const { mode, bridgeUrl, bridgeKey, setMode, setBridgeUrl, setBridgeKey } = useUIStore();
  const live = mode === "live";
  const [showKey, setShowKey] = useState(false);

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
          <>
            <Input
              value={bridgeUrl}
              onChange={(e) => setBridgeUrl(e.target.value)}
              className="h-7 w-52 font-mono text-[11px]"
              aria-label="Bridge base URL"
              spellCheck={false}
            />
            <div className="relative">
              <Input
                type={showKey ? "text" : "password"}
                value={bridgeKey}
                onChange={(e) => setBridgeKey(e.target.value)}
                className="h-7 w-32 pr-7 font-mono text-[11px]"
                aria-label="Bridge key"
                placeholder="bridge key"
                spellCheck={false}
              />
              <button
                type="button"
                onClick={() => setShowKey((v) => !v)}
                className="absolute inset-y-0 right-1 flex items-center text-muted-foreground hover:text-foreground"
                aria-label={showKey ? "Hide bridge key" : "Show bridge key"}
              >
                {showKey ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
              </button>
            </div>
          </>
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
          <Label htmlFor="bridge-key" className="text-[11px] text-muted-foreground">
            Bridge key
          </Label>
          <div className="relative">
            <Input
              id="bridge-key"
              type={showKey ? "text" : "password"}
              value={bridgeKey}
              onChange={(e) => setBridgeKey(e.target.value)}
              className="h-8 pr-8 font-mono text-[11px]"
              placeholder="X-Bridge-Key"
              spellCheck={false}
            />
            <button
              type="button"
              onClick={() => setShowKey((v) => !v)}
              className="absolute inset-y-0 right-1.5 flex items-center text-muted-foreground hover:text-foreground"
              aria-label={showKey ? "Hide bridge key" : "Show bridge key"}
            >
              {showKey ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
            </button>
          </div>
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            Reachable only from a browser on the same machine as{" "}
            <code className="font-mono">bridge/bridge.py</code>. Requires the bridge's{" "}
            <code className="font-mono">BRIDGE_API_KEY</code> — stored in this browser only, never
            sent anywhere except this bridge.
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
