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
