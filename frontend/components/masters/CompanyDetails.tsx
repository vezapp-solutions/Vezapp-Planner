"use client";

import { useState } from "react";

import { CrudScreen } from "@/components/CrudScreen";
import { Panel } from "@/components/Panel";
import { ErrorState, LoadingState } from "@/components/States";
import { FormError, RecordForm, toDraft, toPayload, type Draft, type FieldSpec } from "@/components/forms";
import { ApiError, fieldErrors, patch } from "@/lib/api";
import { useSession } from "@/lib/store";
import type { Company, Page, Plant } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const COMPANY_FIELDS: FieldSpec[] = [
  { key: "name", label: "Company name", type: "text", required: true },
  { key: "gstin", label: "GSTIN", type: "text", placeholder: "24ABCDE1234F1Z5", hint: "15 characters." },
  { key: "address", label: "Address", type: "textarea" },
];

const PLANT_FIELDS: FieldSpec[] = [
  { key: "name", label: "Plant name", type: "text", required: true },
  { key: "address", label: "Address", type: "textarea" },
  { key: "is_active", label: "In use", type: "checkbox" },
];

function CompanyForm({ company, canEdit }: { company: Company; canEdit: boolean }) {
  const [draft, setDraft] = useState<Draft>(() => toDraft(company as unknown as Record<string, unknown>, COMPANY_FIELDS));
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
      await patch(`/companies/${company.id}`, toPayload(draft, COMPANY_FIELDS));
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
      <RecordForm fields={COMPANY_FIELDS} draft={draft} setDraft={(d) => { setSaved(false); setDraft(d); }} errors={errors} readOnly={!canEdit} idPrefix="company" />
      {canEdit && (
        <div className="flex items-center gap-3">
          <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>
            {busy ? "Saving…" : "Save company details"}
          </button>
          {saved && <span role="status" className="text-sm text-ok">Saved.</span>}
        </div>
      )}
    </div>
  );
}

export function CompanyDetails({ canEdit }: { canEdit: boolean }) {
  const { user, actingCompanyId } = useSession();
  const companyId = user?.company?.id ?? actingCompanyId;
  const company = useApi<Page<Company>>("/companies?page_size=500");
  const mine = company.data?.results.find((c) => c.id === companyId);

  return (
    <div className="space-y-6">
      <Panel title="Company details">
        {company.loading ? (
          <LoadingState label="Loading company" />
        ) : company.error || !mine ? (
          <ErrorState message={company.error?.message ?? "Company not found."} onRetry={company.reload} />
        ) : (
          <CompanyForm company={mine} canEdit={canEdit} />
        )}
        <p className="mt-4 text-xs text-ink-soft">A company logo of your own is not supported yet; printed plans carry the Vezapp logo.</p>
      </Panel>
      <Panel title="Plants">
        <CrudScreen<Plant>
          path="/plants"
          noun="plant"
          fields={PLANT_FIELDS}
          canEdit={canEdit}
          defaults={{ is_active: true }}
          columns={[
            { header: "Plant", cell: (p) => p.name },
            { header: "Address", cell: (p) => p.address || <span className="text-ink-soft">–</span> },
            { header: "Status", cell: (p) => (p.is_active ? "In use" : <span className="text-ink-soft">Not in use</span>) },
          ]}
        />
      </Panel>
    </div>
  );
}
