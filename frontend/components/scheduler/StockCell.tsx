"use client";

import { useRef, useState } from "react";

import { Popover } from "@/components/ui/Popover";
import { ApiError, fieldErrors, patch } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/format";
import type { OrderChange, ScheduleLine } from "@/lib/types";
import { useApi } from "@/lib/use-api";

export type StockField = "wip_qty" | "fg_qty" | "actual_dispatched_qty";

/** A stock quantity the planner keeps up to date: type a number, press Enter or leave the cell to save. */
export function StockCell({
  line,
  field,
  label,
  canEdit,
  onSaved,
}: {
  line: ScheduleLine;
  field: StockField;
  label: string;
  canEdit: boolean;
  onSaved: () => void;
}) {
  const stored = line[field] ?? 0;
  const [text, setText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const shown = text ?? String(stored);

  async function commit() {
    if (text === null) return;
    const next = text.trim() === "" ? 0 : Number(text);
    if (!Number.isInteger(next) || next < 0) {
      setError("Whole pieces, 0 or more.");
      return;
    }
    if (next === stored) {
      setText(null);
      setError(null);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await patch(`/schedule-lines/${line.id}`, { [field]: next });
      setText(null);
      onSaved();
    } catch (err) {
      const fe = fieldErrors(err);
      setError(fe[field] ?? (err instanceof ApiError ? err.message : "Could not save."));
    } finally {
      setBusy(false);
    }
  }

  if (!canEdit) return <span className="font-mono">{formatNumber(stored)}</span>;
  return (
    <div>
      <input
        aria-label={`${label} for ${line.part_number}, ${line.customer_code}`}
        type="number"
        min={0}
        step={1}
        inputMode="numeric"
        disabled={busy}
        aria-invalid={error ? true : undefined}
        className="field !min-h-8 !w-[5.5rem] !px-2 text-right font-mono text-sm"
        value={shown}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => void commit()}
        onKeyDown={(e) => {
          if (e.key === "Enter") (e.target as HTMLInputElement).blur();
          if (e.key === "Escape") {
            setText(null);
            setError(null);
          }
        }}
      />
      {error && <p role="alert" className="mt-0.5 max-w-[8rem] text-xs text-danger">{error}</p>}
    </div>
  );
}

/** Who changed this order's quantity, stock or status, when, and from what to what. */
export function HistoryButton({ line }: { line: ScheduleLine }) {
  const [open, setOpen] = useState(false);
  const anchor = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button
        ref={anchor}
        type="button"
        className="inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline"
        aria-expanded={open}
        aria-label={`History of ${line.part_number} for ${line.customer_code}`}
        onClick={() => setOpen((v) => !v)}
      >
        History
      </button>
      <Popover anchor={anchor} open={open} onClose={() => setOpen(false)} label="Changes to this order" matchWidth={false} className="w-[22rem] max-w-[calc(100vw-1rem)] p-3">
        {open && <HistoryList id={line.id} />}
      </Popover>
    </>
  );
}

function HistoryList({ id }: { id: number }) {
  const history = useApi<{ results: OrderChange[] }>(`/schedule-lines/${id}/history`);
  if (history.loading) return <p className="text-sm text-ink-soft">Loading…</p>;
  if (history.error) return <p className="text-sm text-danger">{history.error.message}</p>;
  const rows = history.data?.results ?? [];
  if (rows.length === 0) return <p className="text-sm text-ink-soft">No changes recorded yet.</p>;
  return (
    <ol className="max-h-72 space-y-2 overflow-y-auto text-sm">
      {rows.map((c, i) => (
        <li key={i} className="border-b border-line pb-2 last:border-0 last:pb-0">
          <p className="font-medium">
            {c.field}: <span className="font-mono">{c.old ?? "–"}</span> → <span className="font-mono">{c.new ?? "–"}</span>
          </p>
          <p className="text-xs text-ink-soft">{c.user} · {formatDateTime(c.at)}</p>
        </li>
      ))}
    </ol>
  );
}
