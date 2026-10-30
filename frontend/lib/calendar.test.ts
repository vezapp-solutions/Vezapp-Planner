import { describe, expect, it } from "vitest";

import { addDays, addMonths, daysInMonth, displayValue, monthGrid, parseValue, todayIso } from "./calendar";

describe("parseValue", () => {
  it("reads dates, months and date-times", () => {
    expect(parseValue("2026-10-30")).toEqual({ y: 2026, m: 10, d: 30, hh: 0, mm: 0 });
    expect(parseValue("2026-10")).toMatchObject({ y: 2026, m: 10, d: 1 });
    expect(parseValue("2026-11-02T14:30")).toMatchObject({ d: 2, hh: 14, mm: 30 });
  });

  it("refuses things that are not dates", () => {
    for (const bad of ["", "tomorrow", "2026-13-01", "2026-02-30", "2026-10-30T25:00"]) {
      expect(parseValue(bad)).toBeNull();
    }
  });
});

describe("month maths", () => {
  it("knows leap years", () => {
    expect(daysInMonth(2028, 2)).toBe(29);
    expect(daysInMonth(2026, 2)).toBe(28);
  });

  it("moves across year ends", () => {
    expect(addMonths(2026, 12, 1)).toEqual({ y: 2027, m: 1 });
    expect(addMonths(2026, 1, -1)).toEqual({ y: 2025, m: 12 });
    expect(addMonths(2026, 10, 14)).toEqual({ y: 2027, m: 12 });
  });

  it("adds days across months", () => {
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  });
});

describe("monthGrid", () => {
  it("shows six Monday-first weeks", () => {
    // 1 October 2026 is a Thursday, so the grid starts on Monday 28 September.
    const cells = monthGrid(2026, 10);
    expect(cells).toHaveLength(42);
    expect(cells[0]).toEqual({ iso: "2026-09-28", day: 28, inMonth: false });
    expect(cells[3]).toEqual({ iso: "2026-10-01", day: 1, inMonth: true });
    expect(cells.filter((c) => c.inMonth)).toHaveLength(31);
  });

  it("starts on the 1st when the month starts on a Monday", () => {
    // 1 June 2026 is a Monday.
    expect(monthGrid(2026, 6)[0]).toMatchObject({ iso: "2026-06-01", inMonth: true });
  });
});

describe("displayValue", () => {
  it("writes the Indian day-month-year order", () => {
    expect(displayValue("2026-10-30", "date")).toBe("30-10-2026");
    expect(displayValue("2026-10", "month")).toBe("October 2026");
    expect(displayValue("2026-11-02T09:05", "datetime")).toBe("02-11-2026 09:05");
    expect(displayValue("", "date")).toBe("");
  });
});

describe("todayIso", () => {
  it("uses the India date even when it is already tomorrow there", () => {
    // 20:00 UTC on 30 Oct is 01:30 on 31 Oct in India.
    expect(todayIso(new Date("2026-10-30T20:00:00Z"))).toBe("2026-10-31");
  });
});
