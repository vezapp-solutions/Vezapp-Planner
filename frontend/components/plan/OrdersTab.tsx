"use client";

import { useState } from "react";

import { OrderStateBadge } from "@/components/plan/OrderStateBadge";
import { HistoryButton, StockCell } from "@/components/scheduler/StockCell";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { formatDate, formatNumber } from "@/lib/format";
import { ORDER_STATE_LABEL, type OrderState, type Page, type Plan, type ScheduleLine } from "@/lib/types";
import { useApi } from "@/lib/use-api";

type Filter = "all" | OrderState;
const ORDER: OrderState[] = ["at_risk", "cannot_plan", "planned", "covered", "not_planned_yet", "closed"];

/** Every order with its stock and balance beside the dispatch date, and what planning made of it. */
export function OrdersTab({ plan, canEdit, onStockChanged }: { plan: Plan; canEdit: boolean; onStockChanged: () => void }) {
  const [showClosed, setShowClosed] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [version, setVersion] = useState(0);
  const lines = useApi<Page<ScheduleLine>>(`/schedule-lines?page_size=500${showClosed ? "" : "&open=1"}&v=${version}-${plan.calculated_at}`);

  if (lines.loading) return <LoadingState label="Loading the orders" rows={5} />;
  if (lines.error || !lines.data) return <ErrorState message={lines.error?.message ?? "Could not load."} onRetry={lines.reload} />;

  const all = lines.data.results;
  const counts = new Map<OrderState, number>();
  for (const l of all) counts.set(l.plan_state, (counts.get(l.plan_state) ?? 0) + 1);
  const rows = filter === "all" ? all : all.filter((l) => l.plan_state === filter);
  const saved = () => {
    setVersion((v) => v + 1);
    onStockChanged();
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Show orders" className="flex flex-wrap gap-1">
          <button type="button" aria-pressed={filter === "all"} onClick={() => setFilter("all")} className={`btn !min-h-8 !px-3 ${filter === "all" ? "btn-primary" : "btn-quiet"}`}>
            All ({all.length})
          </button>
          {ORDER.filter((s) => counts.get(s)).map((s) => (
            <button key={s} type="button" aria-pressed={filter === s} onClick={() => setFilter(s)} className={`btn !min-h-8 !px-3 ${filter === s ? "btn-primary" : "btn-quiet"}`}>
              {ORDER_STATE_LABEL[s].replace(": missing master data", "")} ({counts.get(s)})
            </button>
          ))}
        </div>
        <label className="ml-auto flex min-h-9 items-center gap-2 text-sm">
          <input type="checkbox" checked={showClosed} onChange={(e) => { setShowClosed(e.target.checked); setFilter("all"); }} />
          Show closed orders
        </label>
      </div>

      {rows.length === 0 ? (
        <EmptyState title="No orders here">Upload the month&apos;s orders on the Monthly Scheduler, or change the filter.</EmptyState>
      ) : (
        <div className="panel overflow-x-auto">
          <table className="w-full min-w-[60rem] text-left text-sm">
            <thead className="border-b border-line bg-sunken text-ink-soft">
              <tr>
                {["Dispatch date", "Part", "Customer", "Order qty", "WIP", "FG", "Dispatched", "Balance", "Estimated", "Status"].map((h, i) => (
                  <th key={h} scope="col" className={`px-3 py-2 font-medium ${i >= 3 && i <= 7 ? "text-right" : ""}`}>{h}</th>
                ))}
                <th scope="col" className="w-16 px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {rows.map((l) => (
                <tr key={l.id} className={`border-b border-line align-top last:border-0 hover:bg-sunken/60 ${l.is_open ? "" : "text-ink-soft"}`}>
                  <td className="whitespace-nowrap px-3 py-2 font-mono">{formatDate(l.internal_dispatch_date)}</td>
                  <td className="px-3 py-2"><span className="font-medium">{l.part_number}</span> <span className="text-ink-soft">{l.grade_name}</span></td>
                  <td className="px-3 py-2 font-mono text-xs">{l.customer_code}</td>
                  <td className="px-3 py-2 text-right font-mono">{formatNumber(l.dispatch_qty)}</td>
                  <td className="px-2 py-1.5 text-right"><StockCell line={l} field="wip_qty" label="WIP stock" canEdit={canEdit} onSaved={saved} /></td>
                  <td className="px-2 py-1.5 text-right"><StockCell line={l} field="fg_qty" label="FG stock" canEdit={canEdit} onSaved={saved} /></td>
                  <td className="px-2 py-1.5 text-right"><StockCell line={l} field="actual_dispatched_qty" label="Dispatched" canEdit={canEdit} onSaved={saved} /></td>
                  <td className="px-3 py-2 text-right font-mono font-semibold">{formatNumber(l.balance)}</td>
                  <td className="whitespace-nowrap px-3 py-2 font-mono">{l.est_dispatch_date ? formatDate(l.est_dispatch_date) : <span className="text-ink-soft">–</span>}</td>
                  <td className="px-3 py-2"><OrderStateBadge state={l.plan_state} reasons={l.plan_reasons} /></td>
                  <td className="px-3 py-2 text-right"><HistoryButton line={l} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="text-xs text-ink-soft">
        Balance = order qty − (WIP + FG + dispatched). Only the balance is planned, earliest dispatch date first. After you change stock, run planning again.
      </p>
    </div>
  );
}
