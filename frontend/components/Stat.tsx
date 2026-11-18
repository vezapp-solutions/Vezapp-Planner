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

/**
 * One big figure with a quiet label above it and a coloured line below: the quick read at the top of a screen.
 * `badge` is a small pill beside the label (a ratio such as "90% of open orders"); `alert` tints the whole tile red
 * for the one figure that needs attention first.
 */
export function Stat({ label, value, hint, tone = "plain", badge, alert = false }: { label: string; value: ReactNode; hint?: ReactNode; tone?: StatTone; badge?: ReactNode; alert?: boolean }) {
  return (
    <div className="kpi" data-alert={alert || undefined} style={{ ["--kpi-ink" as string]: TONE[tone] }}>
      <div className="flex min-h-[1.625rem] flex-wrap items-center justify-between gap-x-3 gap-y-1.5">
        <p className="kpi-label">{label}</p>
        {badge && <span className="badge hidden bg-danger-wash text-danger sm:inline-flex">{badge}</span>}
      </div>
      <p className="kpi-value">{value}</p>
      {hint && <p className="kpi-hint">{hint}</p>}
      {/* On a narrow tile the ratio goes underneath, so the figures in a row still line up. */}
      {badge && <span className="badge mt-3 bg-danger-wash text-danger sm:hidden">{badge}</span>}
    </div>
  );
}

/** A responsive row of stat tiles. */
export function StatRow({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{children}</div>;
}
