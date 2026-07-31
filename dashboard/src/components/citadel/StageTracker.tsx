import { STAGE_TRACK, STAGE_LABEL, type Stage } from "@/lib/citadel/contract";
import { cn } from "@/lib/utils";
import { motion } from "framer-motion";

/** Round-2 stages collapse onto their round-1 pill. */
function normalize(stage: Stage | null): Stage | null {
  if (!stage) return null;
  if (stage === "BUILDER_PATCH_R2") return "BUILDER_PATCH_R1";
  if (stage === "GATEKEEPER_AUDIT_R2") return "GATEKEEPER_AUDIT_R1";
  return stage;
}

export function StageTracker({ stage, round }: { stage: Stage | null; round?: number }) {
  const current = normalize(stage);
  const activeIndex = current ? STAGE_TRACK.indexOf(current) : -1;

  return (
    <ol className="flex flex-wrap items-center gap-2" aria-label="Run stage tracker">
      {STAGE_TRACK.map((s, i) => {
        const done = activeIndex > i;
        const active = activeIndex === i;
        const showRound =
          active && round && round > 1 && (s === "BUILDER_PATCH_R1" || s === "GATEKEEPER_AUDIT_R1");
        return (
          <li key={s} className="flex items-center gap-2">
            <motion.span
              layout
              animate={{ scale: active ? 1.02 : 1 }}
              transition={{ type: "spring", stiffness: 320, damping: 26 }}
              className={cn(
                "inline-flex items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-medium uppercase tracking-wider",
                active
                  ? "border-primary/50 bg-primary/15 text-primary"
                  : done
                    ? "border-codex/40 bg-codex/10 text-codex"
                    : "border-border bg-muted/30 text-muted-foreground",
              )}
            >
              <span
                className={cn(
                  "size-1.5 rounded-full",
                  active ? "bg-primary live-dot" : done ? "bg-codex" : "bg-muted-foreground/50",
                )}
              />
              {STAGE_LABEL[s]}
              {showRound ? ` R${round}` : ""}
            </motion.span>
            {i < STAGE_TRACK.length - 1 && (
              <span
                aria-hidden
                className={cn("h-px w-4", done ? "bg-codex/50" : "bg-border")}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}
