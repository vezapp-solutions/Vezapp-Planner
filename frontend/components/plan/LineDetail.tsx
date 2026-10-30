"use client";

import { Explain } from "@/components/Explain";
import { SlideOver } from "@/components/SlideOver";
import { ErrorState, LoadingState } from "@/components/States";
import { Slack, StatusBadge } from "@/components/plan/StatusBadge";
import { formatDate, formatDateTime, formatNumber } from "@/lib/format";
import type { PlanLineDetail, Traced } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const UNIT: Record<string, string> = { core: "cores", moulding: "moulds", melting: "moulds" };

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-ink-soft">{label}</dt>
      <dd className="font-medium">{children}</dd>
    </div>
  );
}

function waitText(hours: number | null): string {
  if (hours == null || hours < 1) return "none";
  return hours < 24 ? `${Math.round(hours)} h` : `${(hours / 24).toFixed(1)} days`;
}

export function LineDetailPanel({ planId, lineId, version, onClose }: { planId: number; lineId: number; version: string; onClose: () => void }) {
  const detail = useApi<PlanLineDetail>(`/plans/${planId}/lines/${lineId}?v=${encodeURIComponent(version)}`);
  const d = detail.data;
  const req = d?.requirement;
  const trace = (key: string): Traced | undefined => req?.traces?.[key];

  return (
    <SlideOver wide title={d ? `${d.part_number} · ${d.part_name}` : "Dispatch line"} subtitle={d ? `${d.customer_code} ${d.customer_name} · ${formatNumber(d.qty)} pieces` : undefined} onClose={onClose}>
      {detail.loading ? (
        <LoadingState label="Loading the line" rows={4} />
      ) : detail.error || !d ? (
        <ErrorState message={detail.error?.message ?? "Could not load."} onRetry={detail.reload} />
      ) : (
        <div className="space-y-6">
          <dl className="grid gap-4 sm:grid-cols-4">
            <Fact label="Status"><StatusBadge status={d.status} /></Fact>
            <Fact label="Due (internal date)"><span className="font-mono">{formatDate(d.internal_date)}</span></Fact>
            <Fact label="Estimated dispatch"><span className="font-mono">{d.est_dispatch_date ? formatDate(d.est_dispatch_date) : "–"}</span></Fact>
            <Fact label="Working days spare"><Slack days={d.slack_working_days} /></Fact>
          </dl>

          {d.holding_text && (
            <p className="rounded-md border border-warn bg-warn-wash px-3 py-2 text-sm">
              <strong>Held up by {d.holding_op}.</strong> {d.holding_text}
            </p>
          )}
          {d.notes.length > 0 && (
            <ul className="space-y-1 text-sm text-danger">
              {d.notes.map((n) => <li key={n}>{n}</li>)}
            </ul>
          )}

          <section aria-labelledby="req-title">
            <h3 id="req-title" className="mb-2 font-display text-lg font-semibold">How much work this is</h3>
            <p className="mb-2 text-xs text-ink-soft">Click a number to see how it was worked out.</p>
            <dl className="grid gap-4 sm:grid-cols-4">
              {([
                ["Pieces to pour", "pieces_to_pour", ""],
                ["Moulds", "moulds", ""],
                ["Cores", "cores", ""],
                ["Metal", "metal_kg", " kg"],
              ] as const).map(([label, key, unit]) => {
                const t = trace(key);
                return t ? (
                  <Fact key={key} label={label}><Explain traced={t} label={label} unit={unit} /></Fact>
                ) : null;
              })}
            </dl>
          </section>

          <section aria-labelledby="ops-title">
            <h3 id="ops-title" className="mb-2 font-display text-lg font-semibold">Operations</h3>
            <div className="overflow-x-auto rounded-md border border-line">
              <table className="w-full min-w-[44rem] text-left text-sm">
                <thead className="border-b border-line bg-sunken text-ink-soft">
                  <tr>
                    {["Operation", "On", "Minutes", "Starts", "Finishes", "Needed by", "Waited for capacity"].map((h) => (
                      <th key={h} scope="col" className="px-3 py-2 font-medium">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {d.operations.map((o) => {
                    const t = trace(`minutes.${o.code}`);
                    return (
                      <tr key={o.code} className="border-b border-line align-top last:border-0">
                        <td className="px-3 py-1.5 font-medium">
                          {o.name}
                          {!o.capacity_modelled && !o.outsourced && <span className="ml-1.5 rounded-sm bg-sunken px-1 text-xs text-ink-soft" title="No work centre is set, so this step takes time but is not limited by capacity.">not modelled</span>}
                          {o.outsourced && <span className="ml-1.5 rounded-sm bg-sunken px-1 text-xs text-ink-soft">outside</span>}
                        </td>
                        <td className="px-3 py-1.5 font-mono text-xs">{o.resource_codes || "–"}</td>
                        <td className="px-3 py-1.5 font-mono">{t ? <Explain traced={t} label={`${o.name} minutes`} /> : formatNumber(o.minutes)}</td>
                        <td className="whitespace-nowrap px-3 py-1.5 font-mono">{o.start_at ? formatDateTime(o.start_at) : "–"}</td>
                        <td className="whitespace-nowrap px-3 py-1.5 font-mono">{o.finish_at ? formatDateTime(o.finish_at) : "–"}</td>
                        <td className="whitespace-nowrap px-3 py-1.5 font-mono text-ink-soft">{o.latest_finish ? formatDateTime(o.latest_finish) : "–"}</td>
                        <td className="px-3 py-1.5">{waitText(o.wait_hours)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          <section aria-labelledby="alloc-title">
            <h3 id="alloc-title" className="mb-2 font-display text-lg font-semibold">Where the work runs</h3>
            {d.allocations.length === 0 ? (
              <p className="text-sm text-ink-soft">Nothing is scheduled on a resource.</p>
            ) : (
              <div className="max-h-72 overflow-auto rounded-md border border-line">
                <table className="w-full min-w-[34rem] text-left text-sm">
                  <thead className="sticky top-0 border-b border-line bg-sunken text-ink-soft">
                    <tr>{["Day", "Shift", "Operation", "Resource", "Quantity", "Minutes"].map((h) => <th key={h} scope="col" className="px-3 py-1.5 font-medium">{h}</th>)}</tr>
                  </thead>
                  <tbody>
                    {d.allocations.map((a, i) => (
                      <tr key={i} className="border-b border-line last:border-0">
                        <td className="px-3 py-1 font-mono">{formatDate(a.date)}</td>
                        <td className="px-3 py-1">{a.shift}</td>
                        <td className="px-3 py-1">{a.op_code}</td>
                        <td className="px-3 py-1 font-mono">{a.resource ?? "–"}</td>
                        <td className="px-3 py-1 font-mono">{formatNumber(a.qty, 1)} {UNIT[a.op_code] ?? "pcs"}</td>
                        <td className="px-3 py-1 font-mono">{formatNumber(a.minutes, 1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </div>
      )}
    </SlideOver>
  );
}
