import { describe, expect, it } from "vitest";

import { errorText } from "./api";

describe("errorText", () => {
  it("returns plain text as it is", () => {
    expect(errorText("Enter a number.")).toBe("Enter a number.");
  });

  it("joins a list of messages", () => {
    expect(errorText(["Too short.", "Needs a digit."])).toBe("Too short. Needs a digit.");
  });

  it("reads a nested error keyed by position without printing [object Object]", () => {
    const body = { "6": { time_value: ["Enter the time in minutes."] } };
    const text = errorText(body);
    expect(text).toBe("time_value: Enter the time in minutes.");
    expect(text).not.toContain("[object Object]");
  });

  it("leaves out numbered keys and non-field wrappers", () => {
    expect(errorText({ non_field_errors: ["Pick a machine."] })).toBe("Pick a machine.");
    expect(errorText([{}, { qty: ["Required."] }])).toBe("qty: Required.");
  });

  it("copes with empty and missing values", () => {
    expect(errorText(null)).toBe("");
    expect(errorText(undefined)).toBe("");
    expect(errorText({})).toBe("");
  });
});
