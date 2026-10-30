import type { Insight, InsightRun, InsightType, Severity, Trend } from "./types";

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: "Critical",
  warning: "Warning",
  info: "Info",
};

export const SEVERITY_ORDER: Severity[] = ["critical", "warning", "info"];

export const TYPE_LABEL: Record<InsightType, string> = {
  at_risk: "At-risk dispatches",
  bottleneck_forecast: "Bottleneck forecast",
  capacity_gap: "Capacity",
  melting: "Melting",
  load_balancing: "Load balancing",
  dispatch_performance: "Dispatch performance",
  month_forecast: "Month forecast",
  concentration: "Mix and concentration",
  data_health: "Data health",
};

export const TREND_LABEL: Record<Trend, string> = {
  new: "New",
  worse: "Worse than last run",
  better: "Better than last run",
  same: "Unchanged",
};

/** A short glyph for the trend. Always shown with its words, never colour alone. */
export const TREND_MARK: Record<Trend, string> = { new: "●", worse: "▲", better: "▼", same: "–" };

export function bySeverity(cards: Insight[]): Record<Severity, number> {
  const out: Record<Severity, number> = { critical: 0, warning: 0, info: 0 };
  for (const c of cards) out[c.severity] += 1;
  return out;
}

/** "2 critical, 3 warnings, 4 info", leaving out what is zero. */
export function summaryText(counts: Record<Severity, number>): string {
  const parts: string[] = [];
  if (counts.critical) parts.push(`${counts.critical} critical`);
  if (counts.warning) parts.push(`${counts.warning} ${counts.warning === 1 ? "warning" : "warnings"}`);
  if (counts.info) parts.push(`${counts.info} info`);
  return parts.length ? parts.join(", ") : "Nothing to report";
}

export function triggerText(trigger: InsightRun["trigger"]): string {
  return { plan: "after a plan was calculated", manual: "refreshed by hand", actuals: "after actual dispatch dates were loaded" }[trigger];
}

/** Filter by type and severity, keeping the order the server ranked them in. */
export function filterCards(cards: Insight[], type: string, severity: string): Insight[] {
  return cards.filter((c) => (!type || c.type === type) && (!severity || c.severity === severity));
}

/** The types that actually have cards, in the order of TYPE_LABEL. */
export function typesPresent(cards: Insight[]): InsightType[] {
  const present = new Set(cards.map((c) => c.type));
  return (Object.keys(TYPE_LABEL) as InsightType[]).filter((t) => present.has(t));
}

/** A share (0 to 1) as a whole percentage, for the report tables. */
export function pct(share: number | null | undefined): string {
  return share == null ? "–" : `${Math.round(share * 100)}%`;
}

/** Signed days, "+2" or "-1" or "0". */
export function signedDays(days: number | null): string {
  if (days == null) return "–";
  return days > 0 ? `+${days}` : String(days);
}

/** Query string from only the filters that are set. */
export function query(params: Record<string, string | undefined>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v)
    .map(([k, v]) => `${k}=${encodeURIComponent(v as string)}`);
  return parts.length ? `?${parts.join("&")}` : "";
}
