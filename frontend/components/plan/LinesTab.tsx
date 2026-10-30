"use client";

import { useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { LineDetailPanel } from "@/components/plan/LineDetail";
import { Slack, StatusBadge } from "@/components/plan/StatusBadge";
import { formatDate, formatNumber } from "@/lib/format";
import { PLAN_STATUS_LABEL, type Page, type Plan, type PlanLine } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { Select } from "@/components/ui/Select";
import { DatePicker } from "@/components/ui/DatePicker";

export function LinesTab({ plan }: { plan: Plan }) {
  const [status, setStatus] = useState("");
  const [month, setMonth] = useState("");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<PlanLine | null>(null);
  const version = plan.calculated_at ?? "";
  const query = `${status ? `&status=${status}` : ""}${month ? `&month=${month}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}`;
  const lines = useApi<Page<PlanLine>>(`/plans/${plan.id}/lines?page_size=500${query}&v=${encodeURIComponent(version)}`);

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="mb-1 block text-ink-soft">Status</span>
          <Select className="field !min-h-10 !w-40" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All lines</option>
            {Object.entries(PLAN_STATUS_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-ink-soft">Month of internal date</span>
          <DatePicker mode="month" className="field !min-h-10 !w-44" value={month} onChange={(e) => setMonth(e.target.value)} />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-ink-soft">Part</span>
          <input type="search" className="field !min-h-10 !w-44" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Number or name" />
        </label>
      </div>

      {lines.loading ? (
        <LoadingState label="Loading lines" rows={5} />
      ) : lines.error ? (
        <ErrorState message={lines.error.message} onRetry={lines.reload} />
      ) : lines.data?.results.length === 0 ? (
        <EmptyState title="No lines to show">
          {plan.summary.lines ? "No line matches these filters." : "Add dispatch lines in the Monthly Scheduler, then recalculate the plan."}
        </EmptyState>
      ) : (
        <div className="panel overflow-x-auto">
          <table className="w-full min-w-[52rem] text-left text-sm">
            <thead className="border-b border-line bg-sunken text-ink-soft">
              <tr>
                {["Status", "Internal date", "Estimated", "Spare", "Customer", "Part", "Qty", "Held up by"].map((h, i) => (
                  <th key={h} scope="col" className={`px-3 py-2 font-medium ${i === 3 || i === 6 ? "text-right" : ""}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {lines.data?.results.map((l) => (
                <tr key={l.id} className="border-b border-line last:border-0 hover:bg-sunken/60">
                  <td className="px-3 py-2"><StatusBadge status={l.status} /></td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono">{formatDate(l.internal_date)}</td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono">
                    <button type="button" className="inline-flex min-h-6 min-w-6 items-center underline-offset-2 hover:underline" onClick={() => setSelected(l)} aria-label={`Show how the estimate for ${l.part_number} was worked out`}>
                      {l.est_dispatch_date ? formatDate(l.est_dispatch_date) : "–"}
                    </button>
                  </td>
                  <td className="px-3 py-2 text-right"><Slack days={l.slack_working_days} /></td>
                  <td className="px-3 py-2"><span className="font-mono text-xs text-ink-soft">{l.customer_code}</span> {l.customer_name}</td>
                  <td className="px-3 py-2"><button type="button" className="inline-flex min-h-6 min-w-6 items-center text-left font-medium underline-offset-2 hover:underline" onClick={() => setSelected(l)}>{l.part_number}</button> <span className="text-ink-soft">{l.part_name}</span></td>
                  <td className="px-3 py-2 text-right font-mono">{formatNumber(l.qty)}</td>
                  <td className="max-w-[18rem] px-3 py-2 text-ink-soft">{l.holding_op ? <span title={l.holding_text}>{l.holding_op}</span> : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {lines.data && lines.data.count > lines.data.results.length && (
            <p className="border-t border-line px-3 py-2 text-sm text-ink-soft">Showing the first {lines.data.results.length} of {lines.data.count} lines.</p>
          )}
        </div>
      )}

      {selected && <LineDetailPanel planId={plan.id} lineId={selected.id} version={version} onClose={() => setSelected(null)} />}
    </>
  );
}
