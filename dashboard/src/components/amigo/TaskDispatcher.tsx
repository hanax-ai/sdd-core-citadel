import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Slider } from "@/components/ui/slider";
import { toast } from "sonner";
import { Rocket } from "lucide-react";
import type { useAmigoRun } from "@/hooks/useAmigoRun";

export function TaskDispatcher({ run }: { run: ReturnType<typeof useAmigoRun> }) {
  const [task, setTask] = useState("Refactor auth module and fix race condition");
  const [dir, setDir] = useState(
    "C:\\Users\\JarvisRichardson\\Desktop\\WiP\\SDD-Core-Framework-Analysis",
  );
  const [rounds, setRounds] = useState([3]);

  return (
    <div className="glass rounded-2xl p-5">
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
          disabled={run.status === "running" || !task.trim()}
          onClick={() => {
            run.start();
            toast.success("Run dispatched", {
              description: `${rounds[0]} max rounds · propose-only · no target mutation`,
            });
          }}
        >
          <Rocket /> {run.status === "running" ? "Run in progress…" : "Start run"}
        </Button>
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          Zero-contamination: the harness never writes to the target repository. All patches
          stay in memory for manual hand-application.
        </p>
      </div>
    </div>
  );
}
