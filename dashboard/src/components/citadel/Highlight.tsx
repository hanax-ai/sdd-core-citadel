/** Highlights every case-insensitive occurrence of `query` inside `text`. */
export function Highlight({ text, query }: { text?: string | null; query: string }) {
  const value = text ?? "";
  const q = query.trim();
  if (!q) return <>{value}</>;

  const lower = value.toLowerCase();
  const needle = q.toLowerCase();
  const parts: Array<{ chunk: string; hit: boolean }> = [];
  let i = 0;
  while (i < value.length) {
    const at = lower.indexOf(needle, i);
    if (at === -1) {
      parts.push({ chunk: value.slice(i), hit: false });
      break;
    }
    if (at > i) parts.push({ chunk: value.slice(i, at), hit: false });
    parts.push({ chunk: value.slice(at, at + needle.length), hit: true });
    i = at + needle.length;
  }

  return (
    <>
      {parts.map((p, idx) =>
        p.hit ? (
          <mark key={idx} className="rounded-[3px] bg-primary/25 px-0.5 text-foreground">
            {p.chunk}
          </mark>
        ) : (
          <span key={idx}>{p.chunk}</span>
        ),
      )}
    </>
  );
}
