import { Link, useRouterState } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { Activity, FileDiff, History, ShieldAlert, Cpu, Radio } from "lucide-react";
import { cn } from "@/lib/utils";
import { useUIStore } from "@/stores/useUIStore";
import { ConnectionControl } from "./ConnectionControl";
import { KeyWarningBanner } from "./KeyWarningBanner";
import { BridgeHealthIndicator } from "./BridgeHealthIndicator";

const NAV = [
  { to: "/", label: "Console", icon: Activity, eyebrow: "Operations view · live" },
  { to: "/patches", label: "Patches", icon: FileDiff, eyebrow: "Review view · propose-only" },
  { to: "/replay", label: "Replay", icon: History, eyebrow: "Forensics view · deterministic" },
  { to: "/raid", label: "RAID", icon: ShieldAlert, eyebrow: "Governance view · register" },
  { to: "/system", label: "System", icon: Cpu, eyebrow: "Diagnostics view · bridge" },
] as const;

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="hidden min-w-0 flex-col border-l border-border pl-4 md:flex">
      <span className="micro-label">{label}</span>
      <span className="truncate font-mono text-xs text-foreground">{value}</span>
    </div>
  );
}

export function AppShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
}) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const { mode, bridgeUrl } = useUIStore();
  const live = mode === "live";
  const eyebrow = NAV.find((n) => n.to === pathname)?.eyebrow ?? "Command center";

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-border bg-sidebar lg:flex">
        <Link to="/" className="flex items-center gap-3 border-b border-border px-5 py-4">
          <span className="flex size-8 items-center justify-center rounded-md border border-primary/40 bg-primary/10">
            <Radio className="size-4 text-primary" />
          </span>
          <span className="leading-tight">
            <span className="block font-mono text-[13px] font-semibold tracking-[0.18em]">
              SDD-Core CITADEL
            </span>
            <span className="micro-label block">Amigo Agents command center</span>
          </span>
        </Link>

        <nav className="flex flex-1 flex-col gap-0.5 p-3">
          <p className="micro-label px-2 pb-2">Navigation</p>
          {NAV.map(({ to, label, icon: Icon }) => {
            const active = pathname === to;
            return (
              <Link
                key={to}
                to={to}
                className={cn(
                  "flex items-center gap-3 rounded-md border border-transparent px-3 py-2 text-sm transition-colors",
                  active
                    ? "border-primary/25 bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-muted/60 hover:text-foreground",
                )}
              >
                <Icon className="size-4" />
                {label}
              </Link>
            );
          })}
        </nav>

        <div className="border-t border-border p-4">
          <ConnectionControl />
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-20 flex flex-wrap items-center gap-4 border-b border-border bg-background/95 px-5 py-3 backdrop-blur">
          <span
            className={cn(
              "inline-flex items-center gap-2 rounded-md border px-2.5 py-1 font-mono text-[10px] uppercase tracking-[0.18em]",
              live
                ? "border-success/40 bg-success/10 text-success"
                : "border-primary/40 bg-primary/10 text-primary",
            )}
          >
            <span className={cn("size-1.5 rounded-full bg-current", live && "live-dot")} />
            {live ? "Live bridge" : "Fixture snapshot · demo"}
          </span>
          <BridgeHealthIndicator />
          <Stat label="Harness" value="amigo-agents · propose-only" />
          <Stat label="Endpoint" value={live ? bridgeUrl : "local fixtures"} />
          <div className="hidden border-l border-border pl-4 md:block">
            <ConnectionControl variant="compact" />
          </div>
          <div className="ml-auto lg:hidden">
            <nav className="flex gap-1 overflow-x-auto">
              {NAV.map(({ to, label }) => (
                <Link
                  key={to}
                  to={to}
                  className={cn(
                    "rounded-md px-2.5 py-1 text-xs",
                    pathname === to
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {label}
                </Link>
              ))}
            </nav>
          </div>
        </header>

        <main className="grid-field min-w-0 flex-1 space-y-5 px-5 py-6">
          <div>
            <p className="micro-label">{eyebrow}</p>
            <h1 className="mt-1.5 text-3xl font-semibold tracking-tight">{title}</h1>
            {subtitle && (
              <p className="mt-1.5 max-w-2xl text-sm text-muted-foreground">{subtitle}</p>
            )}
          </div>
          <KeyWarningBanner />
          {children}
        </main>
      </div>
    </div>
  );
}
