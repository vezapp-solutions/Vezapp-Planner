"use client";

import { useState } from "react";

import { SlideOver } from "@/components/SlideOver";
import { FormError, RecordForm, toPayload, type Draft, type FieldSpec } from "@/components/forms";
import { ApiError, fieldErrors, post } from "@/lib/api";
import { formatNumber } from "@/lib/format";
import type { Customer, Grade, Page, UnmatchedPart } from "@/lib/types";
import { useApi } from "@/lib/use-api";

function CreatePart({ part, onClose, onCreated }: { part: UnmatchedPart; onClose: () => void; onCreated: () => void }) {
  const number = part.part_number;
  const grades = useApi<Page<Grade>>("/grades?page_size=500");
  const customers = useApi<Page<Customer>>("/customers?page_size=500");
  const fromFile = customers.data?.results.find((c) => c.code.toLowerCase() === part.customer_code.toLowerCase());
  const fields: FieldSpec[] = [
    { key: "part_number", label: "Part number", type: "text", required: true },
    { key: "name", label: "Part name", type: "text", required: true },
    {
      key: "grade",
      label: "Material grade",
      type: "select",
      required: true,
      options: (grades.data?.results ?? []).map((g) => ({ value: g.id, label: g.name })),
      hint: "One heat is one grade, so the grade decides which castings share a heat.",
    },
    { key: "casting_weight_kg", label: "Casting weight", type: "number", unit: "kg", step: "0.001", min: 0, required: true },
    { key: "pouring_weight_per_mould_kg", label: "Pouring weight per mould", type: "number", unit: "kg", step: "0.001", min: 0, required: true, hint: "Castings in the mould plus runners and risers." },
    { key: "cavities_per_mould", label: "Castings per mould", type: "number", step: "1", min: 1, required: true },
    {
      key: "customer",
      label: "Default customer",
      type: "select",
      blankLabel: "None",
      options: (customers.data?.results ?? []).map((c) => ({ value: c.id, label: `${c.code} ${c.name}` })),
      hint: "Orders in the file with no customer use this one.",
    },
  ];
  const [draft, setDraft] = useState<Draft>({ part_number: number, name: "", grade: "", casting_weight_kg: "", pouring_weight_per_mould_kg: "", cavities_per_mould: "1", customer: "" });
  const chosen = draft.customer !== "" ? String(draft.customer) : fromFile ? String(fromFile.id) : "";
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    setBusy(true);
    setErrors({});
    setMessage(null);
    try {
      const { customer, ...rest } = toPayload({ ...draft, customer: chosen }, fields);
      await post("/parts", { ...rest, ...(customer ? { customer_links: [{ customer, is_default: true }] } : {}) });
      onCreated();
    } catch (err) {
      const fe = fieldErrors(err);
      setErrors(fe);
      setMessage(err instanceof ApiError && !Object.keys(fe).length ? err.message : "Please fix the highlighted fields.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <SlideOver
      title="Create part"
      subtitle="Only what planning needs. Add the route and machines afterwards in Masters, Parts and routes."
      onClose={onClose}
      footer={
        <>
          <button type="button" className="btn btn-primary" onClick={save} disabled={busy}>{busy ? "Creating…" : "Create part"}</button>
          <button type="button" className="btn btn-quiet" onClick={onClose}>Cancel</button>
        </>
      }
    >
      <div className="space-y-4">
        <FormError message={message} />
        <RecordForm fields={fields} draft={{ ...draft, customer: chosen }} setDraft={setDraft} errors={errors} idPrefix="new-part" />
      </div>
    </SlideOver>
  );
}

/**
 * Parts in the file that are not in the Part Master. The rest of the file still loads; each part here can
 * be created on the spot (then the file is checked again), or the rows can be fixed in Excel and re-uploaded.
 */
export function UnmatchedParts({ parts, onCreated, children }: { parts: UnmatchedPart[]; onCreated: () => void; children?: React.ReactNode }) {
  const [creating, setCreating] = useState<string | null>(null);
  if (parts.length === 0) return null;
  return (
    <section aria-label="Parts that are not in the Part Master" className="rounded-md border border-warn bg-warn-wash/50 p-4">
      <h3 className="font-display text-lg font-semibold">
        {parts.length} part{parts.length === 1 ? "" : "s"} not in the Part Master
      </h3>
      <p className="mt-1 text-sm">
        The other rows load as normal. Create each part below and the file is checked again, or fix the part numbers in Excel and upload again.
      </p>
      <ul className="mt-3 divide-y divide-line rounded-md border border-line bg-surface">
        {parts.map((p) => (
          <li key={p.part_number} className="flex flex-wrap items-center justify-between gap-3 px-3 py-2">
            <span>
              <span className="font-mono font-medium">{p.part_number}</span>
              <span className="ml-2 text-sm text-ink-soft">
                {p.rows.length} row{p.rows.length === 1 ? "" : "s"} (row {p.rows.slice(0, 6).join(", ")}
                {p.rows.length > 6 ? ", …" : ""}) · {formatNumber(p.qty)} pieces
              </span>
            </span>
            <button type="button" className="btn btn-quiet !min-h-9" onClick={() => setCreating(p.part_number)}>Create part</button>
          </li>
        ))}
      </ul>
      {children && <div className="mt-3">{children}</div>}
      {creating && (
        <CreatePart
          part={parts.find((p) => p.part_number === creating) ?? parts[0]}
          onClose={() => setCreating(null)}
          onCreated={() => {
            setCreating(null);
            onCreated();
          }}
        />
      )}
    </section>
  );
}
