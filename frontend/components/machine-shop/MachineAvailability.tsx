"use client";

import { useState } from "react";

import { Panel } from "@/components/Panel";
import { formatDate, formatDateTime, formatDayMonth, formatNumber, formatWeekday } from "@/lib/format";
import { dayCell, hours } from "@/lib/machining";
import { HEAT_STYLE, heatLevel, percent } from "@/lib/plan-utils";
import type { Machine, MachineShop, MachineType } from "@/lib/types";

function Detail({ machine, days }: { machine: Machine; days: string[] }) {
  return (
    <div className="space-y-3 border-t border-line px-4 py-3 text-sm" aria-label={`${machine.code} in detail`}>
      <p className="text-ink-soft">
        {machine.name} · {machine.units} unit{machine.units === 1 ? "" : "s"} at {formatNumber(machine.efficiency_pct)}% efficiency
        {machine.status !== "active" ? ` · ${machine.status}` : ""}. {days.length} working day{days.length === 1 ? "" : "s"} shown:{" "}
        <span className="font-mono text-ink">{hours(machine.load)} h</span> planned of <span className="font-mono text-ink">{hours(machine.capacity)} h</span>
        {machine.setup > 0 && <>, including <span className="font-mono text-ink">{hours(machine.setup)} h</span> of setup</>}.
      </p>
      {machine.downtime.length > 0 && (
        <ul className="rounded-md border border-warn bg-warn-wash px-3 py-2" aria-label="Blocked periods">
          {machine.downtime.map((d) => (
            <li key={d.start}><span className="font-medium">Blocked</span> {formatDateTime(d.start)} to {formatDateTime(d.end)}{d.reason ? `: ${d.reason}` : ""}</li>
          ))}
        </ul>
      )}
      {machine.operations.length === 0 ? (
        <p className="text-ink-soft">No machining operation is planned on this machine in this period.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[30rem] text-left">
            <thead className="border-b border-line text-ink-soft">
              <tr>
                {["Part", "Customer", "Operation", "Pieces", "Hours", "of which setup"].map((h, i) => (
                  <th key={h} scope="col" className={`px-2 py-1 font-medium ${i >= 3 ? "text-right" : ""}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {machine.operations.map((o) => (
                <tr key={`${o.line_id}-${o.op_code}`} className="border-b border-line last:border-0">
                  <th scope="row" className="px-2 py-1 font-medium">{o.part_number}</th>
                  <td className="px-2 py-1">{o.customer_code}</td>
                  <td className="px-2 py-1">{o.name}</td>
                  <td className="px-2 py-1 text-right font-mono">{formatNumber(o.pieces, 1)}</td>
                  <td className="px-2 py-1 text-right font-mono">{hours(o.minutes)}</td>
                  <td className="px-2 py-1 text-right font-mono">{o.setup_minutes ? hours(o.setup_minutes) : "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function TypePanel({ type, days }: { type: MachineType; days: string[] }) {
  const [open, setOpen] = useState<number | null>(null);
  return (
    <Panel title={type.name} note={`${hours(type.free)} h free · ${percent(type.utilisation)} used`}>
      <div className="-mx-4 -my-4 overflow-x-auto">
        <table className="w-full min-w-max text-left text-sm">
          <thead className="border-b border-line bg-sunken text-ink-soft">
            <tr>
              <th scope="col" className="sticky left-0 z-10 bg-sunken px-3 py-2 font-medium">Machine</th>
              {days.map((d) => (
                <th key={d} scope="col" className="px-1 py-2 text-center font-medium">
                  <span className="block text-[0.6875rem] uppercase">{formatWeekday(d, "short")}</span>
                  <span className="whitespace-nowrap font-mono text-xs">{formatDayMonth(d)}</span>
                </th>
              ))}
              <th scope="col" className="px-3 py-2 text-right font-medium">Free</th>
            </tr>
          </thead>
          <tbody>
            {type.machines.map((m) => (
              <MachineRows key={m.id} machine={m} days={days} open={open === m.id} onToggle={() => setOpen(open === m.id ? null : m.id)} />
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function MachineRows({ machine, days, open, onToggle }: { machine: Machine; days: string[]; open: boolean; onToggle: () => void }) {
  return (
    <>
      <tr className="border-b border-line">
        <th scope="row" className="sticky left-0 z-10 bg-surface px-3 py-1.5 text-left font-normal">
          <button type="button" className="inline-flex min-h-6 min-w-6 items-center gap-2 text-left underline-offset-2 hover:underline" aria-expanded={open} onClick={onToggle}>
            <span className="font-mono font-medium">{machine.code}</span>
            {machine.status !== "active" && <span className="rounded-sm bg-sunken px-1.5 text-xs text-ink-soft">{machine.status}</span>}
            {machine.downtime.length > 0 && <span className="rounded-sm bg-warn-wash px-1.5 text-xs text-warn">blocked</span>}
          </button>
        </th>
        {days.map((d) => {
          const cell = dayCell(machine.days[d]);
          const day = machine.days[d];
          return (
            <td key={d} className="px-1 py-1 text-center" title={cell.title}>
              <span className="block rounded-sm px-1 py-0.5 font-mono text-xs" style={cell.off ? { color: "var(--ink-soft)" } : HEAT_STYLE[heatLevel(day?.utilisation)]}>
                <span className="block font-medium">{cell.main}</span>
                {cell.sub && <span className="block text-[0.6875rem] opacity-90">{cell.sub}</span>}
              </span>
            </td>
          );
        })}
        <td className="whitespace-nowrap px-3 py-1.5 text-right font-mono">{hours(machine.free)} h</td>
      </tr>
      {open && (
        <tr>
          <td colSpan={days.length + 2} className="p-0"><Detail machine={machine} days={days} /></td>
        </tr>
      )}
    </>
  );
}

/** Every machine by type against the working days: share used and free hours, always printed. */
export function MachineAvailability({ shop }: { shop: MachineShop }) {
  return (
    <div className="space-y-5">
      <p className="text-sm text-ink-soft">
        {formatDate(shop.from)} to {formatDate(shop.to)}, plan v{shop.plan?.version}. Each cell is the share of a machine&apos;s working time that is planned, with the hours left. Click a machine to see what is planned on it.
      </p>
      {shop.types.map((t) => <TypePanel key={t.id} type={t} days={shop.days} />)}
    </div>
  );
}
