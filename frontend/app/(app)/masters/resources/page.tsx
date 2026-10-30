"use client";

import { useMemo, useState } from "react";

import { CrudScreen } from "@/components/CrudScreen";
import { WarnBadge } from "@/components/Explain";
import { Panel } from "@/components/Panel";
import { LoadingState, PageHeader } from "@/components/States";
import type { Draft, FieldSpec } from "@/components/forms";
import { AvailabilityPreview } from "@/components/masters/Availability";
import { DowntimeManager } from "@/components/masters/DowntimeManager";
import { canEditMasters } from "@/lib/nav";
import { useSession } from "@/lib/store";
import { KIND_LABEL, type Page, type Plant, type Resource, type ResourceKind, type ResourceType, type Shift } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { Select } from "@/components/ui/Select";

const STATUS = { active: "Active", inactive: "Inactive", maintenance: "Under maintenance" } as const;

const TYPE_FIELDS: FieldSpec[] = [
  { key: "name", label: "Name", type: "text", required: true },
  {
    key: "kind",
    label: "Kind",
    type: "select",
    required: true,
    options: Object.entries(KIND_LABEL).map(([value, label]) => ({ value, label })),
    hint: "The kind decides which capacity figures a resource of this type needs.",
  },
];

export default function ResourcesPage() {
  const role = useSession((s) => s.user!.role);
  const canEdit = canEditMasters(role);
  const [kindFilter, setKindFilter] = useState("");
  const [version, setVersion] = useState(0);
  const types = useApi<Page<ResourceType>>("/resource-types?page_size=500");
  const plants = useApi<Page<Plant>>("/plants?page_size=500");
  const shifts = useApi<Page<Shift>>("/shifts?page_size=500");

  const kindOf = useMemo(() => new Map((types.data?.results ?? []).map((t) => [String(t.id), t.kind])), [types.data]);
  if (types.loading || plants.loading || shifts.loading) return <LoadingState label="Loading resources" rows={4} />;

  const kind = (d: Draft): ResourceKind | undefined => kindOf.get(String(d.resource_type));
  const is = (k: ResourceKind) => (d: Draft) => kind(d) === k;

  const fields: FieldSpec[] = [
    { key: "code", label: "Code", type: "text", required: true, placeholder: "F1" },
    { key: "name", label: "Name", type: "text", required: true, placeholder: "Induction furnace 1" },
    { key: "resource_type", label: "Type", type: "select", required: true, options: (types.data?.results ?? []).map((t) => ({ value: t.id, label: t.name })) },
    { key: "plant", label: "Plant", type: "select", blankLabel: "Not set", options: (plants.data?.results ?? []).map((p) => ({ value: p.id, label: p.name })) },
    { key: "units", label: "Parallel units", type: "number", step: "1", min: 1, required: true, hint: "Two identical machines = 2." },
    { key: "efficiency_pct", label: "Planned efficiency", type: "number", unit: "%", step: "0.01", min: 1, required: true, hint: "Share of the working time the resource really produces." },
    { key: "status", label: "Status", type: "select", options: Object.entries(STATUS).map(([value, label]) => ({ value, label })) },
    // Rated capacity depends on the kind of resource.
    { key: "rate_per_hour", label: "Cores per hour", type: "number", unit: "per h", showIf: is("core_machine"), hint: "Or give a cycle time below." },
    { key: "cycle_seconds", label: "Cycle time", type: "number", unit: "s/shot", showIf: is("core_machine") },
    { key: "cores_per_shot", label: "Cores per shot", type: "number", step: "1", min: 1, showIf: is("core_machine") },
    { key: "rate_per_hour", label: "Moulds per hour", type: "number", unit: "per h", required: true, showIf: is("moulding_line") },
    { key: "heat_kg", label: "Heat size", type: "number", unit: "kg", required: true, showIf: is("furnace"), hint: "Liquid metal per heat." },
    { key: "heat_minutes", label: "Time per heat", type: "number", unit: "min", required: true, showIf: is("furnace"), hint: "Tap to tap, including slag removal, sampling and pouring." },
    { key: "max_heats_per_shift", label: "Max heats per shift", type: "number", step: "1", min: 1, showIf: is("furnace"), hint: "Optional limit." },
    { key: "rate_per_hour", label: "Pieces per hour", type: "number", unit: "per h", showIf: is("work_centre"), hint: "Optional. Capacity is otherwise the working minutes × units." },
    {
      key: "shifts",
      label: "Shifts it works",
      type: "multi",
      options: (shifts.data?.results ?? []).map((s) => ({ value: s.id, label: s.name })),
      hint: "Leave all unticked to work every company shift.",
    },
    { key: "remarks", label: "Remarks", type: "textarea" },
  ];

  return (
    <>
      <PageHeader title="Resources" subtitle="Machines, lines, furnaces and work centres plans are checked against" />
      <div className="space-y-6">
        <CrudScreen<Resource>
          key={kindFilter}
          path="/resources"
          query={kindFilter ? `&kind=${kindFilter}` : ""}
          noun="resource"
          fields={fields}
          canEdit={canEdit}
          defaults={{ units: "1", efficiency_pct: "100", status: "active" }}
          warnings={(r) => r.warnings}
          subtitle={(r) => `${r.type_name} · ${r.rated_summary || "no rated capacity"}`}
          emptyHint="Add the core machines, moulding lines, furnaces and work centres the foundry plans against."
          wide
          toolbar={
            <label className="flex items-center gap-2 text-sm">
              Show
              <Select className="field !min-h-9 !w-auto" value={kindFilter} onChange={(e) => setKindFilter(e.target.value)}>
                <option value="">All resources</option>
                {Object.entries(KIND_LABEL).map(([value, label]) => (
                  <option key={value} value={value}>{label}s</option>
                ))}
              </Select>
            </label>
          }
          columns={[
            { header: "Resource", cell: (r) => <>{r.code}<WarnBadge issues={r.warnings} /></> },
            { header: "Name", cell: (r) => r.name },
            { header: "Type", cell: (r) => r.type_name },
            { header: "Rated capacity", cell: (r) => r.rated_summary || <span className="text-ink-soft">time-based</span> },
            { header: "Units × eff.", cell: (r) => <span className="font-mono">{r.units} × {Number(r.efficiency_pct)}%</span> },
            { header: "Status", cell: (r) => (r.status === "active" ? "Active" : <span className="text-warn">{STATUS[r.status]}</span>) },
          ]}
          renderExtra={({ row }) =>
            row && (
              <div className="space-y-6 border-t border-line pt-4">
                <DowntimeManager resourceId={row.id} canEdit={canEdit} onChanged={() => setVersion((v) => v + 1)} />
                <AvailabilityPreview resourceId={row.id} isFurnace={row.kind === "furnace"} version={version} />
              </div>
            )
          }
        />

        <Panel title="Resource types" note="the four standard kinds, plus any of your own">
          <CrudScreen<ResourceType>
            path="/resource-types"
            noun="resource type"
            fields={TYPE_FIELDS}
            canEdit={canEdit}
            canDelete={(t) => !t.is_default}
            onChanged={types.reload}
            columns={[
              { header: "Type", cell: (t) => t.name },
              { header: "Kind", cell: (t) => KIND_LABEL[t.kind] },
              { header: "Standard", cell: (t) => (t.is_default ? "Yes" : "No") },
            ]}
          />
        </Panel>
      </div>
    </>
  );
}
