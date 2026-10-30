"use client";

import Link from "next/link";
import { useState } from "react";

import { ErrorState, LoadingState, PageHeader } from "@/components/States";
import { ScheduleGrid } from "@/components/scheduler/ScheduleGrid";
import { ApiError, post } from "@/lib/api";
import { formatNumber, formatTonnes, todayInIndia } from "@/lib/format";
import { useSession } from "@/lib/store";
import { LINE_STATUS_LABEL, type Customer, type Grade, type Page, type ScheduleSummary } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { Select } from "@/components/ui/Select";
import { DatePicker } from "@/components/ui/DatePicker";

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

function shift(month: string, by: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(Date.UTC(y, m - 1 + by, 1));
  return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, "0")}`;
}

const label = (month: string) => `${MONTHS[Number(month.slice(5)) - 1]} ${month.slice(0, 4)}`;

function Stat({ name, value, note }: { name: string; value: string; note?: string }) {
  return (
    <div className="min-w-[7rem] flex-1 border-l-[3px] border-line px-3 py-1">
      <dt className="text-xs text-ink-soft">{name}</dt>
      <dd className="font-display text-2xl font-semibold leading-tight">{value}</dd>
      {note && <p className="text-xs text-ink-soft">{note}</p>}
    </div>
  );
}

export default function SchedulerPage() {
  const role = useSession((s) => s.user!.role);
  const canEdit = role !== "viewer";
  const [month, setMonth] = useState(todayInIndia().slice(0, 7));
  const [customer, setCustomer] = useState("");
  const [grade, setGrade] = useState("");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [version, setVersion] = useState(0);
  const [adding, setAdding] = useState(false);
  const [copy, setCopy] = useState<"idle" | "confirm" | "busy">("idle");
  const [copyMessage, setCopyMessage] = useState<string | null>(null);

  const customers = useApi<Page<Customer>>("/customers?page_size=500");
  const grades = useApi<Page<Grade>>("/grades?page_size=500");

  const query = `${customer ? `&customer=${customer}` : ""}${grade ? `&grade=${grade}` : ""}${status ? `&status=${status}` : ""}${q ? `&q=${encodeURIComponent(q)}` : ""}`;
  const summary = useApi<ScheduleSummary>(`/schedule-lines/summary?month=${month}${query}&v=${version}`);

  async function copyPrevious() {
    setCopy("busy");
    setCopyMessage(null);
    try {
      const r = await post<{ created: number; skipped: number }>("/schedule-lines/copy-month", { from_month: shift(month, -1), to_month: month });
      setCopyMessage(r.created ? `Copied ${r.created} line${r.created > 1 ? "s" : ""} from ${label(shift(month, -1))}${r.skipped ? `; ${r.skipped} were already here.` : "."}` : r.skipped ? "Everything from last month is already here." : `${label(shift(month, -1))} has nothing to copy.`);
      setVersion((v) => v + 1);
    } catch (err) {
      setCopyMessage(err instanceof ApiError ? err.message : "Could not copy.");
    } finally {
      setCopy("idle");
    }
  }

  const s = summary.data;

  return (
    <>
      <PageHeader title="Monthly Scheduler" subtitle="What each customer needs, and the date you plan to dispatch it">
        {canEdit && (
          <div className="flex flex-wrap gap-2">
            <Link href="/scheduler/upload" className="btn btn-quiet">Upload Excel</Link>
            <button type="button" className="btn btn-primary" onClick={() => setAdding(true)} disabled={adding}>Add line</button>
          </div>
        )}
      </PageHeader>

      <div className="mb-4 flex flex-wrap items-end gap-x-4 gap-y-3">
        <div className="flex items-center gap-1" role="group" aria-label="Month">
          <button type="button" className="btn btn-quiet !min-h-10 !px-3" onClick={() => setMonth(shift(month, -1))} aria-label="Previous month">←</button>
          <label className="sr-only" htmlFor="month">Month</label>
          <DatePicker mode="month" id="month" className="field !min-h-10 !w-44" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} clearable={false} />
          <button type="button" className="btn btn-quiet !min-h-10 !px-3" onClick={() => setMonth(shift(month, 1))} aria-label="Next month">→</button>
        </div>
        <label className="text-sm">
          <span className="mb-1 block text-ink-soft">Customer</span>
          <Select className="field !min-h-10 !w-48" value={customer} onChange={(e) => setCustomer(e.target.value)}>
            <option value="">All customers</option>
            {customers.data?.results.map((c) => <option key={c.id} value={c.id}>{c.code} {c.name}</option>)}
          </Select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-ink-soft">Grade</span>
          <Select className="field !min-h-10 !w-36" value={grade} onChange={(e) => setGrade(e.target.value)}>
            <option value="">All grades</option>
            {grades.data?.results.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}
          </Select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-ink-soft">Status</span>
          <Select className="field !min-h-10 !w-36" value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">All statuses</option>
            {Object.entries(LINE_STATUS_LABEL).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
        </label>
        <label className="text-sm">
          <span className="mb-1 block text-ink-soft">Part</span>
          <input type="search" className="field !min-h-10 !w-44" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Number or name" />
        </label>
      </div>

      <section aria-label={`Totals for ${label(month)}`} className="mb-4">
        {summary.loading ? (
          <LoadingState label="Calculating totals" rows={1} />
        ) : summary.error || !s ? (
          <ErrorState message={summary.error?.message ?? "Could not load totals."} onRetry={summary.reload} />
        ) : (
          <dl className="flex flex-wrap gap-y-2">
            <Stat name="Lines" value={formatNumber(s.lines)} />
            <Stat name="Pieces" value={formatNumber(s.pieces)} />
            <Stat name="Weight" value={formatTonnes(s.tonnes * 1000)} note="casting weight × quantity" />
            <Stat name="Value" value={s.value == null ? "–" : `₹ ${formatNumber(s.value)}`} note={s.lines_without_price ? `${s.lines_without_price} line${s.lines_without_price > 1 ? "s" : ""} without a price` : undefined} />
          </dl>
        )}
      </section>

      {canEdit && (
        <div className="mb-4 flex flex-wrap items-center gap-3">
          {copy === "confirm" ? (
            <>
              <span className="text-sm">Copy {label(shift(month, -1))} into {label(month)}? Dates keep their day of the month.</span>
              <button type="button" className="btn btn-primary !min-h-9" onClick={copyPrevious}>Copy lines</button>
              <button type="button" className="btn btn-quiet !min-h-9" onClick={() => setCopy("idle")}>Cancel</button>
            </>
          ) : (
            <button type="button" className="btn btn-quiet !min-h-9" onClick={() => setCopy("confirm")} disabled={copy === "busy"}>
              {copy === "busy" ? "Copying…" : `Copy from ${label(shift(month, -1))}`}
            </button>
          )}
          {copyMessage && <span role="status" className="text-sm text-ink-soft">{copyMessage}</span>}
        </div>
      )}

      <ScheduleGrid
        key={`${month}-${query}`}
        month={month}
        query={query}
        version={version}
        canEdit={canEdit}
        adding={adding}
        onAddDone={() => setAdding(false)}
        onChanged={() => setVersion((v) => v + 1)}
      />
    </>
  );
}
