"use client";

import { useState } from "react";

import { CrudScreen } from "@/components/CrudScreen";
import { Panel } from "@/components/Panel";
import { ErrorState, LoadingState } from "@/components/States";
import type { FieldSpec } from "@/components/forms";
import { ApiError, put } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import type { Shift, Week } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const FIELDS: FieldSpec[] = [
  { key: "name", label: "Shift name", type: "text", required: true, placeholder: "Shift 1" },
  { key: "start_time", label: "Starts", type: "time", required: true },
  { key: "end_time", label: "Ends", type: "time", required: true, hint: "An end earlier than the start means the shift runs past midnight." },
  { key: "break_minutes", label: "Break", type: "number", unit: "min", step: "1", min: 0, hint: "Counts inside the shift and is taken off its working time." },
];

function WeekGrid({ canEdit, version }: { canEdit: boolean; version: number }) {
  const week = useApi<Week>(`/calendar/week?v=${version}`);
  const [edits, setEdits] = useState<Record<number, number[]> | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  if (week.loading) return <LoadingState label="Loading the weekly pattern" rows={4} />;
  if (week.error || !week.data) return <ErrorState message={week.error?.message ?? "Could not load."} onRetry={week.reload} />;
  const { shifts, days } = week.data;
  const chosen = (weekday: number) => edits?.[weekday] ?? days[weekday].shift_ids;
  const net = new Map(shifts.map((s) => [s.id, s.net_minutes]));
  const dayMinutes = (weekday: number) => chosen(weekday).reduce((sum, id) => sum + (net.get(id) ?? 0), 0);
  const weekMinutes = days.reduce((sum, d) => sum + dayMinutes(d.weekday), 0);

  function toggle(weekday: number, shiftId: number) {
    const now = chosen(weekday);
    setSaved(false);
    setEdits({ ...(edits ?? {}), [weekday]: now.includes(shiftId) ? now.filter((i) => i !== shiftId) : [...now, shiftId] });
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await put("/calendar/week", { days: Object.fromEntries(Object.entries(edits ?? {})) });
      setEdits(null);
      setSaved(true);
      week.reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  if (!shifts.length) {
    return <p className="text-sm text-ink-soft">Add at least one shift above, then choose which days it runs.</p>;
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <table className="w-full min-w-[28rem] text-left text-sm">
          <thead className="border-b border-line text-ink-soft">
            <tr>
              <th scope="col" className="py-2 pr-4 font-medium">Day</th>
              {shifts.map((s) => (
                <th key={s.id} scope="col" className="px-3 py-2 font-medium">{s.name}</th>
              ))}
              <th scope="col" className="py-2 pl-3 text-right font-medium">Working minutes</th>
            </tr>
          </thead>
          <tbody>
            {days.map((d) => (
              <tr key={d.weekday} className="border-b border-line last:border-0">
                <th scope="row" className="py-2 pr-4 font-medium">{d.name}</th>
                {shifts.map((s) => (
                  <td key={s.id} className="px-3 py-2">
                    <input
                      type="checkbox"
                      className="size-5 accent-[var(--action)]"
                      checked={chosen(d.weekday).includes(s.id)}
                      disabled={!canEdit}
                      onChange={() => toggle(d.weekday, s.id)}
                      aria-label={`${s.name} runs on ${d.name}`}
                    />
                  </td>
                ))}
                <td className="py-2 pl-3 text-right font-mono">
                  {dayMinutes(d.weekday) ? formatNumber(dayMinutes(d.weekday)) : <span className="text-ink-soft">weekly off</span>}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className="border-t border-line font-medium">
              <td className="py-2 pr-4" colSpan={shifts.length + 1}>Per week</td>
              <td className="py-2 pl-3 text-right font-mono">{formatNumber(weekMinutes)}</td>
            </tr>
          </tfoot>
        </table>
      </div>
      {error && <ErrorState message={error} />}
      {canEdit && (
        <div className="flex items-center gap-3">
          <button type="button" className="btn btn-primary" onClick={save} disabled={busy || !edits}>
            {busy ? "Saving…" : "Save weekly pattern"}
          </button>
          {saved && <span role="status" className="text-sm text-ok">Saved.</span>}
        </div>
      )}
    </div>
  );
}

export function ShiftsWeek({ canEdit }: { canEdit: boolean }) {
  const [version, setVersion] = useState(0);
  return (
    <div className="space-y-6">
      <Panel title="Shifts" note="working time per shift, break taken off">
        <CrudScreen<Shift>
          path="/shifts"
          noun="shift"
          fields={FIELDS}
          canEdit={canEdit}
          defaults={{ break_minutes: "30" }}
          onChanged={() => setVersion((v) => v + 1)}
          emptyHint="A foundry usually runs one to three shifts a day. Shifts that cross midnight belong to the day they start."
          columns={[
            { header: "Shift", cell: (s) => s.name },
            { header: "Time", cell: (s) => <span className="font-mono">{s.start_time.slice(0, 5)}–{s.end_time.slice(0, 5)}{s.crosses_midnight && " (next day)"}</span> },
            { header: "Break", cell: (s) => <span className="font-mono">{s.break_minutes} min</span> },
            { header: "Working", cell: (s) => <span className="font-mono">{formatNumber(s.net_minutes)} min</span>, className: "text-right" },
          ]}
        />
      </Panel>
      <Panel title="Weekly pattern" note="a day with no shift is a weekly off">
        <WeekGrid canEdit={canEdit} version={version} />
      </Panel>
    </div>
  );
}
