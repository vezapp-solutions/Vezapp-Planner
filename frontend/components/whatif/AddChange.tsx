"use client";

import { useState } from "react";

import { FormError, RecordForm, toDraft, toPayload, type Draft, type FieldSpec } from "@/components/forms";
import { LoadingState } from "@/components/States";
import { ApiError, fieldErrors, post } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { CHANGE_KIND_LABEL, type ChangeKind, type Page, type Resource, type ScheduleLine, type Shift } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const KINDS = Object.keys(CHANGE_KIND_LABEL) as ChangeKind[];

function fieldsFor(kind: ChangeKind, resources: Resource[], lines: ScheduleLine[], shifts: Shift[]): FieldSpec[] {
  const resourceOptions = resources.map((r) => ({ value: r.id, label: `${r.code} · ${r.name}` }));
  const lineOptions = lines.map((l) => ({
    value: l.id,
    label: `${l.part_number} for ${l.customer_code}, ${l.dispatch_qty.toLocaleString("en-IN")} pcs, due ${formatDate(l.internal_dispatch_date)}`,
  }));
  const named = { key: "resources", label: "Resources", type: "multi", options: resourceOptions, hint: "Leave all unticked for every resource." } as const;
  const range: FieldSpec[] = [
    { key: "day_from", label: "From day", type: "date", required: true },
    { key: "day_to", label: "To day", type: "date", required: true, hint: "The same day for a single day." },
  ];
  switch (kind) {
    case "block_resource":
      return [
        { key: "resource", label: "Resource", type: "select", required: true, options: resourceOptions, wide: true },
        { key: "start", label: "Blocked from", type: "datetime", required: true },
        { key: "end", label: "Blocked until", type: "datetime", required: true },
        { key: "reason", label: "Reason", type: "text", placeholder: "Lining change", wide: true, hint: "Kept on the blocked period if you apply this." },
      ];
    case "change_qty":
      return [
        { key: "line", label: "Schedule line", type: "select", required: true, options: lineOptions, wide: true },
        { key: "qty", label: "New quantity", type: "number", unit: "pcs", min: 1, required: true },
      ];
    case "change_date":
      return [
        { key: "line", label: "Schedule line", type: "select", required: true, options: lineOptions, wide: true },
        { key: "date", label: "New internal dispatch date", type: "date", required: true },
      ];
    case "extra_shift":
      return [
        ...range,
        { key: "name", label: "Shift name", type: "text", required: true, placeholder: "Sunday day shift" },
        { key: "start_time", label: "Starts", type: "time", required: true },
        { key: "end_time", label: "Ends", type: "time", required: true },
        { key: "break_minutes", label: "Break", type: "number", unit: "min", min: 0 },
        named,
      ];
    case "overtime":
      return [
        ...range,
        { key: "minutes", label: "Extra minutes per shift", type: "number", unit: "min", min: 1, required: true },
        { key: "shift", label: "Only in this shift", type: "select", options: shifts.map((s) => ({ value: s.id, label: s.name })), blankLabel: "Every shift" },
        named,
      ];
  }
}

/** Add one change to a draft scenario. The server checks every value and says what is wrong. */
export function AddChange({ scenarioId, onAdded }: { scenarioId: number; onAdded: () => void }) {
  const resources = useApi<Page<Resource>>("/resources?page_size=500");
  const lines = useApi<Page<ScheduleLine>>("/schedule-lines?page_size=500&status=planned");
  const inProgress = useApi<Page<ScheduleLine>>("/schedule-lines?page_size=500&status=in_progress");
  const shifts = useApi<Page<Shift>>("/shifts?page_size=500");

  const [kind, setKind] = useState<ChangeKind>("block_resource");
  const [draft, setDraft] = useState<Draft>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (resources.loading || lines.loading || inProgress.loading || shifts.loading) return <LoadingState label="Loading resources and lines" rows={2} />;

  const allLines = [...(lines.data?.results ?? []), ...(inProgress.data?.results ?? [])];
  const fields = fieldsFor(kind, resources.data?.results.filter((r) => r.status !== "inactive") ?? [], allLines, shifts.data?.results ?? []);

  function pick(next: ChangeKind) {
    setKind(next);
    setDraft({});
    setErrors({});
    setFormError(null);
  }

  async function add() {
    setBusy(true);
    setErrors({});
    setFormError(null);
    try {
      await post(`/scenarios/${scenarioId}/changes`, { kind, params: toPayload(draft, fields) });
      pick(kind);
      onAdded();
    } catch (err) {
      const fe = fieldErrors(err);
      const inner = parseParams(fe.params);
      setErrors(inner);
      const known = new Set(fields.map((f) => f.key));
      const stray = Object.entries(inner).filter(([k]) => !known.has(k));
      setFormError(
        stray.length
          ? stray.map(([, v]) => v).join(" ")
          : Object.keys(inner).length
            ? "Please fix the highlighted fields."
            : err instanceof ApiError
              ? (fe.detail ?? err.message)
              : "Could not reach the server.",
      );
    } finally {
      setBusy(false);
    }
  }

  const shown: Draft = { ...toDraft(null, fields, kind === "extra_shift" ? { break_minutes: "0" } : {}), ...draft };

  return (
    <div className="space-y-3">
      <label className="block text-sm font-medium">
        Kind of change
        <select className="field mt-1 sm:max-w-xs" value={kind} onChange={(e) => pick(e.target.value as ChangeKind)}>
          {KINDS.map((k) => <option key={k} value={k}>{CHANGE_KIND_LABEL[k]}</option>)}
        </select>
      </label>
      <FormError message={formError} />
      <RecordForm fields={fields} draft={shown} setDraft={setDraft} errors={errors} idPrefix={`chg-${kind}`} />
      <button type="button" className="btn btn-primary" onClick={add} disabled={busy}>
        {busy ? "Adding…" : "Add to scenario"}
      </button>
    </div>
  );
}

/** The server sends field errors for the change's own values as a JSON object under `params`. */
function parseParams(text: string | undefined): Record<string, string> {
  if (!text) return {};
  try {
    const parsed = JSON.parse(text) as Record<string, unknown>;
    return Object.fromEntries(Object.entries(parsed).map(([k, v]) => [k, Array.isArray(v) ? v.map(String).join(" ") : String(v)]));
  } catch {
    return {};
  }
}
