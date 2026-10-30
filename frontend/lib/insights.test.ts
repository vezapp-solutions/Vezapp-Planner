import { describe, expect, it } from "vitest";

import { bySeverity, filterCards, pct, query, signedDays, summaryText, triggerText, typesPresent } from "./insights";
import type { Insight } from "./types";

const card = (key: string, severity: Insight["severity"], type: Insight["type"] = "at_risk"): Insight => ({
  id: 1, key, type, severity, title: key, message: "", numbers: {}, entities: {}, action: "", why: [], impact: 0, rank: 0, trend: "new",
});

describe("bySeverity and summaryText", () => {
  const cards = [card("a", "critical"), card("b", "warning"), card("c", "warning"), card("d", "info")];
  it("counts each severity", () => expect(bySeverity(cards)).toEqual({ critical: 1, warning: 2, info: 1 }));
  it("writes the counts in words and leaves out zeros", () => {
    expect(summaryText({ critical: 1, warning: 2, info: 1 })).toBe("1 critical, 2 warnings, 1 info");
    expect(summaryText({ critical: 0, warning: 1, info: 0 })).toBe("1 warning");
    expect(summaryText({ critical: 0, warning: 0, info: 0 })).toBe("Nothing to report");
  });
});

describe("filterCards", () => {
  const cards = [card("a", "critical", "at_risk"), card("b", "warning", "capacity_gap"), card("c", "warning", "at_risk")];
  it("keeps the server's order and applies both filters", () => {
    expect(filterCards(cards, "", "").map((c) => c.key)).toEqual(["a", "b", "c"]);
    expect(filterCards(cards, "at_risk", "").map((c) => c.key)).toEqual(["a", "c"]);
    expect(filterCards(cards, "at_risk", "warning").map((c) => c.key)).toEqual(["c"]);
    expect(filterCards(cards, "melting", "")).toEqual([]);
  });
});

describe("typesPresent", () => {
  it("lists only the types that have cards, in display order", () => {
    expect(typesPresent([card("a", "info", "data_health"), card("b", "info", "at_risk")])).toEqual(["at_risk", "data_health"]);
  });
});

describe("number helpers", () => {
  it("pct", () => {
    expect(pct(0.456)).toBe("46%");
    expect(pct(1)).toBe("100%");
    expect(pct(null)).toBe("–");
  });
  it("signedDays", () => {
    expect(signedDays(2)).toBe("+2");
    expect(signedDays(-1)).toBe("-1");
    expect(signedDays(0)).toBe("0");
    expect(signedDays(null)).toBe("–");
  });
});

describe("query", () => {
  it("leaves out empty filters and encodes the rest", () => {
    expect(query({ from: "2026-11-01", to: "", customer: "A & B" })).toBe("?from=2026-11-01&customer=A%20%26%20B");
    expect(query({ from: undefined })).toBe("");
  });
});

describe("triggerText", () => {
  it("says why a run happened", () => expect(triggerText("plan")).toBe("after a plan was calculated"));
});
