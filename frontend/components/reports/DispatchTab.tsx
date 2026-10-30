"use client";

import { useState } from "react";

import { Panel } from "@/components/Panel";
import { DateFilters, ExportButtons } from "@/components/reports/ExportButtons";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { formatNumber } from "@/lib/format";
import { pct, query } from "@/lib/insights";
import type { DispatchPerformance, PerfGroup } from "@/lib/types";
import { useApi } from "@/lib/use-api";

function Table({ title, rows, first, named = false }: { title: string; rows: PerfGroup[]; first: string; named?: boolean }) {
  return (
    <Panel title={title}>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[34rem] text-left text-sm">
          <thead className="border-b border-line text-ink-soft">
            <tr>
              {[first, ...(named ? ["Name"] : []), "Lines", "On time", "Late", "On time %", "Avg delay (days)", "Worst (days)"].map((h, i) => (
                <th key={h} scope="col" className={`px-2 py-1.5 font-medium ${i >= (named ? 2 : 1) ? "text-right" : ""}`}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.group} className="border-b border-line last:border-0">
                <th scope="row" className="px-2 py-1.5 font-medium">{r.group}</th>
                {named && <td className="px-2 py-1.5">{r.name}</td>}
                <td className="px-2 py-1.5 text-right font-mono">{formatNumber(r.lines)}</td>
                <td className="px-2 py-1.5 text-right font-mono">{formatNumber(r.on_time)}</td>
                <td className="px-2 py-1.5 text-right font-mono">{formatNumber(r.late)}</td>
                <td className={`px-2 py-1.5 text-right font-mono ${r.on_time_pct < 0.7 ? "text-danger" : ""}`}>{pct(r.on_time_pct)}</td>
                <td className="px-2 py-1.5 text-right font-mono">{formatNumber(r.avg_delay_days, 1)}</td>
                <td className="px-2 py-1.5 text-right font-mono">{formatNumber(r.max_delay_days)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

export function DispatchTab() {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [customer, setCustomer] = useState("");
  const q = query({ from, to, customer });
  const report = useApi<DispatchPerformance>(`/reports/dispatch-performance${q}`);

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-soft">On time means the actual dispatch date is on or before the internal date. Only lines with an actual dispatch date are counted.</p>
      <DateFilters from={from} to={to} onFrom={setFrom} onTo={setTo} customer={customer} onCustomer={setCustomer} />
      <ExportButtons path={`/reports/dispatch-performance${q}`} filename="dispatch-performance" disabled={!report.data?.overall} />
      {report.loading ? (
        <LoadingState label="Loading the report" rows={4} />
      ) : report.error || !report.data ? (
        <ErrorState message={report.error?.message ?? "Could not load."} onRetry={report.reload} />
      ) : !report.data.overall ? (
        <EmptyState title="No dispatched lines to report">Load actual dispatch dates in the Monthly Scheduler (a column in the Excel upload, or the grid) and they appear here.</EmptyState>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              ["Lines dispatched", formatNumber(report.data.overall.lines)],
              ["On time", pct(report.data.overall.on_time_pct)],
              ["Average delay of late lines", `${formatNumber(report.data.overall.avg_delay_days, 1)} days`],
              ["Worst delay", `${formatNumber(report.data.overall.max_delay_days)} days`],
            ].map(([label, value]) => (
              <div key={label} className="panel px-4 py-3">
                <p className="text-xs text-ink-soft">{label}</p>
                <p className="mt-0.5 font-mono text-xl font-semibold">{value}</p>
              </div>
            ))}
          </div>
          <Table title="By month of dispatch" rows={report.data.by_month} first="Month" />
          <Table title="By customer" rows={report.data.by_customer} first="Customer" named />
          <Table title="By part" rows={report.data.by_part} first="Part" />
        </>
      )}
    </div>
  );
}
