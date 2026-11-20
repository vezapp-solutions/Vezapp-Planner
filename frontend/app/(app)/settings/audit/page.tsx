"use client";

import { useState } from "react";

import { EmptyState, ErrorState, LoadingState, PageHeader } from "@/components/States";
import { describeAudit } from "@/lib/audit";
import { formatDateTime } from "@/lib/format";
import { useSession } from "@/lib/store";
import type { AuditEntry, Page } from "@/lib/types";
import { useApi } from "@/lib/use-api";
import { Select } from "@/components/ui/Select";

const MODELS = [
  ["", "Everything"],
  ["scheduler.ScheduleLine", "Orders"],
  ["plans.Plan", "Plans"],
  ["scenarios.Scenario", "What-if scenarios"],
  ["masters.Part", "Parts"],
  ["masters.PartOperation", "Part routes"],
  ["masters.PartCustomer", "Part-customer links"],
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

/** One change, in plain English: what happened in bold, then what exactly changed. */
function Change({ entry }: { entry: AuditEntry }) {
  const { headline, lines } = describeAudit(entry);
  return (
    <div className="space-y-1">
      <p className="font-medium">{headline}</p>
      {lines.length > 0 && (
        <ul className="space-y-0.5 text-sm text-ink-soft">
          {lines.map((line, i) => (
            <li key={i}>{line}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function AuditPage() {
  const role = useSession((s) => s.user!.role);
  const [model, setModel] = useState("");
  const log = useApi<Page<AuditEntry>>(`/audit-log?page_size=100${model ? `&model_label=${model}` : ""}`);
  const allowed = role === "vezapp_admin" || role === "company_admin";

  return (
    <>
      <PageHeader title="Audit log" subtitle="Who changed what, and when, in plain words">
        <label className="filter-inline flex items-center gap-2 text-sm">
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
            <thead className="border-b border-line bg-sunken text-on-sunken">
              <tr>
                <th scope="col" className="px-4 py-2 font-medium">When</th>
                <th scope="col" className="px-4 py-2 font-medium">Who</th>
                <th scope="col" className="px-4 py-2 font-medium">What happened</th>
              </tr>
            </thead>
            <tbody>
              {log.data?.results.map((e) => (
                <tr key={e.id} className="border-b border-line align-top last:border-0">
                  <td className="whitespace-nowrap px-4 py-3 font-mono text-xs">{formatDateTime(e.created_at)}</td>
                  <td className="whitespace-nowrap px-4 py-3">{e.username || "system"}</td>
                  <td className="cell-stack px-4 py-3"><Change entry={e} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}
