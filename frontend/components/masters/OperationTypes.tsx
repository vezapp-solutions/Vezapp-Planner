"use client";

import { CrudScreen } from "@/components/CrudScreen";
import type { FieldSpec } from "@/components/forms";
import type { OperationType } from "@/lib/types";

const KIND_LABEL = { core: "Core", moulding: "Moulding", melting: "Melting and pouring", post: "Post-casting" } as const;

const FIELDS: FieldSpec[] = [
  { key: "name", label: "Name", type: "text", required: true },
  { key: "code", label: "Code", type: "text", required: true, hint: "Lowercase letters, digits and underscores. Fixed for the standard operations.", disabled: () => false },
  {
    key: "kind",
    label: "Kind",
    type: "select",
    options: Object.entries(KIND_LABEL).map(([value, label]) => ({ value, label })),
    hint: "Only extra post-casting operations can be added. The kind of an operation in use cannot change.",
  },
  { key: "default_sequence", label: "Position in a new route", type: "number", step: "1", min: 1, hint: "Lower numbers come earlier." },
  { key: "default_bucket", label: "Capacity is checked", type: "select", options: [{ value: "shift", label: "Per shift" }, { value: "day", label: "Per day" }] },
  { key: "default_enabled", label: "On by default in a new route", type: "checkbox" },
  { key: "is_active", label: "Available to parts", type: "checkbox", hint: "Switch on an extra operation (such as shot blasting) here to use it in routes." },
];

export function OperationTypes({ canEdit }: { canEdit: boolean }) {
  return (
    <CrudScreen<OperationType>
      path="/operation-types"
      noun="operation"
      fields={FIELDS}
      canEdit={canEdit}
      defaults={{ kind: "post", default_sequence: "100", default_bucket: "shift", is_active: true }}
      canDelete={(o) => !o.is_builtin}
      subtitle={(o) => (o.is_builtin ? "Standard operation" : "Extra operation")}
      columns={[
        { header: "Operation", cell: (o) => o.name },
        { header: "Kind", cell: (o) => KIND_LABEL[o.kind] },
        { header: "Order", cell: (o) => <span className="font-mono">{o.default_sequence}</span> },
        { header: "Capacity", cell: (o) => (o.kind === "post" ? (o.default_bucket === "day" ? "Per day" : "Per shift") : "Per shift") },
        { header: "Status", cell: (o) => (o.is_active ? "Available" : <span className="text-ink-soft">Switched off</span>) },
      ]}
    />
  );
}
