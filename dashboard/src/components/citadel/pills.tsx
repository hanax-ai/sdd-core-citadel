import { AGENT_META, accentClasses, type AgentId } from "@/lib/citadel/contract";
import { cn } from "@/lib/utils";

export function AgentBadge({ agent, className }: { agent: AgentId; className?: string }) {
  const a = AGENT_META[agent];
  const c = accentClasses[agent];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium tracking-wide",
        c.border,
        c.bg,
        c.text,
        className,
      )}
    >
      <span aria-hidden>{a.icon}</span>
      {a.name}
    </span>
  );
}

export type Tone = "muted" | "success" | "warning" | "danger" | "primary";

const tones: Record<Tone, string> = {
  muted: "border-border bg-muted/40 text-muted-foreground",
  success: "border-codex/40 bg-codex/10 text-codex",
  warning: "border-warning/40 bg-warning/10 text-warning",
  danger: "border-destructive/40 bg-destructive/10 text-destructive",
  primary: "border-primary/40 bg-primary/10 text-primary",
};

const dots: Record<Tone, string> = {
  muted: "bg-muted-foreground",
  success: "bg-codex",
  warning: "bg-warning",
  danger: "bg-destructive",
  primary: "bg-primary",
};

export function StatusPill({
  label,
  tone = "muted",
  live = false,
  className,
}: {
  label: string;
  tone?: Tone;
  live?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-xs font-medium",
        tones[tone],
        className,
      )}
    >
      <span className={cn("size-1.5 rounded-full", dots[tone], live && "live-dot")} />
      {label}
    </span>
  );
}
