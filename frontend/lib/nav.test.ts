import { describe, expect, it } from "vitest";

import { navFor } from "./nav";

const labels = (items: ReturnType<typeof navFor>) => items.map((i) => i.label);

describe("navFor", () => {
  it("shows every screen of the role while the planned operations are not known", () => {
    expect(labels(navFor("planner"))).toContain("Machine shop");
    expect(labels(navFor("planner", null))).toContain("Machine shop");
  });

  it("hides the Machine shop when machining is not planned, and shows it when it is", () => {
    expect(labels(navFor("planner", ["moulding", "melting"]))).not.toContain("Machine shop");
    expect(labels(navFor("planner", ["moulding", "melting", "machining"]))).toContain("Machine shop");
  });

  it("still follows the role", () => {
    expect(labels(navFor("viewer", ["moulding"]))).not.toContain("What-if");
    expect(labels(navFor("vezapp_admin", ["moulding"]))).toContain("Companies");
  });

  it("gives every role the Help screen", () => {
    for (const role of ["vezapp_admin", "company_admin", "planner", "viewer"] as const) expect(labels(navFor(role))).toContain("Help");
  });
});
