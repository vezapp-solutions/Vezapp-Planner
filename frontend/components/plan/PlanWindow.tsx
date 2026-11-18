"use client";

import { useState } from "react";

import { DatePicker } from "@/components/ui/DatePicker";
import { Select } from "@/components/ui/Select";
import { todayInIndia } from "@/lib/format";
import type { Plan } from "@/lib/types";

/**
 * The window of days a plan tab shows: a start date and a length. Until the planner picks a start, the server
 * opens the window on the first day that has work, so orders due months ahead are not hidden.
 */
export function usePlanWindow(plan: Plan, days = 14) {
  void plan;
  const [from, setFrom] = useState<string | null>(null);
  const [length, setLength] = useState(days);
  const query = `${from ? `from=${from}&` : ""}days=${length}`;
  return { from, length, query, setFrom, setLength };
}

export function PlanWindowControls({ window: w, shownFrom }: { window: ReturnType<typeof usePlanWindow>; shownFrom?: string }) {
  return (
    <div className="filters mb-4 flex flex-wrap items-end gap-3">
      <label className="text-sm">
        <span className="mb-1 block text-ink-soft">From</span>
        <DatePicker className="field !min-h-10 !w-40" value={w.from ?? shownFrom ?? todayInIndia()} onChange={(e) => e.target.value && w.setFrom(e.target.value)} clearable={false} />
      </label>
      <label className="text-sm">
        <span className="mb-1 block text-ink-soft">Window</span>
        <Select className="field !min-h-10 !w-32" value={w.length} onChange={(e) => w.setLength(Number(e.target.value))}>
          <option value={7}>7 days</option>
          <option value={14}>14 days</option>
          <option value={28}>28 days</option>
          <option value={42}>42 days</option>
        </Select>
      </label>
    </div>
  );
}
