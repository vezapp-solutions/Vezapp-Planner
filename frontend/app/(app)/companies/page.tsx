"use client";

import { CrudScreen } from "@/components/CrudScreen";
import { EmptyState, PageHeader } from "@/components/States";
import type { FieldSpec } from "@/components/forms";
import { formatDate } from "@/lib/format";
import { useSession } from "@/lib/store";
import type { Company } from "@/lib/types";

const FIELDS: FieldSpec[] = [
  { key: "name", label: "Company name", type: "text", required: true, wide: true },
  { key: "gstin", label: "GSTIN", type: "text", placeholder: "24ABCDE1234F1Z5", hint: "15 characters. Optional." },
  { key: "address", label: "Address", type: "textarea" },
  {
    key: "is_active",
    label: "Active",
    type: "checkbox",
    hint: "Untick to stop this company's users from signing in. Nothing is deleted.",
  },
];

export default function CompaniesPage() {
  const role = useSession((s) => s.user!.role);

  return (
    <>
      <PageHeader title="Companies" subtitle="Client foundries on this platform" />
      {role !== "vezapp_admin" ? (
        <EmptyState title="You do not have access to this screen">
          Only a Vezapp Admin can manage companies.
        </EmptyState>
      ) : (
        <CrudScreen<Company>
          path="/companies"
          noun="company"
          fields={FIELDS}
          canEdit
          defaults={{ is_active: true }}
          // Deleting a company would delete all of its data, so it is switched off here: deactivate instead.
          canDelete={() => false}
          emptyHint="Add the client first, then add its first Company Admin on the Users screen. The standard operations and resource types are created for you."
          subtitle={(c) => `Added ${formatDate(c.created_at)}`}
          columns={[
            { header: "Company", cell: (c) => c.name },
            { header: "GSTIN", cell: (c) => <span className="font-mono">{c.gstin || "–"}</span> },
            { header: "Status", cell: (c) => (c.is_active ? "Active" : <span className="text-ink-soft">Inactive</span>) },
            { header: "Added", cell: (c) => <span className="font-mono">{formatDate(c.created_at)}</span> },
          ]}
        />
      )}
    </>
  );
}
