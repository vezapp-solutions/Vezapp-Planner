import { describe, expect, it } from "vitest";

import {
  addDays,
  formatDate,
  formatDateTime,
  formatKg,
  formatNumber,
  formatTonnes,
  formatWeekday,
  formatWeight,
  todayInIndia,
} from "./format";

describe("formatDate", () => {
  it("renders DD-MM-YYYY", () => {
    expect(formatDate("2026-10-28")).toBe("28-10-2026");
  });

  it("uses India time for instants, not the machine timezone", () => {
    // 20:00 UTC on the 27th is already 01:30 on the 28th in Kolkata.
    expect(formatDate("2026-10-27T20:00:00Z")).toBe("28-10-2026");
  });

  it("renders date and time together", () => {
    expect(formatDateTime("2026-10-27T20:00:00Z")).toBe("28-10-2026 01:30");
  });

  it("names the weekday of a calendar date", () => {
    expect(formatWeekday("2026-10-28")).toBe("Wednesday");
  });
});

describe("todayInIndia and addDays", () => {
  it("rolls over at Indian midnight", () => {
    expect(todayInIndia(new Date("2026-10-27T18:29:00Z"))).toBe("2026-10-27");
    expect(todayInIndia(new Date("2026-10-27T18:30:00Z"))).toBe("2026-10-28");
  });

  it("adds days across month ends", () => {
    expect(addDays("2026-10-30", 3)).toBe("2026-11-02");
  });
});

describe("numbers and weights", () => {
  it("groups in the Indian style", () => {
    expect(formatNumber(100000)).toBe("1,00,000");
    expect(formatNumber(12345678)).toBe("1,23,45,678");
  });

  it("formats kg and tonnes", () => {
    expect(formatKg(18900)).toBe("18,900 kg");
    expect(formatTonnes(18900)).toBe("18.9 t");
  });

  it("switches to tonnes from one tonne", () => {
    expect(formatWeight(950)).toBe("950 kg");
    expect(formatWeight(1000)).toBe("1 t");
  });
});
