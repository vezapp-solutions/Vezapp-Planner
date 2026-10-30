"use client";

import { useState } from "react";

import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/States";
import { formatDateTime } from "@/lib/format";
import { useSession } from "@/lib/store";
import type { AuditEntry, Page } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { Select } from "@/components/ui/Select";

const MODELS = [
  ["", "Everything"],
  ["masters.Part", "Parts"],
  ["masters.PartOperation", "Part routes"],
  ["masters.Customer", "Customers"],
  ["masters.Grade", "Grades"],
  ["masters.OperationType", "Operations"],
  ["resources.Resource", "Resources"],
  ["resources.Downtime", "Downtime"],
  ["companies.Shift", "Shifts"],
  ["companies.Holiday", "Holidays"],
  ["companies.CompanySettings", "Planning settings"],
  ["companies.Plant", "Plants"],
  ["accounts.User", "Users"],
];

const ACTION = { create: "Created", update: "Changed", delete: "Deleted" } as const;

function changes(entry: AuditEntry): string {
  if (entry.action === "create") return "New record";
  if (entry.action === "delete") return "Record removed";
  const keys = new Set([...Object.keys(entry.before ?? {}), ...Object.keys(entry.after ?? {})]);
  return [...keys]
    .filter((k) => JSON.stringify(entry.before?.[k]) !== JSON.stringify(entry.after?.[k]))
    .map((k) => `${k}: ${JSON.stringify(entry.before?.[k]) ?? "–"} → ${JSON.stringify(entry.after?.[k]) ?? "–"}`)
    .join("; ");
}

export default function AuditPage() {
  const role = useSession((s) => s.user!.role);
  const [model, setModel] = useState("");
  const log = useApi<Page<AuditEntry>>(`/audit-log?page_size=100${model ? `&model_label=${model}` : ""}`);
  const allowed = role === "vezapp_admin" || role === "company_admin";

  return (
    <>
      <PageHeader title="Audit log" subtitle="Who changed what, and when">
        <label className="flex items-center gap-2 text-sm">
          Show
          <Select className="field !min-h-9 !w-auto" value={model} onChange={(e) => setModel(e.target.value)}>
            {MODELS.map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </Select>
        </label>
      </PageHeader>
      {!allowed ? (
        <EmptyState title="You do not have access to this screen">Only a Company Admin or Vezapp Admin can see the audit log.</EmptyState>
      ) : role === "vezapp_admin" && !useSession.getState().actingCompanyId ? (
        <EmptyState title="Choose a company first">Pick one from “Working on” in the top bar.</EmptyState>
      ) : log.loading ? (
        <LoadingState label="Loading the log" rows={5} />
      ) : log.error ? (
        <ErrorState message={log.error.message} onRetry={log.reload} />
      ) : log.data?.results.length === 0 ? (
        <EmptyState title="Nothing recorded yet">Changes to masters and schedules appear here as soon as they are made.</EmptyState>
      ) : (
        <div className="panel overflow-x-auto">
          <table className="w-full min-w-[44rem] text-left text-sm">
            <thead className="border-b border-line bg-sunken text-ink-soft">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">When</th>
                <th scope="col" className="px-4 py-2 font-medium">Who</th>
                <th scope="col" className="px-4 py-2 font-medium">What</th>
                <th scope="col" className="px-4 py-2 font-medium">Record</th>
                <th scope="col" className="px-4 py-2 font-medium">Change</th>
              </tr>
            </thead>
            <tbody>
              {log.data?.results.map((e) => (
                <tr key={e.id} className="border-b border-line align-top last:border-0">
                  <td className="whitespace-nowrap px-4 py-2 font-mono">{formatDateTime(e.created_at)}</td>
                  <td className="px-4 py-2">{e.username || "system"}</td>
                  <td className="px-4 py-2">{ACTION[e.action]}</td>
                  <td className="px-4 py-2"><span className="text-ink-soft">{e.model_label.split(".")[1]}</span> {e.object_repr}</td>
                  <td className="max-w-md break-words px-4 py-2 font-mono text-xs">{changes(e)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
