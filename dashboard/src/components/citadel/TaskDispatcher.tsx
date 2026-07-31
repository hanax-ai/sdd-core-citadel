import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { Rocket } from "lucide-react";
import { toast } from "sonner";
import { useUIStore } from "@/stores/useUIStore";
import type { RunTaskRequest } from "@/lib/citadel/contract";

export function TaskDispatcher({
  onDispatch,
  disabled,
  registerDefaults,
}: {
  onDispatch: (req: RunTaskRequest) => Promise<unknown>;
  disabled: boolean;
  registerDefaults?: (req: RunTaskRequest) => void;
}) {
  const mode = useUIStore((s) => s.mode);
  const [task, setTask] = useState("Refactor auth module and fix token refresh race condition");
  const [dir, setDir] = useState(
    "C:\\Users\\JarvisRichardson\\Desktop\\WiP\\SDD-Core-Framework-Analysis",
  );
  const [rounds, setRounds] = useState([3]);

  const req: RunTaskRequest = { task, target_dir: dir, max_rounds: rounds[0] };
  registerDefaults?.(req);

  return (
    <div className="glass rounded-lg p-5">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          Task dispatcher
        </h3>
        <code className="font-mono text-[11px] text-muted-foreground">POST /api/run-task</code>
      </div>

      <div className="mt-4 space-y-4">
        <div className="space-y-2">
          <Label htmlFor="task">Task description</Label>
          <Textarea
            id="task"
            value={task}
            onChange={(e) => setTask(e.target.value)}
            rows={3}
            className="font-mono text-[13px]"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="dir">Target directory (AMIGO_TARGET_DIR)</Label>
          <Input
            id="dir"
            value={dir}
            onChange={(e) => setDir(e.target.value)}
            className="font-mono text-[12px]"
            spellCheck={false}
          />
        </div>
        <div className="space-y-2">
          <div className="flex justify-between">
            <Label>Max remediation rounds</Label>
            <span className="font-mono text-sm text-primary">{rounds[0]}</span>
          </div>
          <Slider min={1} max={6} step={1} value={rounds} onValueChange={setRounds} />
        </div>
        <Button
          className="w-full"
          disabled={disabled || !task.trim()}
          onClick={async () => {
            try {
              await onDispatch(req);
              toast.success(mode === "live" ? "Run dispatched to bridge" : "Demo run started", {
                description: `${rounds[0]} max rounds · propose-only · no target mutation`,
              });
            } catch (err) {
              toast.error("Dispatch failed", {
                description: err instanceof Error ? err.message : "Unknown error",
              });
            }
          }}
        >
          <Rocket /> {disabled ? "Run in progress…" : "Start run"}
        </Button>
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          Zero-contamination: the harness never writes to the target repository. Patches stay in
          memory for manual hand-application.
        </p>
      </div>
    </div>
  );
}
