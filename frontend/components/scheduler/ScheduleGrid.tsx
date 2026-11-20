"use client";

import { useMemo, useState } from "react";

import { OrderStateBadge } from "@/components/plan/OrderStateBadge";
import { HistoryButton, StockCell } from "@/components/scheduler/StockCell";
import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { DatePicker } from "@/components/ui/DatePicker";
import { Select } from "@/components/ui/Select";
import { ApiError, del, fieldErrors, patch, post } from "@/lib/api";
import { formatDate, formatNumber, todayInIndia } from "@/lib/format";
import { LINE_STATUS_LABEL, type Customer, type LineStatus, type Page, type Part, type ScheduleLine } from "@/lib/types";
import { useApi } from "@/lib/use-api";

interface Draft {
  customer: string;
  part: string;
  dispatch_qty: string;
  internal_dispatch_date: string;
  actual_dispatch_date: string;
  actual_dispatched_qty: string;
  wip_qty: string;
  fg_qty: string;
  status: LineStatus;
  remarks: string;
}

function toDraft(line: ScheduleLine | null, month: string): Draft {
  const today = todayInIndia();
  return {
    customer: line ? String(line.customer) : "",
    part: line ? String(line.part) : "",
    dispatch_qty: line ? String(line.dispatch_qty) : "",
    internal_dispatch_date: line ? line.internal_dispatch_date : today.startsWith(month) ? today : `${month}-01`,
    actual_dispatch_date: line?.actual_dispatch_date ?? "",
    actual_dispatched_qty: line?.actual_dispatched_qty != null ? String(line.actual_dispatched_qty) : "",
    wip_qty: String(line?.wip_qty ?? 0),
    fg_qty: String(line?.fg_qty ?? 0),
    status: line?.status ?? "planned",
    remarks: line?.remarks ?? "",
  };
}

const count = (text: string) => (text === "" ? 0 : Number(text));

function payload(d: Draft) {
  return {
    customer: Number(d.customer) || null,
    part: Number(d.part) || null,
    dispatch_qty: d.dispatch_qty === "" ? null : Number(d.dispatch_qty),
    internal_dispatch_date: d.internal_dispatch_date || null,
    actual_dispatch_date: d.actual_dispatch_date || null,
    actual_dispatched_qty: d.actual_dispatched_qty === "" ? null : Number(d.actual_dispatched_qty),
    wip_qty: count(d.wip_qty),
    fg_qty: count(d.fg_qty),
    status: d.status,
    remarks: d.remarks,
  };
}

function Cell({ error, children }: { error?: string; children: React.ReactNode }) {
  return (
    <td className="px-2 py-1.5 align-top">
      {children}
      {error && <p className="mt-0.5 max-w-[14rem] text-xs text-danger">{error}</p>}
    </td>
  );
}

const qtyInput = "field !min-h-9 !px-2 text-sm !w-24 font-mono";

function EditRow({
  line,
  month,
  customers,
  parts,
  onDone,
  onCancel,
}: {
  line: ScheduleLine | null;
  month: string;
  customers: Customer[];
  parts: Part[];
  onDone: () => void;
  onCancel: () => void;
}) {
  const [d, setD] = useState<Draft>(() => toDraft(line, month));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [general, setGeneral] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const set = (patch: Partial<Draft>) => setD((prev) => ({ ...prev, ...patch }));

  // Parts are offered for the chosen customer; with no customer yet (or none linked), all parts.
  const forCustomer = d.customer ? parts.filter((p) => p.customers.some((c) => c.id === Number(d.customer))) : [];
  const partOptions = forCustomer.length ? forCustomer : parts;
  const linkedOnly = forCustomer.length > 0;
  const balance = Math.max(0, count(d.dispatch_qty) - count(d.wip_qty) - count(d.fg_qty) - count(d.actual_dispatched_qty));

  async function save() {
    setBusy(true);
    setErrors({});
    setGeneral(null);
    try {
      if (line) await patch(`/schedule-lines/${line.id}`, payload(d));
      else await post("/schedule-lines", payload(d));
      onDone();
    } catch (err) {
      const fe = fieldErrors(err);
      setErrors(fe);
      setGeneral(err instanceof ApiError && !Object.keys(fe).length ? err.message : "Please fix the marked fields.");
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    if (!line) return;
    setBusy(true);
    try {
      await del(`/schedule-lines/${line.id}`);
      onDone();
    } catch (err) {
      setGeneral(err instanceof ApiError ? err.message : "Could not delete.");
      setConfirmDelete(false);
    } finally {
      setBusy(false);
    }
  }

  const id = `line-${line?.id ?? "new"}`;
  const input = "field !min-h-9 !px-2 text-sm";
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !busy) void save();
    if (e.key === "Escape") onCancel();
  };

  return (
    <tr className="border-b border-line bg-brand-wash/40" onKeyDown={onKey}>
      <Cell error={errors.internal_dispatch_date}>
        <DatePicker aria-label="Dispatch date" className={`${input} w-36`} value={d.internal_dispatch_date} onChange={(e) => set({ internal_dispatch_date: e.target.value })} />
      </Cell>
      <Cell error={errors.customer}>
        <Select aria-label="Customer" className={`${input} w-44`} value={d.customer} onChange={(e) => set({ customer: e.target.value, part: "" })}>
          <option value="">Customer…</option>
          {customers.filter((c) => c.is_active || String(c.id) === d.customer).map((c) => (
            <option key={c.id} value={c.id}>{c.code} {c.name}</option>
          ))}
        </Select>
      </Cell>
      <Cell error={errors.part}>
        <Select aria-label="Part" className={`${input} w-48`} value={d.part} onChange={(e) => set({ part: e.target.value })}>
          <option value="">Part…</option>
          {partOptions.filter((p) => p.is_active || String(p.id) === d.part).map((p) => (
            <option key={p.id} value={p.id}>{p.part_number} {p.name}</option>
          ))}
        </Select>
        {d.customer && !linkedOnly && <p className="mt-0.5 text-xs text-ink-soft">No parts linked to this customer yet; showing all.</p>}
      </Cell>
      <Cell error={errors.dispatch_qty}>
        <input aria-label="Order quantity" type="number" min={1} step={1} inputMode="numeric" className={qtyInput} value={d.dispatch_qty} onChange={(e) => set({ dispatch_qty: e.target.value })} />
      </Cell>
      <Cell error={errors.wip_qty}>
        <input aria-label="WIP stock" type="number" min={0} step={1} inputMode="numeric" className={qtyInput} value={d.wip_qty} onChange={(e) => set({ wip_qty: e.target.value })} />
      </Cell>
      <Cell error={errors.fg_qty}>
        <input aria-label="FG stock" type="number" min={0} step={1} inputMode="numeric" className={qtyInput} value={d.fg_qty} onChange={(e) => set({ fg_qty: e.target.value })} />
      </Cell>
      <Cell error={errors.actual_dispatched_qty}>
        <input aria-label="Dispatched quantity" type="number" min={0} step={1} inputMode="numeric" className={qtyInput} value={d.actual_dispatched_qty} onChange={(e) => set({ actual_dispatched_qty: e.target.value })} />
      </Cell>
      <td className="px-2 py-1.5 text-right align-top font-mono" aria-label="Balance to produce">{formatNumber(balance)}</td>
      <Cell error={errors.status}>
        <Select aria-label="Status" className={`${input} w-40`} value={d.status} onChange={(e) => set({ status: e.target.value as LineStatus })}>
          {Object.entries(LINE_STATUS_LABEL).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </Select>
      </Cell>
      <Cell error={errors.actual_dispatch_date}>
        <DatePicker aria-label="Last dispatch date" className={`${input} w-36`} value={d.actual_dispatch_date} onChange={(e) => set({ actual_dispatch_date: e.target.value })} />
      </Cell>
      <Cell error={errors.remarks}>
        <input aria-label="Remarks" className={`${input} w-44`} value={d.remarks} maxLength={500} onChange={(e) => set({ remarks: e.target.value })} />
      </Cell>
      <td className="px-2 py-1.5 align-top">
        <div className="flex flex-wrap items-center gap-1.5" id={id}>
          <button type="button" className="btn btn-primary !min-h-9 !px-3" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</button>
          <button type="button" className="btn btn-quiet !min-h-9 !px-3" onClick={onCancel} disabled={busy}>Cancel</button>
          {line && (confirmDelete ? (
            <button type="button" className="btn btn-danger !min-h-9 !px-3" onClick={remove} disabled={busy}>Yes, delete</button>
          ) : (
            <button type="button" className="btn btn-quiet !min-h-9 !px-3" onClick={() => setConfirmDelete(true)} disabled={busy}>Delete</button>
          ))}
        </div>
        {general && <p role="alert" className="mt-1 max-w-[16rem] text-xs text-danger">{general}</p>}
      </td>
    </tr>
  );
}

const HEADERS = ["Dispatch date", "Customer", "Part", "Order qty", "WIP", "FG", "Dispatched", "Balance", "Status", "Last dispatch", "Remarks"];
const RIGHT = new Set([3, 4, 5, 6, 7]);

export function ScheduleGrid({
  month,
  query,
  version,
  canEdit,
  adding,
  onAddDone,
  onChanged,
}: {
  month: string;
  query: string;
  version: number;
  canEdit: boolean;
  adding: boolean;
  onAddDone: () => void;
  onChanged: () => void;
}) {
  const lines = useApi<Page<ScheduleLine>>(`/schedule-lines?page_size=500&month=${month}${query}&v=${version}`);
  const customers = useApi<Page<Customer>>("/customers?page_size=500");
  const parts = useApi<Page<Part>>("/parts?page_size=500");
  const [editing, setEditing] = useState<number | null>(null);
  const today = useMemo(() => todayInIndia(), []);

  if (lines.loading || customers.loading || parts.loading) return <LoadingState label="Loading the schedule" rows={5} />;
  const failure = lines.error ?? customers.error ?? parts.error;
  if (failure || !lines.data || !customers.data || !parts.data) {
    return <ErrorState message={failure?.message ?? "Could not load."} onRetry={() => { lines.reload(); customers.reload(); parts.reload(); }} />;
  }
  const rows = lines.data.results;
  const customerList = customers.data.results;
  const partList = parts.data.results;
  const done = () => {
    setEditing(null);
    onAddDone();
    onChanged();
  };
  const stockSaved = () => {
    lines.reload();
    onChanged();
  };

  if (rows.length === 0 && !adding) {
    return (
      <EmptyState title="No orders in this month">
        {canEdit
          ? "Add an order, copy last month's schedule, or upload an Excel file. Each order is a part, a quantity and the date it must be dispatched."
          : "Nothing has been scheduled for this month yet."}
      </EmptyState>
    );
  }

  return (
    <div className="panel overflow-x-auto">
      <table className="w-full min-w-[78rem] text-left text-sm">
        <thead className="border-b border-line bg-sunken text-on-sunken">
          <tr>
            {HEADERS.map((h, i) => (
              <th key={h} scope="col" className={`px-3 py-2 font-medium ${RIGHT.has(i) ? "text-right" : ""}`}>{h}</th>
            ))}
            <th scope="col" className="w-28 px-3 py-2" />
          </tr>
        </thead>
        <tbody>
          {adding && (
            <EditRow line={null} month={month} customers={customerList} parts={partList} onDone={done} onCancel={onAddDone} />
          )}
          {rows.map((line) =>
            editing === line.id ? (
              <EditRow key={line.id} line={line} month={month} customers={customerList} parts={partList} onDone={done} onCancel={() => setEditing(null)} />
            ) : (
              <tr key={line.id} className={`border-b border-line last:border-0 ${line.is_open ? "" : "text-ink-soft"}`}>
                <td className="whitespace-nowrap px-3 py-2 font-mono">
                  {formatDate(line.internal_dispatch_date)}
                  {line.internal_dispatch_date < today && line.is_open && (
                    <span className="ml-1.5 rounded-sm bg-warn-wash px-1 text-xs text-warn" title="The dispatch date has passed and the order is still open.">late</span>
                  )}
                </td>
                <td className="px-3 py-2"><span className="font-mono text-xs text-ink-soft">{line.customer_code}</span> {line.customer_name}</td>
                <td className="px-3 py-2">
                  <span className="whitespace-nowrap font-semibold">{line.part_number}</span> {line.part_name}
                  {line.grade_name && <span className="ml-1.5 text-xs text-ink-soft">{line.grade_name}</span>}
                  {line.warnings.length > 0 && <span className="ml-1.5 rounded-sm bg-warn-wash px-1 text-xs text-warn" title={line.warnings.join("\n")}>check</span>}
                </td>
                <td className="px-3 py-2 text-right font-mono">{formatNumber(line.dispatch_qty)}</td>
                <td className="px-2 py-1.5 text-right"><StockCell line={line} field="wip_qty" label="WIP stock" canEdit={canEdit} onSaved={stockSaved} /></td>
                <td className="px-2 py-1.5 text-right"><StockCell line={line} field="fg_qty" label="FG stock" canEdit={canEdit} onSaved={stockSaved} /></td>
                <td className="px-2 py-1.5 text-right"><StockCell line={line} field="actual_dispatched_qty" label="Dispatched" canEdit={canEdit} onSaved={stockSaved} /></td>
                <td className={`px-3 py-2 text-right font-mono font-semibold ${line.balance === 0 ? "text-ink-soft" : ""}`}>{formatNumber(line.balance)}</td>
                <td className="min-w-[15rem] px-3 py-2"><OrderStateBadge state={line.plan_state} reasons={line.plan_reasons} /></td>
                <td className="whitespace-nowrap px-3 py-2 font-mono">{line.actual_dispatch_date ? formatDate(line.actual_dispatch_date) : <span className="text-ink-soft">–</span>}</td>
                <td className="max-w-[12rem] truncate px-3 py-2 text-ink-soft" title={line.remarks}>{line.remarks || "–"}</td>
                <td className="px-3 py-2 text-right">
                  <div className="flex items-center justify-end gap-3">
                    <HistoryButton line={line} />
                    {canEdit && (
                      <button type="button" className="inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline" onClick={() => setEditing(line.id)} aria-label={`Edit ${line.part_number} for ${line.customer_code}`}>
                        Edit
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ),
          )}
        </tbody>
      </table>
      {lines.data.count > rows.length && (
        <p className="border-t border-line px-3 py-2 text-sm text-ink-soft">Showing the first {rows.length} of {lines.data.count} orders. Narrow the filters to see the rest.</p>
      )}
    </div>
  );
}
