"use client";

import { useState } from "react";

import { CrudScreen } from "@/components/CrudScreen";
import { LoadingState } from "@/components/States";
import type { FieldSpec } from "@/components/forms";
import { formatDate, formatWeekday, todayInIndia } from "@/lib/format";
import type { Holiday, Page, Shift } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { Select } from "@/components/ui/Select";

export function Holidays({ canEdit }: { canEdit: boolean }) {
  const thisYear = Number(todayInIndia().slice(0, 4));
  const [year, setYear] = useState(thisYear);
  const shifts = useApi<Page<Shift>>("/shifts?page_size=500");
  if (shifts.loading) return <LoadingState label="Loading shifts" />;
  const list = shifts.data?.results ?? [];
  const nameOf = new Map(list.map((s) => [s.id, s.name]));

  const fields: FieldSpec[] = [
    { key: "date", label: "Date", type: "date", required: true },
    { key: "name", label: "Holiday", type: "text", required: true, placeholder: "Diwali" },
    { key: "full_day", label: "The whole day is off", type: "checkbox" },
    {
      key: "shifts_off",
      label: "Shifts that are off",
      type: "multi",
      options: list.map((s) => ({ value: s.id, label: s.name })),
      showIf: (d) => !d.full_day,
      hint: "The other shifts of that day still run.",
    },
  ];

  return (
    <CrudScreen<Holiday>
      key={year}
      path="/holidays"
      query={`&year=${year}`}
      noun="holiday"
      fields={fields}
      canEdit={canEdit}
      defaults={{ full_day: true }}
      emptyHint={`No holidays in ${year}. Planned capacity assumes every weekday in the weekly pattern is worked.`}
      toolbar={
        <label className="flex items-center gap-2 text-sm">
          Year
          <Select className="field !min-h-9 !w-auto" value={year} onChange={(e) => setYear(Number(e.target.value))}>
            {[thisYear - 1, thisYear, thisYear + 1, thisYear + 2].map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </Select>
        </label>
      }
      columns={[
        { header: "Date", cell: (h) => <span className="font-mono">{formatDate(h.date)}</span> },
        { header: "Day", cell: (h) => formatWeekday(h.date) },
        { header: "Holiday", cell: (h) => h.name },
        {
          header: "Effect",
          cell: (h) => (h.full_day ? "Whole day off" : `Off: ${h.shifts_off.map((id) => nameOf.get(id) ?? id).join(", ")}`),
        },
      ]}
    />
  );
}
