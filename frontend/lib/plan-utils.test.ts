import { describe, expect, it } from "vitest";

import { DAY_MS, capacityLevel, clip, heatLevel, holdingSummary, percent, placeResourceBars, riskShare, slackLabel, slackWords, xOf } from "./plan-utils";
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

describe("capacityLevel", () => {
  it("is gray with no load, then teal, amber and red from 70% and 90%", () => {
    expect(capacityLevel(null)).toBe("none");
    expect(capacityLevel(0)).toBe("none");
    expect(capacityLevel(0.01)).toBe("cool");
    expect(capacityLevel(0.699)).toBe("cool");
    expect(capacityLevel(0.7)).toBe("warm");
    expect(capacityLevel(0.899)).toBe("warm");
    expect(capacityLevel(0.9)).toBe("hot");
    expect(capacityLevel(1.4)).toBe("hot");
  });
});

describe("holdingSummary", () => {
  it("gives the step and the days from either wording the plan uses", () => {
    expect(holdingSummary("moulding", "Moulding takes the longest (0.3 days from first to last piece).")).toEqual({ step: "Moulding", days: "0.3d" });
    expect(holdingSummary("moulding", "Moulding held it up: its work waited about 0.3 days on average for capacity.")).toEqual({ step: "Moulding", days: "0.3d" });
    expect(holdingSummary("melting", "Melting takes the longest (2 days from first to last piece).")).toEqual({ step: "Melting", days: "2d" });
  });

  it("returns only the step when the sentence has no figure, and nothing when there is no step", () => {
    expect(holdingSummary("moulding", "")).toEqual({ step: "Moulding", days: null });
    expect(holdingSummary("", "")).toEqual({ step: "", days: null });
  });
});

describe("slackLabel and slackWords", () => {
  it("puts the unit on the number so -4 is never ambiguous", () => {
    expect(slackLabel(-4)).toBe("-4d");
    expect(slackLabel(2)).toBe("+2d");
    expect(slackLabel(0)).toBe("0d");
    expect(slackLabel(null)).toBe("–");
  });

  it("says it in words for tooltips", () => {
    expect(slackWords(-4)).toBe("4 working days late");
    expect(slackWords(-1)).toBe("1 working day late");
    expect(slackWords(3)).toBe("3 working days spare");
    expect(slackWords(0)).toBe("Ships on the internal due date");
    expect(slackWords(null)).toBe("No estimate");
  });
});

describe("riskShare", () => {
  it("is quiet when nothing is late or nothing is planned", () => {
    expect(riskShare(0, 21)).toEqual({ share: 0, badge: null, level: "none" });
    expect(riskShare(5, 0)).toEqual({ share: 0, badge: null, level: "none" });
  });

  it("shows a ratio for a few late orders and raises an alert from a quarter", () => {
    expect(riskShare(2, 21)).toMatchObject({ badge: "10% of open orders", level: "watch" });
    expect(riskShare(5, 21).level).toBe("watch"); // 24%
    expect(riskShare(6, 24)).toMatchObject({ badge: "25% of open orders", level: "alert" });
    expect(riskShare(19, 21)).toMatchObject({ badge: "90% of open orders", level: "alert" });
  });

  it("never reports more than all of the orders", () => {
    expect(riskShare(30, 21)).toMatchObject({ badge: "100% of open orders", level: "alert" });
  });
});
