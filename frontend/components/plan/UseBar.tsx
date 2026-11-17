/** A small bar with the percentage always printed, so colour is never the only signal. */
export function UseBar({ pct, label }: { pct: number | null; label?: string }) {
  if (pct === null) return <span className="text-ink-soft">–</span>;
  const tone = pct >= 98 ? "bg-danger" : pct >= 85 ? "bg-warn" : "bg-action";
  return (
    <span className="inline-flex items-center gap-2" title={label}>
      <span className="h-2 w-20 overflow-hidden rounded-full bg-sunken" aria-hidden="true">
        <span className={`block h-full rounded-full ${tone}`} style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} />
      </span>
      <span className="font-mono text-xs">{pct.toFixed(0)}%</span>
    </span>
  );
}
