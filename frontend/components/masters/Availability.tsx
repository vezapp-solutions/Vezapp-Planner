"use client";

import { useState } from "react";

import { Explain } from "@/components/Explain";
import { ErrorState, LoadingState } from "@/components/States";
import { addDays, formatDayMonth, formatNumber, formatWeekday, todayInIndia } from "@/lib/format";
import type { Availability } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { DatePicker } from "@/components/ui/DatePicker";

/** Shift-by-shift available minutes for one resource. Click a number to see how it was worked out. */
export function AvailabilityPreview({ resourceId, isFurnace, version }: { resourceId: number; isFurnace: boolean; version: number }) {
  const [from, setFrom] = useState(todayInIndia());
  const to = addDays(from, 6);
  const data = useApi<Availability>(`/resources/${resourceId}/availability?from=${from}&to=${to}&v=${version}`);

  return (
    <section aria-labelledby="avail-title" className="space-y-2">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h3 id="avail-title" className="font-display text-lg font-semibold">Available minutes, 7 days</h3>
        <label className="flex items-center gap-2 text-sm">
          From
          <DatePicker className="field !min-h-9 !w-auto" value={from} onChange={(e) => e.target.value && setFrom(e.target.value)} clearable={false} />
        </label>
      </div>
      {data.loading ? (
        <LoadingState label="Calculating availability" rows={2} />
      ) : data.error || !data.data ? (
        <ErrorState message={data.error?.message ?? "Could not load."} onRetry={data.reload} />
      ) : data.data.shifts.length === 0 ? (
        <p className="text-sm text-ink-soft">No working shifts in this period (weekly off, holidays, or no shifts set up).</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[26rem] text-left text-sm">
            <thead className="border-b border-line text-ink-soft">
              <tr>
                <th scope="col" className="py-1.5 pr-3 font-medium">Day</th>
                <th scope="col" className="px-3 py-1.5 font-medium">Shift</th>
                <th scope="col" className="px-3 py-1.5 text-right font-medium">Shift min</th>
                <th scope="col" className="px-3 py-1.5 text-right font-medium">Downtime</th>
                <th scope="col" className="px-3 py-1.5 text-right font-medium">Available</th>
                {isFurnace && <th scope="col" className="py-1.5 pl-3 text-right font-medium">Heats</th>}
              </tr>
            </thead>
            <tbody>
              {data.data.shifts.map((s) => (
                <tr key={`${s.date}-${s.shift_id}`} className="border-b border-line last:border-0">
                  <td className="py-1.5 pr-3 font-mono">{formatWeekday(s.date, "short")} {formatDayMonth(s.date)}</td>
                  <td className="px-3 py-1.5">{s.shift_name}</td>
                  <td className="px-3 py-1.5 text-right font-mono">{formatNumber(s.shift_minutes)}</td>
                  <td className="px-3 py-1.5 text-right font-mono">{s.downtime_minutes ? formatNumber(s.downtime_minutes, 1) : "–"}</td>
                  <td className="px-3 py-1.5 text-right">
                    <Explain label={`Available minutes, ${s.shift_name} ${formatDayMonth(s.date)}`} traced={{ ...s.trace, value: s.available_minutes }} />
                  </td>
                  {isFurnace && (
                    <td className="py-1.5 pl-3 text-right">{s.heats ? <Explain label="Heats in this shift" traced={s.heats} /> : "–"}</td>
                  )}
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-line font-medium">
                <td className="py-1.5 pr-3" colSpan={4}>Total, 7 days</td>
                <td className="px-3 py-1.5 text-right font-mono">{formatNumber(data.data.total_available_minutes, 1)}</td>
                {isFurnace && <td />}
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </section>
  );
}
