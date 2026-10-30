"use client";

import { CrudScreen } from "@/components/CrudScreen";
import { PageHeader } from "@/components/States";
import type { FieldSpec } from "@/components/forms";
import { canEditMasters } from "@/lib/nav";
import { useSession } from "@/lib/store";
import type { Customer } from "@/lib/types";

const FIELDS: FieldSpec[] = [
  { key: "code", label: "Code", type: "text", required: true, placeholder: "CUST-01" },
  { key: "name", label: "Customer name", type: "text", required: true },
  {
    key: "priority",
    label: "Priority",
    type: "select",
    required: true,
    options: [
      { value: "A", label: "A (highest)" },
      { value: "B", label: "B" },
      { value: "C", label: "C" },
    ],
    hint: "Breaks ties when two dispatch lines share a date: A is planned before B before C.",
  },
  { key: "contact_person", label: "Contact person", type: "text" },
  { key: "phone", label: "Phone", type: "text" },
  { key: "email", label: "Email", type: "text" },
  { key: "gstin", label: "GSTIN", type: "text", placeholder: "24ABCDE1234F1Z5", hint: "15 characters." },
  { key: "state", label: "State", type: "text" },
  { key: "billing_address", label: "Billing address", type: "textarea" },
  { key: "shipping_address", label: "Shipping address", type: "textarea" },
  { key: "is_active", label: "Active customer", type: "checkbox" },
];

export default function CustomersPage() {
  const canEdit = canEditMasters(useSession((s) => s.user!.role));
  return (
    <>
      <PageHeader title="Customers" subtitle="Who you dispatch to" />
      <CrudScreen<Customer>
        path="/customers"
        noun="customer"
        fields={FIELDS}
        canEdit={canEdit}
        defaults={{ priority: "B", is_active: true }}
        emptyHint="Customers are chosen on every monthly schedule line, and each part can be linked to the customers it is supplied to."
        columns={[
          { header: "Code", cell: (c) => c.code },
          { header: "Customer", cell: (c) => c.name },
          { header: "Priority", cell: (c) => <span className="font-mono">{c.priority}</span> },
          { header: "State", cell: (c) => c.state || <span className="text-ink-soft">–</span> },
          { header: "Status", cell: (c) => (c.is_active ? "Active" : <span className="text-ink-soft">Inactive</span>) },
        ]}
      />
    </>
  );
}
