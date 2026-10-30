"use client";

import { useState } from "react";

import { Panel } from "@/components/Panel";
import { ErrorState, LoadingState } from "@/components/States";
import { FormError, RecordForm, toDraft, toPayload, type Draft, type FieldSpec } from "@/components/forms";
import { ApiError, fieldErrors, patch } from "@/lib/api";
import type { CompanySettings, OperationType, Page } from "@/lib/types";
import { useApi } from "@/lib/use-api";

function Form({ settings, ops, canEdit }: { settings: CompanySettings; ops: OperationType[]; canEdit: boolean }) {
  const fields: FieldSpec[] = [
    { key: "horizon_days", label: "Planning horizon", type: "number", unit: "days", step: "1", min: 1, hint: "How far ahead plans are calculated. Default 30." },
    { key: "default_bucket", label: "Default planning bucket", type: "select", options: [{ value: "shift", label: "Shift" }, { value: "day", label: "Day" }] },
    {
      key: "rejection_booked_at",
      label: "Rejection is booked after",
      type: "select",
      options: ops.filter((o) => o.is_active).map((o) => ({ value: o.code, label: o.name })),
      hint: "Operations up to and including this one are planned for the extra pieces that rejection will scrap.",
    },
    { key: "melt_loss_default_pct", label: "Melt loss when a part has none", type: "number", unit: "%", step: "0.01", min: 0 },
    {
      key: "flow_mode",
      label: "How a lot moves between operations",
      type: "select",
      options: [
        { value: "progressive", label: "Pieces flow on as the previous operation releases them" },
        { value: "whole_lot", label: "Each operation waits for the whole lot" },
      ],
      hint: "Pieces flow on gives earlier, more realistic dispatch dates.",
    },
    { key: "pour_same_shift", label: "Pour in the same shift as moulding", type: "checkbox", hint: "When on, the furnace limits how many moulds are made in a shift." },
  ];
  const [draft, setDraft] = useState<Draft>(() => toDraft(settings as unknown as Record<string, unknown>, fields));
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setErrors({});
    setMessage(null);
    setSaved(false);
    try {
      await patch("/company/settings", toPayload(draft, fields));
      setSaved(true);
    } catch (err) {
      setErrors(fieldErrors(err));
      setMessage(err instanceof ApiError ? "Please fix the highlighted fields." : "Could not save.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-4">
      <FormError message={message} />
      <RecordForm fields={fields} draft={draft} setDraft={(d) => { setSaved(false); setDraft(d); }} errors={errors} readOnly={!canEdit} idPrefix="settings" />
      {canEdit && (
        <div className="flex items-center gap-3">
          <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>
            {busy ? "Saving…" : "Save settings"}
          </button>
          {saved && <span role="status" className="text-sm text-ok">Saved.</span>}
        </div>
      )}
    </div>
  );
}

export function PlanningSettings({ canEdit }: { canEdit: boolean }) {
  const settings = useApi<CompanySettings>("/company/settings");
  const ops = useApi<Page<OperationType>>("/operation-types?page_size=500");
  return (
    <Panel title="Planning settings">
      {settings.loading || ops.loading ? (
        <LoadingState label="Loading settings" />
      ) : settings.error || ops.error || !settings.data || !ops.data ? (
        <ErrorState message={(settings.error ?? ops.error)?.message ?? "Could not load."} onRetry={() => { settings.reload(); ops.reload(); }} />
      ) : (
        <Form settings={settings.data} ops={ops.data.results} canEdit={canEdit} />
      )}
    </Panel>
  );
}
