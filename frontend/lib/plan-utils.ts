import type { GanttBar, PlanLineStatus } from "./types";

/** Heatmap buckets for a utilisation share (0 to 1+). The % is always printed too, never colour alone. */
export type HeatLevel = "none" | "idle" | "light" | "busy" | "high" | "over";

export function heatLevel(utilisation: number | null | undefined): HeatLevel {
  if (utilisation == null) return "none";
  if (utilisation <= 0) return "idle";
  if (utilisation < 0.5) return "light";
  if (utilisation < 0.85) return "busy";
  if (utilisation < 1) return "high";
  return "over";
}

export const HEAT_STYLE: Record<HeatLevel, { background: string; color: string }> = {
  none: { background: "transparent", color: "var(--ink-soft)" },
  idle: { background: "var(--sunken)", color: "var(--ink-soft)" },
  light: { background: "var(--brand-wash)", color: "var(--ink)" },
  busy: { background: "color-mix(in srgb, var(--brand) 32%, var(--surface))", color: "var(--ink)" },
  high: { background: "var(--warn-wash)", color: "var(--warn)" },
  over: { background: "var(--danger-wash)", color: "var(--danger)" },
};

export function percent(utilisation: number | null | undefined): string {
  return utilisation == null ? "–" : `${Math.round(utilisation * 100)}%`;
}

export const STATUS_COLOR: Record<PlanLineStatus, string> = {
  on_track: "var(--action)",
  tight: "var(--warn)",
  at_risk: "var(--danger)",
  unscheduled: "var(--ink-soft)",
};

// --- Gantt geometry --------------------------------------------------------------------------------------
export const DAY_MS = 24 * 60 * 60 * 1000;

export interface GanttScale {
  startMs: number;
  days: number;
  width: number;
}

export function xOf(scale: GanttScale, iso: string | number): number {
  const ms = typeof iso === "number" ? iso : new Date(iso).getTime();
  return ((ms - scale.startMs) / (scale.days * DAY_MS)) * scale.width;
}

export interface PlacedBar<T> {
  bar: T;
  x: number;
  width: number;
}

/**
 * Lay the bars of one resource out. Several lines share a shift, so inside each shift they are
 * packed left to right, each as wide as its share of that shift's capacity. Free capacity is left blank.
 */
export function placeResourceBars(bars: GanttBar[], scale: GanttScale): PlacedBar<GanttBar>[] {
  const bySlot = new Map<number | string, GanttBar[]>();
  for (const b of bars) {
    const key = b.slot ?? `${b.start}`;
    bySlot.set(key, [...(bySlot.get(key) ?? []), b]);
  }
  const placed: PlacedBar<GanttBar>[] = [];
  for (const group of bySlot.values()) {
    const x0 = xOf(scale, group[0].start);
    const slotWidth = xOf(scale, group[0].end) - x0;
    const capacity = group[0].slot_capacity && group[0].slot_capacity > 0 ? group[0].slot_capacity : group.reduce((s, b) => s + (b.minutes ?? 0), 0);
    let cursor = x0;
    for (const b of group) {
      const share = capacity > 0 ? Math.min(1, (b.minutes ?? 0) / capacity) : 0;
      const w = Math.max(1.5, slotWidth * share);
      placed.push({ bar: b, x: cursor, width: w });
      cursor += w;
    }
  }
  return placed;
}

/** Bars that fall inside the window, clipped to its edges. */
export function clip(x: number, width: number, total: number): { x: number; width: number } | null {
  const end = x + width;
  if (end <= 0 || x >= total) return null;
  const cx = Math.max(0, x);
  return { x: cx, width: Math.min(total, end) - cx };
}

/** How loaded a machine is, for the home page's capacity chart: red from 90%, amber from 70%, teal below, gray when idle. */
export type CapacityLevel = "none" | "cool" | "warm" | "hot";

export function capacityLevel(utilisation: number | null | undefined): CapacityLevel {
  if (utilisation == null || utilisation <= 0) return "none";
  if (utilisation < 0.7) return "cool";
  if (utilisation < 0.9) return "warm";
  return "hot";
}

export const CAPACITY_COLOR: Record<CapacityLevel, string> = {
  none: "var(--line)",
  cool: "color-mix(in srgb, var(--brand) 82%, var(--link))",
  warm: "#e6a21a",
  hot: "#d6453a",
};

export const CAPACITY_LABEL: Record<CapacityLevel, string> = {
  none: "No load",
  cool: "Under 70%",
  warm: "70 to 89%",
  hot: "90% or more",
};

/**
 * What holds a late order up, short enough for a table cell: the step ("Moulding") and the days it costs ("0.3d").
 * The days come from the sentence the plan wrote ("... (0.3 days from first to last piece)" or "... waited about
 * 0.3 days ..."); when there is none, only the step is returned.
 */
export function holdingSummary(op: string, text: string): { step: string; days: string | null } {
  const step = op ? op.charAt(0).toUpperCase() + op.slice(1) : "";
  const found = /(\d+(?:\.\d+)?)\s*days?/i.exec(text ?? "");
  return { step, days: found ? `${found[1]}d` : null };
}

/** Working days spare (+) or late (-) with its unit: "+2d", "-4d", "0d". Empty when there is no estimate. */
export function slackLabel(days: number | null | undefined): string {
  if (days == null) return "–";
  return `${days > 0 ? "+" : ""}${days}d`;
}

/** The same, in words, for tooltips and screen readers: "4 working days late". */
export function slackWords(days: number | null | undefined): string {
  if (days == null) return "No estimate";
  if (days === 0) return "Ships on the internal due date";
  const n = Math.abs(days);
  return `${n} working ${n === 1 ? "day" : "days"} ${days < 0 ? "late" : "spare"}`;
}

/** How much of the work is late, and how loudly the At risk tile should say so. */
export interface RiskShare {
  /** 0 to 1; 0 when there is nothing planned. */
  share: number;
  /** "90% of open orders", or null when nothing is late. */
  badge: string | null;
  /** none: nothing late. watch: a few late, shown with a ratio. alert: a quarter or more, so the whole tile is tinted. */
  level: "none" | "watch" | "alert";
}

/** The share of planned orders that will miss their date. A quarter or more turns the tile into an alert. */
export function riskShare(atRisk: number, planned: number): RiskShare {
  if (atRisk <= 0 || planned <= 0) return { share: 0, badge: null, level: "none" };
  const share = Math.min(1, atRisk / planned);
  return { share, badge: `${Math.round(share * 100)}% of open orders`, level: share >= 0.25 ? "alert" : "watch" };
}
