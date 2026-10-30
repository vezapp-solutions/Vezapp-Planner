"use client";

import { useState } from "react";

import { ErrorState, LoadingState } from "@/components/States";
import { FormError } from "@/components/forms";
import { ApiError, del, fieldErrors, post } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { Downtime, Page } from "@/lib/types";
import { useApi } from "@/lib/use-api";

/** Blocked periods (maintenance, breakdown, lining change). They remove capacity from the plan. */
export function DowntimeManager({ resourceId, canEdit, onChanged }: { resourceId: number; canEdit: boolean; onChanged: () => void }) {
  const list = useApi<Page<Downtime>>(`/downtimes?resource=${resourceId}&page_size=200`);
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function add() {
    setBusy(true);
    setError(null);
    try {
      await post("/downtimes", {
        resource: resourceId,
        start_at: new Date(from).toISOString(),
        end_at: new Date(to).toISOString(),
        reason,
      });
      setFrom("");
      setTo("");
      setReason("");
      list.reload();
      onChanged();
    } catch (err) {
      const fe = fieldErrors(err);
      setError(Object.values(fe).join(" ") || (err instanceof ApiError ? err.message : "Could not add."));
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: number) {
    await del(`/downtimes/${id}`);
    list.reload();
    onChanged();
  }

  return (
    <section aria-labelledby="down-title" className="space-y-2">
      <h3 id="down-title" className="font-display text-lg font-semibold">Downtime</h3>
      {list.loading ? (
        <LoadingState label="Loading downtime" rows={1} />
      ) : list.error ? (
        <ErrorState message={list.error.message} onRetry={list.reload} />
      ) : list.data?.results.length ? (
        <ul className="divide-y divide-line rounded-md border border-line text-sm">
          {list.data.results.map((d) => (
            <li key={d.id} className="flex items-center justify-between gap-3 px-3 py-2">
              <span>
                <span className="font-mono">{formatDateTime(d.start_at)} → {formatDateTime(d.end_at)}</span>
                {d.reason && <span className="text-ink-soft"> · {d.reason}</span>}
              </span>
              {canEdit && (
                <button type="button" className="inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline" onClick={() => void remove(d.id)}>
                  Remove
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-ink-soft">No blocked periods.</p>
      )}

      {canEdit && (
        <div className="space-y-2 rounded-md border border-dashed border-line p-3">
          <FormError message={error} />
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="text-sm font-medium">
              From
              <input type="datetime-local" className="field mt-1" value={from} onChange={(e) => setFrom(e.target.value)} />
            </label>
            <label className="text-sm font-medium">
              To
              <input type="datetime-local" className="field mt-1" value={to} onChange={(e) => setTo(e.target.value)} />
            </label>
          </div>
          <label className="block text-sm font-medium">
            Reason
            <input className="field mt-1" value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Lining change" />
          </label>
          <button type="button" className="btn btn-quiet" onClick={add} disabled={busy || !from || !to}>
            {busy ? "Adding…" : "Add blocked period"}
          </button>
        </div>
      )}
    </section>
  );
}
