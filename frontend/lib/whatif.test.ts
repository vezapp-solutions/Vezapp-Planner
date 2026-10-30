import { describe, expect, it } from "vitest";

import type { LineDiff, ScenarioResult } from "./types";
import { bottleneckText, dateChange, groupLines, headline, movedText, utilisationChanges } from "./whatif";

const line = (id: number, tags: LineDiff["tags"]): LineDiff => ({
  line_id: id, part_number: `P${id}`, part_name: "", customer_code: "C", customer_name: "", status_before: "on_track", status_after: "on_track",
  est_before: "2026-11-05", est_after: "2026-11-06", slack_before: 2, slack_after: 1, moved_working_days: 1, holding_after: null,
  holding_text_after: "", tags, internal_date_before: "2026-11-20", internal_date_after: "2026-11-20", qty_before: 600, qty_after: 600,
});

const result = (over: Partial<ScenarioResult["diff"]> = {}): ScenarioResult => ({
  plan_from: "2026-11-02", lines_planned: 3, runtime_ms: 10, resources: { "1": { code: "F1" }, "2": { code: "KO" } },
  diff: { lines: [], counts: { later: 0, earlier: 0, newly_at_risk: 0, recovered: 0, changed: 0, total: 0 }, status_before: {}, status_after: {}, bottleneck_before: 1, bottleneck_after: 1, day_bottlenecks: [], peak_utilisation: {}, ...over },
});

describe("groupLines", () => {
  it("shows bad news first and leaves empty groups out", () => {
    const groups = groupLines([line(1, ["earlier"]), line(2, ["later"]), line(3, ["newly_at_risk", "later"])]);
    expect(groups.map((g) => g.tag)).toEqual(["newly_at_risk", "later", "earlier"]);
    expect(groups[0].lines[0].line_id).toBe(3);
  });
});

describe("movedText", () => {
  it.each([
    [1, "1 working day later"],
    [3, "3 working days later"],
    [-2, "2 working days earlier"],
    [0, null],
    [null, null],
  ])("%s", (days, text) => expect(movedText(days)).toBe(text));
});

describe("dateChange", () => {
  it("writes both dates in DD-MM-YYYY", () => expect(dateChange(line(1, ["later"]))).toBe("05-11-2026 → 06-11-2026"));
  it("shows a dash for a line that is not scheduled", () => expect(dateChange({ est_before: "2026-11-05", est_after: null })).toBe("05-11-2026 → –"));
});

describe("headline", () => {
  it("says so when nothing changes", () => expect(headline(result().diff.counts)).toBe("No line changes."));
  it("lists what moved", () =>
    expect(headline({ later: 2, earlier: 0, newly_at_risk: 1, recovered: 0, changed: 0, total: 2 })).toBe("2 lines change: 2 later, 1 newly at risk."));
  it("uses the singular for one line", () => expect(headline({ later: 1, earlier: 0, newly_at_risk: 0, recovered: 0, changed: 0, total: 1 })).toBe("1 line change: 1 later."));
});

describe("utilisationChanges", () => {
  it("keeps only resources that moved, biggest first", () => {
    const r = result({ peak_utilisation: { "1": [0.5, 0.5], "2": [0.4, 0.9] } });
    expect(utilisationChanges(r)).toEqual([{ id: 2, code: "KO", before: 0.4, after: 0.9 }]);
  });
});

describe("bottleneckText", () => {
  it("reports no change", () => expect(bottleneckText(result())).toBe("Unchanged (F1)"));
  it("reports a move", () => expect(bottleneckText(result({ bottleneck_after: 2 }))).toBe("F1 → KO"));
  it("copes with none", () => expect(bottleneckText(result({ bottleneck_before: null }))).toBe("none → F1"));
});
