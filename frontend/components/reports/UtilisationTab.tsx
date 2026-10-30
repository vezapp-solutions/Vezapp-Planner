"use client";

import { useState } from "react";

import { Panel } from "@/components/Panel";
import { DateFilters, ExportButtons } from "@/components/reports/ExportButtons";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { formatDate, formatNumber } from "@/lib/format";
import { query } from "@/lib/insights";
import { HEAT_STYLE, heatLevel, percent } from "@/lib/plan-utils";
import type { UtilisationReport } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export function UtilisationTab() {
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const q = query({ from, to });
  const report = useApi<UtilisationReport>(`/reports/utilisation${q}`);
  const weeks = [...new Set(report.data?.resources.flatMap((r) => r.weeks.map((w) => w.week_start)) ?? [])].sort();

  return (
    <div className="space-y-4">
      <p className="text-sm text-ink-soft">How much of each resource&apos;s capacity the latest plan uses. Leave the dates empty for the next four weeks.</p>
      <DateFilters from={from} to={to} onFrom={setFrom} onTo={setTo} />
      <ExportButtons path={`/reports/utilisation${q}`} filename="utilisation" disabled={!report.data?.plan} />
      {report.loading ? (
        <LoadingState label="Loading the report" rows={4} />
      ) : report.error || !report.data ? (
        <ErrorState message={report.error?.message ?? "Could not load."} onRetry={report.reload} />
      ) : !report.data.plan || report.data.resources.length === 0 ? (
        <EmptyState title="Nothing to report yet">Calculate a plan on the Plan screen; resource utilisation then appears here.</EmptyState>
      ) : (
        <Panel title="Planned load against capacity" note={`plan v${report.data.plan.version} · ${formatDate(report.data.from!)} to ${formatDate(report.data.to!)}`}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[36rem] text-left text-sm">
              <thead className="border-b border-line text-ink-soft">
                <tr>
                  <th scope="col" className="px-2 py-1.5 font-medium">Resource</th>
                  <th scope="col" className="px-2 py-1.5 text-right font-medium">Load (h)</th>
                  <th scope="col" className="px-2 py-1.5 text-right font-medium">Capacity (h)</th>
                  <th scope="col" className="px-2 py-1.5 text-right font-medium">Utilisation</th>
                  <th scope="col" className="px-2 py-1.5 font-medium">Busiest day</th>
                  {weeks.map((w) => <th key={w} scope="col" className="px-2 py-1.5 text-right font-medium">Wk {formatDate(w).slice(0, 5)}</th>)}
                </tr>
              </thead>
              <tbody>
                {report.data.resources.map((r) => {
                  const byWeek = new Map(r.weeks.map((w) => [w.week_start, w.utilisation]));
                  return (
                    <tr key={r.id} className="border-b border-line last:border-0">
                      <th scope="row" className="px-2 py-1.5 font-medium">{r.code} <span className="font-normal text-ink-soft">{r.name}</span></th>
                      <td className="px-2 py-1.5 text-right font-mono">{formatNumber(r.load / 60, 1)}</td>
                      <td className="px-2 py-1.5 text-right font-mono">{formatNumber(r.capacity / 60, 1)}</td>
                      <td className="px-2 py-1.5 text-right font-mono">{percent(r.utilisation)}</td>
                      <td className="px-2 py-1.5 font-mono text-xs">{r.peak_date ? `${formatDate(r.peak_date)} (${percent(r.peak_utilisation)})` : "–"}</td>
                      {weeks.map((w) => {
                        const u = byWeek.get(w);
                        return (
                          <td key={w} className="px-2 py-1.5 text-right font-mono">
                            <span className="rounded-sm px-1.5 py-0.5" style={HEAT_STYLE[heatLevel(u)]}>{percent(u)}</span>
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </div>
  );
}
