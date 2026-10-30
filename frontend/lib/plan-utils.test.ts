import { describe, expect, it } from "vitest";

import { DAY_MS, clip, heatLevel, percent, placeResourceBars, xOf } from "./plan-utils";
import type { GanttBar } from "./types";

describe("heatLevel", () => {
  it("buckets utilisation and keeps missing capacity separate", () => {
    expect(heatLevel(null)).toBe("none");
    expect(heatLevel(0)).toBe("idle");
    expect(heatLevel(0.3)).toBe("light");
    expect(heatLevel(0.5)).toBe("busy");
    expect(heatLevel(0.84)).toBe("busy");
    expect(heatLevel(0.85)).toBe("high");
    expect(heatLevel(0.98)).toBe("high");
    expect(heatLevel(1)).toBe("over");
    expect(heatLevel(1.4)).toBe("over");
  });

  it("prints a percentage or a dash", () => {
    expect(percent(0.9804)).toBe("98%");
    expect(percent(null)).toBe("–");
  });
});

const scale = { startMs: Date.parse("2026-11-02T00:00:00+05:30"), days: 7, width: 700 };

describe("gantt geometry", () => {
  it("maps time to x so that one day is width / days", () => {
    expect(xOf(scale, scale.startMs)).toBe(0);
    expect(xOf(scale, scale.startMs + DAY_MS)).toBeCloseTo(100);
    expect(xOf(scale, "2026-11-04T00:00:00+05:30")).toBeCloseTo(200);
  });

  const bar = (minutes: number, line: number): GanttBar => ({
    row: 1,
    row_label: "F1",
    status: "on_track",
    start: "2026-11-02T06:00:00+05:30",
    end: "2026-11-02T14:00:00+05:30",
    code: "melting",
    slot: 7,
    slot_capacity: 400,
    minutes,
    line,
  });

  it("packs lines inside one shift by their share of capacity and leaves the rest free", () => {
    const placed = placeResourceBars([bar(100, 1), bar(200, 2)], scale);
    const slotWidth = (8 / 24) * 100; // an 8 hour shift on a 100 px day
    expect(placed[0].width).toBeCloseTo(slotWidth * 0.25);
    expect(placed[1].x).toBeCloseTo(placed[0].x + placed[0].width);
    expect(placed[1].width).toBeCloseTo(slotWidth * 0.5);
    expect(placed[1].x + placed[1].width).toBeLessThan(placed[0].x + slotWidth); // 75 of 400 min free
  });

  it("never draws a bar wider than its shift", () => {
    const placed = placeResourceBars([bar(900, 1)], scale);
    expect(placed[0].width).toBeCloseTo((8 / 24) * 100);
  });

  it("clips bars to the window", () => {
    expect(clip(-20, 50, 700)).toEqual({ x: 0, width: 30 });
    expect(clip(680, 50, 700)).toEqual({ x: 680, width: 20 });
    expect(clip(710, 20, 700)).toBeNull();
    expect(clip(-30, 20, 700)).toBeNull();
  });
});
