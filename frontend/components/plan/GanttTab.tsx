"use client";

import { useMemo, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { LineDetailPanel } from "@/components/plan/LineDetail";
import { formatDate, formatDayMonth, formatWeekday, addDays, todayInIndia } from "@/lib/format";
import { STATUS_COLOR, clip, placeResourceBars, xOf, type GanttScale } from "@/lib/plan-utils";
import { PLAN_STATUS_LABEL, type GanttBar, type Plan } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const LABEL_W = 150;
const ROW_H = 30;
const HEAD_H = 40;
const DAY_PX = 96;

interface Gantt {
  by: "resource" | "line";
  from: string;
  to: string;
  bars: GanttBar[];
}

export function GanttTab({ plan }: { plan: Plan }) {
  const [by, setBy] = useState<"resource" | "line">("resource");
  const [from, setFrom] = useState(() => {
    const today = todayInIndia();
    return today > plan.plan_from ? today : plan.plan_from;
  });
  const [days, setDays] = useState(14);
  const [lineId, setLineId] = useState<number | null>(null);
  const to = addDays(from, days - 1);
  const version = plan.calculated_at ?? "";
  const data = useApi<Gantt>(`/plans/${plan.id}/gantt?by=${by}&from=${from}&to=${to}&v=${encodeURIComponent(version)}`);

  const scale: GanttScale = useMemo(() => ({ startMs: new Date(`${from}T00:00:00+05:30`).getTime(), days, width: days * DAY_PX }), [from, days]);
  const dayList = useMemo(() => Array.from({ length: days }, (_, i) => addDays(from, i)), [from, days]);

  const rows = useMemo(() => {
    const order: number[] = [];
    const labels = new Map<number, string>();
    for (const b of data.data?.bars ?? []) {
      if (!labels.has(b.row)) {
        order.push(b.row);
        labels.set(b.row, b.row_label);
      }
    }
    return order.map((id) => ({ id, label: labels.get(id) ?? "", bars: (data.data?.bars ?? []).filter((b) => b.row === id) }));
  }, [data.data]);

  const height = HEAD_H + rows.length * ROW_H + 8;

  return (
    <>
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div role="group" aria-label="Rows by" className="flex">
          {(["resource", "line"] as const).map((v) => (
            <button key={v} type="button" aria-pressed={by === v} onClick={() => setBy(v)} className={`btn !min-h-10 ${by === v ? "btn-primary" : "btn-quiet"}`}>
              By {v}
            </button>
          ))}
        </div>
        <label className="text-sm">
          <span className="mb-1 block text-ink-soft">From</span>
          <input type="date" className="field !min-h-10 !w-40" value={from} onChange={(e) => e.target.value && setFrom(e.target.value)} />
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-ink-soft">Window</span>
          <select className="field !min-h-10 !w-32" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            {[7, 14, 28].map((d) => <option key={d} value={d}>{d} days</option>)}
          </select>
        </label>
        <ul className="flex flex-wrap gap-3 text-xs" aria-label="Colour key">
          {(Object.keys(STATUS_COLOR) as (keyof typeof STATUS_COLOR)[]).map((s) => (
            <li key={s} className="flex items-center gap-1.5">
              <span className="inline-block size-3 rounded-sm" style={{ background: STATUS_COLOR[s] }} /> {PLAN_STATUS_LABEL[s]}
            </li>
          ))}
        </ul>
      </div>

      {data.loading ? (
        <LoadingState label="Drawing the chart" rows={4} />
      ) : data.error ? (
        <ErrorState message={data.error.message} onRetry={data.reload} />
      ) : rows.length === 0 ? (
        <EmptyState title="Nothing planned in this window">Pick another start date, or check the Lines tab.</EmptyState>
      ) : (
        <div className="panel overflow-auto">
          <svg
            width={LABEL_W + scale.width}
            height={height}
            role="img"
            aria-label={`Gantt chart by ${by}, ${formatDate(from)} to ${formatDate(to)}, ${rows.length} rows. The Lines tab lists the same work as a table.`}
            style={{ display: "block", minWidth: "100%" }}
          >
            {/* day columns */}
            {dayList.map((d, i) => {
              const dow = new Date(`${d}T00:00:00+05:30`).getDay();
              return (
                <g key={d}>
                  <rect x={LABEL_W + i * DAY_PX} y={0} width={DAY_PX} height={height} fill={dow === 0 ? "var(--sunken)" : "transparent"} />
                  <line x1={LABEL_W + i * DAY_PX} x2={LABEL_W + i * DAY_PX} y1={0} y2={height} stroke="var(--line)" />
                  <text x={LABEL_W + i * DAY_PX + 6} y={16} fontSize="11" fill="var(--ink-soft)">{formatWeekday(d, "short")}</text>
                  <text x={LABEL_W + i * DAY_PX + 6} y={31} fontSize="12" fill="var(--ink)" fontFamily="var(--font-mono)">{formatDayMonth(d)}</text>
                </g>
              );
            })}
            <line x1={0} x2={LABEL_W + scale.width} y1={HEAD_H} y2={HEAD_H} stroke="var(--line)" />

            {rows.map((row, r) => {
              const y = HEAD_H + r * ROW_H;
              const placed =
                by === "resource"
                  ? placeResourceBars(row.bars, scale)
                  : row.bars.map((b) => ({ bar: b, x: xOf(scale, b.start), width: Math.max(3, xOf(scale, b.end) - xOf(scale, b.start)) }));
              return (
                <g key={row.id}>
                  <line x1={0} x2={LABEL_W + scale.width} y1={y + ROW_H} y2={y + ROW_H} stroke="var(--line)" opacity={0.6} />
                  <text x={8} y={y + 19} fontSize="12" fill="var(--ink)" fontFamily={by === "resource" ? "var(--font-mono)" : undefined}>
                    {row.label.length > 20 ? `${row.label.slice(0, 19)}…` : row.label}
                  </text>
                  {placed.map(({ bar, x, width }, i) => {
                    const c = clip(x, width, scale.width);
                    if (!c) return null;
                    const id = bar.line ?? bar.row;
                    const title = by === "resource"
                      ? `${bar.label} · ${bar.code} · ${Math.round(bar.minutes ?? 0)} min · ${PLAN_STATUS_LABEL[bar.status]}`
                      : `${bar.name} · ${formatDate(bar.start.slice(0, 10))} to ${formatDate(bar.end.slice(0, 10))} · ${PLAN_STATUS_LABEL[bar.status]}`;
                    return (
                      <g key={i} role="button" tabIndex={0} aria-label={title} style={{ cursor: "pointer" }} onClick={() => setLineId(id)} onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && setLineId(id)}>
                        <title>{title}</title>
                        <rect x={LABEL_W + c.x} y={y + 5} width={c.width} height={ROW_H - 10} rx={2} fill={STATUS_COLOR[bar.status]} opacity={by === "line" ? 0.85 : 1} />
                        {by === "line" && c.width > 44 && (
                          <text x={LABEL_W + c.x + 4} y={y + 19} fontSize="10" fill="var(--on-action)">{bar.code}</text>
                        )}
                      </g>
                    );
                  })}
                  {by === "line" && row.bars[0]?.due && (() => {
                    const dx = xOf(scale, `${row.bars[0].due}T23:59:00+05:30`);
                    return dx >= 0 && dx <= scale.width ? (
                      <g>
                        <title>{`Internal date ${formatDate(row.bars[0].due!)}`}</title>
                        <polygon points={`${LABEL_W + dx},${y + 4} ${LABEL_W + dx + 5},${y + ROW_H / 2} ${LABEL_W + dx},${y + ROW_H - 4}`} fill="var(--ink)" />
                      </g>
                    ) : null;
                  })()}
                </g>
              );
            })}
          </svg>
        </div>
      )}
      <p className="mt-2 text-xs text-ink-soft">
        {by === "resource"
          ? "Each block is one line's work in one shift. Its width is its share of the shift's capacity; blank space is free capacity."
          : "Each bar runs from the first to the last piece of an operation. The black marker is the internal dispatch date."}{" "}
        Click a bar for the line.
      </p>
      {lineId && <LineDetailPanel planId={plan.id} lineId={lineId} version={version} onClose={() => setLineId(null)} />}
    </>
  );
}

