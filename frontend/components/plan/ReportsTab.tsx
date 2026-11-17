"use client";

import { useState } from "react";

import { Panel } from "@/components/Panel";
import { FormErrorLine } from "@/components/States";
import { ApiError, download } from "@/lib/api";
import { addDays, todayInIndia } from "@/lib/format";
import type { Page, Plan, Shift } from "@/lib/types";
import { usePlanningConfig } from "@/lib/planning-config";
import { useApi } from "@/lib/use-api";
import { Select } from "@/components/ui/Select";
import { DatePicker } from "@/components/ui/DatePicker";

const REPORTS = [
  { id: "shift_plan", label: "Shift plan", note: "What each department runs in each shift of a day." },
  { id: "day_plan", label: "Day plan", note: "The same, added up over the whole day." },
  { id: "dispatch_vs_estimate", label: "Dispatch plan vs estimated dates", note: "Every line of a month with its internal and estimated date." },
  { id: "resource_load", label: "Resource load", note: "Utilisation of every resource on each working day." },
  { id: "planning_pack", label: "Mould and melt plan (Excel)", note: "Both plans for a window of days, in one workbook." },
  { id: "mould_plan", label: "Mould plan (Excel)", note: "Moulds per day, shift and machine, with machine use and the orders that cannot meet their date." },
  { id: "melt_plan", label: "Melt plan (Excel)", note: "Heats per day and furnace: grade, metal, fill and what each heat pours." },
];
const EXCEL_ONLY = new Set(["planning_pack", "mould_plan", "melt_plan"]);

const DEPARTMENTS = [
  ["all", "All departments"], ["core", "Core shop"], ["moulding", "Moulding"], ["melting", "Melting and pouring"],
  ["knockout", "Knockout"], ["fettling", "Fettling"], ["machining", "Machining"], ["packing", "Packing"], ["dispatch", "Dispatch"],
];

export function ReportsTab({ plan }: { plan: Plan }) {
  const today = todayInIndia();
  const start = today > plan.plan_from ? today : plan.plan_from;
  const [report, setReport] = useState("shift_plan");
  const [department, setDepartment] = useState("all");
  const [date, setDate] = useState(start);
  const [shift, setShift] = useState("");
  const [month, setMonth] = useState(start.slice(0, 7));
  const [from, setFrom] = useState(start);
  const [to, setTo] = useState(addDays(start, 13));
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const shifts = useApi<Page<Shift>>("/shifts?page_size=50");
  const chosen = REPORTS.find((r) => r.id === report)!;
  const perDay = report === "shift_plan" || report === "day_plan";
  const windowed = report === "resource_load" || EXCEL_ONLY.has(report);
  const { isPlanned } = usePlanningConfig();
  const departments = DEPARTMENTS.filter(([v]) => v === "all" || isPlanned(v));

  async function get(output: "pdf" | "xlsx") {
    setBusy(output);
    setError(null);
    const q = new URLSearchParams({ report, output });
    if (perDay) {
      q.set("department", department);
      q.set("date", date);
      if (report === "shift_plan" && shift) q.set("shift", shift);
    }
    if (report === "dispatch_vs_estimate") q.set("month", month);
    if (windowed) {
      q.set("from", from);
      q.set("to", to);
    }
    try {
      await download(`/plans/${plan.id}/export?${q.toString()}`, `${report.replaceAll("_", "-")}.${output}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not create the file.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <Panel title="Print or export" note={`plan v${plan.version}`}>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="sm:col-span-2">
          <label htmlFor="report" className="mb-1 block text-sm font-medium">Report</label>
          <Select id="report" className="field" value={report} onChange={(e) => setReport(e.target.value)}>
            {REPORTS.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
          </Select>
          <p className="mt-1 text-xs text-ink-soft">{chosen.note}</p>
        </div>
        {perDay && (
          <>
            <div>
              <label htmlFor="department" className="mb-1 block text-sm font-medium">Department</label>
              <Select id="department" className="field" value={department} onChange={(e) => setDepartment(e.target.value)}>
                {departments.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            </div>
            <div>
              <label htmlFor="rep-date" className="mb-1 block text-sm font-medium">Day</label>
              <DatePicker id="rep-date" className="field" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} clearable={false} />
            </div>
            {report === "shift_plan" && (
              <div>
                <label htmlFor="shift" className="mb-1 block text-sm font-medium">Shift</label>
                <Select id="shift" className="field" value={shift} onChange={(e) => setShift(e.target.value)}>
                  <option value="">Every shift of the day</option>
                  {shifts.data?.results.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </Select>
              </div>
            )}
          </>
        )}
        {report === "dispatch_vs_estimate" && (
          <div>
            <label htmlFor="rep-month" className="mb-1 block text-sm font-medium">Month</label>
            <DatePicker mode="month" id="rep-month" className="field" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} clearable={false} />
          </div>
        )}
        {windowed && (
          <>
            <div>
              <label htmlFor="rep-from" className="mb-1 block text-sm font-medium">From</label>
              <DatePicker id="rep-from" className="field" value={from} onChange={(e) => e.target.value && setFrom(e.target.value)} clearable={false} />
            </div>
            <div>
              <label htmlFor="rep-to" className="mb-1 block text-sm font-medium">To</label>
              <DatePicker id="rep-to" className="field" value={to} onChange={(e) => e.target.value && setTo(e.target.value)} clearable={false} />
            </div>
          </>
        )}
      </div>
      {error && <div className="mt-4"><FormErrorLine message={error} /></div>}
      <div className="mt-5 flex flex-wrap gap-2">
        {!EXCEL_ONLY.has(report) && (
          <button type="button" className="btn btn-primary" onClick={() => get("pdf")} disabled={busy !== null}>{busy === "pdf" ? "Preparing…" : "Download PDF"}</button>
        )}
        <button type="button" className={`btn ${EXCEL_ONLY.has(report) ? "btn-primary" : "btn-quiet"}`} onClick={() => get("xlsx")} disabled={busy !== null}>{busy === "xlsx" ? "Preparing…" : "Download Excel"}</button>
      </div>
      <p className="mt-3 text-xs text-ink-soft">Every printed page carries the Vezapp logo, the plan version and when it was calculated. Only the operations planned in this phase (moulding and melting) are offered as departments.</p>
    </Panel>
  );
}
