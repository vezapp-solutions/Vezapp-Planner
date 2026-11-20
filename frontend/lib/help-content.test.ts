import { describe, expect, it } from "vitest";

import { FAQ, GLOSSARY, GUIDE, TOUR_STEPS, hasSeenTour, markTourSeen, stepsFor, tourKey } from "./help-content";

describe("the tour", () => {
  it("starts with a welcome and ends with a send-off, for every role", () => {
    for (const role of ["vezapp_admin", "company_admin", "planner", "viewer"] as const) {
      const steps = stepsFor(role);
      expect(steps[0].id).toBe("welcome");
      expect(steps[steps.length - 1].id).toBe("done");
    }
  });

  it("does not show a viewer the What-if step, which they cannot use", () => {
    expect(stepsFor("viewer").map((s) => s.id)).not.toContain("whatif");
    expect(stepsFor("planner").map((s) => s.id)).toContain("whatif");
  });

  it("gives every step a title, friendly text and a unique id", () => {
    expect(new Set(TOUR_STEPS.map((s) => s.id)).size).toBe(TOUR_STEPS.length);
    for (const s of TOUR_STEPS) {
      expect(s.title.length).toBeGreaterThan(3);
      expect(s.body.length).toBeGreaterThan(40);
    }
  });
});

describe("the tour flag", () => {
  const store = new Map<string, string>();
  const fake = { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => void store.set(k, v) };

  it("is per person: one person seeing the tour does not hide it from another", () => {
    Object.defineProperty(globalThis, "window", { value: { localStorage: fake }, configurable: true });
    expect(hasSeenTour(1)).toBe(false);
    markTourSeen(1);
    expect(store.get(tourKey(1))).toBe("1");
    expect(hasSeenTour(1)).toBe(true);
    expect(hasSeenTour(2)).toBe(false);
  });

  it("does not nag when the browser blocks storage", () => {
    Object.defineProperty(globalThis, "window", { value: { localStorage: { getItem: () => { throw new Error("blocked"); } } }, configurable: true });
    expect(hasSeenTour(1)).toBe(true);
  });
});

describe("the help content", () => {
  it("has the full journey, a glossary and answers, all filled in", () => {
    expect(GUIDE.length).toBeGreaterThanOrEqual(6);
    for (const g of GUIDE) {
      expect(g.href.startsWith("/")).toBe(true);
      expect(g.tips.length).toBeGreaterThan(0);
    }
    expect(GLOSSARY.every((g) => g.term && g.meaning)).toBe(true);
    expect(FAQ.every((f) => f.q.endsWith("?") && f.a)).toBe(true);
  });
});
