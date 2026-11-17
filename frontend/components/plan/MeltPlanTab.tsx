"use client";

import { PlanWindowControls, usePlanWindow } from "@/components/plan/PlanWindow";
import { UseBar } from "@/components/plan/UseBar";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { formatDate, formatNumber, formatWeekday } from "@/lib/format";
import type { MeltPlan, Plan } from "@/lib/types";
import { useApi } from "@/lib/use-api";

/** Heats per day and furnace: one heat is one grade. Follows the mould plan, so it is always in step with it. */
export function MeltPlanTab({ plan }: { plan: Plan }) {
  const w = usePlanWindow(plan, 14);
  const data = useApi<MeltPlan>(`/plans/${plan.id}/melt-plan?${w.query}`);
  const summary = plan.summary.melt;

  return (
    <div>
      <PlanWindowControls window={w} shownFrom={data.data?.from} />
      {data.loading ? (
        <LoadingState label="Loading the melt plan" rows={4} />
      ) : data.error || !data.data ? (
        <ErrorState message={data.error?.message ?? "Could not load."} onRetry={data.reload} />
      ) : !data.data.enabled ? (
        <EmptyState title="Melting is not planned heat by heat in this setup">
          The melt plan is switched off for this plan. Melting is then scheduled together with moulding, per part.
        </EmptyState>
      ) : (
        <div className="space-y-4">
          {summary && (summary.shortfall_heats || summary.under_filled) ? (
            <div className="flex flex-wrap gap-2 text-sm" aria-label="Melt plan warnings">
              {summary.shortfall_heats ? (
                <span className="rounded-md bg-danger-wash px-3 py-1.5 text-danger">
                  {summary.shortfall_heats} heat{summary.shortfall_heats === 1 ? "" : "s"} with no furnace room
                </span>
              ) : null}
              {summary.under_filled ? (
                <span className="rounded-md bg-warn-wash px-3 py-1.5 text-warn">
                  {summary.under_filled} under-filled heat{summary.under_filled === 1 ? "" : "s"}
                </span>
              ) : null}
            </div>
          ) : null}

          {data.data.days.length === 0 ? (
            <EmptyState title="No heats are planned in this window">Heats follow the mould plan: pick another start date, or run planning.</EmptyState>
          ) : (
            data.data.days.map((day) => (
              <section key={day.date} className="panel overflow-hidden" aria-label={`Heats on ${formatDate(day.date)}`}>
                <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-line bg-sunken px-4 py-2">
                  <h3 className="font-display text-lg font-semibold">
                    {formatWeekday(day.date)} <span className="font-mono text-base">{formatDate(day.date)}</span>
                  </h3>
                  <p className="text-sm text-ink-soft">
                    <span className="font-mono">{formatNumber(day.heats.length)}</span> heats · <span className="font-mono">{formatNumber(Math.round(day.kg))}</span> kg
                  </p>
                </header>
                {day.furnaces.length > 0 && (
                  <ul className="flex flex-wrap gap-x-6 gap-y-1 border-b border-line px-4 py-2 text-sm" aria-label="Furnace use">
                    {day.furnaces.map((f) => (
                      <li key={f.furnace} className="flex items-center gap-2">
                        <span className="font-mono font-medium">{f.furnace}</span>
                        <UseBar pct={f.used_pct} label={`${f.heats} of ${f.capacity_heats} heats`} />
                        <span className="text-xs text-ink-soft">{f.heats} of {f.capacity_heats} heats</span>
                      </li>
                    ))}
                  </ul>
                )}
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[44rem] text-left text-sm">
                    <thead className="border-b border-line text-ink-soft">
                      <tr>
                        {["Heat", "Furnace", "Shift", "Grade", "Metal (kg)", "Fill", "Pours"].map((h, i) => (
                          <th key={h} scope="col" className={`px-3 py-1.5 font-medium ${i === 4 ? "text-right" : ""}`}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {day.heats.map((h) => (
                        <tr key={h.id} className={`border-b border-line align-top last:border-0 ${h.furnace ? "" : "bg-danger-wash/40"}`}>
                          <td className="px-3 py-1.5 font-mono font-medium">{h.heat_no}</td>
                          <td className="px-3 py-1.5 font-mono">{h.furnace ?? <span className="text-danger">no room</span>}</td>
                          <td className="px-3 py-1.5">{h.shift || "–"}</td>
                          <td className="px-3 py-1.5 font-medium">{h.grade}</td>
                          <td className="px-3 py-1.5 text-right font-mono">{formatNumber(Math.round(h.kg))}</td>
                          <td className="px-3 py-1.5"><UseBar pct={h.capacity_kg ? h.fill_pct : null} label={`${formatNumber(Math.round(h.kg))} of ${formatNumber(Math.round(h.capacity_kg))} kg`} /></td>
                          <td className="px-3 py-1.5">
                            {h.pours.map((p) => `${p.part_number} × ${formatNumber(p.moulds)}`).join(", ")}
                            {h.warnings.map((text) => (
                              <p key={text} className="text-xs text-warn">{text}</p>
                            ))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            ))
          )}
          <p className="text-xs text-ink-soft">
            Each day&apos;s metal is the moulds made that day times their pouring weight, split by grade. A heat takes whole moulds of one grade, up to what the furnace taps after melt loss.
          </p>
        </div>
      )}
    </div>
  );
}
