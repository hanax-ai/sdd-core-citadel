import { useEffect, useMemo, useState } from "react";
import type { Finding } from "@/lib/citadel/contract";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

type Line = { text: string; kind: "add" | "del" | "meta" | "hunk" | "ctx"; n: number };

function classify(text: string): Line["kind"] {
  if (text.startsWith("@@")) return "hunk";
  if (text.startsWith("+++") || text.startsWith("---")) return "meta";
  if (text.startsWith("+")) return "add";
  if (text.startsWith("-")) return "del";
  return "ctx";
}

const severityTone: Record<Finding["severity"], string> = {
  blocker: "border-destructive/50 bg-destructive/15 text-destructive",
  warning: "border-warning/50 bg-warning/15 text-warning",
  note: "border-border bg-muted/50 text-muted-foreground",
  resolved: "border-codex/50 bg-codex/15 text-codex",
};

/**
 * Unified diff viewer. Prism highlights the code payload of each line on the
 * client only (SSR renders plain text), and Gatekeeper findings are badged
 * against their line numbers. No motion on diff text — spec §5.1.
 */
export function DiffViewer({
  patch,
  findings = [],
  language = "python",
}: {
  patch: string;
  findings?: Finding[];
  language?: string;
}) {
  const lines = useMemo<Line[]>(
    () =>
      patch
        .replace(/\n$/, "")
        .split("\n")
        .map((text, i) => ({ text, kind: classify(text), n: i + 1 })),
    [patch],
  );

  const [html, setHtml] = useState<string[] | null>(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      const Prism = (await import("prismjs")).default;
      await import("prismjs/components/prism-python");
      if (!alive) return;
      const grammar = Prism.languages[language] ?? Prism.languages.python;
      setHtml(
        lines.map((l) =>
          l.kind === "meta" || l.kind === "hunk"
            ? escapeHtml(l.text)
            : escapeHtml(l.text.slice(0, 1)) + Prism.highlight(l.text.slice(1), grammar, language),
        ),
      );
    })();
    return () => {
      alive = false;
    };
  }, [lines, language]);

  const byLine = useMemo(() => {
    const map = new Map<number, Finding[]>();
    findings.forEach((f) => map.set(f.line, [...(map.get(f.line) ?? []), f]));
    return map;
  }, [findings]);

  if (!patch.trim()) {
    return (
      <p className="p-6 text-sm text-muted-foreground">
        No patch proposed yet. Diffs appear here once the Builder emits a patch.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto font-mono text-[13px] leading-relaxed">
      <table className="w-full border-collapse">
        <tbody>
          {lines.map((l, i) => {
            const lineFindings = byLine.get(l.n);
            return (
              <tr
                key={l.n}
                className={cn(
                  "align-top",
                  l.kind === "add" && "bg-diff-add/10",
                  l.kind === "del" && "bg-diff-del/10",
                  l.kind === "hunk" && "bg-muted/40",
                  lineFindings && "outline outline-1 -outline-offset-1 outline-warning/30",
                )}
              >
                <td className="w-12 select-none border-r border-border px-3 py-0.5 text-right text-muted-foreground/70">
                  {l.n}
                </td>
                <td className="px-3 py-0.5">
                  <code
                    className={cn(
                      "whitespace-pre-wrap break-words",
                      l.kind === "add" && "text-diff-add",
                      l.kind === "del" && "text-diff-del",
                      l.kind === "meta" && "text-muted-foreground",
                      l.kind === "hunk" && "text-gemini",
                    )}
                    dangerouslySetInnerHTML={{ __html: html?.[i] ?? escapeHtml(l.text) }}
                  />
                  {lineFindings?.map((f, k) => (
                    <div key={k} className="mt-1 mb-1 flex items-start gap-2">
                      <Badge
                        variant="outline"
                        className={cn("shrink-0 uppercase", severityTone[f.severity])}
                      >
                        {f.severity}
                      </Badge>
                      <span className="font-sans text-xs text-foreground/80">{f.text}</span>
                    </div>
                  ))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function escapeHtml(s: string) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
