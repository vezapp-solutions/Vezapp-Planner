"use client";

import Link from "next/link";
import { useState } from "react";

import { CrudScreen } from "@/components/CrudScreen";
import { WarnBadge } from "@/components/Explain";
import { Panel } from "@/components/Panel";
import { LoadingState, PageHeader } from "@/components/States";
import type { FieldSpec } from "@/components/forms";
import { formatNumber } from "@/lib/format";
import { canEditMasters } from "@/lib/nav";
import { useSession } from "@/lib/store";
import type { Customer, Grade, Page, Part } from "@/lib/types";
import { useApi } from "@/lib/use-api";

const GRADE_FIELDS: FieldSpec[] = [
  { key: "name", label: "Grade", type: "text", required: true, placeholder: "GG25" },
  { key: "description", label: "Description", type: "text" },
];

export default function PartsPage() {
  const canEdit = canEditMasters(useSession((s) => s.user!.role));
  const grades = useApi<Page<Grade>>("/grades?page_size=500");
  const customers = useApi<Page<Customer>>("/customers?page_size=500");
  const [q, setQ] = useState("");

  if (grades.loading || customers.loading) return <LoadingState label="Loading parts" rows={4} />;
  const gradeList = grades.data?.results ?? [];
  const customerList = customers.data?.results ?? [];

  const fields: FieldSpec[] = [
    { key: "part_number", label: "Part number", type: "text", required: true, placeholder: "H-120" },
    { key: "name", label: "Part name", type: "text", required: true, placeholder: "Housing" },
    { key: "grade", label: "Grade", type: "select", blankLabel: "Not set", options: gradeList.map((g) => ({ value: g.id, label: g.name })), hint: "Only one grade can be in a heat, so parts of the same grade may share one." },
    { key: "material_grade", label: "Grade as on the drawing", type: "text" },
    { key: "casting_weight_kg", label: "Casting weight", type: "number", unit: "kg", step: "0.001", required: true, hint: "Per piece." },
    { key: "finished_weight_kg", label: "Finished weight", type: "number", unit: "kg", step: "0.001" },
    { key: "pouring_weight_per_mould_kg", label: "Pouring weight per mould", type: "number", unit: "kg", step: "0.001", required: true, hint: "Metal poured into one mould, runners and risers included." },
    { key: "cavities_per_mould", label: "Pieces per mould (cavities)", type: "number", step: "1", min: 1, required: true },
    { key: "cores_per_mould", label: "Cores per mould", type: "number", step: "1", min: 0 },
    { key: "rejection_pct", label: "Expected rejection", type: "number", unit: "%", step: "0.01", min: 0 },
    { key: "pattern_number", label: "Pattern number", type: "text" },
    { key: "drawing_number", label: "Drawing number", type: "text" },
    { key: "drawing_revision", label: "Drawing revision", type: "text" },
    { key: "selling_price", label: "Selling price per piece", type: "number", unit: "₹", step: "0.01", hint: "Optional. Used for value insights." },
    { key: "description", label: "Description", type: "textarea" },
    {
      key: "customer_ids",
      label: "Supplied to",
      type: "multi",
      options: customerList.map((c) => ({ value: c.id, label: `${c.code} ${c.name}` })),
      hint: customerList.length ? "A part can be supplied to more than one customer." : "Add customers first.",
    },
    {
      key: "default_customer",
      label: "Default customer",
      type: "select",
      blankLabel: "First one ticked",
      options: customerList.map((c) => ({ value: c.id, label: c.name })),
      showIf: (d) => (d.customer_ids as number[]).length > 1,
    },
    { key: "is_active", label: "Active part", type: "checkbox" },
  ];

  return (
    <>
      <PageHeader title="Parts and routes" subtitle="Part data, and the operation route each part follows" />
      <div className="space-y-6">
        <CrudScreen<Part>
          path="/parts"
          query={q ? `&q=${encodeURIComponent(q)}` : ""}
          key={q}
          noun="part"
          fields={fields}
          canEdit={canEdit}
          wide
          defaults={{ cavities_per_mould: "1", cores_per_mould: "0", rejection_pct: "0", is_active: true }}
          warnings={(p) => p.warnings}
          subtitle={(p) => `${p.part_number} · ${p.name}`}
          emptyHint="Each part needs its weights and mould data here. Its operation route is set on the next screen."
          toolbar={
            <label className="flex items-center gap-2 text-sm">
              Search
              <input type="search" className="field !min-h-9 !w-56" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Part number or name" />
            </label>
          }
          extraDraft={(row) => ({
            customer_ids: row ? row.customers.map((c) => c.id) : [],
            default_customer: row ? String(row.customers.find((c) => c.is_default)?.id ?? "") : "",
          })}
          adjustPayload={(payload) => {
            // Customer links travel with the part. The two helper fields become one list.
            const ids = (payload.customer_ids as number[]) ?? [];
            const chosen = Number(payload.default_customer);
            payload.customer_links = ids.map((id, i) => ({
              customer: id,
              is_default: ids.includes(chosen) ? id === chosen : i === 0,
            }));
            delete payload.customer_ids;
            delete payload.default_customer;
            return payload;
          }}
          renderExtra={({ row }) =>
            row && (
              <p className="border-t border-line pt-4 text-sm">
                <Link className="font-medium inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline" href={`/masters/parts/${row.id}`}>
                  Open operation route →
                </Link>
              </p>
            )
          }
          columns={[
            { header: "Part", cell: (p) => <>{p.part_number}<WarnBadge issues={p.warnings} /></> },
            { header: "Name", cell: (p) => p.name },
            { header: "Grade", cell: (p) => p.grade_name ?? <span className="text-ink-soft">–</span> },
            { header: "Customer", cell: (p) => p.customers.find((c) => c.is_default)?.name ?? <span className="text-ink-soft">–</span> },
            { header: "Casting", cell: (p) => <span className="font-mono">{formatNumber(Number(p.casting_weight_kg), 3)} kg</span>, className: "text-right" },
            { header: "Route", cell: (p) => <Link className="inline-flex min-h-6 items-center text-link underline-offset-2 hover:underline" href={`/masters/parts/${p.id}`}>Route</Link> },
          ]}
        />

        <Panel title="Grades" note="metal grades used by parts">
          <CrudScreen<Grade>
            path="/grades"
            noun="grade"
            fields={GRADE_FIELDS}
            canEdit={canEdit}
            onChanged={grades.reload}
            columns={[
              { header: "Grade", cell: (g) => g.name },
              { header: "Description", cell: (g) => g.description || <span className="text-ink-soft">–</span> },
              { header: "Parts", cell: (g) => <span className="font-mono">{g.part_count}</span> },
            ]}
          />
        </Panel>
      </div>
    </>
  );
}
