import { describe, expect, it } from "vitest";

import { formatTime12, from12Hour, minuteChoices, parseTime, to12Hour, toTime } from "./time";

describe("parseTime", () => {
  it("reads HH:mm, with or without seconds and a leading zero", () => {
    expect(parseTime("06:00")).toEqual({ hour: 6, minute: 0 });
    expect(parseTime("6:05")).toEqual({ hour: 6, minute: 5 });
    expect(parseTime("22:30:00")).toEqual({ hour: 22, minute: 30 });
  });

  it("rejects empty values and impossible times", () => {
    expect(parseTime("")).toBeNull();
    expect(parseTime(null)).toBeNull();
    expect(parseTime("24:00")).toBeNull();
    expect(parseTime("12:60")).toBeNull();
    expect(parseTime("noon")).toBeNull();
  });
});

describe("12-hour clock", () => {
  it("turns 24-hour times into 12-hour ones, with midnight as 12 AM and noon as 12 PM", () => {
    expect(to12Hour(0)).toEqual({ hour12: 12, pm: false });
    expect(to12Hour(6)).toEqual({ hour12: 6, pm: false });
    expect(to12Hour(12)).toEqual({ hour12: 12, pm: true });
    expect(to12Hour(14)).toEqual({ hour12: 2, pm: true });
    expect(to12Hour(23)).toEqual({ hour12: 11, pm: true });
  });

  it("goes back the other way for every hour of the day", () => {
    for (let hour = 0; hour < 24; hour += 1) {
      const { hour12, pm } = to12Hour(hour);
      expect(from12Hour(hour12, pm)).toBe(hour);
    }
  });

  it("formats for display", () => {
    expect(formatTime12("06:00")).toBe("06:00 AM");
    expect(formatTime12("14:30")).toBe("02:30 PM");
    expect(formatTime12("00:00")).toBe("12:00 AM");
    expect(formatTime12("12:00")).toBe("12:00 PM");
    expect(formatTime12("")).toBe("");
  });

  it("writes back as 24-hour HH:mm", () => {
    expect(toTime({ hour: 6, minute: 5 })).toBe("06:05");
    expect(toTime({ hour: 0, minute: 0 })).toBe("00:00");
  });
});

describe("minuteChoices", () => {
  it("offers steps of five", () => {
    expect(minuteChoices(null)).toEqual([0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55]);
    expect(minuteChoices(30)).toHaveLength(12);
  });

  it("keeps a saved minute that is off the grid, in order", () => {
    expect(minuteChoices(23)).toEqual([0, 5, 10, 15, 20, 23, 25, 30, 35, 40, 45, 50, 55]);
  });
});
