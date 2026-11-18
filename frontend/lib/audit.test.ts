import { describe, expect, it } from "vitest";

import { describeAudit } from "./audit";
import type { AuditEntry } from "./types";

function entry(over: Partial<AuditEntry>): AuditEntry {
  return {
    id: 1,
    username: "a.admin",
    action: "update",
    model_label: "scheduler.ScheduleLine",
    object_pk: "1",
    object_repr: "C-101 SPR-900 × 60",
    before: null,
    after: null,
    created_at: "2026-11-18T10:00:00Z",
    ...over,
  };
}

describe("describeAudit", () => {
  it("says what changed in plain words, with the old and new value", () => {
    const text = describeAudit(entry({ before: { dispatch_qty: 200, status: "planned" }, after: { dispatch_qty: 250, status: "planned" } }));
    expect(text.headline).toBe("Changed order C-101 SPR-900 × 60");
    expect(text.lines).toEqual(["Order quantity changed from 200 to 250."]);
  });

  it("names the records that ids point to", () => {
    const text = describeAudit(
      entry({
        before: { customer_id: 1 },
        after: { customer_id: 2 },
        refs: { customer_id: { "1": "C-101 Aarav Pumps", "2": "C-102 Bharat Valves" } },
      }),
    );
    expect(text.lines).toEqual(["Customer changed from C-101 Aarav Pumps to C-102 Bharat Valves."]);
  });

  it("treats 1.8000 and 1.8 as the same number, and says when a value was set or cleared", () => {
    const same = describeAudit(entry({ model_label: "masters.PartOperation", before: { time_value: "1.8000" }, after: { time_value: 1.8 } }));
    expect(same.lines).toEqual(["Saved, with no visible change."]);
    const set = describeAudit(entry({ before: { remarks: "" }, after: { remarks: "Rush" } }));
    expect(set.lines).toEqual(["Remarks set to Rush."]);
    const cleared = describeAudit(entry({ before: { remarks: "Rush" }, after: { remarks: "" } }));
    expect(cleared.lines).toEqual(["Remarks cleared (it was Rush)."]);
  });

  it("shows dates the way the app does and words instead of codes", () => {
    const text = describeAudit(entry({ before: { internal_dispatch_date: "2026-11-20", status: "planned" }, after: { internal_dispatch_date: "2026-11-25", status: "in_progress" } }));
    expect(text.lines).toEqual(["Internal dispatch date changed from 20-11-2026 to 25-11-2026.", "Status changed from planned to in progress."]);
  });

  it("summarises a plan recalculation instead of dumping its internals", () => {
    const text = describeAudit(
      entry({
        model_label: "plans.Plan",
        object_repr: "Plan v3",
        before: { status: "draft", summary: { lines: 22 }, settings_snapshot: { a: 1 }, calculated_at: "2026-11-17T10:00:00Z" },
        after: { status: "draft", summary: { lines: 25 }, settings_snapshot: { a: 2 }, calculated_at: "2026-11-18T10:00:00Z" },
      }),
    );
    expect(text.headline).toBe("Changed Plan v3");
    expect(text.lines).toEqual(["Recalculated the plan."]);
  });

  it("lists the key facts of something added or deleted, without bookkeeping", () => {
    const added = describeAudit(
      entry({
        action: "create",
        model_label: "masters.Part",
        object_repr: "SPR-900 Spacer plate",
        after: { id: 14, created_at: "2026-10-30T05:30:39Z", company_id: 1, part_number: "SPR-900", name: "Spacer plate", grade_id: 2, drawing_number: "", casting_weight_kg: "3.000", is_active: true },
        refs: { grade_id: { "2": "GG25" } },
      }),
    );
    expect(added.headline).toBe("Added part SPR-900 Spacer plate");
    expect(added.lines).toEqual(["Part number: SPR-900 · Name: Spacer plate · Grade: GG25 · Casting weight (kg): 3 · Active: yes"]);
    const gone = describeAudit(entry({ action: "delete", model_label: "masters.Customer", object_repr: "C-104 Himal", before: { id: 4, code: "C-104", name: "Himal" } }));
    expect(gone.headline).toBe("Deleted customer C-104 Himal");
  });

  it("does not print 'object (109)' for records with no name, and uses the step label instead", () => {
    const text = describeAudit(entry({ action: "create", model_label: "masters.PartOperation", object_repr: "PartOperation object (109)", after: { id: 109, label: "Finish bore", step: 20 } }));
    expect(text.headline).toBe("Added route step “Finish bore”");
  });
});
