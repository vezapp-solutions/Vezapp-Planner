"use client";

import { CrudScreen } from "@/components/CrudScreen";
import { LoadingState } from "@/components/States";
import type { FieldSpec } from "@/components/forms";
import type { CapacityAdjustment, Page, Resource, Shift } from "@/lib/types";
import { useApi } from "@/lib/use-api";

/** One-off extra shifts and overtime. Every plan uses them, which is also where an applied what-if puts them. */
export function CapacityAdjustments({ canEdit }: { canEdit: boolean }) {
  const shifts = useApi<Page<Shift>>("/shifts?page_size=500");
  const resources = useApi<Page<Resource>>("/resources?page_size=500");
  if (shifts.loading || resources.loading) return <LoadingState label="Loading shifts and resources" />;

  const resourceOptions = (resources.data?.results ?? []).map((r) => ({ value: r.id, label: r.code }));
  const nameOf = new Map(resourceOptions.map((o) => [o.value, o.label]));
  const isShift = (d: Record<string, unknown>) => d.kind === "extra_shift";

  const fields: FieldSpec[] = [
    {
      key: "kind",
      label: "Type",
      type: "select",
      required: true,
      options: [
        { value: "extra_shift", label: "Extra shift (for example a Sunday)" },
        { value: "overtime", label: "Overtime on the normal shifts" },
      ],
    },
    { key: "day_from", label: "From day", type: "date", required: true },
    { key: "day_to", label: "To day", type: "date", required: true, hint: "The same day for a single day. At most 92 days." },
    { key: "name", label: "Shift name", type: "text", placeholder: "Sunday day shift", showIf: isShift },
    { key: "start_time", label: "Starts", type: "time", showIf: isShift },
    { key: "end_time", label: "Ends", type: "time", showIf: isShift, hint: "Past midnight is fine. It may not overlap another shift." },
    { key: "break_minutes", label: "Break", type: "number", unit: "min", min: 0, showIf: isShift },
    { key: "minutes", label: "Extra minutes per shift", type: "number", unit: "min", min: 1, showIf: (d) => !isShift(d), hint: "Added to each named resource's capacity in every shift of those days, times its units and efficiency." },
    {
      key: "shift",
      label: "Only in this shift",
      type: "select",
      options: (shifts.data?.results ?? []).map((s) => ({ value: s.id, label: s.name })),
      blankLabel: "Every shift",
      showIf: (d) => !isShift(d),
    },
    { key: "resources", label: "Resources", type: "multi", options: resourceOptions, hint: "Leave all unticked for every resource." },
    { key: "note", label: "Note", type: "text", wide: true },
  ];

  return (
    <CrudScreen<CapacityAdjustment>
      path="/capacity-adjustments"
      noun="adjustment"
      fields={fields}
      canEdit={canEdit}
      defaults={{ kind: "extra_shift", break_minutes: "0" }}
      emptyHint="Normal working hours come from the weekly pattern. Add an extra shift or overtime here for days that need more, or apply a what-if that does."
      columns={[
        { header: "What", cell: (a) => a.summary },
        { header: "Resources", cell: (a) => (a.resources.length ? a.resources.map((id) => nameOf.get(id) ?? id).join(", ") : "All") },
        { header: "Note", cell: (a) => a.note || "–" },
      ]}
    />
  );
}
