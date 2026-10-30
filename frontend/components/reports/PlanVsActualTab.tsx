"use client";

import { useState } from "react";

import { Panel } from "@/components/Panel";
import { DateFilters, ExportButtons } from "@/components/reports/ExportButtons";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { formatDate, formatNumber } from "@/lib/format";
import { pct, query, signedDays } from "@/lib/insights";
import type { PlanVsActual } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export function PlanVsActualTab() {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const q = query({ from, to });
  const report = useApi<PlanVsActual>(`/reports/plan-vs-actual${q}`);
  const s = report.data?.summary;

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-soft">
        Compares each line&apos;s estimated date in the latest confirmed plan with the date it really shipped. Confirm a plan on the Plan screen to start keeping a baseline.
      </p>
      <DateFilters from={from} to={to} onFrom={setFrom} onTo={setTo} />
      <ExportButtons path={`/reports/plan-vs-actual${q}`} filename="plan-vs-actual" disabled={!s?.lines} />
      {report.loading ? (
        <LoadingState label="Loading the report" rows={4} />
      ) : report.error || !report.data || !s ? (
        <ErrorState message={report.error?.message ?? "Could not load."} onRetry={report.reload} />
      ) : s.lines === 0 ? (
        <EmptyState title="No dispatched lines to compare">Lines need an actual dispatch date before they can be compared with the plan.</EmptyState>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              ["Lines with an actual date", formatNumber(s.lines)],
              ["Estimated in a confirmed plan", formatNumber(s.with_confirmed_plan)],
              ["Average miss", s.mean_abs_error_days == null ? "–" : `${formatNumber(s.mean_abs_error_days, 1)} days`],
              ["Within one day", pct(s.within_one_day)],
            ].map(([label, value]) => (
              <div key={label} className="panel px-4 py-3">
                <p className="text-xs text-ink-soft">{label}</p>
                <p className="mt-0.5 font-mono text-xl font-semibold">{value}</p>
              </div>
            ))}
          </div>
          <Panel title="Lines, biggest miss first" note="error = actual minus estimated, in days">
            <div className="overflow-x-auto">
              <table className="w-full min-w-[44rem] text-left text-sm">
                <thead className="border-b border-line text-ink-soft">
                  <tr>
                    {["Customer", "Part", "Qty", "Internal date", "Estimated", "Actual", "Error (days)", "Late vs internal", "Plan"].map((h, i) => (
                      <th key={h} scope="col" className={`px-2 py-1.5 font-medium ${i === 2 || i === 6 || i === 7 ? "text-right" : ""}`}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {report.data.lines.map((r) => (
                    <tr key={r.line_id} className="border-b border-line last:border-0">
                      <td className="px-2 py-1.5">{r.customer_code}</td>
                      <td className="px-2 py-1.5 font-medium">{r.part_number}</td>
                      <td className="px-2 py-1.5 text-right font-mono">{formatNumber(r.qty)}</td>
                      <td className="whitespace-nowrap px-2 py-1.5 font-mono">{formatDate(r.internal_date)}</td>
                      <td className="whitespace-nowrap px-2 py-1.5 font-mono">{r.est_date ? formatDate(r.est_date) : "–"}</td>
                      <td className="whitespace-nowrap px-2 py-1.5 font-mono">{formatDate(r.actual_date)}</td>
                      <td className="px-2 py-1.5 text-right font-mono">{signedDays(r.est_error_days)}</td>
                      <td className={`px-2 py-1.5 text-right font-mono ${r.delay_days > 0 ? "text-danger" : ""}`}>{r.delay_days}</td>
                      <td className="px-2 py-1.5 text-ink-soft">{r.plan_version ? `v${r.plan_version}` : "no confirmed plan"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
    </div>
  );
}
