import type { ReactNode } from "react";

export type StatTone = "plain" | "ok" | "warn" | "danger" | "ember" | "brand";

/** The colour of the small line under the figure, like the green and red change figures on a finance dashboard. */
const TONE: Record<StatTone, string> = {
  plain: "var(--ink-soft)",
  ok: "var(--ok)",
  warn: "var(--warn)",
  danger: "var(--danger)",
  ember: "var(--ember-ink)",
  brand: "var(--link)",
};

/** One big figure with a quiet label above it and a coloured line below: the quick read at the top of a screen. */
export function Stat({ label, value, hint, tone = "plain" }: { label: string; value: ReactNode; hint?: ReactNode; tone?: StatTone }) {
  return (
    <div className="kpi" style={{ ["--kpi-ink" as string]: TONE[tone] }}>
      <p className="kpi-label">{label}</p>
      <p className="kpi-value">{value}</p>
      {hint && <p className="kpi-hint">{hint}</p>}
    </div>
  );
}

/** A responsive row of stat tiles. */
export function StatRow({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{children}</div>;
}
