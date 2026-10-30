"use client";

import { useMemo, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/States";
import { ApiError, del, fieldErrors, patch, post } from "@/lib/api";
import { formatDate, formatNumber, formatTonnes, todayInIndia } from "@/lib/format";
import { LINE_STATUS_LABEL, type Customer, type LineStatus, type Page, type Part, type ScheduleLine } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { Select } from "@/components/ui/Select";
import { DatePicker } from "@/components/ui/DatePicker";

interface Draft {
  customer: string;
  part: string;
  dispatch_qty: string;
  internal_dispatch_date: string;
  actual_dispatch_date: string;
  actual_dispatched_qty: string;
  status: LineStatus;
  remarks: string;
}

const STATUS_STYLE: Record<LineStatus, string> = {
  planned: "",
  in_progress: "text-link",
  dispatched: "text-ok",
  cancelled: "text-ink-soft line-through",
};

function toDraft(line: ScheduleLine | null, month: string): Draft {
  const today = todayInIndia();
  return {
    customer: line ? String(line.customer) : "",
    part: line ? String(line.part) : "",
    dispatch_qty: line ? String(line.dispatch_qty) : "",
    internal_dispatch_date: line ? line.internal_dispatch_date : today.startsWith(month) ? today : `${month}-01`,
    actual_dispatch_date: line?.actual_dispatch_date ?? "",
    actual_dispatched_qty: line?.actual_dispatched_qty != null ? String(line.actual_dispatched_qty) : "",
    status: line?.status ?? "planned",
    remarks: line?.remarks ?? "",
  };
}

function payload(d: Draft) {
  return {
    customer: Number(d.customer) || null,
    part: Number(d.part) || null,
    dispatch_qty: d.dispatch_qty === "" ? null : Number(d.dispatch_qty),
    internal_dispatch_date: d.internal_dispatch_date || null,
    actual_dispatch_date: d.actual_dispatch_date || null,
    actual_dispatched_qty: d.actual_dispatched_qty === "" ? null : Number(d.actual_dispatched_qty),
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
        <DatePicker aria-label="Internal dispatch date" className={`${input} w-36`} value={d.internal_dispatch_date} onChange={(e) => set({ internal_dispatch_date: e.target.value })} />
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
        <input aria-label="Dispatch quantity" type="number" min={1} step={1} inputMode="numeric" className={`${input} w-24 font-mono`} value={d.dispatch_qty} onChange={(e) => set({ dispatch_qty: e.target.value })} />
      </Cell>
      <td className="px-2 py-1.5 text-right font-mono text-ink-soft">–</td>
      <Cell error={errors.actual_dispatch_date}>
        <DatePicker aria-label="Actual dispatch date" className={`${input} w-36`} value={d.actual_dispatch_date} onChange={(e) => set({ actual_dispatch_date: e.target.value, status: e.target.value && (d.status === "planned" || d.status === "in_progress") ? "dispatched" : !e.target.value && d.status === "dispatched" ? "planned" : d.status })} clearable={false} />
      </Cell>
      <Cell error={errors.actual_dispatched_qty}>
        <input aria-label="Actual dispatched quantity" type="number" min={1} step={1} inputMode="numeric" className={`${input} w-24 font-mono`} value={d.actual_dispatched_qty} onChange={(e) => set({ actual_dispatched_qty: e.target.value })} />
      </Cell>
      <Cell error={errors.status}>
        <Select aria-label="Status" className={`${input} w-32`} value={d.status} onChange={(e) => set({ status: e.target.value as LineStatus })}>
          {Object.entries(LINE_STATUS_LABEL).map(([value, label]) => (
            <option key={value} value={value}>{label}</option>
          ))}
        </Select>
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

  if (rows.length === 0 && !adding) {
    return (
      <EmptyState title="No dispatch lines in this month">
        {canEdit
          ? "Add a line, copy last month's schedule, or upload an Excel file. Each line is a customer, a part, a quantity and the date you plan to dispatch it."
          : "Nothing has been scheduled for this month yet."}
      </EmptyState>
    );
  }

  return (
    <div className="panel overflow-x-auto">
      <table className="w-full min-w-[68rem] text-left text-sm">
        <thead className="border-b border-line bg-sunken text-ink-soft">
          <tr>
            {["Internal date", "Customer", "Part", "Qty", "Tonnes", "Actual date", "Actual qty", "Status", "Remarks"].map((h, i) => (
              <th key={h} scope="col" className={`px-3 py-2 font-medium ${i === 3 || i === 4 ? "text-right" : ""}`}>{h}</th>
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
              <tr key={line.id} className="border-b border-line last:border-0 hover:bg-sunken/60">
                <td className="whitespace-nowrap px-3 py-2 font-mono">
                  {formatDate(line.internal_dispatch_date)}
                  {line.internal_dispatch_date < today && (line.status === "planned" || line.status === "in_progress") && (
                    <span className="ml-1.5 rounded-sm bg-warn-wash px-1 text-xs text-warn" title="The internal date has passed and nothing is recorded as dispatched.">late</span>
                  )}
                </td>
                <td className="px-3 py-2"><span className="font-mono text-xs text-ink-soft">{line.customer_code}</span> {line.customer_name}</td>
                <td className="px-3 py-2">
                  <span className="font-medium">{line.part_number}</span> {line.part_name}
                  {line.grade_name && <span className="ml-1.5 text-xs text-ink-soft">{line.grade_name}</span>}
                  {line.warnings.length > 0 && <span className="ml-1.5 rounded-sm bg-warn-wash px-1 text-xs text-warn" title={line.warnings.join("\n")}>check</span>}
                </td>
                <td className="px-3 py-2 text-right font-mono">{formatNumber(line.dispatch_qty)}</td>
                <td className="px-3 py-2 text-right font-mono text-ink-soft">{formatTonnes(line.tonnes * 1000)}</td>
                <td className="whitespace-nowrap px-3 py-2 font-mono">{line.actual_dispatch_date ? formatDate(line.actual_dispatch_date) : <span className="text-ink-soft">–</span>}</td>
                <td className="px-3 py-2 font-mono">{line.actual_dispatched_qty != null ? formatNumber(line.actual_dispatched_qty) : <span className="text-ink-soft">–</span>}</td>
                <td className={`px-3 py-2 ${STATUS_STYLE[line.status]}`}>{LINE_STATUS_LABEL[line.status]}</td>
                <td className="max-w-[14rem] truncate px-3 py-2 text-ink-soft" title={line.remarks}>{line.remarks || "–"}</td>
                <td className="px-3 py-2 text-right">
                  {canEdit && (
                    <button type="button" className="inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline" onClick={() => setEditing(line.id)} aria-label={`Edit ${line.part_number} for ${line.customer_code}`}>
                      Edit
                    </button>
                  )}
                </td>
              </tr>
            ),
          )}
        </tbody>
      </table>
      {lines.data.count > rows.length && (
        <p className="border-t border-line px-3 py-2 text-sm text-ink-soft">Showing the first {rows.length} of {lines.data.count} lines. Narrow the filters to see the rest.</p>
      )}
    </div>
  );
}
