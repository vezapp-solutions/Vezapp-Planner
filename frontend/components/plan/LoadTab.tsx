"use client";

import { useState } from "react";

import { SlideOver } from "@/components/SlideOver";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { addDays, formatDate, formatDayMonth, formatNumber, formatWeekday, todayInIndia } from "@/lib/format";
import { HEAT_STYLE, heatLevel, percent } from "@/lib/plan-utils";
import { KIND_LABEL, type LoadGrid, type Plan } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { Select } from "@/components/ui/Select";
import { DatePicker } from "@/components/ui/DatePicker";

interface CellLines {
  date: string;
  lines: { line: number; part: string; customer: string; op_code: string; minutes: number; qty: number }[];
}

function CellDetail({ planId, resource, code, date, shift, onClose }: { planId: number; resource: number; code: string; date: string; shift: string | null; onClose: () => void }) {
  const data = useApi<CellLines>(`/plans/${planId}/load/cell?resource=${resource}&date=${date}${shift ? `&shift=${shift}` : ""}`);
  return (
    <SlideOver title={`${code} on ${formatDate(date)}`} subtitle="Which lines put work here" onClose={onClose}>
      {data.loading ? (
        <LoadingState label="Loading" rows={3} />
      ) : data.error ? (
        <ErrorState message={data.error.message} onRetry={data.reload} />
      ) : data.data?.lines.length === 0 ? (
        <EmptyState title="No work here">Nothing is planned on this resource in this period.</EmptyState>
      ) : (
        <table className="w-full text-left text-sm">
          <thead className="border-b border-line text-ink-soft">
            <tr>{["Part", "Customer", "Operation", "Quantity", "Minutes"].map((h) => <th key={h} scope="col" className="py-1.5 pr-3 font-medium">{h}</th>)}</tr>
          </thead>
          <tbody>
            {data.data?.lines.map((l) => (
              <tr key={`${l.line}-${l.op_code}`} className="border-b border-line last:border-0">
                <td className="py-1.5 pr-3 font-medium">{l.part}</td>
                <td className="py-1.5 pr-3">{l.customer}</td>
                <td className="py-1.5 pr-3">{l.op_code}</td>
                <td className="py-1.5 pr-3 font-mono">{formatNumber(l.qty, 1)}</td>
                <td className="py-1.5 font-mono">{formatNumber(l.minutes, 1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </SlideOver>
  );
}

export function LoadTab({ plan }: { plan: Plan }) {
  const [from, setFrom] = useState(() => {
    const today = todayInIndia();
    return today > plan.plan_from ? today : plan.plan_from;
  });
  const [days, setDays] = useState(14);
  const [byShift, setByShift] = useState(false);
  const [open, setOpen] = useState<{ resource: number; code: string; date: string; shift: string | null } | null>(null);
  const to = addDays(from, days - 1);
  const grid = useApi<LoadGrid>(`/plans/${plan.id}/load?from=${from}&to=${to}${byShift ? "&by=shift" : ""}&v=${encodeURIComponent(plan.calculated_at ?? "")}`);

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <label className="text-sm">
          <span className="mb-1 block text-ink-soft">From</span>
          <DatePicker className="field !min-h-10 !w-40" value={from} onChange={(e) => e.target.value && setFrom(e.target.value)} clearable={false} />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-ink-soft">Window</span>
          <Select className="field !min-h-10 !w-32" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {[7, 14, 21].map((d) => <option key={d} value={d}>{d} days</option>)}
          </Select>
        </label>
        <label className="flex min-h-10 items-center gap-2 text-sm">
          <input type="checkbox" className="size-4 accent-[var(--action)]" checked={byShift} onChange={(e) => setByShift(e.target.checked)} /> Show each shift
        </label>
        <ul className="flex flex-wrap gap-2 text-xs" aria-label="Colour key">
          {(["light", "busy", "high", "over"] as const).map((l) => (
            <li key={l} className="rounded-sm px-2 py-0.5" style={HEAT_STYLE[l]}>
              {{ light: "under 50%", busy: "50–84%", high: "85–99%", over: "100% or more" }[l]}
            </li>
          ))}
        </ul>
      </div>

      {grid.loading ? (
        <LoadingState label="Building the heatmap" rows={4} />
      ) : grid.error || !grid.data ? (
        <ErrorState message={grid.error?.message ?? "Could not load."} onRetry={grid.reload} />
      ) : grid.data.resources.length === 0 ? (
        <EmptyState title="No capacity in this window">There are no working shifts or resources in these dates.</EmptyState>
      ) : (
        <div className="panel overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-line bg-sunken text-ink-soft">
                <th scope="col" className="sticky left-0 z-10 bg-sunken px-3 py-2 text-left font-medium">Resource</th>
                {grid.data.columns.map((c) => (
                  <th key={c.key} scope="col" className="min-w-[3.6rem] px-1 py-2 text-center font-medium">
                    <span className="block text-[0.6875rem] uppercase">{formatWeekday(c.date, "short")}</span>
                    <span className="block font-mono text-xs">{formatDayMonth(c.date)}</span>
                    {c.shift && <span className="block text-[0.625rem]">{c.shift}</span>}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {grid.data.resources.map((r) => (
                <tr key={r.id} className="border-b border-line last:border-0">
                  <th scope="row" className="sticky left-0 z-10 bg-surface px-3 py-1.5 text-left font-normal">
                    <span className="font-mono font-medium">{r.code}</span>
                    <span className="ml-1.5 text-xs text-ink-soft">{KIND_LABEL[r.kind]}</span>
                  </th>
                  {grid.data!.columns.map((c) => {
                    const cell = r.cells[c.key];
                    const u = cell?.utilisation ?? null;
                    const level = heatLevel(u);
                    const overload = cell && cell.required > cell.capacity && cell.capacity > 0;
                    const label = cell ? `${r.code}, ${formatDate(c.date)}${c.shift ? ` ${c.shift}` : ""}: ${percent(u)} loaded, ${formatNumber(cell.load)} of ${formatNumber(cell.capacity)} minutes; ${formatNumber(cell.required)} minutes are needed by the due dates` : `${r.code}: no capacity`;
                    return (
                      <td key={c.key} className="p-0.5">
                        {cell ? (
                          <button
                            type="button"
                            title={label}
                            aria-label={label}
                            onClick={() => setOpen({ resource: r.id, code: r.code, date: c.date, shift: c.shift ? c.key.split("|")[1] : null })}
                            className="relative block h-9 w-full min-w-[3.4rem] rounded-sm font-mono text-xs hover:outline hover:outline-1 hover:outline-ink-soft"
                            style={HEAT_STYLE[level]}
                          >
                            {percent(u)}
                            {overload && <span aria-hidden="true" className="absolute right-0.5 top-0.5 size-1.5 rounded-full bg-danger" />}
                          </button>
                        ) : (
                          <span className="block h-9 text-center text-xs leading-9 text-ink-soft">–</span>
                        )}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="mt-2 text-xs text-ink-soft">
        Load ÷ capacity of each resource. A red dot means the lines due in that period need more minutes than the resource has there, so the dates cannot all be met. Click a cell to see which lines are behind it.
      </p>
      {open && <CellDetail planId={plan.id} resource={open.resource} code={open.code} date={open.date} shift={open.shift} onClose={() => setOpen(null)} />}
    </>
  );
}
