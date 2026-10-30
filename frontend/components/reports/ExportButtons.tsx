"use client";

import { useState } from "react";

import { FormErrorLine } from "@/components/States";
import { ApiError, download } from "@/lib/api";
import { DatePicker } from "@/components/ui/DatePicker";

/** PDF and Excel downloads of a report, with the same filters as the screen. */
export function ExportButtons({ path, filename, disabled = false }: { path: string; filename: string; disabled?: boolean }) {
  const [busy, setBusy] = useState<"pdf" | "xlsx" | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function get(output: "pdf" | "xlsx") {
    setBusy(output);
    setError(null);
    try {
      const joiner = path.includes("?") ? "&" : "?";
      await download(`${path}${joiner}output=${output}`, `${filename}.${output}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not download.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <button type="button" className="btn btn-quiet !min-h-9" onClick={() => void get("pdf")} disabled={disabled || busy !== null}>
          {busy === "pdf" ? "Preparing…" : "Download PDF"}
        </button>
        <button type="button" className="btn btn-quiet !min-h-9" onClick={() => void get("xlsx")} disabled={disabled || busy !== null}>
          {busy === "xlsx" ? "Preparing…" : "Download Excel"}
        </button>
      </div>
      {error && <FormErrorLine message={error} />}
    </div>
  );
}

/** A from and to date pair, and an optional customer box. */
export function DateFilters({
  from,
  to,
  onFrom,
  onTo,
  customer,
  onCustomer,
}: {
  from: string;
  to: string;
  onFrom: (v: string) => void;
  onTo: (v: string) => void;
  customer?: string;
  onCustomer?: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <label className="text-sm">
        <span className="mb-1 block text-ink-soft">From</span>
        <DatePicker className="field !min-h-10 !w-44" value={from} onChange={(e) => onFrom(e.target.value)} />
      </label>
      <label className="text-sm">
        <span className="mb-1 block text-ink-soft">To</span>
        <DatePicker className="field !min-h-10 !w-44" value={to} onChange={(e) => onTo(e.target.value)} />
      </label>
      {onCustomer && (
        <label className="text-sm">
          <span className="mb-1 block text-ink-soft">Customer code</span>
          <input className="field !min-h-10 !w-40" value={customer ?? ""} onChange={(e) => onCustomer(e.target.value.trim().toUpperCase())} placeholder="All customers" />
        </label>
      )}
    </div>
  );
}
