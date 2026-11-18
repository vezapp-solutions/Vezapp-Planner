"use client";

import { PlanWindowControls, usePlanWindow } from "@/components/plan/PlanWindow";
import { UseBar } from "@/components/plan/UseBar";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { formatDate, formatNumber, formatWeekday } from "@/lib/format";
import { PLAN_STATUS_LABEL, type MouldPlan, type Plan } from "@/lib/types";
import { useApi } from "@/lib/use-api";

/** Moulds per day, shift and machine, from the moulding capacity, with the orders that cannot make their date. */
export function MouldPlanTab({ plan }: { plan: Plan }) {
  const w = usePlanWindow(plan, 14);
  const data = useApi<MouldPlan>(`/plans/${plan.id}/mould-plan?${w.query}`);

  return (
    <div>
      <PlanWindowControls window={w} shownFrom={data.data?.from} />
      {data.loading ? (
        <LoadingState label="Loading the mould plan" rows={4} />
      ) : data.error || !data.data ? (
        <ErrorState message={data.error?.message ?? "Could not load."} onRetry={data.reload} />
      ) : (
        <div className="space-y-4">
          {data.data.warnings.length > 0 && (
            <section aria-label="Orders that cannot meet their dispatch date" className="rounded-card border border-danger bg-danger-wash/50 p-4">
              <h3 className="font-display text-lg font-semibold text-danger">
                {data.data.warnings.length} order{data.data.warnings.length === 1 ? "" : "s"} cannot meet the dispatch date
              </h3>
              <ul className="mt-2 space-y-1 text-sm">
                {data.data.warnings.slice(0, 12).map((x) => (
                  <li key={x.line_id}>
                    <span className="font-medium">{x.part_number}</span> for {x.customer_code}, due{" "}
                    <span className="font-mono">{formatDate(x.due)}</span>: {x.text}
                  </li>
                ))}
                {data.data.warnings.length > 12 && <li className="text-ink-soft">…and {data.data.warnings.length - 12} more on the Orders tab.</li>}
              </ul>
            </section>
          )}

          {data.data.days.length === 0 ? (
            <EmptyState title="No moulds are planned in this window">
              Pick another start date, or run planning if orders were added or changed.
            </EmptyState>
          ) : (
            data.data.days.map((day) => (
              <section key={day.date} className="panel overflow-hidden" aria-label={`Moulds on ${formatDate(day.date)}`}>
                <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line bg-sunken px-4 py-2">
                  <h3 className="font-display text-lg font-semibold">
                    {formatWeekday(day.date)} <span className="font-mono text-base">{formatDate(day.date)}</span>
                  </h3>
                  <p className="text-sm text-ink-soft">
                    <span className="font-mono">{formatNumber(Math.round(day.moulds))}</span> moulds ·{" "}
                    <span className="font-mono">{formatNumber(day.castings)}</span> castings
                  </p>
                </header>
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[40rem] text-left text-sm">
                    <thead className="border-b border-line text-ink-soft">
                      <tr>
                        {["Shift", "Machine", "Part", "Customer", "Moulds", "Castings", "Due", "Status"].map((h, i) => (
                          <th key={h} scope="col" className={`px-3 py-1.5 font-medium ${i === 4 || i === 5 ? "text-right" : ""}`}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {day.shifts.flatMap((shift) =>
                        shift.machines.flatMap((m) => [
                          <tr key={`${shift.slot}-${m.id}`} className="border-b border-line bg-brand-wash/30">
                            <td className="px-3 py-1.5 font-medium">{shift.shift}</td>
                            <td className="px-3 py-1.5 font-mono font-medium">{m.code}</td>
                            <td className="px-3 py-1.5" colSpan={2}>
                              <UseBar pct={m.used_pct} label={`${formatNumber(Math.round(m.load_minutes))} of ${formatNumber(Math.round(m.capacity_minutes))} minutes`} />
                              <span className="ml-2 text-xs text-ink-soft">machine used</span>
                            </td>
                            <td className="px-3 py-1.5 text-right font-mono">{formatNumber(Math.round(m.moulds))}</td>
                            <td className="px-3 py-1.5 text-right font-mono">{formatNumber(m.castings)}</td>
                            <td colSpan={2} />
                          </tr>,
                          ...m.items.map((it) => (
                            <tr key={`${shift.slot}-${m.id}-${it.line_id}`} className="border-b border-line last:border-0">
                              <td />
                              <td />
                              <td className="px-3 py-1.5"><span className="font-medium">{it.part_number}</span> <span className="text-ink-soft">{it.part_name}</span></td>
                              <td className="px-3 py-1.5 font-mono text-xs">{it.customer_code}</td>
                              <td className="px-3 py-1.5 text-right font-mono">{formatNumber(Math.round(it.moulds))}</td>
                              <td className="px-3 py-1.5 text-right font-mono">{formatNumber(it.castings)}</td>
                              <td className="px-3 py-1.5 font-mono">{formatDate(it.due)}</td>
                              <td className={`px-3 py-1.5 ${it.status === "at_risk" || it.status === "unscheduled" ? "text-danger" : ""}`}>{PLAN_STATUS_LABEL[it.status]}</td>
                            </tr>
                          )),
                        ]),
                      )}
                    </tbody>
                  </table>
                </div>
              </section>
            ))
          )}
          <p className="text-xs text-ink-soft">
            Moulds follow the moulding machine&apos;s shifts, rate and downtime. Orders are planned earliest dispatch date first, for the balance still to produce.
          </p>
        </div>
      )}
    </div>
  );
}
